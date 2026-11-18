"""Campaign recommender: ordered tiers, a hard limit and a fallback.

How a campaign is applied to one customer:

1. Only *eligible* events are considered (``campaign.eligibility``, by default
   ``Available()``: not sold out, not started).
2. Tiers run in order. Each tier adds its matching events, sorted by start time
   and then event id, skipping events an earlier tier already picked.
3. Picking stops as soon as ``limit`` events are chosen.
4. If slots are still free after every tier, the ``fallback`` rule fills them in
   the same order. So a customer only gets an empty list if no eligible event
   exists at all.

Every call builds its own local state. Nothing is cached on the campaign, the
rules or the module, so customers can never receive each other's results.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from .models import Context, Customer, Event, ModelError
from .rules import Available, Rule

FALLBACK_TIER = "fallback"


@dataclass(frozen=True)
class Tier:
    name: str
    rule: Rule

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name or self.name == FALLBACK_TIER:
            raise ValueError(f"tier name must be a non-empty string other than {FALLBACK_TIER!r}")
        if not isinstance(self.rule, Rule):
            raise TypeError("tier rule must be a Rule")


@dataclass(frozen=True)
class Campaign:
    name: str
    tiers: tuple[Tier, ...]
    limit: int
    fallback: Rule | None = None
    eligibility: Rule = Available()

    def __post_init__(self):
        object.__setattr__(self, "tiers", tuple(self.tiers))
        if not self.tiers:
            raise ValueError("a campaign needs at least one tier")
        names = [t.name for t in self.tiers]
        if len(set(names)) != len(names):
            raise ValueError("tier names must be unique")
        if type(self.limit) is not int or self.limit < 1:
            raise ValueError("limit must be a positive integer")
        if self.fallback is not None and not isinstance(self.fallback, Rule):
            raise TypeError("fallback must be a Rule or None")


@dataclass(frozen=True)
class Recommendation:
    event_id: str
    event_name: str
    tier: str
    starts_at: str

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_name": self.event_name,
            "tier": self.tier,
            "starts_at": self.starts_at,
        }


def recommend(
    campaign: Campaign, customer: Customer, events: Iterable[Event], now: datetime
) -> list[Recommendation]:
    # Read the iterable exactly once: generators and other one-shot inputs work.
    return _recommend(campaign, customer, _materialize(events), now)


def recommend_many(
    campaign: Campaign, customers: Iterable[Customer], events: Iterable[Event], now: datetime
) -> dict[str, list[Recommendation]]:
    """Recommendations per customer id, in the order customers were given."""
    catalogue = _materialize(events)
    results: dict[str, list[Recommendation]] = {}
    for customer in customers:
        if not isinstance(customer, Customer):
            raise TypeError("customers must contain Customer objects")
        if customer.id in results:
            raise ValueError(f"duplicate customer id: {customer.id}")
        results[customer.id] = _recommend(campaign, customer, catalogue, now)
    return results


def _materialize(events: Iterable[Event]) -> tuple[Event, ...]:
    catalogue = tuple(events)
    seen: set[str] = set()
    for e in catalogue:
        if not isinstance(e, Event):
            raise TypeError("events must contain Event objects")
        if e.id in seen:
            raise ValueError(f"duplicate event id: {e.id}")
        seen.add(e.id)
    # Sorted once, so every tier walks events in the same deterministic order.
    return tuple(sorted(catalogue, key=lambda e: (e.starts_at, e.id)))


def _recommend(
    campaign: Campaign, customer: Customer, catalogue: tuple[Event, ...], now: datetime
) -> list[Recommendation]:
    if not isinstance(campaign, Campaign):
        raise TypeError("campaign must be a Campaign")
    try:
        ctx = Context(customer=customer, now=now)
    except ModelError as exc:
        raise ValueError(str(exc)) from None

    eligible = [e for e in catalogue if campaign.eligibility.matches(e, ctx)]
    picked: list[Recommendation] = []
    taken: set[str] = set()

    stages = [(t.name, t.rule) for t in campaign.tiers]
    if campaign.fallback is not None:
        stages.append((FALLBACK_TIER, campaign.fallback))

    for tier_name, rule in stages:
        for event in eligible:
            if len(picked) == campaign.limit:
                return picked
            if event.id in taken or not rule.matches(event, ctx):
                continue
            taken.add(event.id)
            picked.append(
                Recommendation(
                    event_id=event.id,
                    event_name=event.name,
                    tier=tier_name,
                    starts_at=event.starts_at.isoformat(),
                )
            )
    return picked
