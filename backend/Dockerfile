# STAGE 1: Build wheels & dependencies
FROM python:3.11-slim AS builder

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install build dependencies
RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt


# STAGE 2: Final runtime
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium

# Install runtime dependencies
RUN apt-get update && apt-get install --no-install-recommends -y \
    chromium \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install wheels from builder stage
COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt && \
    rm -rf /wheels

# Create directory for static files
RUN mkdir -p /app/staticfiles

# Copy project files
COPY . .
RUN useradd --create-home --shell /usr/sbin/nologin appuser && \
    chown -R appuser:appuser /app && \
    chmod +x /app/docker-entrypoint.sh

USER appuser

EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "core.asgi:application"]
