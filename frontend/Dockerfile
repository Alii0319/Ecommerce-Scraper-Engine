# Stage 1: Build React/Vite App
FROM node:22-alpine AS builder

WORKDIR /app

# Optimize caching by copying lock files first
COPY package.json package-lock.json* yarn.lock* pnpm-lock.yaml* ./

RUN \
  if [ -f yarn.lock ]; then yarn --frozen-lockfile; \
  elif [ -f package-lock.json ]; then npm ci; \
  elif [ -f pnpm-lock.yaml ]; then corepack enable pnpm && pnpm i --frozen-lockfile; \
  else npm install; \
  fi

COPY . .

# --- ADDED: Vite Build Arguments (Relative paths for K8s Ingress) ---
ARG VITE_API_BASE_URL=/api
ARG VITE_WS_BASE_URL=/ws
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_WS_BASE_URL=$VITE_WS_BASE_URL

# Run type check and Vite build
RUN npm run build


# Stage 2: Production Web Server (Unprivileged Non-Root Nginx)
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runner

# Copy custom Nginx configuration (replace default site config)
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy static assets from build stage
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8080/ || exit 1

CMD ["nginx", "-g", "daemon off;"]