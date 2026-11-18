"""SeatScout: composable rules for event recommendation campaigns."""

from .models import Context, Customer, Event, Location, ModelError
from .recommender import Campaign, Recommendation, Tier, recommend, recommend_many
from .rules import (
    AllOf,
    AnyOf,
    Available,
    InCategory,
    MatchesInterests,
    Nearby,
    Not,
    PriceUnder,
    Rule,
    StartsWithin,
    ThisWeekend,
)

__all__ = [
    "AllOf", "AnyOf", "Available", "Campaign", "Context", "Customer", "Event",
    "InCategory", "Location", "MatchesInterests", "ModelError", "Nearby", "Not",
    "PriceUnder", "Recommendation", "Rule", "StartsWithin", "ThisWeekend", "Tier",
    "recommend", "recommend_many",
]
