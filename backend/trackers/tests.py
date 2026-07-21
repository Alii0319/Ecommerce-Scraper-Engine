from decimal import Decimal
from unittest.mock import patch

from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from core.asgi import application
from .models import PriceHistory, TrackedProduct
from .scraping import (
    PriceNotFoundError,
    ScrapeResult,
    UnsafeTargetUrlError,
    extract_price,
    validate_public_url,
)
from .tasks import scrape_single_product, should_send_threshold_alert

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

    @patch("trackers.tasks.dispatch_websocket_alert")
    @patch("trackers.tasks.extract_price")
    @patch("trackers.tasks.fetch_rendered_html")
    def test_scrape_creates_history_and_alerts_when_crossing_threshold(
        self, mock_fetch, mock_extract, mock_dispatch
    ):
        mock_fetch.return_value = "<html></html>"
        mock_extract.return_value = ScrapeResult(price=Decimal("80.00"))

        result = scrape_single_product(self.product.id)

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["alert_sent"])
        self.assertEqual(PriceHistory.objects.filter(product=self.product).count(), 1)

        self.product.refresh_from_db()
        self.assertEqual(self.product.last_alerted_price, Decimal("80.00"))
        self.assertIsNotNone(self.product.last_scraped_at)
        mock_dispatch.assert_called_once()

    @patch("trackers.tasks.dispatch_websocket_alert")
    @patch("trackers.tasks.extract_price")
    @patch("trackers.tasks.fetch_rendered_html")
    def test_duplicate_alert_prevented_for_unchanged_price(
        self, mock_fetch, mock_extract, mock_dispatch
    ):
        mock_fetch.return_value = "<html></html>"
        mock_extract.return_value = ScrapeResult(price=Decimal("80.00"))

        # First scrape -> alerts
        scrape_single_product(self.product.id)
        mock_dispatch.reset_mock()

        # Second scrape at same price -> no alert
        result = scrape_single_product(self.product.id)
        self.assertFalse(result["alert_sent"])
        mock_dispatch.assert_not_called()

    @patch("trackers.tasks.dispatch_websocket_alert")
    @patch("trackers.tasks.extract_price")
    @patch("trackers.tasks.fetch_rendered_html")
    def test_new_lower_price_triggers_alert(
        self, mock_fetch, mock_extract, mock_dispatch
    ):
        mock_fetch.return_value = "<html></html>"
        mock_extract.return_value = ScrapeResult(price=Decimal("80.00"))
        scrape_single_product(self.product.id)
        mock_dispatch.reset_mock()

        # Lower price -> alerts again
        mock_extract.return_value = ScrapeResult(price=Decimal("70.00"))
        result = scrape_single_product(self.product.id)
        self.assertTrue(result["alert_sent"])
        mock_dispatch.assert_called_once()

    def test_should_send_threshold_alert_logic(self):
        # 1. Crossing threshold from above
        self.assertTrue(
            should_send_threshold_alert(
                previous_price=Decimal("120.00"),
                current_price=Decimal("90.00"),
                threshold=Decimal("100.00"),
                last_alerted_price=None,
            )
        )

        # 2. Unchanged price below threshold -> no alert
        self.assertFalse(
            should_send_threshold_alert(
                previous_price=Decimal("90.00"),
                current_price=Decimal("90.00"),
                threshold=Decimal("100.00"),
                last_alerted_price=Decimal("90.00"),
            )
        )

        # 3. Risen price below threshold -> no alert
        self.assertFalse(
            should_send_threshold_alert(
                previous_price=Decimal("80.00"),
                current_price=Decimal("90.00"),
                threshold=Decimal("100.00"),
                last_alerted_price=Decimal("80.00"),
            )
        )

        # 4. New lower price below threshold -> alert
        self.assertTrue(
            should_send_threshold_alert(
                previous_price=Decimal("90.00"),
                current_price=Decimal("75.00"),
                threshold=Decimal("100.00"),
                last_alerted_price=Decimal("90.00"),
            )
        )


class SSRFValidationTests(TestCase):
    def test_private_ip_raises_unsafe_error(self):
        with self.assertRaises(UnsafeTargetUrlError):
            validate_public_url("http://127.0.0.1:8000/internal")

        with self.assertRaises(UnsafeTargetUrlError):
            validate_public_url("http://169.254.169.254/latest/meta-data/")

        with self.assertRaises(UnsafeTargetUrlError):
            validate_public_url("ftp://example.com/file")


class WebSocketConsumerTests(TransactionTestCase):
    async def test_missing_token_rejected_with_4401(self):
        communicator = WebsocketCommunicator(application, "/ws/alerts/")
        connected, close_code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4401)

    async def test_invalid_token_rejected_with_4403(self):
        communicator = WebsocketCommunicator(
            application, "/ws/alerts/?token=invalid_jwt_token"
        )
        connected, close_code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4403)

    async def test_valid_token_connects_and_receives_alert(self):
        user = await User.objects.acreate(
            email="wsuser@example.com", password="StrongPass123!"
        )
        token = str(AccessToken.for_user(user))

        communicator = WebsocketCommunicator(
            application, f"/ws/alerts/?token={token}"
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Trigger event to group
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        event = {
            "type": "price_threshold_alert",
            "version": 1,
            "data": {
                "product_id": 10,
                "history_id": 100,
                "product_name": "Test Item",
                "current_price": "50.00",
                "threshold": "100.00",
                "target_url": "https://example.com/test",
                "timestamp": "2026-07-21T10:00:00Z",
            },
        }
        await channel_layer.group_send(
            f"user_{user.id}_alerts", {"type": "broadcast.alert", "event": event}
        )

        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "price_threshold_alert")
        self.assertEqual(response["version"], 1)
        self.assertEqual(response["data"]["product_name"], "Test Item")

        await communicator.disconnect()
