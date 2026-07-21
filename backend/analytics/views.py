from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from trackers.models import PriceHistory, TrackedProduct

_latest_price_serializer = inline_serializer(
    name="LatestPrice",
    fields={
        "product_id": serializers.IntegerField(),
        "product_name": serializers.CharField(),
        "current_price": serializers.CharField(),
        "last_scraped_at": serializers.DateTimeField(),
        "is_active": serializers.BooleanField(),
    },
)

_analytics_summary_serializer = inline_serializer(
    name="AnalyticsSummary",
    fields={
        "tracker_count": serializers.IntegerField(),
        "active_trackers": serializers.IntegerField(),
        "history_points": serializers.IntegerField(),
        "latest_prices": _latest_price_serializer,
    },
)


class AnalyticsSummaryView(APIView):
    """Returns a per-user analytics summary: counts and most recent price snapshots."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: _analytics_summary_serializer})
    def get(self, request, *args, **kwargs):
        products = (
            TrackedProduct.objects.filter(user=request.user)
            .prefetch_related("price_histories")
        )
        history_points = PriceHistory.objects.filter(product__user=request.user).count()

        latest_prices = []
        for product in products:
            latest_price = product.price_histories.order_by("-scraped_at").first()
            if latest_price:
                latest_prices.append({
                    "product_id": product.id,
                    "product_name": product.product_name,
                    "current_price": f"{latest_price.price:.2f}",
                    "last_scraped_at": latest_price.scraped_at.isoformat(),
                    "last_scraped_at_dt": latest_price.scraped_at,
                    "is_active": product.is_active,
                })

        # Sort by actual datetime for robust, timezone-aware ordering
        latest_prices.sort(key=lambda item: item["last_scraped_at_dt"], reverse=True)
        for item in latest_prices:
            item.pop("last_scraped_at_dt", None)

        summary = {
            "tracker_count": products.count(),
            "active_trackers": products.filter(is_active=True).count(),
            "history_points": history_points,
            "latest_prices": latest_prices,
        }

        return Response(summary, status=status.HTTP_200_OK)
