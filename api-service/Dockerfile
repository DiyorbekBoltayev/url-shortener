# syntax=docker/dockerfile:1.7
# ------------------------------------------------------------
# Stage 1 — builder (uv + wheel cache)
# ------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /usr/local/bin/

WORKDIR /app

# ---- Resolve deps first (cache layer) ----------------------
COPY pyproject.toml README.md ./
# Optional lockfile
COPY uv.loc[k] ./
RUN uv venv /opt/venv \
    && . /opt/venv/bin/activate \
    && uv sync --no-dev || uv pip install --python /opt/venv/bin/python -e .

# ---- Copy source + final sync -----------------------------
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN . /opt/venv/bin/activate && uv pip install --python /opt/venv/bin/python -e . --no-deps

# ------------------------------------------------------------
# Stage 2 — runtime (slim, non-root)
# ------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
        tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --create-home --home-dir /home/app app

COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --from=builder --chown=app:app /app      /app

WORKDIR /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--proxy-headers", "--forwarded-allow-ips", "*", \
     "--log-config", "app/log_config.json"]
