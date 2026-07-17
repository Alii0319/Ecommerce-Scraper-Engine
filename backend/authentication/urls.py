from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import RegisterView, CustomTokenObtainPairView

urlpatterns = [
    # Dedicated onboarding route
    path('register/', RegisterView.as_view(), name='auth_register'),
    
    # SimpleJWT native controller nodes for handling token lifecycles
    path('login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]