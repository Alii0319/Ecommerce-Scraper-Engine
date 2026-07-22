import json
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model
from django_redis import get_redis_connection

User = get_user_model()


class AlertNotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        ticket = self._extract_ticket()

        if not ticket:
            await self.close(code=4401)
            return

        self.user = await self._authenticate_ticket(ticket)
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

    def _extract_ticket(self) -> str | None:
        query_string = self.scope.get("query_string", b"").decode()
        params = parse_qs(query_string)
        return params.get("ticket", [None])[0]

    @database_sync_to_async
    def _authenticate_ticket(self, ticket: str):
        redis_conn = get_redis_connection("default")
        cache_key = f"ws-ticket:{ticket}"

        # Atomically retrieve and delete ticket to prevent reuse
        ticket_data_bytes = redis_conn.getdel(cache_key)
        if not ticket_data_bytes:
            return None

        try:
            ticket_data = json.loads(ticket_data_bytes)
            user_id = ticket_data.get("user_id")
            if not user_id:
                return None
            return User.objects.get(id=user_id, is_active=True)
        except (json.JSONDecodeError, User.DoesNotExist):
            return None

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return

        try:
            message = json.loads(text_data)
        except json.JSONDecodeError:
            return

        if (
            message.get("type") == "alert_ack"
            and message.get("version") == 1
        ):
            await self._acknowledge_alert(
                event_id=message.get("event_id"),
                user_id=self.user.id,
            )

    @database_sync_to_async
    def _acknowledge_alert(self, event_id: str, user_id: int):
        from django.utils import timezone
        from trackers.models import PriceAlert

        if not event_id:
            return

        PriceAlert.objects.filter(
            event_id=event_id,
            user_id=user_id,
            status__in=[
                PriceAlert.DeliveryStatus.PUBLISHED,
                PriceAlert.DeliveryStatus.ACKNOWLEDGED,
            ]
        ).update(
            status=PriceAlert.DeliveryStatus.ACKNOWLEDGED,
            acknowledged_at=timezone.now()
        )

    async def broadcast_alert(self, event):
        await self.send(text_data=json.dumps(event["event"]))