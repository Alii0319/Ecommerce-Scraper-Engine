# E-Commerce Scraper Engine

A production-grade web scraping and analytics engine that tracks e-commerce product pricing in real-time, displays historical trends, and dispatches instant price-drop alerts.

## Tech Stack

| Component | Technology | Version / Specification |
| :--- | :--- | :--- |
| **Backend Framework** | Django | v5.0.14 |
| **API Architecture** | Django REST Framework | v3.17.1 |
| **Real-time Server** | Django Channels (Daphne) | v4.3.2 |
| **Task Queue** | Celery | v5.6.3 |
| **Database** | PostgreSQL | v13 |
| **Message Broker & Cache** | Redis | v6 |
| **HTML Parser** | BeautifulSoup4 | v4.15.0 |
| **Headless Browser** | Playwright (Chromium) | v1.61.0 |
| **Frontend Core** | React | v19.1.0 |
| **Frontend Builder** | Vite | v6.0.3 |
| **Styles** | TailwindCSS & PostCSS | v3.4.16 |
| **Charts** | Recharts | v2.9.0 |
| **HTTP Client** | Axios | v1.7.2 |

## Features

- **Multi-Source E-Commerce Scraping**: Crawls target product URLs using BeautifulSoup4 and Playwright (Chromium) to retrieve dynamic, fully-rendered HTML DOM structures.
- **Robust Price Extraction Logic**: Employs reliable Shopify metadata scrapers (`og:price:amount`, `product:price:amount`, etc.) with flexible fallbacks to generic CSS/HTML selectors.
- **Real-Time Price-Drop Alerts**: Delivers instantaneous desktop notifications and UI toasts using Django Channels WebSockets when a product's price drops to or below a user's defined threshold.
- **Automated Scraping Scheduler**: Orchestrates periodic inventory scans every 4 hours using Celery Workers and a Celery Beat schedule.
- **Interactive Price Analytics**: Visualizes historical price trends and tracker statistics on a dashboard powered by React and Recharts.
- **Secure Token Authentication**: Implements JSON Web Token (JWT) credentials (via SimpleJWT) with automatic request queuing and token refresh interception inside Axios.

## Prerequisites

Ensure the following software is installed on your system with the exact versions (or compatible ranges) matching the codebase:
- **Python**: `v3.11.x`
- **Node.js**: `v20.x` (LTS) and **npm** `v10.x`
- **PostgreSQL**: `v13`
- **Redis**: `v6`
- **Docker**: `v20.10+` and **Docker Compose** `v2.0+`

## Setup

### 🐧 Linux/macOS

1. **Clone and Enter Directory**:
   ```bash
   git clone <repository_url> ecommerce-scraper-engine
   cd ecommerce-scraper-engine
   ```

2. **Configure Environment Variables**:
   Create a `.env` file in the root directory from the provided `.env.example` template and copy it to the `backend/` directory:
   ```bash
   cp .env.example .env
   cp .env backend/.env
   ```
   *Note: Ensure `DB_HOST` and `REDIS_HOST` are set to `127.0.0.1` if running services natively, or keep `db` and `redis` if running services through Docker.*

3. **Backend Virtual Environment & Dependencies**:
   ```bash
   cd backend
   python3.11 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Install Playwright Browsers**:
   ```bash
   playwright install chromium
   playwright install-deps chromium
   ```

5. **Run Migrations & Start Server**:
   Ensure your local PostgreSQL database is running (configured on the port matching `DB_PORT` in your backend `.env`, standard `5432` or host-mapped `5433`).
   ```bash
   python manage.py migrate
   python manage.py runserver
   ```

6. **Start Celery Asynchronous Workers**:
   In separate shell instances (with the virtual environment activated):
   - **Celery Worker**:
     ```bash
     celery -A core worker --loglevel=info
     ```
   - **Celery Beat**:
     ```bash
     celery -A core beat --loglevel=info
     ```

7. **Frontend Setup**:
   Open a new terminal session and run:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   Open `http://localhost:5173` in your browser.

---

### 🪟 Windows

1. **Clone and Enter Directory**:
   ```powershell
   git clone <repository_url> ecommerce-scraper-engine
   cd ecommerce-scraper-engine
   ```

2. **Configure Environment Variables**:
   Create a `.env` file in the root directory from the `.env.example` template and copy it to `backend\`:
   ```powershell
   copy .env.example .env
   copy .env backend\.env
   ```

3. **Backend Setup**:
   ```powershell
   cd backend
   python -m venv venv
   # For PowerShell:
   .\venv\Scripts\Activate.ps1
   # For Command Prompt:
   .\venv\Scripts\activate.bat
   
   pip install --upgrade pip
   pip install -r requirements.txt
   playwright install chromium
   ```

4. **Run Migrations & Start Server**:
   ```powershell
   python manage.py migrate
   python manage.py runserver
   ```

5. **Redis & Celery Scheduler Note**:
   > [!WARNING]
   > Redis and Celery are not officially supported natively on Windows and are complex to configure and run. It is strongly recommended to run these components using **WSL2 (Windows Subsystem for Linux)** or via **Docker**.
   
   To run them on Windows via WSL2:
   - Install Ubuntu on WSL2.
   - Install Redis: `sudo apt-get install redis-server` and run it: `sudo service redis-server start`.
   - Run Celery workers inside the WSL2 terminal environment.

6. **Frontend Setup**:
   ```powershell
   cd ..\frontend
   npm install
   npm run dev
   ```

## Environment Variables

The system retrieves environment variables from a `.env` file located in the root/backend directories.

| Variable Name | Description | Example Value |
| :--- | :--- | :--- |
| `DJANGO_SECRET_KEY` | Secret key used for cryptographic signing in Django | `django-insecure-prod-grade-secret-key-2026` |
| `DJANGO_DEBUG` | Enables/disables debug mode (set to `False` in production) | `True` |
| `DB_NAME` | Relational datastore database name | `scraper_db` |
| `DB_USER` | Relational datastore database username | `postgres` |
| `DB_PASSWORD` | Relational datastore database password | `12345678` |
| `DB_HOST` | Database host name (`db` for Docker Compose, `127.0.0.1` local) | `db` |
| `DB_PORT` | Database connection port (`5432` internal, `5433` host-mapped) | `5432` |
| `REDIS_HOST` | Host address of Redis server (`redis` for Docker Compose, `127.0.0.1` local) | `redis` |
| `REDIS_PORT` | Port address of Redis server | `6379` |
| `REDIS_URL` | Full Redis connection string used for Channels and Celery | `redis://redis:6379/1` |
| `ALLOWED_HOSTS` | Comma-separated list of hostnames this Django application serves | `localhost,127.0.0.1` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated list of web origins permitted to request backend APIs | `http://localhost:5173,http://localhost:80` |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated list of origins trusted for CSRF protection checks | `http://localhost:5173,http://localhost:80` |
| `TIME_ZONE` | Standard localization timezone for Celery scheduling tasks | `UTC` |
| `VITE_API_BASE_URL` | Frontend target URL for connecting to the Django API | `http://127.0.0.1:8000/api/` |

## Docker Instructions

A multi-container Docker development workspace is configured via the `docker-compose.yml` file.

To control the container stack:

```bash
# Build and start all services in the background (web, frontend, db, redis, celery, celery-beat)
docker compose up --build -d

# Check the live status logs of all running services
docker compose logs -f

# Run database migrations manually inside the web container (normally run by docker-entrypoint.sh)
docker compose exec web python manage.py migrate

# Stop and tear down the container services
docker compose down

# Stop and tear down services, removing all named volume data (wipes the database volume)
docker compose down -v
```

## Running Tests

The test suite validates authentication, API operations, custom models, and database price metrics logs.

Run backend tests using:

```bash
cd backend

# Option A: Run using pytest (recommended)
pytest

# Option B: Run using Django's default test runner
python manage.py test
```

## Project Structure

```
ecommerce-scraper-engine/
├── backend/
│   ├── analytics/         # Analytics views for tracking counts and latest prices
│   ├── authentication/    # Custom User identity models and JWT serializers
│   ├── core/              # Main routing urls, ASGI/WSGI, settings, and Celery setup
│   ├── trackers/          # Scraping engines (Playwright/BS4), tasks, models, and WS consumers
│   ├── Dockerfile         # Docker recipe for Django/Celery execution environment
│   ├── manage.py          # Command-line utility for administrative tasks
│   └── requirements.txt   # Python dependency list
├── frontend/
│   ├── src/               # React application, components, custom hooks, and API services
│   ├── Dockerfile         # Production builder and Nginx distribution setup
│   ├── nginx.conf         # Nginx reverse proxy configuration for static files
│   ├── package.json       # Node scripts and library dependencies
│   ├── tailwind.config.js # Styling configurations for Tailwind utility classes
│   └── tsconfig.json      # TypeScript build rules
├── docker-compose.yml     # Docker Compose orchestration file
├── .env                   # Local configuration environment settings file
└── .env.example           # Template environment configuration file
```

