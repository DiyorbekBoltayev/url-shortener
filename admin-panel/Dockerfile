# syntax=docker/dockerfile:1.7
# ---- build stage ----
FROM node:20-alpine AS builder
WORKDIR /app

# Install deps with deterministic lockfile. Accept fallback to `npm install`
# on first image build if lockfile is absent (host may not have run npm yet).
COPY package*.json ./
RUN --mount=type=cache,target=/root/.npm \
    (npm ci --no-audit --no-fund || npm install --no-audit --no-fund)

COPY . .

ARG BUILD_CONFIG=production
RUN npm run build -- --configuration=${BUILD_CONFIG}

# ---- runtime stage ----
# RV10 2.3: use `nginx-unprivileged`, which runs as uid 101 and listens on 8080
# by default. This avoids running the SPA container as root just to bind :80.
FROM nginxinc/nginx-unprivileged:1.25-alpine AS runtime

# Running as root here is fine — USER is set back to `nginx` before CMD.
USER root
RUN rm -f /etc/nginx/conf.d/default.conf

# nginx.conf must `listen 8080;` (not 80) — the base image is not privileged.
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Angular 19 esbuild output lives at dist/<project>/browser/
COPY --from=builder --chown=nginx:nginx /app/dist/admin-panel/browser /usr/share/nginx/html

# Drop privileges for runtime.
USER nginx

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD wget -q --spider http://localhost:8080/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
