from django.conf import settings
from django.db import DatabaseError, OperationalError
from django.db import connection, transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from redis import Redis, RedisError
from rest_framework import permissions, viewsets

from .models import TrackedProduct
from .serializers import TrackedProductSerializer


@extend_schema(
    parameters=[
        OpenApiParameter(
            name="id",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.PATH,
            description="Unique integer ID of the tracked product.",
        )
    ]
)
class TrackedProductViewSet(viewsets.ModelViewSet):
    """Isolated tracker management — strictly scoped to the authenticated user."""

    serializer_class = TrackedProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Enforce strict multi-tenant data isolation — each user only sees their own trackers
        return (
            TrackedProduct.objects.filter(user=self.request.user)
            .prefetch_related("price_histories")
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        with transaction.atomic():
            serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        with transaction.atomic():
            serializer.save()

    def perform_destroy(self, instance):
        with transaction.atomic():
            instance.delete()


@require_GET
def liveness_check(request):
    """Liveness probe: verifies process is running without hitting DB/Redis."""
    return JsonResponse({"status": "live"})


@require_GET
def readiness_check(request):
    """Readiness probe: verifies database and Redis cluster connectivity."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        redis_status = "skipped"
        if not getattr(settings, "USE_IN_MEMORY_CHANNEL_LAYER", False):
            redis_client = Redis.from_url(settings.REDIS_URL, socket_timeout=2)
            redis_client.ping()
            redis_status = "ok"

        return JsonResponse({"status": "ready", "db": "ok", "redis": redis_status})
    except (DatabaseError, OperationalError, RedisError):
        import logging
        logging.getLogger(__name__).exception("Health check failed")
        return JsonResponse({"status": "degraded"}, status=503)


@require_GET
def health_check(request):
    """Backward compatible health endpoint mapping to readiness probe."""
    return readiness_check(request)
