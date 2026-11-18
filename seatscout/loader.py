"""Build campaigns, customers and events from plain JSON-style dicts.

Rule specs are small dicts with exactly one key, e.g.::

    {"all": [{"nearby": 25}, {"this_weekend": true}, {"price_under": "50"}]}
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from .models import Customer, Event, Location, ModelError
from .recommender import Campaign, Tier
from . import rules as r


class SpecError(ValueError):
    pass


def parse_rule(spec) -> r.Rule:
    if not isinstance(spec, dict) or len(spec) != 1:
        raise SpecError(f"a rule spec must be an object with exactly one key, got {spec!r}")
    (kind, arg), = spec.items()
    if kind == "all":
        return r.AllOf(tuple(parse_rule(s) for s in _non_empty_list(arg, kind)))
    if kind == "any":
        return r.AnyOf(tuple(parse_rule(s) for s in _non_empty_list(arg, kind)))
    if kind == "not":
        return r.Not(parse_rule(arg))
    if kind == "nearby":
        return _build(r.Nearby, arg)
    if kind == "price_under":
        return _build(r.PriceUnder, _decimal(arg, kind))
    if kind == "category":
        return _build(r.InCategory, frozenset(_non_empty_list(arg, kind)))
    if kind == "starts_within_hours":
        if type(arg) not in (int, float):
            raise SpecError("starts_within_hours must be a number")
        return _build(r.StartsWithin, timedelta(hours=arg))
    flags = {"this_weekend": r.ThisWeekend, "available": r.Available, "matches_interests": r.MatchesInterests}
    if kind in flags:
        if arg is not True:
            raise SpecError(f"{kind} takes the value true")
        return flags[kind]()
    raise SpecError(f"unknown rule: {kind}")


def parse_campaign(spec: dict) -> Campaign:
    try:
        tiers = tuple(Tier(t["name"], parse_rule(t["rule"])) for t in spec["tiers"])
        fallback = parse_rule(spec["fallback"]) if spec.get("fallback") is not None else None
        return Campaign(name=spec["name"], tiers=tiers, limit=spec["limit"], fallback=fallback)
    except (KeyError, TypeError) as exc:
        raise SpecError(f"invalid campaign: {exc}") from None
    except ValueError as exc:
        raise SpecError(str(exc)) from None


def parse_location(spec: dict) -> Location:
    try:
        return Location(spec["name"], spec["lat"], spec["lon"])
    except (KeyError, TypeError, ModelError) as exc:
        raise SpecError(f"invalid location: {exc}") from None


def parse_customer(spec: dict) -> Customer:
    try:
        shared = spec.get("shared_location")
        return Customer(
            id=spec["id"],
            home=parse_location(spec["home"]),
            timezone=spec["timezone"],
            interests=frozenset(spec.get("interests", ())),
            shared_location=parse_location(shared) if shared else None,
        )
    except (KeyError, TypeError, ModelError) as exc:
        raise SpecError(f"invalid customer: {exc}") from None


def parse_event(spec: dict) -> Event:
    try:
        price = spec.get("price")
        return Event(
            id=spec["id"],
            name=spec["name"],
            category=spec["category"],
            venue=parse_location(spec["venue"]),
            starts_at=parse_datetime(spec["starts_at"]),
            price=None if price is None else _decimal(price, "price"),
            tickets_left=spec["tickets_left"],
        )
    except (KeyError, TypeError, ModelError) as exc:
        raise SpecError(f"invalid event {spec.get('id', '?')!r}: {exc}") from None


def parse_datetime(value) -> datetime:
    if not isinstance(value, str):
        raise SpecError("datetimes must be ISO-8601 strings")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise SpecError(f"invalid datetime: {value!r}") from None
    if parsed.tzinfo is None:
        raise SpecError(f"datetime must include a UTC offset: {value!r}")
    return parsed


def _decimal(value, field: str) -> Decimal:
    # Strings and ints only: floats like 49.99 can't be represented exactly.
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise SpecError(f"{field} must be a string or integer, e.g. \"49.99\"")
    try:
        d = Decimal(value)
    except InvalidOperation:
        raise SpecError(f"{field} is not a valid number: {value!r}") from None
    if not d.is_finite():
        raise SpecError(f"{field} must be finite")
    return d


def _non_empty_list(value, field: str) -> list:
    if not isinstance(value, list) or not value:
        raise SpecError(f"{field} needs a non-empty list")
    return value


def _build(cls, arg):
    try:
        return cls(arg)
    except (ValueError, TypeError) as exc:
        raise SpecError(str(exc)) from None
