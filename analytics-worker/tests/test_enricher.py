"""Enricher tests — static fixtures only, no network."""
from __future__ import annotations

from worker.enricher import Enricher
from worker.geoip import Geo, GeoIPReader


class _StubGeo(GeoIPReader):
    """GeoIPReader without a real mmdb."""

    def __init__(self, geo: Geo | None = None):
        self._reader = None
        self._path = ""
        self._geo = geo or Geo(None, None, None, None, None, None)

    def lookup(self, ip: str) -> Geo:  # type: ignore[override]
        if not ip:
            return Geo(None, None, None, None, None, None)
        return self._geo

    def close(self) -> None:
        pass


def test_enrich_full_browser_payload():
    enricher = Enricher(
        _StubGeo(Geo("US", "United States", "California", "San Francisco", 37.77, -122.41))
    )
    fields = {
        b"code": b"aB3xK9",
        b"ts": b"1728345600000",
        b"ip": b"8.8.8.8",
        b"ua": (
            b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            b"(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        b"ref": b"https://www.google.com/search?q=foo",
        b"country": b"US",
    }
    row = enricher.enrich(fields)
    assert row.short_code == "aB3xK9"
    assert row.country_code == "US"
    assert row.city == "San Francisco"
    assert row.region == "California"
    assert row.lat == 37.77
    assert row.lon == -122.41
    assert row.ua_browser == "Chrome"
    assert row.ua_os == "Windows"
    assert row.ua_device == "desktop"
    assert row.is_bot == 0
    assert row.referer_domain == "www.google.com"
    assert row.referer_type == "search"
    assert row.ip_hash and len(row.ip_hash) == 32  # blake2b 16 bytes -> 32 hex


def test_enrich_bot_payload():
    enricher = Enricher(_StubGeo())
    fields = {
        b"code": b"bot01",
        b"ts": b"1728345600000",
        b"ip": b"66.249.66.1",
        b"ua": b"Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        b"ref": b"",
        b"country": b"US",
    }
    row = enricher.enrich(fields)
    assert row.is_bot == 1
    assert row.referer_type == "direct"
    assert row.referer_domain == ""


def test_enrich_missing_ts_falls_back_to_now():
    enricher = Enricher(_StubGeo())
    fields = {
        b"code": b"a",
        b"ts": b"",
        b"ip": b"",
        b"ua": b"",
        b"ref": b"",
    }
    row = enricher.enrich(fields)
    assert row.short_code == "a"
    # event_time should be timezone-aware
    assert row.event_time.tzinfo is not None


def test_enrich_social_referer():
    enricher = Enricher(_StubGeo())
    fields = {
        b"code": b"x",
        b"ts": b"1728345600000",
        b"ip": b"",
        b"ua": b"Mozilla/5.0",
        b"ref": b"https://t.co/abc",
        b"country": b"",
    }
    row = enricher.enrich(fields)
    assert row.referer_domain == "t.co"
    assert row.referer_type == "social"


def test_enrich_other_referer():
    enricher = Enricher(_StubGeo())
    fields = {
        b"code": b"x",
        b"ts": b"1728345600000",
        b"ip": b"",
        b"ua": b"Mozilla/5.0",
        b"ref": b"https://example.com/path",
        b"country": b"",
    }
    row = enricher.enrich(fields)
    assert row.referer_domain == "example.com"
    assert row.referer_type == "other"


def test_enrich_handles_str_keys():
    """Real redis-py returns bytes, but tests/fake redis may use str."""
    enricher = Enricher(_StubGeo())
    fields = {
        "code": "a1",
        "ts": "1728345600000",
        "ip": "1.2.3.4",
        "ua": "Mozilla/5.0 (X11; Linux x86_64) Chrome/120",
        "ref": "",
        "country": "",
    }
    row = enricher.enrich(fields)
    assert row.short_code == "a1"


def test_ip_hash_stable():
    enricher = Enricher(_StubGeo())
    f = {
        b"code": b"a",
        b"ts": b"1728345600000",
        b"ip": b"8.8.8.8",
        b"ua": b"Mozilla/5.0",
        b"ref": b"",
    }
    h1 = enricher.enrich(f).ip_hash
    h2 = enricher.enrich(f).ip_hash
    assert h1 == h2
    assert h1 != ""


def test_as_tuple_length_matches_cols():
    from worker.writer import COLS

    enricher = Enricher(_StubGeo())
    row = enricher.enrich(
        {b"code": b"a", b"ts": b"1728345600000", b"ip": b"1.1.1.1", b"ua": b"Mozilla/5.0"}
    )
    # +1 for stream_id appended in writer
    assert len(row.as_tuple()) + 1 == len(COLS)
