"""Bulk jobs router smoke tests."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_list_jobs_requires_auth(client):
    r = await client.get("/api/v1/bulk-jobs")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_export_requires_auth(client):
    r = await client.post("/api/v1/links/export", json={})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_bulk_patch_requires_auth(client):
    r = await client.post(
        "/api/v1/links/bulk-patch",
        json={
            "ids": ["00000000-0000-0000-0000-000000000000"],
            "patch": {"is_active": False},
        },
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_routing_rules_schema_validates():
    """RoutingRules must require at least one of ab/device/geo and
    reject ab weights that don't sum to 100."""
    from pydantic import ValidationError

    from app.schemas.url import ABRule, RoutingRules

    with pytest.raises(ValidationError):
        RoutingRules()
    with pytest.raises(ValidationError):
        RoutingRules(
            ab=[
                ABRule(url="https://a", weight=40),
                ABRule(url="https://b", weight=40),
            ]
        )
    # Exact 100 — ok.
    rr = RoutingRules(
        ab=[
            ABRule(url="https://a", weight=50),
            ABRule(url="https://b", weight=50),
        ]
    )
    assert rr.ab and len(rr.ab) == 2
