from __future__ import annotations

import logging
from decimal import Decimal

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.core.cache import cache
from django.db import DatabaseError, transaction
from django.utils import timezone

from .models import PriceAlert, PriceHistory, TrackedProduct
from .scraping import (
    PriceNotFoundError,
    ScrapeError,
    ScrapeResult,
    UnsafeTargetUrlError,
    extract_price,
    fetch_rendered_html,
)

logger = logging.getLogger(__name__)


def evaluate_alert_type(
    *,
    previous_price: Decimal | None,
    current_price: Decimal,
    threshold: Decimal,
    last_alerted_price: Decimal | None,
) -> str | None:
    """Evaluates precise alert semantics: threshold_reached vs new_lower_price vs price_drop."""
    if (
        previous_price is not None
        and previous_price > threshold
        and current_price <= threshold
    ):
        return PriceAlert.AlertType.THRESHOLD_REACHED

    if (
        current_price <= threshold
        and last_alerted_price is not None
        and current_price < last_alerted_price
    ):
        return PriceAlert.AlertType.NEW_LOWER_PRICE

    if (
        previous_price is not None
        and current_price < previous_price
    ):
        return PriceAlert.AlertType.PRICE_DROP

    if previous_price is None and current_price <= threshold:
        return PriceAlert.AlertType.THRESHOLD_REACHED

    return None


@shared_task(
    bind=True,
    name="trackers.tasks.scrape_single_product",
    autoretry_for=(ScrapeError,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    soft_time_limit=90,
    time_limit=120,
)
def scrape_single_product(self, product_id: int) -> dict:
    lock_key = f"scrape-lock:{product_id}"
    acquired = cache.add(lock_key, "true", timeout=120)
    if not acquired:
        logger.info(f"Scrape task already running for product_id={product_id}")
        return {"status": "already_running", "product_id": product_id}

    try:
        try:
            snapshot = (
                TrackedProduct.objects
                .only(
                    "id",
                    "product_name",
                    "target_url",
                    "notification_threshold",
                    "is_active",
                    "user_id",
                )
                .get(id=product_id, is_active=True)
            )
        except TrackedProduct.DoesNotExist:
            return {"status": "skipped", "product_id": product_id}

        now = timezone.now()
        created_alert_id = None

        try:
            html = fetch_rendered_html(snapshot.target_url)
            result = extract_price(html, snapshot.target_url)

            with transaction.atomic():
                product = (
                    TrackedProduct.objects
                    .select_for_update()
                    .get(id=product_id, is_active=True)
                )

                previous_history = (
                    PriceHistory.objects
                    .filter(product=product)
                    .order_by("-scraped_at", "-id")
                    .first()
                )
                previous_price = previous_history.price if previous_history else None

                history = PriceHistory.objects.create(
                    product=product,
                    price=result.price,
                    is_available=result.is_available,
                    scraped_at=now,
                )

                alert_type = evaluate_alert_type(
                    previous_price=previous_price,
                    current_price=result.price,
                    threshold=product.notification_threshold,
                    last_alerted_price=product.last_alerted_price,
                )

                product.last_scraped_at = now
                product.last_scrape_status = "success"
                product.last_scrape_error_code = ""
                product.last_scrape_error_message = ""
                product.consecutive_failures = 0

                update_fields = [
                    "last_scraped_at",
                    "last_scrape_status",
                    "last_scrape_error_code",
                    "last_scrape_error_message",
                    "consecutive_failures",
                ]

                if alert_type is not None:
                    product.last_alerted_price = result.price
                    product.last_alerted_at = now
                    update_fields.extend(["last_alerted_price", "last_alerted_at"])

                    alert = PriceAlert.objects.create(
                        product=product,
                        price_history=history,
                        user=product.user,
                        alert_type=alert_type,
                        current_price=result.price,
                        threshold=product.notification_threshold,
                        payload={
                            "product_name": product.product_name,
                            "target_url": product.target_url,
                            "previous_price": str(previous_price) if previous_price else None,
                        },
                        status=PriceAlert.DeliveryStatus.PENDING,
                    )
                    created_alert_id = alert.id

                product.save(update_fields=update_fields)

                if created_alert_id is not None:
                    transaction.on_commit(
                        lambda aid=created_alert_id: deliver_price_alert.delay(aid)
                    )

            logger.info(
                "Product scrape completed",
                extra={
                    "product_id": product_id,
                    "price": str(result.price),
                    "alert_created": created_alert_id is not None,
                },
            )

            return {
                "status": "success",
                "product_id": product_id,
                "price": str(result.price),
                "alert_id": created_alert_id,
            }

        except Exception as exc:
            with transaction.atomic():
                try:
                    product = TrackedProduct.objects.select_for_update().get(id=product_id)
                    product.last_scraped_at = now
                    product.last_scrape_status = "failed"
                    product.last_scrape_error_code = exc.__class__.__name__
                    product.last_scrape_error_message = str(exc)[:500]
                    product.consecutive_failures += 1
                    product.save(
                        update_fields=[
                            "last_scraped_at",
                            "last_scrape_status",
                            "last_scrape_error_code",
                            "last_scrape_error_message",
                            "consecutive_failures",
                        ]
                    )
                except TrackedProduct.DoesNotExist:
                    pass
            raise

    finally:
        cache.delete(lock_key)


@shared_task(
    bind=True,
    name="trackers.tasks.deliver_price_alert",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
    soft_time_limit=30,
    time_limit=45,
)
def deliver_price_alert(self, alert_id: int) -> dict:
    with transaction.atomic():
        try:
            alert = (
                PriceAlert.objects
                .select_for_update(skip_locked=True)
                .select_related("user", "product")
                .get(id=alert_id)
            )
        except PriceAlert.DoesNotExist:
            return {"status": "skipped_not_found", "alert_id": alert_id}

        if alert.status in [PriceAlert.DeliveryStatus.PUBLISHED, PriceAlert.DeliveryStatus.ACKNOWLEDGED]:
            return {"status": "already_delivered", "alert_id": alert_id}

        alert.status = PriceAlert.DeliveryStatus.PROCESSING
        alert.attempts += 1
        alert.save(update_fields=["status", "attempts", "updated_at"])

    try:
        dispatch_websocket_alert(alert=alert)
    except Exception as exc:
        PriceAlert.objects.filter(id=alert_id).update(
            status=PriceAlert.DeliveryStatus.FAILED,
            last_error=str(exc)[:500],
            available_at=timezone.now(),
        )
        raise

    PriceAlert.objects.filter(id=alert_id).update(
        status=PriceAlert.DeliveryStatus.PUBLISHED,
        published_at=timezone.now(),
        last_error="",
    )

    return {"status": "delivered", "alert_id": alert_id}


def dispatch_websocket_alert(*, alert: PriceAlert) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        raise RuntimeError("Channel layer is not configured")

    event = {
        "type": "price_alert",
        "version": 2,
        "event_id": str(alert.event_id),
        "data": {
            "alert_type": alert.alert_type,
            "product_id": alert.product_id,
            "history_id": alert.price_history_id,
            "product_name": alert.product.product_name,
            "current_price": str(alert.current_price),
            "threshold": str(alert.threshold),
            "target_url": alert.product.target_url,
            "previous_price": alert.payload.get("previous_price"),
            "timestamp": alert.created_at.isoformat(),
        },
    }

    async_to_sync(channel_layer.group_send)(
        f"user_{alert.user_id}_alerts",
        {"type": "broadcast.alert", "event": event},
    )


@shared_task(name="trackers.tasks.recover_undelivered_alerts")
def recover_undelivered_alerts() -> dict:
    now = timezone.now()
    stale_cutoff = now - timezone.timedelta(minutes=5)

    from django.db.models import Q
    alerts = (
        PriceAlert.objects
        .filter(
            Q(
                status__in=[
                    PriceAlert.DeliveryStatus.PENDING,
                    PriceAlert.DeliveryStatus.FAILED,
                ],
                available_at__lte=now,
            )
            | Q(
                status=PriceAlert.DeliveryStatus.PROCESSING,
                updated_at__lt=stale_cutoff,
            )
        )
        .values_list("id", flat=True)
    )

    requeued = 0
    for alert_id in alerts.iterator(chunk_size=500):
        PriceAlert.objects.filter(
            id=alert_id,
            status=PriceAlert.DeliveryStatus.PROCESSING,
            updated_at__lt=stale_cutoff,
        ).update(
            status=PriceAlert.DeliveryStatus.PENDING,
            available_at=now,
            last_error="Recovered stale processing alert.",
        )

        deliver_price_alert.delay(alert_id)
        requeued += 1

    return {"status": "success", "queued": requeued}


@shared_task(name="trackers.tasks.orchestrate_scraping_pipeline")
def orchestrate_scraping_pipeline() -> dict:
    product_ids = (
        TrackedProduct.objects
        .filter(is_active=True)
        .values_list("id", flat=True)
        .iterator(chunk_size=500)
    )

    dispatched = 0
    for product_id in product_ids:
        scrape_single_product.delay(product_id)
        dispatched += 1

    return {"status": "success", "dispatched_count": dispatched}