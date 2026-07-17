from django.contrib import admin
from .models import TrackedProduct, PriceHistory
# Register your models here.
admin.site.register(TrackedProduct)
admin.site.register(PriceHistory)