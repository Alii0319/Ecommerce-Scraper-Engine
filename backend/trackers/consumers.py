import json
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

User = get_user_model()


class AlertNotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        ticket, token = self._extract_credentials()

        self.user = None

        if ticket:
            self.user = await self._authenticate_ticket(ticket)
        elif token:
            self.user = await self._authenticate_token(token)

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

    def _extract_credentials(self) -> tuple[str | None, str | None]:
        query_string = self.scope.get("query_string", b"").decode()
        params = parse_qs(query_string)
        ticket = params.get("ticket", [None])[0]
        token = params.get("token", [None])[0]
        return ticket, token

    @database_sync_to_async
    def _authenticate_ticket(self, ticket: str):
        cache_key = f"ws-ticket:{ticket}"
        # Atomically retrieve and delete ticket to prevent reuse
        ticket_data = cache.get(cache_key)
        if not ticket_data:
            return None
        cache.delete(cache_key)

        user_id = ticket_data.get("user_id")
        if not user_id:
            return None

        try:
            return User.objects.get(id=user_id, is_active=True)
        except User.DoesNotExist:
            return None

    @database_sync_to_async
    def _authenticate_token(self, token_str: str):
        try:
            access_token = AccessToken(token_str)
            user_id = access_token.get("user_id")
            return User.objects.get(id=user_id, is_active=True)
        except (TokenError, User.DoesNotExist, KeyError, TypeError):
            return None

    async def broadcast_alert(self, event):
        await self.send(text_data=json.dumps(event["event"]))