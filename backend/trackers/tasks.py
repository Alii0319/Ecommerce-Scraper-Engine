from __future__ import annotations

import logging
from decimal import Decimal

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.db import DatabaseError, transaction
from django.utils import timezone

from .models import PriceHistory, TrackedProduct
from .scraping import (
    PriceNotFoundError,
    ScrapeError,
    ScrapeResult,
    UnsafeTargetUrlError,
    extract_price,
    fetch_rendered_html,
)

logger = logging.getLogger(__name__)


def should_send_threshold_alert(
    *,
    previous_price: Decimal | None,
    current_price: Decimal,
    threshold: Decimal,
    last_alerted_price: Decimal | None,
) -> bool:
    crossed_threshold = (
        current_price <= threshold
        and (previous_price is None or previous_price > threshold)
    )

    new_lower_price = (
        current_price <= threshold
        and last_alerted_price is not None
        and current_price < last_alerted_price
    )

    return crossed_threshold or new_lower_price


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

    html = fetch_rendered_html(snapshot.target_url)
    result = extract_price(html)
    now = timezone.now()

    alert_payload = None

    try:
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

            should_alert = should_send_threshold_alert(
                previous_price=previous_price,
                current_price=result.price,
                threshold=product.notification_threshold,
                last_alerted_price=product.last_alerted_price,
            )

            product.last_scraped_at = now
            update_fields = ["last_scraped_at"]

            if should_alert:
                product.last_alerted_price = result.price
                product.last_alerted_at = now
                update_fields.extend(["last_alerted_price", "last_alerted_at"])

                alert_payload = {
                    "product_id": product.id,
                    "user_id": product.user_id,
                    "product_name": product.product_name,
                    "target_url": product.target_url,
                    "threshold": product.notification_threshold,
                    "current_price": result.price,
                    "history_id": history.id,
                    "timestamp": now,
                }

            product.save(update_fields=update_fields)

            if alert_payload is not None:
                transaction.on_commit(
                    lambda payload=alert_payload: dispatch_websocket_alert(**payload)
                )

    except TrackedProduct.DoesNotExist:
        return {"status": "skipped", "product_id": product_id}
    except DatabaseError:
        logger.exception(
            "Database write failed after scraping",
            extra={"product_id": product_id},
        )
        raise

    logger.info(
        "Product scrape completed",
        extra={
            "product_id": product_id,
            "price": str(result.price),
            "alert_sent": alert_payload is not None,
        },
    )

    return {
        "status": "success",
        "product_id": product_id,
        "price": str(result.price),
        "alert_sent": alert_payload is not None,
    }


def dispatch_websocket_alert(
    *,
    product_id: int,
    user_id: int,
    product_name: str,
    target_url: str,
    threshold: Decimal,
    current_price: Decimal,
    history_id: int,
    timestamp,
) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        raise RuntimeError("Channel layer is not configured")

    event = {
        "type": "price_threshold_alert",
        "version": 1,
        "data": {
            "product_id": product_id,
            "history_id": history_id,
            "product_name": product_name,
            "current_price": str(current_price),
            "threshold": str(threshold),
            "target_url": target_url,
            "timestamp": timestamp.isoformat(),
        },
    }

    async_to_sync(channel_layer.group_send)(
        f"user_{user_id}_alerts",
        {"type": "broadcast.alert", "event": event},
    )


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