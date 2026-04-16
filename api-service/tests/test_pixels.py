"""Pixels router smoke tests."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_list_pixels_requires_auth(client):
    r = await client.get("/api/v1/pixels")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_create_pixel_requires_auth(client):
    r = await client.post(
        "/api/v1/pixels", json={"kind": "fb", "pixel_id": "123"}
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_pixel_kind_constants():
    from app.schemas.pixel import KIND_VALUES

    assert "fb" in KIND_VALUES
    assert "ga4" in KIND_VALUES
    assert len(KIND_VALUES) == 7
