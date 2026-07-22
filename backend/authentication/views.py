import secrets
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import (
    CustomTokenObtainPairSerializer,
    RegisterSerializer,
    WebSocketTicketSerializer,
)

User = get_user_model()


class CustomTokenObtainPairView(TokenObtainPairView):
    """Custom Token Obtain View returning JWT with user email, first name, and last name."""

    serializer_class = CustomTokenObtainPairSerializer


class RegisterView(generics.CreateAPIView):
    """Controller for user onboarding and automatic database row insertion."""

    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                "message": "User registered successfully",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class WebSocketTicketView(APIView):
    """Generates short-lived (30s) single-use ticket for WebSocket authentication."""

    permission_classes = (IsAuthenticated,)
    serializer_class = WebSocketTicketSerializer

    def post(self, request, *args, **kwargs):
        ticket = secrets.token_hex(32)
        expires_at = timezone.now() + timedelta(seconds=30)
        cache_key = f"ws-ticket:{ticket}"

        import json
        from django_redis import get_redis_connection
        redis_conn = get_redis_connection("default")

        # Save to cache with 30s expiration using raw json string
        redis_conn.setex(cache_key, 30, json.dumps({"user_id": request.user.id}))

        return Response(
            {
                "ticket": ticket,
                "expires_at": expires_at.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )
