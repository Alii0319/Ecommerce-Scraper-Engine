from django.urls import re_path
from .consumers import AlertNotificationConsumer

websocket_urlpatterns = [
    # Explicit regex target routing map node to stream live pipeline logs securely
    re_path(r'^ws/alerts/$', AlertNotificationConsumer.as_asgi()),
]