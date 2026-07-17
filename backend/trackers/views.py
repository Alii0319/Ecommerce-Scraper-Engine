from django.db import transaction
from rest_framework import viewsets, permissions
from .models import TrackedProduct
from .serializers import TrackedProductSerializer

class TrackedProductViewSet(viewsets.ModelViewSet):
    """Production gateway handling isolated user operations for inventory tracking trackers."""
    serializer_class = TrackedProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Enforce strict multi-tenant tenant data isolation boundary constraints
        return TrackedProduct.objects.filter(user=self.request.user).prefetch_related('price_histories')

    def perform_create(self, serializer):
        # Bind the incoming tracking metadata scope exactly to the requesting User identity
        with transaction.atomic():
            serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        # Apply updates inside a database transaction to avoid partial writes
        with transaction.atomic():
            serializer.save()

    def perform_destroy(self, instance):
        # Delete tracker records inside a single atomic operation
        with transaction.atomic():
            instance.delete()