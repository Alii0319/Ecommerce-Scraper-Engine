from django.db import models
from django.conf import settings

class TrackedProduct(models.Model):
    """Stores target products metadata designated for continuous web scraping."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tracked_products')
    product_name = models.CharField(max_length=255)
    target_url = models.URLField(max_length=1000)
    notification_threshold = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_scraped_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.product_name} - {self.user.email}"

class PriceHistory(models.Model):
    """Stores time-series historical price metrics fetched by Celery scraping tasks."""
    product = models.ForeignKey(TrackedProduct, on_delete=models.CASCADE, related_name='price_histories')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_available = models.BooleanField(default=True)
    scraped_at = models.DateTimeField()

    class Meta:
        ordering = ['-scraped_at']  # Always retrieves the newest price log first

    def __str__(self):
        return f"{self.product.product_name}: {self.price} at {self.scraped_at}"