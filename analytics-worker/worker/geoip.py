"""geoip2 reader wrapper — open once at startup, reuse mmap across lookups."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import geoip2.database
import geoip2.errors

from .logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True, frozen=True)
class Geo:
    country_code: str | None
    country_name: str | None
    region: str | None
    city: str | None
    lat: float | None
    lon: float | None


_EMPTY = Geo(None, None, None, None, None, None)


class GeoIPReader:
    """Thread-safe wrapper. The underlying `geoip2.database.Reader` uses a memory-
    mapped .mmdb; concurrent reads are safe. Close only at shutdown.

    When the mmdb is missing (e.g. geoip-updater hasn't run yet), we degrade
    gracefully: every lookup returns an empty `Geo` instead of crashing.
    """

    __slots__ = ("_reader", "_path")

    def __init__(self, path: str) -> None:
        self._path = path
        if Path(path).exists():
            try:
                self._reader = geoip2.database.Reader(path)
                log.info("geoip_opened", path=path)
            except Exception as e:
                log.warning("geoip_open_failed", path=path, error=str(e))
                self._reader = None
        else:
            log.warning("geoip_missing", path=path)
            self._reader = None

    @property
    def available(self) -> bool:
        return self._reader is not None

    def lookup(self, ip: str) -> Geo:
        if not ip or self._reader is None:
            return _EMPTY
        try:
            r = self._reader.city(ip)
        except (geoip2.errors.AddressNotFoundError, ValueError):
            return _EMPTY
        except Exception as e:
            log.debug("geoip_lookup_error", ip=ip, error=str(e))
            return _EMPTY
        return Geo(
            country_code=r.country.iso_code,
            country_name=r.country.name,
            region=(r.subdivisions.most_specific.name if r.subdivisions else None),
            city=r.city.name,
            lat=float(r.location.latitude) if r.location.latitude is not None else None,
            lon=float(r.location.longitude) if r.location.longitude is not None else None,
        )

    def close(self) -> None:
        if self._reader is not None:
            try:
                self._reader.close()
            except Exception:  # noqa: BLE001
                pass
            self._reader = None
