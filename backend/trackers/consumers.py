import json
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

User = get_user_model()


class AlertNotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        token = self._extract_token()

        if not token:
            await self.close(code=4401)
            return

        self.user = await self._get_authenticated_user(token)
        if self.user is None:
            await self.close(code=4403)
            return

        self.group_name = f"user_{self.user.id}_alerts"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        group_name = getattr(self, "group_name", None)
        if group_name:
            await self.channel_layer.group_discard(
                group_name,
                self.channel_name,
            )

    def _extract_token(self) -> str | None:
        query_string = self.scope.get("query_string", b"").decode()
        params = parse_qs(query_string)
        return params.get("token", [None])[0]

    @database_sync_to_async
    def _get_authenticated_user(self, token_str):
        try:
            access_token = AccessToken(token_str)
            user_id = access_token.get("user_id")
            return User.objects.get(id=user_id, is_active=True)
        except (TokenError, User.DoesNotExist, KeyError, TypeError):
            return None

    async def broadcast_alert(self, event):
        await self.send(text_data=json.dumps(event["event"]))