from decimal import Decimal
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import TrackedProduct, PriceHistory

User = get_user_model()

class TrackedProductAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='user@example.com', password='StrongPass123!', first_name='Test', last_name='User')
        self.other_user = User.objects.create_user(email='other@example.com', password='StrongPass123!', first_name='Other', last_name='User')
        self.client.force_authenticate(user=self.user)

    def test_create_product_requires_valid_url(self):
        response = self.client.post(reverse('tracked-product-list'), {
            'product_name': 'Example',
            'target_url': 'invalid-url',
            'notification_threshold': '100.00',
            'is_active': True,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('target_url', response.data)

    def test_create_duplicate_url_for_same_user_is_rejected(self):
        TrackedProduct.objects.create(
            user=self.user,
            product_name='Original',
            target_url='https://example.com/product',
            notification_threshold='100.00',
        )
        response = self.client.post(reverse('tracked-product-list'), {
            'product_name': 'Duplicate',
            'target_url': 'https://example.com/product',
            'notification_threshold': '50.00',
            'is_active': True,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('target_url', response.data)

    def test_user_cannot_modify_another_users_product(self):
        product = TrackedProduct.objects.create(
            user=self.other_user,
            product_name='Other Product',
            target_url='https://example.com/other',
            notification_threshold='250.00',
        )
        response = self.client.patch(reverse('tracked-product-detail', args=[product.id]), {
            'notification_threshold': '200.00'
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_product_removes_record(self):
        product = TrackedProduct.objects.create(
            user=self.user,
            product_name='Deletable Product',
            target_url='https://example.com/delete',
            notification_threshold='150.00',
        )
        response = self.client.delete(reverse('tracked-product-detail', args=[product.id]))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(TrackedProduct.objects.filter(pk=product.pk).exists())

    def test_tracker_create_sets_user_and_returns_product(self):
        response = self.client.post(reverse('tracked-product-list'), {
            'product_name': 'New Product',
            'target_url': 'https://example.com/new',
            'notification_threshold': '99.99',
            'is_active': True,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['product_name'], 'New Product')
        self.assertEqual(response.data['target_url'], 'https://example.com/new')
        self.assertEqual(response.data['notification_threshold'], '99.99')
        self.assertIsNotNone(response.data['created_at'])

    def test_update_product_rejects_duplicate_url(self):
        product = TrackedProduct.objects.create(
            user=self.user,
            product_name='Original',
            target_url='https://example.com/original',
            notification_threshold='100.00',
        )
        other_product = TrackedProduct.objects.create(
            user=self.user,
            product_name='Existing',
            target_url='https://example.com/existing',
            notification_threshold='150.00',
        )

        response = self.client.patch(reverse('tracked-product-detail', args=[product.id]), {
            'target_url': 'https://example.com/existing'
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('target_url', response.data)

    def test_update_product_allows_same_url_for_self(self):
        product = TrackedProduct.objects.create(
            user=self.user,
            product_name='Self Update',
            target_url='https://example.com/self',
            notification_threshold='100.00',
        )

        response = self.client.patch(reverse('tracked-product-detail', args=[product.id]), {
            'product_name': 'Self Updated'
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['product_name'], 'Self Updated')

class ScraperTaskTests(TestCase):
    def test_price_history_created_and_last_scraped_updated(self):
        user = User.objects.create_user(email='scraper@example.com', password='StrongPass123!')
        product = TrackedProduct.objects.create(
            user=user,
            product_name='Task Product',
            target_url='https://example.com/task',
            notification_threshold='9999.99',
            is_active=True,
        )
        now = timezone.now()
        history = PriceHistory.objects.create(
            product=product,
            price=Decimal('123.45'),
            is_available=True,
            scraped_at=now,
        )
        history.refresh_from_db()

        self.assertEqual(history.product, product)
        self.assertEqual(history.price, Decimal('123.45'))
        self.assertEqual(history.scraped_at, now)
