from decimal import Decimal
from urllib.parse import urlparse

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import PriceHistory, TrackedProduct

class PriceHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceHistory
        fields = ('id', 'price', 'is_available', 'scraped_at')

class TrackedProductSerializer(serializers.ModelSerializer):
    # Read-only integration to pull nested historic time-series metrics dynamically
    price_histories = PriceHistorySerializer(many=True, read_only=True)
    domain_name = serializers.SerializerMethodField()
    notification_threshold = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))

    class Meta:
        model = TrackedProduct
        fields = ('id', 'product_name', 'target_url', 'notification_threshold', 'is_active', 'created_at', 'last_scraped_at', 'domain_name', 'price_histories')
        read_only_fields = ('id', 'created_at', 'last_scraped_at')

    @extend_schema_field(serializers.CharField())
    def get_domain_name(self, obj) -> str:
        # Extract clear human-readable domain text from pure raw target URLs
        try:
            return urlparse(obj.target_url).netloc.replace('www.', '')
        except (AttributeError, ValueError):
            return 'unknown'

    def validate_target_url(self, value):
        # Prevent parsing anomalies by asserting minimum standard URI parameters early
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            raise serializers.ValidationError('Invalid domain footprint. Provide a fully qualified URL.')
        if parsed.scheme not in {'http', 'https'}:
            raise serializers.ValidationError('Only http and https URLs are supported.')

        request = self.context.get('request') if hasattr(self, 'context') else None
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            existing = TrackedProduct.objects.filter(user=user, target_url=value)
            if self.instance is not None:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise serializers.ValidationError('You are already tracking a product with this URL.')
        return value

    def validate_notification_threshold(self, value):
        if value <= 0:
            raise serializers.ValidationError('Notification threshold must be a positive value.')
        return value
