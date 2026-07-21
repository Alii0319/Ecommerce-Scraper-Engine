from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from trackers.views import health_check

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health_check, name='health-check'),

    # Internal Feature App Enclaves
    path('api/auth/', include('authentication.urls')),
    path('api/trackers/', include('trackers.urls')),
    path('api/analytics/', include('analytics.urls')),

    # OpenAPI Generation and Auto-Documentation Interface Nodes
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]