from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.test import APITestCase

from trackers.models import PriceHistory, TrackedProduct

User = get_user_model()


class AnalyticsSummaryTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='user@example.com', password='StrongPass123!', first_name='Test', last_name='User')
        self.other_user = User.objects.create_user(email='other@example.com', password='StrongPass123!', first_name='Other', last_name='User')

        self.product = TrackedProduct.objects.create(
            user=self.user,
            product_name='Wireless Headphones',
            target_url='https://example.com/headphones',
            notification_threshold=1200,
            is_active=True,
        )
        self.other_product = TrackedProduct.objects.create(
            user=self.other_user,
            product_name='Other Product',
            target_url='https://example.com/other',
            notification_threshold=500,
            is_active=True,
        )

        PriceHistory.objects.create(product=self.product, price=1500, is_available=True, scraped_at=timezone.now())
        PriceHistory.objects.create(product=self.product, price=1350, is_available=True, scraped_at=timezone.now())
        PriceHistory.objects.create(product=self.other_product, price=900, is_available=True, scraped_at=timezone.now())

    def test_authenticated_user_receives_only_their_analytics_summary(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse('analytics-summary'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['tracker_count'], 1)
        self.assertEqual(response.data['active_trackers'], 1)
        self.assertEqual(response.data['history_points'], 2)
        self.assertEqual(len(response.data['latest_prices']), 1)
        self.assertEqual(response.data['latest_prices'][0]['product_name'], self.product.product_name)
        self.assertEqual(response.data['latest_prices'][0]['current_price'], '1350.00')

    def test_latest_prices_are_ordered_by_most_recent_scrape(self):
        older_timestamp = timezone.now() - timedelta(days=1)
        newer_timestamp = timezone.now()

        TrackedProduct.objects.filter(user=self.user).delete()

        older_product = TrackedProduct.objects.create(
            user=self.user,
            product_name='Older Tracker',
            target_url='https://example.com/older',
            notification_threshold=800,
            is_active=True,
        )
        newer_product = TrackedProduct.objects.create(
            user=self.user,
            product_name='Newer Tracker',
            target_url='https://example.com/newer',
            notification_threshold=900,
            is_active=True,
        )

        newer_history = PriceHistory.objects.create(product=newer_product, price=1250, is_available=True, scraped_at=newer_timestamp)
        PriceHistory.objects.create(product=older_product, price=1100, is_available=True, scraped_at=older_timestamp)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse('analytics-summary'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        latest_prices = response.data['latest_prices']
        self.assertEqual(len(latest_prices), 2)
        # Parse ISO timestamps to datetimes for robust ordering checks
        last0 = parse_datetime(latest_prices[0]['last_scraped_at'])
        last1 = parse_datetime(latest_prices[1]['last_scraped_at'])
        self.assertIsNotNone(last0)
        self.assertIsNotNone(last1)
        self.assertGreater(last0, last1)
        # Ensure both trackers are present regardless of list ordering
        names = {p['product_name'] for p in latest_prices}
        self.assertSetEqual(names, {'Older Tracker', 'Newer Tracker'})
        # Confirm prices mapped correctly for the newer item exists
        self.assertIn('1250.00', {p['current_price'] for p in latest_prices})
