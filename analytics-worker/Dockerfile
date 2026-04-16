# syntax=docker/dockerfile:1.7
# =========================================================
# Stage 1: Build virtualenv with uv.
# =========================================================
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy

# Build deps (gcc for any sdists — clickhouse-connect / hiredis wheels exist
# but keep gcc for safety on non-amd64 archs).
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock* README.md* ./

# Install deps straight via uv pip (bypasses project build; resilient to missing README/src).
RUN uv venv /opt/venv \
    && . /opt/venv/bin/activate \
    && uv pip install \
        "redis[hiredis]==5.2.1" \
        "clickhouse-connect==0.8.17" \
        "geoip2==5.2.0" \
        "ua-parser[regex]==1.0.1" \
        "structlog==24.4.0" \
        "prometheus-client==0.21.1" \
        "pydantic==2.10.4" \
        "pydantic-settings==2.7.0" \
        "orjson==3.10.12" \
        "tenacity==9.0.0" \
        "aiohttp==3.11.11" \
        "uvloop==0.21.0; sys_platform != 'win32'"

# =========================================================
# Stage 2: Runtime.
# =========================================================
FROM python:3.12-slim-bookworm AS runtime

RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app

# RV10 2.1: chown the venv so the non-root `app` user can write __pycache__
# entries instead of silently falling back to in-memory / read-only cache.
COPY --from=builder --chown=app:app /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY --chown=app:app worker ./worker

USER app

# Metrics on 9091, /-/healthy on 9092.
EXPOSE 9091 9092

# Use /-/healthy (per INTEGRATION_CONTRACT.md section 8).
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; \
  r=urllib.request.urlopen('http://localhost:9092/-/healthy', timeout=2); \
  sys.exit(0 if r.status==200 else 1)" || exit 1

CMD ["python", "-m", "worker.main"]
