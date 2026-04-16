"""UTM templates router smoke tests."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_list_utm_templates_requires_auth(client):
    r = await client.get("/api/v1/utm-templates")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_create_utm_template_requires_auth(client):
    r = await client.post("/api/v1/utm-templates", json={"name": "x"})
    assert r.status_code == 401
