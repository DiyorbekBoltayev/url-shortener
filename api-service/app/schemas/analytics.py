"""Analytics response schemas."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel


Bucket = Literal["hour", "day"]


class SummaryOut(BaseModel):
    short_code: str
    clicks: int
    uniques: int
    bot_clicks: int
    real_uniques: int


class TimeBucket(BaseModel):
    t: str
    c: int


class TimeSeriesOut(BaseModel):
    short_code: str
    bucket: Bucket
    since: date
    until: date
    buckets: list[TimeBucket]


class GeoRow(BaseModel):
    country: str
    clicks: int


class DeviceRow(BaseModel):
    device: str
    os: str
    browser: str
    clicks: int


class ReferrerRow(BaseModel):
    referrer: str
    clicks: int
