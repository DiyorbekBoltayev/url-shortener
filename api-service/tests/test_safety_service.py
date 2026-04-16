"""Safety classifier — heuristic-backend smoke tests."""
from __future__ import annotations

import pytest

from app.config import settings
from app.services import safety_service


@pytest.mark.asyncio
async def test_heuristic_denylist_warns(monkeypatch):
    monkeypatch.setattr(settings, "safety_provider", "heuristic")
    monkeypatch.setattr(
        settings, "safety_denylist_domains", ["phishing.example"]
    )
    verdict = await safety_service.scan("https://phishing.example/login")
    assert verdict.status == "warn"
    assert "denylist" in verdict.reason


@pytest.mark.asyncio
async def test_heuristic_denylist_subdomain_match(monkeypatch):
    monkeypatch.setattr(settings, "safety_provider", "heuristic")
    monkeypatch.setattr(
        settings, "safety_denylist_domains", ["phishing.example"]
    )
    v = await safety_service.scan("https://foo.phishing.example/x")
    assert v.status == "warn"


@pytest.mark.asyncio
async def test_heuristic_userinfo_warns(monkeypatch):
    monkeypatch.setattr(settings, "safety_provider", "heuristic")
    monkeypatch.setattr(settings, "safety_denylist_domains", [])
    v = await safety_service.scan("https://evil@bank.example/")
    assert v.status == "warn"
    assert "userinfo" in v.reason


@pytest.mark.asyncio
async def test_heuristic_ip_literal_warns(monkeypatch):
    monkeypatch.setattr(settings, "safety_provider", "heuristic")
    monkeypatch.setattr(settings, "safety_denylist_domains", [])
    v = await safety_service.scan("http://203.0.113.9/login")
    assert v.status == "warn"
    assert "ip_literal" in v.reason


@pytest.mark.asyncio
async def test_heuristic_clean_url(monkeypatch):
    monkeypatch.setattr(settings, "safety_provider", "heuristic")
    monkeypatch.setattr(settings, "safety_denylist_domains", [])
    v = await safety_service.scan("https://example.com/about")
    assert v.status == "ok"


@pytest.mark.asyncio
async def test_provider_none_always_ok(monkeypatch):
    monkeypatch.setattr(settings, "safety_provider", "none")
    v = await safety_service.scan("https://phishing.example/login")
    assert v.status == "ok"
