from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TrackedProductViewSet

router = DefaultRouter()
router.register(r'products', TrackedProductViewSet, basename='tracked-product')

urlpatterns = [
    path('', include(router.urls)),
]