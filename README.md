# E-Commerce Scraper Engine

A production-oriented multi-user e-commerce price-monitoring platform built with Django REST Framework, React, PostgreSQL, Redis, Celery, Django Channels and Playwright.

## Tech Stack

| Component | Technology | Version / Specification |
| :--- | :--- | :--- |
| **Backend Framework** | Django | v4.2.30 LTS |
| **API Architecture** | Django REST Framework | v3.17.1 |
| **Real-time Server** | Django Channels + Daphne | Channels v4.3.2 / Daphne v4.2.2 |
| **Task Queue** | Celery | v5.6.3 |
| **Database** | PostgreSQL | Docker image `postgres:13-alpine` |
| **Message Broker & Cache** | Redis | Docker image `redis:7-alpine` / Python client v8.0.1 |
| **HTML Parser** | BeautifulSoup4 | v4.15.0 |
| **Headless Browser** | Playwright + Chromium | Playwright v1.61.0 / system Chromium in Docker |
| **Frontend Core** | React | v19.2.7 |
| **Frontend Builder** | Vite | v6.4.3 |
| **Styles** | TailwindCSS & PostCSS | TailwindCSS v3.4.19 |
| **Charts** | Recharts | v2.15.4 |
| **HTTP Client** | Axios | v1.18.1 |

## Architecture

The stack consists of 7 services:
1. `migrate` - Dedicated single-owner database migration and static collection service
2. `web` - ASGI server (Daphne) serving REST APIs and WebSockets
3. `frontend` - Nginx serving the React SPA and proxying /api/ and /ws/ requests
4. `db` - PostgreSQL database
5. `redis` - Redis for Channels layer, Celery broker, and WebSocket ticket caching
6. `celery` - Background workers for executing scraping tasks
7. `celery-beat` - Periodic task scheduler

## Features

- **Multi-Source E-Commerce Scraping**: Crawls target product URLs using BeautifulSoup4 and Playwright (Chromium) to support dynamic pages.
- **Scheduled Scraping**: Orchestrates periodic inventory scans every 4 hours using Celery Workers and Beat.
- **Historical Records**: Maintains a detailed history of all price changes and product availability.
- **Three Alert Semantics**: Dispatches `threshold_reached`, `new_lower_price`, and general `price_drop` alerts.
- **Durable Alert Outbox**: Uses a persistent PostgreSQL outbox pattern to ensure reliable alert delivery even during worker crashes.
- **Browser Acknowledgement**: Requires explicit acknowledgement from the frontend to mark an alert as fully acknowledged, preventing lost alerts.
- **Redis/Channels Publishing**: Uses Django Channels backed by Redis to deliver real-time messages to connected clients.
- **Secure Authentication**: User-isolated APIs and WebSockets. WebSockets are authenticated using single-use, 30-second Redis-backed tickets.
- **SSRF Protection**: Defends against Server-Side Request Forgery with strict target hostname validation.
- **Health Probes**: Dedicated liveness (`/api/health/live/`) and readiness (`/api/health/ready/`) endpoints for container orchestration.
- **Comprehensive CI**: Backend, frontend, security, integration, and Playwright E2E checks run automatically.

## Setup

### 🐧 Linux/macOS

1. **Clone and Enter Directory**:
   ```bash
   git clone <repository_url> ecommerce-scraper-engine
   cd ecommerce-scraper-engine
   ```

2. **Configure Environment Variables**:
   Create a `.env` file from the `.env.example` template:
   ```bash
   cp .env.example .env
   ```
   *Ensure you use secure placeholders for secrets (e.g. `DB_PASSWORD=replace-with-a-strong-password`).*

3. **Backend Virtual Environment & Dependencies**:
   ```bash
   cd backend
   python3.11 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   playwright install chromium
   ```

4. **Frontend Setup**:
   ```bash
   cd ../frontend
   npm install
   npm run dev
   ```

## Docker Instructions

A multi-container Docker development workspace is configured via the `docker-compose.yml` file.

To control the container stack:

```bash
# Build and start all services in the background
docker compose up --build -d
```

> **Note**: The dedicated `migrate` service runs and completes database migrations before any application services (`web`, `celery`, `celery-beat`) start.

### Health Endpoints

Docker uses the following endpoints to determine service health:
- Liveness check: `/api/health/live/` (checks process health)
- Readiness check: `/api/health/ready/` (verifies DB and Redis connectivity)

## WebSocket Authentication

The system uses a highly secure ticketing system for WebSockets:
1. The authenticated frontend requests a ticket via `POST /api/auth/ws-ticket/`
2. The server issues a short-lived ticket that lasts 30 seconds
3. The ticket is single-use and atomically consumed upon connection
4. The WebSocket connects using `wss://api.example.com/ws/alerts/?ticket=<ticket>`
5. JWT tokens are never placed in WebSocket URLs or query strings.

## Alert Lifecycle State

Price alerts transition through the following states:
- `pending`: Waiting to be picked up by the delivery task
- `processing`: Currently being delivered via Channels
- `published`: Sent to Channels but not yet acknowledged by the browser
- `acknowledged`: Successfully received and explicitly acknowledged by the frontend
- `failed`: Failed to deliver after maximum retries

## Running Tests

### Backend Tests
```bash
docker compose exec -T web python manage.py test
```

### Frontend Tests
```bash
docker compose run --rm frontend npm run test -- --run
```

### Build & Lint
```bash
docker compose run --rm frontend npm run lint
docker compose run --rm frontend npm run typecheck
docker compose run --rm frontend npm run build
```

### End-to-End (E2E) Tests
```bash
docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d --build
cd e2e
npm ci
npx playwright test
```

### Security Audits
```bash
pip-audit
npm audit --audit-level=high
```
