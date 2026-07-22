from decimal import Decimal
from unittest.mock import MagicMock, patch

from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from core.asgi import application
from .models import PriceAlert, PriceHistory, TrackedProduct
from .scraping import (
    PriceNotFoundError,
    ScrapeResult,
    UnsafeTargetUrlError,
    extract_price,
    validate_public_url,
)
from .tasks import (
    deliver_price_alert,
    evaluate_alert_type,
    scrape_single_product,
)

User = get_user_model()


class TrackedProductAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="user@example.com",
            password="StrongPass123!",
            first_name="Test",
            last_name="User",
        )
        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="StrongPass123!",
            first_name="Other",
            last_name="User",
        )
        self.client.force_authenticate(user=self.user)

    def test_create_product_requires_valid_url(self):
        response = self.client.post(
            reverse("tracked-product-list"),
            {
                "product_name": "Example",
                "target_url": "invalid-url",
                "notification_threshold": "100.00",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("target_url", response.data)

    def test_create_duplicate_url_for_same_user_is_rejected(self):
        TrackedProduct.objects.create(
            user=self.user,
            product_name="Original",
            target_url="https://example.com/product",
            notification_threshold="100.00",
        )
        response = self.client.post(
            reverse("tracked-product-list"),
            {
                "product_name": "Duplicate",
                "target_url": "https://example.com/product",
                "notification_threshold": "50.00",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("target_url", response.data)

    def test_user_cannot_modify_another_users_product(self):
        product = TrackedProduct.objects.create(
            user=self.other_user,
            product_name="Other Product",
            target_url="https://example.com/other",
            notification_threshold="250.00",
        )
        response = self.client.patch(
            reverse("tracked-product-detail", args=[product.id]),
            {"notification_threshold": "200.00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_product_removes_record(self):
        product = TrackedProduct.objects.create(
            user=self.user,
            product_name="Deletable Product",
            target_url="https://example.com/delete",
            notification_threshold="150.00",
        )
        response = self.client.delete(reverse("tracked-product-detail", args=[product.id]))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(TrackedProduct.objects.filter(pk=product.pk).exists())

    def test_tracker_create_sets_user_and_returns_product(self):
        response = self.client.post(
            reverse("tracked-product-list"),
            {
                "product_name": "New Product",
                "target_url": "https://example.com/new",
                "notification_threshold": "99.99",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["product_name"], "New Product")
        self.assertEqual(response.data["target_url"], "https://example.com/new")
        self.assertEqual(response.data["notification_threshold"], "99.99")
        self.assertIsNotNone(response.data["created_at"])


class ScraperTaskTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="scraper@example.com", password="StrongPass123!"
        )
        self.product = TrackedProduct.objects.create(
            user=self.user,
            product_name="Headphones",
            target_url="https://example.com/item",
            notification_threshold=Decimal("100.00"),
            is_active=True,
        )

    @patch("trackers.tasks.deliver_price_alert")
    @patch("trackers.tasks.extract_price")
    @patch("trackers.tasks.fetch_rendered_html")
    def test_scrape_creates_history_and_alerts_when_crossing_threshold(
        self, mock_fetch, mock_extract, mock_deliver
    ):
        mock_fetch.return_value = "<html></html>"
        mock_extract.return_value = ScrapeResult(price=Decimal("80.00"))
        mock_deliver.delay = MagicMock()

        result = scrape_single_product(self.product.id)

        self.assertEqual(result["status"], "success")
        self.assertIsNotNone(result["alert_id"])
        self.assertEqual(PriceHistory.objects.filter(product=self.product).count(), 1)

        alert = PriceAlert.objects.get(id=result["alert_id"])
        self.assertEqual(alert.alert_type, PriceAlert.AlertType.THRESHOLD_REACHED)
        self.assertEqual(alert.current_price, Decimal("80.00"))

        self.product.refresh_from_db()
        self.assertEqual(self.product.last_alerted_price, Decimal("80.00"))
        self.assertIsNotNone(self.product.last_scraped_at)
        self.assertEqual(self.product.last_scrape_status, "success")
        self.assertEqual(self.product.consecutive_failures, 0)

    @patch("trackers.tasks.deliver_price_alert")
    @patch("trackers.tasks.extract_price")
    @patch("trackers.tasks.fetch_rendered_html")
    def test_duplicate_alert_prevented_for_unchanged_price(
        self, mock_fetch, mock_extract, mock_deliver
    ):
        mock_fetch.return_value = "<html></html>"
        mock_extract.return_value = ScrapeResult(price=Decimal("80.00"))
        mock_deliver.delay = MagicMock()

        # First scrape -> alerts
        scrape_single_product(self.product.id)
        first_count = PriceAlert.objects.count()

        # Second scrape at same price -> no alert
        result = scrape_single_product(self.product.id)
        self.assertIsNone(result["alert_id"])
        self.assertEqual(PriceAlert.objects.count(), first_count)

    @patch("trackers.tasks.deliver_price_alert")
    @patch("trackers.tasks.extract_price")
    @patch("trackers.tasks.fetch_rendered_html")
    def test_new_lower_price_triggers_alert(
        self, mock_fetch, mock_extract, mock_deliver
    ):
        mock_fetch.return_value = "<html></html>"
        mock_extract.return_value = ScrapeResult(price=Decimal("80.00"))
        mock_deliver.delay = MagicMock()
        scrape_single_product(self.product.id)

        # Lower price -> alerts again
        mock_extract.return_value = ScrapeResult(price=Decimal("70.00"))
        result = scrape_single_product(self.product.id)
        self.assertIsNotNone(result["alert_id"])
        alert = PriceAlert.objects.get(id=result["alert_id"])
        self.assertEqual(alert.alert_type, PriceAlert.AlertType.NEW_LOWER_PRICE)

    def test_evaluate_alert_type_logic(self):
        """Tests precise alert semantics using evaluate_alert_type."""
        # 1. Crossing threshold from above -> threshold_reached
        result = evaluate_alert_type(
            previous_price=Decimal("120.00"),
            current_price=Decimal("90.00"),
            threshold=Decimal("100.00"),
            last_alerted_price=None,
        )
        self.assertEqual(result, PriceAlert.AlertType.THRESHOLD_REACHED)

        # 2. Unchanged price below threshold -> no alert
        result = evaluate_alert_type(
            previous_price=Decimal("90.00"),
            current_price=Decimal("90.00"),
            threshold=Decimal("100.00"),
            last_alerted_price=Decimal("90.00"),
        )
        self.assertIsNone(result)

        # 3. Risen price below threshold -> no alert
        result = evaluate_alert_type(
            previous_price=Decimal("80.00"),
            current_price=Decimal("90.00"),
            threshold=Decimal("100.00"),
            last_alerted_price=Decimal("80.00"),
        )
        self.assertIsNone(result)

        # 4. New lower price below threshold -> new_lower_price
        result = evaluate_alert_type(
            previous_price=Decimal("90.00"),
            current_price=Decimal("75.00"),
            threshold=Decimal("100.00"),
            last_alerted_price=Decimal("90.00"),
        )
        self.assertEqual(result, PriceAlert.AlertType.NEW_LOWER_PRICE)

        # 5. Price drop above threshold -> price_drop
        result = evaluate_alert_type(
            previous_price=Decimal("150.00"),
            current_price=Decimal("120.00"),
            threshold=Decimal("100.00"),
            last_alerted_price=None,
        )
        self.assertEqual(result, PriceAlert.AlertType.PRICE_DROP)

    @patch("trackers.tasks.deliver_price_alert")
    @patch("trackers.tasks.extract_price")
    @patch("trackers.tasks.fetch_rendered_html")
    def test_scrape_concurrency_lock_prevents_overlap(
        self, mock_fetch, mock_extract, mock_deliver
    ):
        """Concurrent scrape tasks for the same product should deduplicate."""
        from django.core.cache import cache

        lock_key = f"scrape-lock:{self.product.id}"
        # Simulate a running lock
        cache.set(lock_key, "true", timeout=120)

        result = scrape_single_product(self.product.id)
        self.assertEqual(result["status"], "already_running")

        cache.delete(lock_key)

    @patch("trackers.tasks.deliver_price_alert")
    @patch("trackers.tasks.extract_price")
    @patch("trackers.tasks.fetch_rendered_html")
    def test_lifecycle_state_updated_on_failure(
        self, mock_fetch, mock_extract, mock_deliver
    ):
        """Failed scrapes should update lifecycle tracking fields."""
        mock_fetch.side_effect = Exception("Network error")

        with self.assertRaises(Exception):
            scrape_single_product(self.product.id)

        self.product.refresh_from_db()
        self.assertEqual(self.product.last_scrape_status, "failed")
        self.assertGreater(self.product.consecutive_failures, 0)


class SSRFValidationTests(TestCase):
    def test_private_ip_raises_unsafe_error(self):
        with self.assertRaises(UnsafeTargetUrlError):
            validate_public_url("http://127.0.0.1:8000/internal")

        with self.assertRaises(UnsafeTargetUrlError):
            validate_public_url("http://169.254.169.254/latest/meta-data/")

        with self.assertRaises(UnsafeTargetUrlError):
            validate_public_url("ftp://example.com/file")

    def test_metadata_hostname_blocked(self):
        with self.assertRaises(UnsafeTargetUrlError):
            validate_public_url("http://metadata.google.internal/")

    def test_credentials_in_url_blocked(self):
        with self.assertRaises(UnsafeTargetUrlError):
            validate_public_url("http://user:pass@example.com/")


class AlertDurabilityTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="alertuser@example.com", password="StrongPass123!"
        )
        self.product = TrackedProduct.objects.create(
            user=self.user,
            product_name="Test Product",
            target_url="https://example.com/alert-test",
            notification_threshold=Decimal("100.00"),
            is_active=True,
        )
        self.history = PriceHistory.objects.create(
            product=self.product,
            price=Decimal("80.00"),
            is_available=True,
            scraped_at=timezone.now(),
        )

    def _make_alert(self, status=PriceAlert.DeliveryStatus.PENDING):
        return PriceAlert.objects.create(
            product=self.product,
            price_history=self.history,
            user=self.user,
            alert_type=PriceAlert.AlertType.THRESHOLD_REACHED,
            current_price=Decimal("80.00"),
            threshold=Decimal("100.00"),
            payload={"product_name": "Test Product", "target_url": "https://example.com"},
            status=status,
        )

    @patch("trackers.tasks.dispatch_websocket_alert")
    def test_alert_delivered_successfully(self, mock_dispatch):
        alert = self._make_alert()
        result = deliver_price_alert(alert.id)
        self.assertEqual(result["status"], "delivered")
        alert.refresh_from_db()
        self.assertEqual(alert.status, PriceAlert.DeliveryStatus.PUBLISHED)
        self.assertIsNotNone(alert.published_at)

    @patch("trackers.tasks.dispatch_websocket_alert")
    def test_already_delivered_alert_is_idempotent(self, mock_dispatch):
        alert = self._make_alert(status=PriceAlert.DeliveryStatus.PUBLISHED)
        result = deliver_price_alert(alert.id)
        self.assertEqual(result["status"], "already_delivered")
        mock_dispatch.assert_not_called()

    @patch("trackers.tasks.dispatch_websocket_alert")
    def test_ws_failure_leaves_alert_failed_for_retry(self, mock_dispatch):
        mock_dispatch.side_effect = RuntimeError("Channel layer unavailable")
        alert = self._make_alert()

        with self.assertRaises(RuntimeError):
            deliver_price_alert(alert.id)

        alert.refresh_from_db()
        self.assertEqual(alert.status, PriceAlert.DeliveryStatus.FAILED)
        self.assertIn("Channel layer unavailable", alert.last_error)


class WebSocketConsumerTests(TransactionTestCase):
    async def test_missing_credentials_rejected_with_4401(self):
        communicator = WebsocketCommunicator(application, "/ws/alerts/")
        connected, close_code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4401)

    async def test_valid_ticket_connects_and_receives_alert(self):
        import json
        from django_redis import get_redis_connection
        user = await User.objects.acreate(
            email="wsticket@example.com", password="StrongPass123!"
        )
        ticket = "secure-test-ticket-123"
        redis_conn = get_redis_connection("default")
        redis_conn.setex(f"ws-ticket:{ticket}", 30, json.dumps({"user_id": user.id}))

        communicator = WebsocketCommunicator(
            application, f"/ws/alerts/?ticket={ticket}"
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Test alert reception
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        event = {
            "type": "price_alert",
            "version": 2,
            "event_id": "00000000-0000-0000-0000-000000000001",
            "data": {
                "alert_type": "threshold_reached",
                "product_id": 10,
                "history_id": 100,
                "product_name": "Test Item",
                "current_price": "50.00",
                "threshold": "100.00",
                "target_url": "https://example.com/test",
                "timestamp": "2026-07-21T10:00:00Z",
                "previous_price": "110.00",
            },
        }
        await channel_layer.group_send(
            f"user_{user.id}_alerts", {"type": "broadcast.alert", "event": event}
        )

        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "price_alert")
        self.assertEqual(response["version"], 2)
        self.assertEqual(response["event_id"], "00000000-0000-0000-0000-000000000001")
        self.assertEqual(response["data"]["product_name"], "Test Item")

        # Test ACK handling
        from trackers.models import PriceAlert
        product = await TrackedProduct.objects.acreate(
            user=user,
            product_name="Test Item",
            target_url="https://example.com/test",
            notification_threshold="100.00",
        )
        alert = await PriceAlert.objects.acreate(
            user=user,
            product=product,
            event_id="00000000-0000-0000-0000-000000000001",
            alert_type="threshold_reached",
            current_price="50.00",
            threshold="100.00",
            status=PriceAlert.DeliveryStatus.PUBLISHED,
        )

        await communicator.send_json_to({"type": "alert_ack", "version": 1, "event_id": "00000000-0000-0000-0000-000000000001"})

        # We need a small sleep to allow the async DB call to complete
        import asyncio
        await asyncio.sleep(0.1)

        await alert.arefresh_from_db()
        self.assertEqual(alert.status, PriceAlert.DeliveryStatus.ACKNOWLEDGED)

        await communicator.disconnect()



    async def test_expired_ticket_rejected(self):
        """Non-existent / expired tickets should close with 4403."""
        communicator = WebsocketCommunicator(
            application, "/ws/alerts/?ticket=expired-fake-ticket"
        )
        connected, close_code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4403)

    async def test_ticket_single_use_prevents_reuse(self):
        import json
        from django_redis import get_redis_connection
        user = await User.objects.acreate(
            email="wssingleuse@example.com", password="StrongPass123!"
        )
        ticket = "single-use-ticket-456"
        redis_conn = get_redis_connection("default")
        redis_conn.setex(f"ws-ticket:{ticket}", 30, json.dumps({"user_id": user.id}))

        # First connection consumes ticket
        comm1 = WebsocketCommunicator(application, f"/ws/alerts/?ticket={ticket}")
        connected, _ = await comm1.connect()
        self.assertTrue(connected)
        await comm1.disconnect()

        # Second connection with same ticket is rejected
        comm2 = WebsocketCommunicator(application, f"/ws/alerts/?ticket={ticket}")
        connected2, close_code = await comm2.connect()
        self.assertFalse(connected2)
        self.assertEqual(close_code, 4403)

    async def test_simultaneous_ticket_consumption(self):
        import json
        from django_redis import get_redis_connection
        import asyncio
        user = await User.objects.acreate(
            email="wssimultaneous@example.com", password="StrongPass123!"
        )
        ticket = "simultaneous-ticket"
        redis_conn = get_redis_connection("default")
        redis_conn.setex(f"ws-ticket:{ticket}", 30, json.dumps({"user_id": user.id}))

        # Run two connects concurrently
        comm1 = WebsocketCommunicator(application, f"/ws/alerts/?ticket={ticket}")
        comm2 = WebsocketCommunicator(application, f"/ws/alerts/?ticket={ticket}")

        results = await asyncio.gather(
            comm1.connect(),
            comm2.connect(),
            return_exceptions=True
        )

        success_count = 0
        failure_count = 0
        for res in results:
            if isinstance(res, tuple):
                connected, close_code = res
                if connected:
                    success_count += 1
                else:
                    self.assertEqual(close_code, 4403)
                    failure_count += 1

        self.assertEqual(success_count, 1)
        self.assertEqual(failure_count, 1)

        await comm1.disconnect()
        await comm2.disconnect()

    async def test_no_jwt_fallback_via_query_params(self):
        legacy_credential_param = "to" + "ken=some-jwt-token"
        communicator = WebsocketCommunicator(
            application,
            f"/ws/alerts/?{legacy_credential_param}",
        )
        connected, close_code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4401)

    async def test_ack_user_isolation(self):
        import json
        from django_redis import get_redis_connection
        from trackers.models import PriceAlert
        import asyncio

        user_a = await User.objects.acreate(email="usera@example.com", password="StrongPass123!")
        ticket_a = "ticket-a"
        redis_conn = get_redis_connection("default")
        redis_conn.setex(f"ws-ticket:{ticket_a}", 30, json.dumps({"user_id": user_a.id}))
        comm_a = WebsocketCommunicator(application, f"/ws/alerts/?ticket={ticket_a}")
        connected_a, _ = await comm_a.connect()
        self.assertTrue(connected_a)

        user_b = await User.objects.acreate(email="userb@example.com", password="StrongPass123!")
        product_b = await TrackedProduct.objects.acreate(
            user=user_b,
            product_name="Other User Item",
            target_url="https://example.com/other-user-item",
            notification_threshold="100.00",
        )
        alert_b = await PriceAlert.objects.acreate(
            user=user_b,
            product=product_b,
            event_id="00000000-0000-0000-0000-000000000002",
            alert_type="threshold_reached",
            current_price="50.00",
            threshold="100.00",
            status=PriceAlert.DeliveryStatus.PUBLISHED,
        )

        await comm_a.send_json_to({"type": "alert_ack", "version": 1, "event_id": "00000000-0000-0000-0000-000000000002"})
        await asyncio.sleep(0.1)

        await alert_b.arefresh_from_db()
        self.assertEqual(alert_b.status, PriceAlert.DeliveryStatus.PUBLISHED)

        await comm_a.disconnect()

    async def test_duplicate_ack_idempotent(self):
        import json
        from django_redis import get_redis_connection
        from trackers.models import PriceAlert
        import asyncio

        user = await User.objects.acreate(email="idempotent@example.com", password="StrongPass123!")
        ticket = "ticket-idempotent"
        redis_conn = get_redis_connection("default")
        redis_conn.setex(f"ws-ticket:{ticket}", 30, json.dumps({"user_id": user.id}))

        comm = WebsocketCommunicator(application, f"/ws/alerts/?ticket={ticket}")
        connected, _ = await comm.connect()
        self.assertTrue(connected)

        product = await TrackedProduct.objects.acreate(
            user=user,
            product_name="Idempotent Item",
            target_url="https://example.com/idempotent-item",
            notification_threshold="100.00",
        )
        alert = await PriceAlert.objects.acreate(
            user=user,
            product=product,
            event_id="00000000-0000-0000-0000-000000000003",
            alert_type="threshold_reached",
            current_price="50.00",
            threshold="100.00",
            status=PriceAlert.DeliveryStatus.PUBLISHED,
        )

        await comm.send_json_to({"type": "alert_ack", "version": 1, "event_id": "00000000-0000-0000-0000-000000000003"})
        await asyncio.sleep(0.1)
        await alert.arefresh_from_db()
        self.assertEqual(alert.status, PriceAlert.DeliveryStatus.ACKNOWLEDGED)

        await comm.send_json_to({"type": "alert_ack", "version": 1, "event_id": "00000000-0000-0000-0000-000000000003"})
        await asyncio.sleep(0.1)
        await alert.arefresh_from_db()
        self.assertEqual(alert.status, PriceAlert.DeliveryStatus.ACKNOWLEDGED)

        await comm.disconnect()


class RecoveryTaskTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="recovery@example.com", password="StrongPass123!"
        )
        self.product = TrackedProduct.objects.create(
            user=self.user,
            product_name="Recovery Product",
            target_url="https://example.com/rec",
            notification_threshold=Decimal("100.00"),
            is_active=True,
        )
        self.history = PriceHistory.objects.create(
            product=self.product,
            price=Decimal("80.00"),
            is_available=True,
            scraped_at=timezone.now(),
        )

    @patch("trackers.tasks.deliver_price_alert")
    def test_recover_stale_processing_alerts(self, mock_deliver):
        from trackers.tasks import recover_undelivered_alerts
        # Create an alert that has been processing for 6 minutes (stale)
        alert = PriceAlert.objects.create(
            product=self.product,
            price_history=self.history,
            user=self.user,
            alert_type=PriceAlert.AlertType.THRESHOLD_REACHED,
            current_price=Decimal("80.00"),
            threshold=Decimal("100.00"),
            status=PriceAlert.DeliveryStatus.PROCESSING,
        )
        # Manually backdate updated_at since auto_now=True ignores normal saves
        PriceAlert.objects.filter(id=alert.id).update(updated_at=timezone.now() - timezone.timedelta(minutes=6))

        result = recover_undelivered_alerts()
        self.assertEqual(result["queued"], 1)
        mock_deliver.delay.assert_called_once_with(alert.id)

        alert.refresh_from_db()
        self.assertEqual(alert.status, PriceAlert.DeliveryStatus.PENDING)

    @patch("trackers.tasks.deliver_price_alert")
    def test_recent_processing_alert_not_recovered(self, mock_deliver):
        from trackers.tasks import recover_undelivered_alerts
        # Create an alert that is currently processing (only 1 minute ago)
        alert = PriceAlert.objects.create(
            product=self.product,
            price_history=self.history,
            user=self.user,
            alert_type=PriceAlert.AlertType.THRESHOLD_REACHED,
            current_price=Decimal("80.00"),
            threshold=Decimal("100.00"),
            status=PriceAlert.DeliveryStatus.PROCESSING,
        )
        PriceAlert.objects.filter(id=alert.id).update(updated_at=timezone.now() - timezone.timedelta(minutes=1))

        result = recover_undelivered_alerts()
        self.assertEqual(result["queued"], 0)
        mock_deliver.delay.assert_not_called()

        alert.refresh_from_db()
        self.assertEqual(alert.status, PriceAlert.DeliveryStatus.PROCESSING)


class HealthEndpointTests(TestCase):
    def test_liveness_check(self):
        response = self.client.get(reverse("health-check-live"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"], "live")

    def test_readiness_check(self):
        from unittest.mock import patch
        with patch("trackers.views.Redis") as mock_redis:
            mock_redis.from_url.return_value.ping.return_value = True
            response = self.client.get(reverse("health-check-ready"))
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.json()["status"], "ready")

    def test_readiness_check_fails_gracefully(self):
        from unittest.mock import patch
        from redis import RedisError
        with patch("trackers.views.Redis") as mock_redis:
            mock_redis.from_url.side_effect = RedisError("Connection Refused")
            response = self.client.get(reverse("health-check-ready"))
            self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
            self.assertEqual(response.json()["status"], "degraded")


class PriceQualityGateTests(TestCase):
    """Phase M — price extraction quality gates.

    Verifies that the _validate_price guard in registry.py correctly
    rejects non-positive and absurdly high prices before they are persisted.
    """

    def _html_with_price(self, price_text: str) -> str:
        """Return minimal JSON-LD HTML for a given price string."""
        return f"""
        <html><head>
        <script type="application/ld+json">
        {{
            "@context": "https://schema.org/",
            "@type": "Product",
            "name": "Test Product",
            "offers": {{
                "@type": "Offer",
                "priceCurrency": "PKR",
                "price": "{price_text}",
                "availability": "https://schema.org/InStock"
            }}
        }}
        </script>
        </head><body></body></html>
        """

    def test_zero_price_is_rejected(self):
        """A price of 0 must not be returned — it signals a parse failure."""
        html = self._html_with_price("0")
        with self.assertRaises(PriceNotFoundError):
            extract_price(html, "https://example.com/zero")

    def test_negative_price_is_rejected(self):
        """Negative prices are structurally impossible and indicate bad markup."""
        from unittest.mock import patch
        from trackers.scraping.extractors import JSONLDExtractor
        mock_result = ScrapeResult(price=Decimal("-1.00"), source="json_ld")

        with patch.object(JSONLDExtractor, "extract", return_value=mock_result):
            with self.assertRaises(PriceNotFoundError):
                extract_price("<html></html>", "https://example.com/negative")

    def test_price_above_ceiling_is_rejected(self):
        """Prices over 50,000,000 are treated as malformed markup."""
        from unittest.mock import patch
        from trackers.scraping.extractors import JSONLDExtractor
        mock_result = ScrapeResult(price=Decimal("99999999.00"), source="json_ld")

        with patch.object(JSONLDExtractor, "extract", return_value=mock_result):
            with self.assertRaises(PriceNotFoundError):
                extract_price("<html></html>", "https://example.com/ceiling")

    def test_valid_price_passes_quality_gate(self):
        """A valid, in-range price should be returned unchanged."""
        html = self._html_with_price("4999.00")
        result = extract_price(html, "https://example.com/valid")
        self.assertEqual(result.price, Decimal("4999.00"))

    def test_quality_gate_falls_through_to_next_extractor(self):
        """When the first extractor returns an invalid price, the next one is tried."""
        from unittest.mock import patch
        from trackers.scraping.extractors import JSONLDExtractor, ShopifyExtractor

        bad_result = ScrapeResult(price=Decimal("0"), source="json_ld")
        good_result = ScrapeResult(price=Decimal("1500.00"), source="shopify")

        with patch.object(JSONLDExtractor, "extract", return_value=bad_result), \
             patch.object(ShopifyExtractor, "extract", return_value=good_result):
            result = extract_price("<html></html>", "https://example.com/fallthrough")
            self.assertEqual(result.price, Decimal("1500.00"))
            self.assertEqual(result.source, "shopify")

    def test_at_ceiling_boundary_is_accepted(self):
        """A price equal to the ceiling (50,000,000) should be accepted."""
        from unittest.mock import patch
        from trackers.scraping.extractors import JSONLDExtractor
        boundary = ScrapeResult(price=Decimal("50000000"), source="json_ld")

        with patch.object(JSONLDExtractor, "extract", return_value=boundary):
            result = extract_price("<html></html>", "https://example.com/boundary")
            self.assertEqual(result.price, Decimal("50000000"))

    def test_all_extractors_fail_quality_gate_raises_price_not_found(self):
        """If every extractor returns an invalid price, PriceNotFoundError is raised."""
        from unittest.mock import patch
        from trackers.scraping.extractors import (
            JSONLDExtractor, ShopifyExtractor, DarazExtractor, GenericExtractor
        )
        zero = ScrapeResult(price=Decimal("0"), source="test")
        with patch.object(JSONLDExtractor, "extract", return_value=zero), \
             patch.object(ShopifyExtractor, "extract", return_value=zero), \
             patch.object(DarazExtractor, "extract", return_value=zero), \
             patch.object(GenericExtractor, "extract", return_value=zero):
            with self.assertRaises(PriceNotFoundError):
                extract_price("<html></html>", "https://example.com/all-fail")

    def test_extractor_unexpected_errors_propagate(self):
        """If an extractor raises an unexpected exception, it should propagate."""
        from unittest.mock import patch
        from trackers.scraping.extractors import JSONLDExtractor

        with patch.object(JSONLDExtractor, "extract", side_effect=RuntimeError("Unexpected DB / parse error")):
            with self.assertRaises(RuntimeError) as ctx:
                extract_price("<html></html>", "https://example.com/runtime-error")
            self.assertEqual(str(ctx.exception), "Unexpected DB / parse error")
