import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

# Declare base variables state initialization configurations before parsing layers execution
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django_asgi_app = get_asgi_application()

import trackers.routing

# Multi-Protocol network transport distribution multiplexer engine
application = ProtocolTypeRouter({
    # Decouple classic HTTP request pipelines directly from stream-oriented networks stack
    "http": django_asgi_app,
    
    # Fast real-time frames pipelines layer routing manager interface nodes
    "websocket": AuthMiddlewareStack(
        URLRouter(
            trackers.routing.websocket_urlpatterns
        )
    ),
})