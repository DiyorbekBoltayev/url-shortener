"""Folders router smoke tests."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_list_folders_requires_auth(client):
    r = await client.get("/api/v1/folders")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_create_folder_requires_auth(client):
    r = await client.post("/api/v1/folders", json={"name": "x"})
    assert r.status_code == 401
