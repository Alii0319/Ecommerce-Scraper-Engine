# syntax=docker/dockerfile:1.7

# ---------- Stage 1: Builder (Wheel Generation) ----------
FROM python:3.13-slim-bookworm AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip wheel --wheel-dir /build/wheels -r requirements.txt


# ---------- Stage 2: Runner (Production Runtime) ----------
FROM python:3.13-slim-bookworm AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install runtime system packages and tini for process management
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Dedicated non-root user setup
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

WORKDIR /app

# Copy requirements text and install compiled wheels
COPY requirements.txt /app/requirements.txt
COPY --from=builder /build/wheels /wheels

RUN pip install --upgrade pip && \
    pip install --no-cache-dir --no-index --find-links /wheels -r /app/requirements.txt && \
    rm -rf /wheels

# Optional Playwright Chromium install
ARG INSTALL_PLAYWRIGHT=false
RUN if [ "$INSTALL_PLAYWRIGHT" = "true" ]; then \
      playwright install-deps chromium && \
      playwright install chromium-headless-shell; \
    fi && \
    mkdir -p /app/staticfiles /ms-playwright && \
    chown -R appuser:appgroup /app /ms-playwright

# Copy project source code and entrypoint script
COPY --chown=appuser:appgroup . /app
COPY --chown=appuser:appgroup ./docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER appuser

# Collect static assets for WhiteNoise production serving
RUN DJANGO_DEBUG=True python manage.py collectstatic --noinput --clear

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health/live/ || exit 1

# Tini passes OS signals correctly and prevents zombie processes
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/docker-entrypoint.sh"]

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "core.asgi:application"]