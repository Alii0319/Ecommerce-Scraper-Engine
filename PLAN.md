# Ecommerce Scraper Engine — Production Remediation Plan

## Purpose

This document is an execution plan for an engineering agent to make the repository fully functional end-to-end and align the implementation with the portfolio claims.

Repository:

- `https://github.com/Alii0319/Ecommerce-Scraper-Engine`
- Backend: Django, Django REST Framework, Celery, Channels, PostgreSQL, Redis, Playwright
- Frontend: React, TypeScript, Vite, Recharts
- Infrastructure: Docker Compose, Nginx, GitHub Actions

The agent must treat this as a production-hardening task, not a redesign. Preserve existing API behavior and UI unless a change is required for correctness, security, reliability, or deployment.

---

# 1. Target end-to-end behavior

After all phases are complete, the following flow must work:

1. A user registers or logs in and receives JWT credentials.
2. The user creates a product tracker with product name, target URL, threshold, and active status.
3. Celery Beat runs the orchestration task every four hours.
4. The orchestration task queues one scrape task per active tracker.
5. Playwright loads dynamic content and extracts a validated price.
6. The price is stored in `PriceHistory`, and `last_scraped_at` is updated.
7. The new price is compared with previous state.
8. A WebSocket alert is sent only for a meaningful threshold event.
9. Only the authenticated owner's browser receives the event.
10. The frontend displays one toast and optionally one browser notification.
11. Backend tests, frontend checks, Docker health checks, and CI pass.

---

# 2. Non-negotiable acceptance criteria

The work is complete only when all of the following are true:

- No `TransactionManagementError` is raised by scraper tasks.
- Playwright runs before short database write transactions.
- Django is served through ASGI in Docker.
- WebSockets work through the production container stack.
- Backend and frontend use one documented WebSocket schema.
- Frontend WebSocket URLs are environment-driven and support `wss://`.
- Alerts are not emitted repeatedly for the same unchanged state.
- Redis failure is not silently hidden in production.
- Database migrations run safely during deployment.
- PostgreSQL and Redis health checks gate dependent services.
- CI executes backend tests and frontend validation.
- Test failures cause CI to fail.
- Scraper failures retry with bounded exponential backoff.
- Logs contain useful context without exposing tokens or secrets.
- Existing user data remains compatible or is migrated safely.
- README and portfolio wording match the verified implementation.

---

# 3. Execution order

Implement in this order:

1. Baseline and branch
2. Fix scraper transaction bug
3. Prevent duplicate alerts
4. Standardize WebSocket contract
5. Serve Django through ASGI
6. Make frontend WebSocket configuration production-safe
7. Harden Channels and Redis configuration
8. Improve scraper reliability and extraction
9. Add health checks and safe container startup
10. Upgrade CI
11. Add full pipeline tests
12. Update documentation and portfolio wording
13. Run final acceptance tests

Prefer one focused commit per phase.

---

# 4. Phase 0 — baseline and safety

## Tasks

```bash
git checkout -b fix/production-readiness
cp .env .env.local.backup
```

Never commit `.env`, JWT tokens, database passwords, browser profiles, or generated credentials.

Record the baseline:

```bash
docker compose config
docker compose build
docker compose up -d
docker compose ps
docker compose logs --no-color > baseline-compose.log
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py test
```

Create `docs/baseline.md` with current test count, failures, container status, runtime errors, date, and commit SHA.

---

# 5. Phase 1 — fix the scraper transaction bug

## Problem

`select_for_update()` is currently executed outside `transaction.atomic()`. PostgreSQL can raise `TransactionManagementError` before Playwright starts. Browser I/O must also not run while holding a row lock.

## Required design

1. Read scrape inputs without a lock.
2. Perform browser/network work outside a transaction.
3. Open a short atomic transaction to re-fetch, compare, and write.
4. Dispatch the WebSocket event only after a successful commit.

## Replace/refactor `backend/trackers/tasks.py`

Use this as the production-oriented reference. Adapt model fields only where the repository differs.

```python
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

from asgiref.sync import async_to_sync
from bs4 import BeautifulSoup
from celery import shared_task
from channels.layers import get_channel_layer
from django.db import DatabaseError, transaction
from django.utils import timezone
from playwright.sync_api import (
    Browser,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from .models import PriceHistory, TrackedProduct

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScrapeResult:
    price: Decimal
    currency: str = "PKR"
    is_available: bool = True


class ScrapeError(Exception):
    """Base exception for expected scraper failures."""


class PriceNotFoundError(ScrapeError):
    """Raised when no trustworthy price can be extracted."""


def parse_price_from_text(text: str | None) -> Optional[Decimal]:
    if not text:
        return None

    normalized = text.replace("\u00a0", " ").replace(",", "").strip()
    matches = re.findall(r"(?<!\d)(\d+(?:\.\d{1,2})?)(?!\d)", normalized)

    for raw_value in matches:
        try:
            value = Decimal(raw_value)
        except InvalidOperation:
            continue

        if value > 0:
            return value

    return None


def _configure_page(page: Page) -> None:
    def route_handler(route):
        if route.request.resource_type in {"image", "font", "media"}:
            route.abort()
        else:
            route.continue_()

    page.route("**/*", route_handler)
    page.set_default_navigation_timeout(30_000)
    page.set_default_timeout(10_000)


def fetch_rendered_html(url: str) -> str:
    validate_public_url(url)

    with sync_playwright() as playwright:
        browser: Browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage", "--no-sandbox"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            java_script_enabled=True,
        )
        page = context.new_page()
        _configure_page(page)

        try:
            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=30_000,
            )

            if response is not None and response.status >= 400:
                raise ScrapeError(f"Target returned HTTP {response.status}")

            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except PlaywrightTimeoutError:
                logger.info("Network idle timeout; using rendered DOM")

            return page.content()

        except PlaywrightTimeoutError as exc:
            raise ScrapeError("Timed out loading target page") from exc

        finally:
            context.close()
            browser.close()


def extract_price(html: str) -> ScrapeResult:
    soup = BeautifulSoup(html, "lxml")

    metadata_selectors = (
        'meta[property="product:price:amount"]',
        'meta[property="og:price:amount"]',
        'meta[name="twitter:data1"]',
        '[itemprop="price"][content]',
    )

    for selector in metadata_selectors:
        node = soup.select_one(selector)
        if not node:
            continue

        candidate = node.get("content") or node.get("value")
        price = parse_price_from_text(candidate)
        if price is None:
            continue

        currency_node = (
            soup.select_one('meta[property="product:price:currency"]')
            or soup.select_one('[itemprop="priceCurrency"]')
        )
        currency = "PKR"
        if currency_node:
            currency = (
                currency_node.get("content")
                or currency_node.get_text(strip=True)
                or "PKR"
            ).upper()

        return ScrapeResult(price=price, currency=currency)

    visible_selectors = (
        '[data-automation="product-price"]',
        '[itemprop="price"]',
        ".price-item--sale",
        ".price--special",
        ".pdp-price",
        ".pdp-product-price",
        ".sale-price",
        ".current-price",
        ".price",
    )

    for selector in visible_selectors:
        node = soup.select_one(selector)
        if not node:
            continue

        price = parse_price_from_text(node.get_text(" ", strip=True))
        if price is not None:
            return ScrapeResult(price=price)

    raise PriceNotFoundError("No supported price source was found")


def should_send_threshold_alert(
    *,
    previous_price: Decimal | None,
    current_price: Decimal,
    threshold: Decimal,
    last_alerted_price: Decimal | None,
) -> bool:
    crossed_threshold = (
        current_price <= threshold
        and (previous_price is None or previous_price > threshold)
    )

    new_lower_price = (
        current_price <= threshold
        and last_alerted_price is not None
        and current_price < last_alerted_price
    )

    return crossed_threshold or new_lower_price


@shared_task(
    bind=True,
    name="trackers.tasks.scrape_single_product",
    autoretry_for=(ScrapeError,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    soft_time_limit=90,
    time_limit=120,
)
def scrape_single_product(self, product_id: int) -> dict:
    try:
        snapshot = (
            TrackedProduct.objects
            .only(
                "id",
                "product_name",
                "target_url",
                "notification_threshold",
                "is_active",
                "user_id",
            )
            .get(id=product_id, is_active=True)
        )
    except TrackedProduct.DoesNotExist:
        return {"status": "skipped", "product_id": product_id}

    html = fetch_rendered_html(snapshot.target_url)
    result = extract_price(html)
    now = timezone.now()

    alert_payload = None

    try:
        with transaction.atomic():
            product = (
                TrackedProduct.objects
                .select_for_update()
                .get(id=product_id, is_active=True)
            )

            previous_history = (
                PriceHistory.objects
                .filter(product=product)
                .order_by("-scraped_at", "-id")
                .first()
            )
            previous_price = previous_history.price if previous_history else None

            history = PriceHistory.objects.create(
                product=product,
                price=result.price,
                is_available=result.is_available,
                scraped_at=now,
            )

            should_alert = should_send_threshold_alert(
                previous_price=previous_price,
                current_price=result.price,
                threshold=product.notification_threshold,
                last_alerted_price=product.last_alerted_price,
            )

            product.last_scraped_at = now
            update_fields = ["last_scraped_at"]

            if should_alert:
                product.last_alerted_price = result.price
                product.last_alerted_at = now
                update_fields.extend(["last_alerted_price", "last_alerted_at"])

                alert_payload = {
                    "product_id": product.id,
                    "user_id": product.user_id,
                    "product_name": product.product_name,
                    "target_url": product.target_url,
                    "threshold": product.notification_threshold,
                    "current_price": result.price,
                    "history_id": history.id,
                    "timestamp": now,
                }

            product.save(update_fields=update_fields)

            if alert_payload is not None:
                transaction.on_commit(
                    lambda payload=alert_payload: dispatch_websocket_alert(**payload)
                )

    except TrackedProduct.DoesNotExist:
        return {"status": "skipped", "product_id": product_id}
    except DatabaseError:
        logger.exception(
            "Database write failed after scraping",
            extra={"product_id": product_id},
        )
        raise

    logger.info(
        "Product scrape completed",
        extra={
            "product_id": product_id,
            "price": str(result.price),
            "alert_sent": alert_payload is not None,
        },
    )

    return {
        "status": "success",
        "product_id": product_id,
        "price": str(result.price),
        "alert_sent": alert_payload is not None,
    }


def dispatch_websocket_alert(
    *,
    product_id: int,
    user_id: int,
    product_name: str,
    target_url: str,
    threshold: Decimal,
    current_price: Decimal,
    history_id: int,
    timestamp,
) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        raise RuntimeError("Channel layer is not configured")

    event = {
        "type": "price_threshold_alert",
        "version": 1,
        "data": {
            "product_id": product_id,
            "history_id": history_id,
            "product_name": product_name,
            "current_price": str(current_price),
            "threshold": str(threshold),
            "target_url": target_url,
            "timestamp": timestamp.isoformat(),
        },
    }

    async_to_sync(channel_layer.group_send)(
        f"user_{user_id}_alerts",
        {"type": "broadcast.alert", "event": event},
    )


@shared_task(name="trackers.tasks.orchestrate_scraping_pipeline")
def orchestrate_scraping_pipeline() -> dict:
    product_ids = (
        TrackedProduct.objects
        .filter(is_active=True)
        .values_list("id", flat=True)
        .iterator(chunk_size=500)
    )

    dispatched = 0
    for product_id in product_ids:
        scrape_single_product.delay(product_id)
        dispatched += 1

    return {"status": "success", "dispatched_count": dispatched}
```

---

# 6. Phase 2 — persistent duplicate-alert protection

Add fields to `TrackedProduct`:

```python
last_alerted_price = models.DecimalField(
    max_digits=12,
    decimal_places=2,
    null=True,
    blank=True,
)

last_alerted_at = models.DateTimeField(
    null=True,
    blank=True,
)
```

Create and apply the migration:

```bash
docker compose exec web python manage.py makemigrations trackers
docker compose exec web python manage.py migrate
```

Required behavior:

- Alert when price crosses from above threshold to at/below threshold.
- Alert again only if it reaches a new lower price below threshold.
- Do not alert for unchanged price.
- Do not alert when price rises while still below threshold.
- Do not alert on scrape failure or inactive tracker.

Optional future improvement: add a dedicated `PriceAlert` model for delivery auditing.

---

# 7. Phase 3 — standardize WebSocket contract

Use this exact versioned schema:

```json
{
  "type": "price_threshold_alert",
  "version": 1,
  "data": {
    "product_id": 12,
    "history_id": 105,
    "product_name": "Wireless Headphones",
    "current_price": "8499.00",
    "threshold": "9000.00",
    "target_url": "https://example.com/product",
    "timestamp": "2026-07-21T10:00:00Z"
  }
}
```

Transmit decimal prices as strings.

## Replace `backend/trackers/consumers.py`

```python
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
```

Never log query-string JWTs.

---

# 8. Phase 4 — serve Django through ASGI

The backend Docker container must run Daphne, not WSGI Gunicorn.

## Recommended `backend/Dockerfile`

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.61.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=core.settings

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/requirements.txt

COPY . /app
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "core.asgi:application"]
```

## Required `backend/docker-entrypoint.sh`

```bash
#!/usr/bin/env sh
set -eu

python - <<'PY'
import os
import time
import psycopg

for attempt in range(30):
    try:
        connection = psycopg.connect(
            host=os.environ.get("DB_HOST", "db"),
            port=int(os.environ.get("DB_PORT", "5432")),
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            connect_timeout=3,
        )
        connection.close()
        break
    except Exception:
        if attempt == 29:
            raise
        time.sleep(2)
PY

python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec "$@"
```

If the project uses `psycopg2`, adapt the connection import.

## Verify `backend/core/asgi.py`

```python
import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django_asgi_app = get_asgi_application()

from trackers.routing import websocket_urlpatterns

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        ),
    }
)
```

---

# 9. Phase 5 — production-safe frontend WebSocket hook

Add to `frontend/.env.example`:

```env
VITE_API_BASE_URL=http://localhost:8000/api/
VITE_WS_BASE_URL=ws://localhost:8000
```

Production:

```env
VITE_API_BASE_URL=https://api.example.com/api/
VITE_WS_BASE_URL=wss://api.example.com
```

## Reference replacement for `useWebSocketAlerts.ts`

```typescript
import { useCallback, useEffect, useRef, useState } from "react";

type AlertPayload = {
  product_id: number;
  history_id: number;
  product_name: string;
  current_price: string;
  threshold: string;
  target_url: string;
  timestamp: string;
};

type AlertEvent = {
  type: "price_threshold_alert";
  version: 1;
  data: AlertPayload;
};

export type PriceAlert = {
  id: string;
  productId: number;
  historyId: number;
  productName: string;
  currentPrice: number;
  threshold: number;
  targetUrl: string;
  timestamp: string;
};

type ConnectionState =
  | "idle"
  | "connecting"
  | "connected"
  | "disconnected"
  | "error";

const MAX_RECONNECT_DELAY_MS = 30_000;

function getWebSocketBaseUrl(): string {
  const configured = import.meta.env.VITE_WS_BASE_URL?.trim();
  if (configured) return configured.replace(/\/+$/, "");

  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}`;
}

function isAlertEvent(value: unknown): value is AlertEvent {
  if (!value || typeof value !== "object") return false;

  const event = value as Partial<AlertEvent>;
  const data = event.data as Partial<AlertPayload> | undefined;

  return (
    event.type === "price_threshold_alert" &&
    event.version === 1 &&
    !!data &&
    typeof data.product_id === "number" &&
    typeof data.history_id === "number" &&
    typeof data.product_name === "string" &&
    typeof data.current_price === "string" &&
    typeof data.threshold === "string" &&
    typeof data.target_url === "string" &&
    typeof data.timestamp === "string"
  );
}

export function useWebSocketAlerts(accessToken: string | null) {
  const [alerts, setAlerts] = useState<PriceAlert[]>([]);
  const [connectionState, setConnectionState] =
    useState<ConnectionState>("idle");

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectAttemptRef = useRef(0);
  const shouldReconnectRef = useRef(false);

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const addAlert = useCallback((event: AlertEvent) => {
    const payload = event.data;
    const alert: PriceAlert = {
      id: String(payload.history_id),
      productId: payload.product_id,
      historyId: payload.history_id,
      productName: payload.product_name,
      currentPrice: Number(payload.current_price),
      threshold: Number(payload.threshold),
      targetUrl: payload.target_url,
      timestamp: payload.timestamp,
    };

    setAlerts((current) => {
      if (current.some((item) => item.id === alert.id)) return current;
      return [alert, ...current].slice(0, 50);
    });

    if (Notification.permission === "granted") {
      new Notification("Price threshold reached", {
        body: `${alert.productName}: ${alert.currentPrice}`,
      });
    }
  }, []);

  const connect = useCallback(() => {
    if (!accessToken || !shouldReconnectRef.current) return;

    if (
      socketRef.current?.readyState === WebSocket.OPEN ||
      socketRef.current?.readyState === WebSocket.CONNECTING
    ) {
      return;
    }

    setConnectionState("connecting");

    const url = `${getWebSocketBaseUrl()}/ws/alerts/?token=${encodeURIComponent(
      accessToken
    )}`;
    const socket = new WebSocket(url);
    socketRef.current = socket;

    socket.onopen = () => {
      reconnectAttemptRef.current = 0;
      setConnectionState("connected");
    };

    socket.onmessage = (message) => {
      try {
        const parsed: unknown = JSON.parse(message.data);
        if (isAlertEvent(parsed)) addAlert(parsed);
      } catch {
        // Ignore malformed external frames.
      }
    };

    socket.onerror = () => setConnectionState("error");

    socket.onclose = (event) => {
      socketRef.current = null;
      setConnectionState("disconnected");

      if (!shouldReconnectRef.current) return;
      if (event.code === 4401 || event.code === 4403) {
        shouldReconnectRef.current = false;
        return;
      }

      reconnectAttemptRef.current += 1;
      const delay = Math.min(
        1_000 * 2 ** (reconnectAttemptRef.current - 1),
        MAX_RECONNECT_DELAY_MS
      );

      clearReconnectTimer();
      reconnectTimerRef.current = window.setTimeout(connect, delay);
    };
  }, [accessToken, addAlert, clearReconnectTimer]);

  useEffect(() => {
    clearReconnectTimer();
    socketRef.current?.close();
    socketRef.current = null;

    if (!accessToken) {
      shouldReconnectRef.current = false;
      setConnectionState("idle");
      return;
    }

    shouldReconnectRef.current = true;
    connect();

    return () => {
      shouldReconnectRef.current = false;
      clearReconnectTimer();
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [accessToken, clearReconnectTimer, connect]);

  const dismissAlert = useCallback((alertId: string) => {
    setAlerts((current) => current.filter((item) => item.id !== alertId));
  }, []);

  return { alerts, connectionState, dismissAlert };
}
```

Request browser notification permission only from a user-clicked button.

---

# 10. Phase 6 — Channels, Redis, and Celery settings

Do not ping Redis during Django settings import. Do not silently fall back to an in-memory channel layer in production.

```python
DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() == "true"
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/1")
USE_IN_MEMORY_CHANNEL_LAYER = (
    os.getenv("USE_IN_MEMORY_CHANNEL_LAYER", "False").lower() == "true"
)

if DEBUG and USE_IN_MEMORY_CHANNEL_LAYER:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [REDIS_URL],
                "capacity": 1500,
                "expiry": 60,
            },
        }
    }

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 120
CELERY_TASK_SOFT_TIME_LIMIT = 90
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

CELERY_BEAT_SCHEDULE = {
    "orchestrate-scraping-every-four-hours": {
        "task": "trackers.tasks.orchestrate_scraping_pipeline",
        "schedule": 14_400.0,
    },
}
```

---

# 11. Phase 7 — SSRF protection

Because users submit arbitrary target URLs, the scraper must reject internal and private network destinations.

```python
import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeTargetUrlError(ScrapeError):
    pass


def validate_public_url(url: str) -> None:
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise UnsafeTargetUrlError("Unsupported URL scheme")

    if not parsed.hostname:
        raise UnsafeTargetUrlError("Missing hostname")

    if parsed.username or parsed.password:
        raise UnsafeTargetUrlError("Credentials in URLs are forbidden")

    addresses = socket.getaddrinfo(
        parsed.hostname,
        parsed.port or (443 if parsed.scheme == "https" else 80),
    )

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeTargetUrlError(
                "Target resolves to a non-public address"
            )
```

Also validate redirect targets. Do not allow Playwright to reach localhost, private subnets, link-local addresses, or cloud metadata endpoints.

---

# 12. Phase 8 — scraper extraction architecture

Recommended layout:

```text
backend/trackers/scraping/
├── __init__.py
├── browser.py
├── exceptions.py
├── result.py
├── registry.py
└── extractors/
    ├── __init__.py
    ├── base.py
    ├── json_ld.py
    ├── shopify.py
    ├── daraz.py
    └── generic.py
```

Priority order:

1. JSON-LD Product/Offer data
2. Shopify metadata
3. Domain-specific extractor
4. Structured itemprop metadata
5. Visible sale/current-price selectors
6. Generic fallback

Use `Decimal`, record currency, and avoid returning the first arbitrary number from a large text block.

Recommended additional fields:

```python
# PriceHistory
currency = models.CharField(max_length=3, default="PKR")
source = models.CharField(max_length=32, default="generic")
raw_price_text = models.CharField(max_length=255, blank=True)

# TrackedProduct
last_scrape_status = models.CharField(max_length=32, default="never")
last_scrape_error = models.TextField(blank=True)
consecutive_failures = models.PositiveIntegerField(default=0)
```

Do not store full page HTML by default.

---

# 13. Phase 9 — Docker Compose hardening

Keep the six real services: `web`, `frontend`, `db`, `redis`, `celery`, and `celery-beat`.

Reference Compose configuration:

```yaml
services:
  db:
    image: postgres:13-alpine
    restart: unless-stopped
    env_file: [.env]
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d ${DB_NAME}"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 10s

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  web:
    build: ./backend
    restart: unless-stopped
    env_file: [.env]
    command: ["daphne", "-b", "0.0.0.0", "-p", "8000", "core.asgi:application"]
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test:
        [
          "CMD-SHELL",
          "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health/', timeout=3)\""
        ]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 20s

  celery:
    build: ./backend
    restart: unless-stopped
    env_file: [.env]
    command: ["celery", "-A", "core", "worker", "--loglevel=INFO", "--concurrency=2"]
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

  celery-beat:
    build: ./backend
    restart: unless-stopped
    env_file: [.env]
    command: ["celery", "-A", "core", "beat", "--loglevel=INFO", "--pidfile="]
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

  frontend:
    build:
      context: ./frontend
      args:
        VITE_API_BASE_URL: ${VITE_API_BASE_URL}
        VITE_WS_BASE_URL: ${VITE_WS_BASE_URL}
    restart: unless-stopped
    ports:
      - "80:80"
    depends_on:
      web:
        condition: service_healthy

volumes:
  postgres_data:
  redis_data:
```

---

# 14. Phase 10 — health endpoint

Add a lightweight database and Redis health endpoint.

```python
from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from redis import Redis


@require_GET
def health_check(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()

    Redis.from_url(settings.REDIS_URL).ping()
    return JsonResponse({"status": "ok"})
```

Route:

```python
path("api/health/", health_check, name="health-check")
```

Return only a generic unhealthy response on errors; do not expose stack traces or connection details.

---

# 15. Phase 11 — Nginx WebSocket proxy

```nginx
location /api/ {
    proxy_pass http://web:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location /ws/ {
    proxy_pass http://web:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 60s;
    proxy_send_timeout 60s;
}
```

A single production domain with `/api/` and `/ws/` proxying is preferred.

---

# 16. Phase 12 — CI must run real tests

Replace `.github/workflows/ci.yml` with a workflow that builds, starts dependencies, checks migrations, runs backend tests, builds/lints the frontend, verifies Compose, and fails on errors.

```yaml
name: CI

on:
  push:
    branches: ["main"]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest

    env:
      DJANGO_SECRET_KEY: ci-only-secret-key
      DJANGO_DEBUG: "False"
      DB_NAME: scraper_test
      DB_USER: postgres
      DB_PASSWORD: postgres
      DB_HOST: db
      DB_PORT: "5432"
      REDIS_URL: redis://redis:6379/1
      REDIS_HOST: redis
      REDIS_PORT: "6379"
      ALLOWED_HOSTS: localhost,127.0.0.1,web
      CORS_ALLOWED_ORIGINS: http://localhost
      CSRF_TRUSTED_ORIGINS: http://localhost
      VITE_API_BASE_URL: http://localhost:8000/api/
      VITE_WS_BASE_URL: ws://localhost:8000

    steps:
      - uses: actions/checkout@v4

      - name: Build services
        run: docker compose build

      - name: Start dependencies and backend
        run: docker compose up -d db redis web

      - name: Django checks
        run: docker compose exec -T web python manage.py check

      - name: Check migrations
        run: docker compose exec -T web python manage.py makemigrations --check --dry-run

      - name: Backend tests
        run: docker compose exec -T web python manage.py test

      - name: Deployment checks
        run: docker compose exec -T web python manage.py check --deploy

      - name: Frontend install, lint, typecheck, and build
        run: |
          docker run --rm \
            -v "$PWD/frontend:/app" \
            -w /app \
            node:20-alpine \
            sh -c "npm ci && npm run lint && npm run typecheck && npm run build"

      - name: Full Compose startup
        run: docker compose up -d

      - name: Verify services
        run: docker compose ps

      - name: Logs
        if: always()
        run: docker compose logs --no-color

      - name: Shutdown
        if: always()
        run: docker compose down -v
```

Ensure `frontend/package.json` includes `lint`, `typecheck`, and `build` scripts.

---

# 17. Phase 13 — tests to add

## Backend scraper tests

Test:

1. Scrape creates history without transaction errors.
2. Previous above threshold/current below sends alert.
3. Unchanged below-threshold price sends no duplicate.
4. New lower below-threshold price sends another alert.
5. Current above threshold sends no alert.
6. Inactive product is skipped.
7. Missing product is skipped.
8. Parse failure retries and eventually fails.
9. Browser timeout retries.
10. Database failure does not emit an alert.

Mock network/browser calls. Do not scrape live websites in unit tests.

## WebSocket consumer tests

Use `channels.testing.WebsocketCommunicator` to test:

- missing token rejected
- invalid token rejected
- inactive user rejected
- valid user accepted
- correct user receives event
- another user does not receive event
- payload exactly matches version 1 schema

## API isolation tests

Verify user A cannot list, retrieve, update, delete, or analyze user B's trackers.

## Frontend tests

Mock WebSocket and test:

- environment-based URL
- encoded token
- valid event parsing
- invalid event ignored
- duplicate `history_id` ignored
- reconnect on temporary failure
- no reconnect after `4401`/`4403`
- no reconnect after logout/unmount

---

# 18. Phase 14 — Django security settings

For production behind correctly configured HTTPS:

```python
DEBUG = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
```

Parse environment lists safely:

```python
def env_list(name: str) -> list[str]:
    return [
        value.strip()
        for value in os.getenv(name, "").split(",")
        if value.strip()
    ]

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS")
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
```

Do not use wildcard CORS with credentials.

Add DRF throttling for login, registration, tracker creation, manual scrape actions, and anonymous traffic.

---

# 19. Phase 15 — validation and constraints

Validate tracker data:

- URL is public and HTTP/HTTPS.
- threshold is greater than zero.
- decimal precision is valid.
- product name length is bounded.
- request body cannot select another user.

```python
def perform_create(self, serializer):
    serializer.save(user=self.request.user)
```

Recommended constraints/indexes:

```python
class Meta:
    constraints = [
        models.CheckConstraint(
            condition=models.Q(notification_threshold__gt=0),
            name="tracked_product_threshold_gt_zero",
        ),
    ]
    indexes = [
        models.Index(fields=["user", "is_active"]),
        models.Index(fields=["last_scraped_at"]),
    ]
```

For history:

```python
models.Index(fields=["product", "-scraped_at"])
```

---

# 20. Phase 16 — logging and observability

Every scrape log should include product ID, task ID, attempt, target hostname, result status, price, duration, and error class.

Never log JWTs, passwords, authorization headers, database credentials, or full page HTML.

Replace `print()` with `logger.info`, `logger.warning`, or `logger.exception`.

Useful future metrics:

- scrape success/failure count
- scrape duration
- extraction failure rate
- queue depth
- alerts generated/delivered
- consecutive tracker failures

---

# 21. Phase 17 — deployment correctness

- Run migrations once before scaled deployments.
- Use `collectstatic` and Nginx or WhiteNoise.
- Store production secrets outside Git.
- Replace realistic example passwords with placeholders.
- Document PostgreSQL backup and restore.
- Test restore before calling the project production-ready.

---

# 22. README and portfolio corrections

Before all fixes are verified, use:

> A containerized multi-user e-commerce price-monitoring platform with scheduled Playwright scraping, historical analytics, user-defined thresholds, and WebSocket alert infrastructure.

After all acceptance tests pass, use:

> A production-oriented multi-user e-commerce price-monitoring platform that performs scheduled dynamic-page scraping, stores price history, and delivers real-time WebSocket notifications when products cross user-defined thresholds.

Do not call WebSocket a separate Docker service. Correct services are Django ASGI API, React frontend, PostgreSQL, Redis, Celery worker, and Celery Beat.

Do not say “price-drop alerts” unless previous prices are actually compared. Do not say “instant” until the ASGI-to-browser path is tested.

---

# 23. Commit plan

```text
fix: move scraper row locks into short atomic writes
feat: add threshold crossing and duplicate alert protection
fix: standardize websocket alert event schema
fix: serve django channels through daphne asgi
fix: make websocket frontend configuration production safe
chore: harden redis channels and celery settings
feat: add structured scraper extraction pipeline
chore: add service health checks and safe entrypoint
ci: execute backend tests and frontend checks
test: cover scraper transactions websocket delivery and isolation
docs: align readme and portfolio claims with implementation
```

---

# 24. Final validation commands

```bash
docker compose down -v
docker compose build --no-cache
docker compose up -d
docker compose ps

docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py check --deploy
docker compose exec -T web python manage.py makemigrations --check --dry-run
docker compose exec -T web python manage.py test

docker compose run --rm frontend npm run lint
docker compose run --rm frontend npm run typecheck
docker compose run --rm frontend npm run build

docker compose exec -T celery celery -A core inspect ping
```

Manual WebSocket acceptance:

1. Log in.
2. Confirm `/ws/alerts/` returns `101 Switching Protocols`.
3. Trigger a threshold alert.
4. Confirm one toast appears.
5. Confirm another user receives nothing.
6. Repeat the same price and confirm no duplicate.
7. Lower the price again and confirm one new alert.

---

# 25. Definition of done

The agent's final report must include:

- changed files
- migration names
- test output
- frontend build output
- Docker service status
- proof of WebSocket upgrade
- proof of user isolation
- proof duplicate alerts are prevented
- proof scrape retries are bounded
- proof CI runs tests
- updated README wording
- remaining risks and deferred work

Separate the report into `Completed`, `Verified`, `Deferred`, and `Known limitations`.

---

# 26. Deferred improvements

Do not implement these before the critical path works:

- email alerts
- mobile push
- single-use WebSocket tickets
- proxy rotation
- CAPTCHA handling
- browser pools
- Prometheus/Sentry
- Kubernetes
- horizontal scaling
- alert delivery receipts
- data-retention jobs

---

# 27. Critical path summary

1. Fix transaction placement.
2. Prevent duplicate alerts.
3. Standardize WebSocket schema.
4. Run Daphne ASGI.
5. Configure environment-based WebSocket URLs.
6. Require Redis in production.
7. Add migrations and health checks.
8. Run tests in CI.
9. Prove scrape-to-browser behavior.
10. Update README and portfolio claims.
