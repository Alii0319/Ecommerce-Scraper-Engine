import uuid
from django.conf import settings
from django.db import models


class TrackedProduct(models.Model):
    """Stores target products metadata designated for continuous web scraping."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tracked_products",
    )
    product_name = models.CharField(max_length=255)
    target_url = models.URLField(max_length=1000)
    notification_threshold = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_scraped_at = models.DateTimeField(null=True, blank=True)
    last_alerted_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    last_alerted_at = models.DateTimeField(null=True, blank=True)

    # Scrape lifecycle tracking state
    last_scrape_status = models.CharField(max_length=32, default="never")
    last_scrape_error_code = models.CharField(max_length=64, blank=True)
    last_scrape_error_message = models.CharField(max_length=500, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "target_url"],
                name="unique_user_target_url",
            ),
            models.CheckConstraint(
                check=models.Q(notification_threshold__gte=0),
                name="positive_notification_threshold",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        return f"{self.product_name} - {self.user.email}"


class PriceHistory(models.Model):
    """Stores time-series historical price metrics fetched by Celery scraping tasks."""

    product = models.ForeignKey(
        TrackedProduct,
        on_delete=models.CASCADE,
        related_name="price_histories",
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_available = models.BooleanField(default=True)
    scraped_at = models.DateTimeField()

    class Meta:
        ordering = ["-scraped_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(price__gte=0),
                name="positive_price_history_price",
            ),
        ]
        indexes = [
            models.Index(fields=["product", "scraped_at"]),
        ]

    def __str__(self):
        return f"{self.product.product_name}: {self.price} at {self.scraped_at}"


class PriceAlert(models.Model):
    """Durable alert outbox for threshold and price drop notification delivery."""

    class AlertType(models.TextChoices):
        THRESHOLD_REACHED = "threshold_reached", "Threshold reached"
        NEW_LOWER_PRICE = "new_lower_price", "New lower price"
        PRICE_DROP = "price_drop", "Price drop"

    class DeliveryStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"

    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    product = models.ForeignKey(
        TrackedProduct, on_delete=models.CASCADE, related_name="alerts"
    )
    price_history = models.ForeignKey(
        PriceHistory,
        on_delete=models.CASCADE,
        related_name="alerts",
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="price_alerts",
    )
    alert_type = models.CharField(max_length=32, choices=AlertType.choices)
    current_price = models.DecimalField(max_digits=12, decimal_places=2)
    threshold = models.DecimalField(max_digits=12, decimal_places=2)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=16,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING,
    )
    attempts = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "available_at"], name="alert_delivery_queue_idx"),
            models.Index(fields=["user", "-created_at"], name="alert_user_created_idx"),
        ]

    def __str__(self):
        return f"Alert {self.event_id} - {self.product.product_name} ({self.status})"