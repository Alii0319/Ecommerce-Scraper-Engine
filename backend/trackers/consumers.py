import json
from urllib.parse import parse_qs
from channels.generic.websocket import AsyncWebsocketConsumer
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from channels.db import database_sync_to_async

User = get_user_model()

class AlertNotificationConsumer(AsyncWebsocketConsumer):
    """Asynchronous WebSocket consumer managing live multi-tenant alert broadcast pipelines."""
    
    async def connect(self):
        # Extract query parameters payload from incoming WS connection URI string
        query_string = self.scope.get('query_string', b'').decode()
        params = parse_qs(query_string)
        token = params.get('token', [None])[0]

        if not token:
            await self.close(code=4401)
            return

        # Authenticate token dynamically against shared PostgreSQL tables context
        self.user = await self.get_authenticated_user(token)
        if self.user is None:
            await self.close(code=4403)
            return

        # Set atomic multiplex group specific to the unique user workspace footprint
        self.group_name = f'user_{self.user.id}_alerts'

        # Register channel inside the Redis distribution cluster mesh
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        # Gracefully isolate nodes on link failure states to prevent dangling state loops
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    @database_sync_to_async
    def get_authenticated_user(self, token_str):
        """Validates incoming simplejwt access key matrix safely within thread-pool constraints."""
        try:
            access_token = AccessToken(token_str)
            user_id = access_token['user_id']
            return User.objects.get(id=user_id)
        except Exception:
            return None

    async def broadcast_alert(self, event):
        """Handler triggered by internal system celery routines through redis channels layer."""
        payload = event["payload"]
        
        # Dispatch structured JSON frames directly into active physical downstream client frames
        await self.send(text_data=json.dumps({
            "event": "price_threshold_alert",
            "data": payload
        }))