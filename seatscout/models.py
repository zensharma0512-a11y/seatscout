"""Immutable domain models. Frozen dataclasses mean a rule can never mutate its inputs."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

EARTH_RADIUS_KM = 6371.0088


class ModelError(ValueError):
    """Raised when a model is constructed with invalid data."""


def _require_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ModelError(f"{field_name} must be a timezone-aware datetime")


@dataclass(frozen=True)
class Location:
    name: str
    lat: float
    lon: float

    def __post_init__(self):
        for attr, lo, hi in (("lat", -90, 90), ("lon", -180, 180)):
            value = getattr(self, attr)
            if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
                raise ModelError(f"{attr} must be a number between {lo} and {hi}")

    def distance_km(self, other: "Location") -> float:
        """Great-circle distance (haversine)."""
        lat1, lon1, lat2, lon2 = map(math.radians, (self.lat, self.lon, other.lat, other.lon))
        a = (
            math.sin((lat2 - lat1) / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
        )
        return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


@dataclass(frozen=True)
class Event:
    id: str
    name: str
    category: str
    venue: Location
    starts_at: datetime
    price: Decimal | None  # None = price not announced yet
    tickets_left: int

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id:
            raise ModelError("event id must be a non-empty string")
        _require_aware(self.starts_at, "starts_at")
        if self.price is not None and (not isinstance(self.price, Decimal) or self.price < 0):
            raise ModelError("price must be a non-negative Decimal or None")
        if type(self.tickets_left) is not int or self.tickets_left < 0:
            raise ModelError("tickets_left must be a non-negative integer")

    @property
    def sold_out(self) -> bool:
        return self.tickets_left == 0


@dataclass(frozen=True)
class Customer:
    id: str
    home: Location
    timezone: str
    interests: frozenset[str] = field(default_factory=frozenset)
    # A location the customer chose to share (e.g. "I'm in Goa this week").
    # When present it takes priority over the home city.
    shared_location: Location | None = None

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id:
            raise ModelError("customer id must be a non-empty string")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            raise ModelError(f"unknown timezone: {self.timezone!r}") from None
        # Accept any iterable of strings but always store an immutable copy.
        object.__setattr__(self, "interests", frozenset(self.interests))

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def effective_location(self) -> Location:
        return self.shared_location if self.shared_location is not None else self.home


@dataclass(frozen=True)
class Context:
    """Everything a rule may look at besides the event. Built fresh per customer."""

    customer: Customer
    now: datetime

    def __post_init__(self):
        _require_aware(self.now, "now")
