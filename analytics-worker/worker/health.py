"""aiohttp healthcheck server. Mounted on settings.health_port (default :9092).

Liveness: process alive.
Readiness: we flushed at least once recently (within STALE_AFTER seconds),
           OR we are still in the cold-start grace window.

Path: /-/healthy (per INTEGRATION_CONTRACT.md section 8 for workers).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from aiohttp import web

from .logging import get_logger
from .metrics import LAST_FLUSH_TS

log = get_logger(__name__)

STALE_AFTER_SEC = 60.0
COLD_START_GRACE_SEC = 120.0

_START_TS = time.time()


async def _healthz(_request: web.Request) -> web.Response:
    last = float(LAST_FLUSH_TS._value.get())  # type: ignore[attr-defined]
    now = time.time()
    if last == 0.0:
        if (now - _START_TS) < COLD_START_GRACE_SEC:
            return web.json_response({"status": "starting"}, status=200)
        return web.json_response(
            {"status": "no_flush_yet", "age_s": None}, status=503
        )
    age = now - last
    if age > STALE_AFTER_SEC:
        return web.json_response(
            {"status": "stale", "age_s": round(age, 2)}, status=503
        )
    return web.json_response({"status": "ok", "age_s": round(age, 2)}, status=200)


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/-/healthy", _healthz)
    app.router.add_get("/healthz", _healthz)  # alias
    return app


async def start_health_server(port: int) -> tuple[web.AppRunner, web.TCPSite]:
    app = build_app()
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    log.info("health_server_started", port=port)
    return runner, site


async def stop_health_server(runner: web.AppRunner) -> None:
    try:
        await runner.cleanup()
    except Exception:  # noqa: BLE001
        pass


async def _noop_forever() -> Any:  # pragma: no cover
    await asyncio.Event().wait()
