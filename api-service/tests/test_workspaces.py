"""Workspaces router smoke tests."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_list_my_workspaces_requires_auth(client):
    r = await client.get("/api/v1/workspaces/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_switch_workspace_requires_auth(client):
    r = await client.post(
        "/api/v1/auth/switch-workspace",
        json={"workspace_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert r.status_code == 401
