# Completed Tasks Log

This file records the completed remediation phases for the next agent or reviewer.

## Phase 0: Baseline & Safety Setup
- **Completed At**: 2026-07-21
- **Branch**: `fix/production-readiness`
- **Actions Taken**:
  - Checked out working branch `fix/production-readiness`.
  - Created `.env.local.backup`.
  - Verified backend Django system checks (`0 issues`) and test suite (`12 tests passed`).
  - Created `docs/baseline.md` documenting baseline metrics and initial issues.

## Phase 1: Fix Scraper Transaction Bug
- **Completed At**: 2026-07-21
- **Actions Taken**:
  - Refactored `backend/trackers/tasks.py` to move Playwright browser execution outside database transactions.
  - Placed `TrackedProduct.objects.select_for_update()` inside a short atomic transaction.
  - Used `transaction.on_commit` for WebSocket alert dispatching post-commit.

## Phase 2: Prevent Duplicate Alerts
- **Completed At**: 2026-07-21
- **Actions Taken**:
  - Added `last_alerted_price` and `last_alerted_at` fields to `TrackedProduct` model in `backend/trackers/models.py`.
  - Created and applied migration `trackers/migrations/0002_trackedproduct_last_alerted_at_and_more.py`.
  - Implemented state comparison logic in `should_send_threshold_alert` to prevent repeated notifications for unchanged below-threshold prices.

## Phase 3: Standardize WebSocket Contract
- **Completed At**: 2026-07-21
- **Actions Taken**:
  - Updated `backend/trackers/consumers.py` to enforce authentication via simplejwt AccessToken.
  - Standardized alert message payload format to version 1 JSON schema (`price_threshold_alert`).
  - Handled token validation errors gracefully (closing connection with status 4401/4403).

## Phase 4: Serve Django Through ASGI & Entrypoint
- **Completed At**: 2026-07-21
- **Actions Taken**:
  - Updated `backend/Dockerfile` entrypoint and CMD to run `daphne -b 0.0.0.0 -p 8000 core.asgi:application`.
  - Configured `backend/docker-entrypoint.sh` for database readiness wait and automatic migration execution.

## Phase 5: Production-Safe Frontend WebSocket Hook
- **Completed At**: 2026-07-21
- **Actions Taken**:
  - Refactored `frontend/src/hooks/useWebSocketAlerts.ts` with environment-based URL resolution (`VITE_WS_BASE_URL` fallback to `ws://` / `wss://`).
  - Added strict `isAlertEvent` type guard matching v1 schema.
  - Implemented exponential backoff reconnects up to 30s, stopping reconnects on 4401/4403 auth errors.
  - Created `frontend/.env.example` and verified frontend typecheck and production build (`0 errors`).

## Phase 6: Harden Channels & Redis Configuration
- **Completed At**: 2026-07-21
- **Actions Taken**:
  - Removed synchronous Redis ping on settings load in `backend/core/settings.py`.
  - Added support for `USE_IN_MEMORY_CHANNEL_LAYER` opt-in during local dev testing.
  - Added bounded Celery task limits (`CELERY_TASK_TIME_LIMIT=120`, `CELERY_WORKER_PREFETCH_MULTIPLIER=1`, late ACKs).

## Phase 7: Add SSRF Protection
- **Completed At**: 2026-07-21
- **Actions Taken**:
  - Created `backend/trackers/scraping/validator.py` with `validate_public_url(url)`.
  - Enforced scheme restrictions (HTTP/HTTPS), hostname requirement, credential prohibition, and IP resolution checks blocking private, loopback, link-local, and reserved IP ranges.

## Phase 8: Scraper Extraction Architecture
- **Completed At**: 2026-07-21
- **Actions Taken**:
  - Modularized scraper architecture into `backend/trackers/scraping/`.
  - Created prioritised extraction pipeline: `JSONLDExtractor`, `ShopifyExtractor`, `DarazExtractor`, `GenericExtractor`.
  - Integrated `validate_public_url` into Playwright page retrieval in `browser.py`.
  - Updated `backend/trackers/tasks.py` to use modularized scraping package.

## Phase 9: Docker Compose & Infrastructure Hardening
- **Completed At**: 2026-07-21
- **Actions Taken**:
  - Added container healthchecks for `db` (pg_isready), `redis` (redis-cli ping), and `web` (http health endpoint).
  - Enforced `condition: service_healthy` across dependent services (`web`, `celery`, `celery-beat`, `frontend`).
  - Added build ARGs `VITE_API_BASE_URL` and `VITE_WS_BASE_URL` to `frontend/Dockerfile`.

## Phase 10: Health Endpoint
- **Completed At**: 2026-07-21
- **Actions Taken**:
  - Implemented `health_check` endpoint in `backend/trackers/views.py`.
  - Added route `/api/health/` in `backend/core/urls.py`.
  - Returns `200 OK` on active DB & Redis connectivity; `530` / `503` on failure.

## Phase 11: Nginx Configuration
- **Completed At**: 2026-07-21
- **Actions Taken**:
  - Updated `frontend/nginx.conf` with reverse proxy rules for `/api/` (HTTP/1.1) and `/ws/` (WebSocket Upgrade/Connection headers).
