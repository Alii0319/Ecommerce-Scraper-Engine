from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from trackers.models import PriceHistory, TrackedProduct


class AnalyticsSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        products = TrackedProduct.objects.filter(user=request.user).prefetch_related('price_histories')
        history_points = PriceHistory.objects.filter(product__user=request.user).count()

        latest_prices = []
        for product in products:
            latest_price = product.price_histories.order_by('-scraped_at').first()
            if latest_price:
                latest_prices.append({
                    'product_id': product.id,
                    'product_name': product.product_name,
                    'current_price': f"{latest_price.price:.2f}",
                    'last_scraped_at': latest_price.scraped_at.isoformat(),
                    'last_scraped_at_dt': latest_price.scraped_at,
                    'is_active': product.is_active,
                })

        # Sort by actual datetime for robust, timezone-aware ordering
        latest_prices.sort(key=lambda item: item['last_scraped_at_dt'], reverse=True)
        # Remove helper datetime key before returning
        for item in latest_prices:
            item.pop('last_scraped_at_dt', None)

        summary = {
            'tracker_count': products.count(),
            'active_trackers': products.filter(is_active=True).count(),
            'history_points': history_points,
            'latest_prices': latest_prices,
        }

        return Response(summary, status=status.HTTP_200_OK)
