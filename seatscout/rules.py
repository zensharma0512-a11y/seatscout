"""Composable, stateless recommendation rules.

A rule is a frozen object with one method, ``matches(event, ctx) -> bool``.
Rules combine with ``&``, ``|`` and ``~``. Because rules hold no per-call state
and take the customer only through ``ctx``, one rule instance can be reused
across campaigns, customers and threads with no cross-talk.

The exact definition of every rule is in SPEC.md, and each clause there has a
test in tests/test_rules.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal

from .models import Context, Event


class Rule:
    name = "rule"

    def matches(self, event: Event, ctx: Context) -> bool:  # pragma: no cover - abstract
        raise NotImplementedError

    def __and__(self, other: "Rule") -> "Rule":
        return AllOf((self, _check(other)))

    def __or__(self, other: "Rule") -> "Rule":
        return AnyOf((self, _check(other)))

    def __invert__(self) -> "Rule":
        return Not(self)

    def __repr__(self) -> str:
        return self.describe()

    def describe(self) -> str:
        return self.name


def _check(other) -> Rule:
    if not isinstance(other, Rule):
        raise TypeError(f"can only combine rules with rules, got {type(other).__name__}")
    return other


# ---------------------------------------------------------------- combinators


@dataclass(frozen=True, repr=False)
class AllOf(Rule):
    rules: tuple[Rule, ...]

    def matches(self, event, ctx):
        return all(r.matches(event, ctx) for r in self.rules)

    def describe(self):
        return "(" + " & ".join(r.describe() for r in self.rules) + ")"


@dataclass(frozen=True, repr=False)
class AnyOf(Rule):
    rules: tuple[Rule, ...]

    def matches(self, event, ctx):
        return any(r.matches(event, ctx) for r in self.rules)

    def describe(self):
        return "(" + " | ".join(r.describe() for r in self.rules) + ")"


@dataclass(frozen=True, repr=False)
class Not(Rule):
    rule: Rule

    def matches(self, event, ctx):
        return not self.rule.matches(event, ctx)

    def describe(self):
        return f"~{self.rule.describe()}"


# --------------------------------------------------------------- basic rules


@dataclass(frozen=True, repr=False)
class Nearby(Rule):
    """Venue within ``radius_km`` (inclusive) of the customer's effective location:
    the shared location if they have one, otherwise their home city."""

    radius_km: float

    def __post_init__(self):
        if type(self.radius_km) not in (int, float) or not self.radius_km > 0:
            raise ValueError("radius_km must be a positive number")

    def matches(self, event, ctx):
        return ctx.customer.effective_location.distance_km(event.venue) <= self.radius_km

    def describe(self):
        return f"nearby({self.radius_km:g}km)"


@dataclass(frozen=True, repr=False)
class ThisWeekend(Rule):
    """Starts between Saturday 00:00 and Monday 00:00 (exclusive) of the current or
    next weekend, in the customer's own timezone, and has not started yet.

    "Current or next": on Monday-Friday that's the coming weekend; on Saturday or
    Sunday it's the weekend we're in.
    """

    def matches(self, event, ctx):
        start, end = weekend_window(ctx.now, ctx.customer.tz)
        starts = event.starts_at
        return start <= starts < end and starts >= ctx.now

    def describe(self):
        return "this_weekend"


def weekend_window(now: datetime, tz) -> tuple[datetime, datetime]:
    local = now.astimezone(tz)
    # weekday(): Monday=0 ... Saturday=5, Sunday=6
    days_back_to_saturday = {5: 0, 6: 1}.get(local.weekday())
    if days_back_to_saturday is not None:
        saturday = local.date() - timedelta(days=days_back_to_saturday)
    else:
        saturday = local.date() + timedelta(days=5 - local.weekday())
    monday = saturday + timedelta(days=2)
    # Build wall-clock midnights in the zone, so DST changes are handled correctly.
    start = datetime.combine(saturday, time.min, tzinfo=tz)
    end = datetime.combine(monday, time.min, tzinfo=tz)
    return start, end


@dataclass(frozen=True, repr=False)
class PriceUnder(Rule):
    """Has a known price strictly below ``limit`` and tickets left to buy.
    A sold-out event is never "under $50": you can't buy it at any price."""

    limit: Decimal

    def __post_init__(self):
        if not isinstance(self.limit, Decimal) or self.limit <= 0:
            raise ValueError("limit must be a positive Decimal")

    def matches(self, event, ctx):
        return event.price is not None and not event.sold_out and event.price < self.limit

    def describe(self):
        return f"price_under({self.limit})"


@dataclass(frozen=True, repr=False)
class Available(Rule):
    """Tickets left and the event hasn't started."""

    def matches(self, event, ctx):
        return not event.sold_out and event.starts_at >= ctx.now

    def describe(self):
        return "available"


@dataclass(frozen=True, repr=False)
class InCategory(Rule):
    categories: frozenset[str]

    def __post_init__(self):
        cats = frozenset(c.lower() for c in self.categories)
        if not cats:
            raise ValueError("at least one category is required")
        object.__setattr__(self, "categories", cats)

    def matches(self, event, ctx):
        return event.category.lower() in self.categories

    def describe(self):
        return f"category({','.join(sorted(self.categories))})"


@dataclass(frozen=True, repr=False)
class MatchesInterests(Rule):
    """Event category is one of the customer's interests."""

    def matches(self, event, ctx):
        return event.category.lower() in {i.lower() for i in ctx.customer.interests}

    def describe(self):
        return "matches_interests"


@dataclass(frozen=True, repr=False)
class StartsWithin(Rule):
    """Starts within ``window`` from now (now inclusive, now + window inclusive)."""

    window: timedelta

    def __post_init__(self):
        if not isinstance(self.window, timedelta) or self.window <= timedelta(0):
            raise ValueError("window must be a positive timedelta")

    def matches(self, event, ctx):
        return ctx.now <= event.starts_at <= ctx.now + self.window

    def describe(self):
        return f"starts_within({self.window})"
