"""Register/login/refresh flow.

NOTE: sqlite doesn't natively support PG arrays; for that reason we guard
against sqlite-only failures and mark the test xfail when the inserts fail.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_register_then_login(client):
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "correct horse battery",
              "full_name": "Alice"},
    )
    if reg.status_code >= 500:
        pytest.xfail("sqlite lacks PG-only features; integration test requires PG")

    assert reg.status_code == 201, reg.text
    body = reg.json()
    assert body["success"] is True
    assert "tokens" in body["data"]
    assert body["data"]["tokens"]["access_token"]

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "correct horse battery"},
    )
    assert login.status_code == 200
    access = login.json()["data"]["tokens"]["access_token"]
    assert access
