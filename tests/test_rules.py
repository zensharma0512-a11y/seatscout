from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from seatscout import (
    Available,
    Context,
    InCategory,
    MatchesInterests,
    Nearby,
    PriceUnder,
    StartsWithin,
    ThisWeekend,
)

from .conftest import DELHI, GOA, JAIPUR, WEDNESDAY, ist, make_customer, make_event


# ------------------------------------------------------------------- Nearby


class TestNearby:
    def test_uses_home_city_without_shared_location(self, ctx):
        assert Nearby(25).matches(make_event(venue=JAIPUR), ctx)
        assert not Nearby(25).matches(make_event(venue=GOA), ctx)

    def test_shared_location_takes_priority_over_home(self):
        ctx = Context(make_customer(home=JAIPUR, shared=GOA), WEDNESDAY)
        assert Nearby(25).matches(make_event(venue=GOA), ctx)
        assert not Nearby(25).matches(make_event(venue=JAIPUR), ctx)

    def test_radius_is_inclusive(self, ctx):
        distance = JAIPUR.distance_km(DELHI)
        assert 230 < distance < 250
        assert Nearby(distance).matches(make_event(venue=DELHI), ctx)
        assert not Nearby(distance - 0.001).matches(make_event(venue=DELHI), ctx)

    @pytest.mark.parametrize("radius", [0, -5, True, "10"])
    def test_rejects_bad_radius(self, radius):
        with pytest.raises(ValueError):
            Nearby(radius)


# -------------------------------------------------------------- ThisWeekend


class TestThisWeekend:
    @pytest.mark.parametrize(
        "starts, expected",
        [
            (ist(2026, 11, 20, 23, 59, 59), False),  # Friday night
            (ist(2026, 11, 21, 0, 0), True),          # Saturday 00:00 (inclusive)
            (ist(2026, 11, 22, 12, 0), True),         # Sunday midday
            (ist(2026, 11, 22, 23, 59, 59), True),    # last second of Sunday
            (ist(2026, 11, 23, 0, 0), False),         # Monday 00:00 (exclusive)
            (ist(2026, 11, 28, 12, 0), False),        # following weekend
        ],
    )
    def test_boundaries(self, ctx, starts, expected):
        assert ThisWeekend().matches(make_event(starts_at=starts), ctx) is expected

    def test_on_sunday_means_today_not_next_weekend(self):
        sunday_noon = ist(2026, 11, 22, 12, 0)
        ctx = Context(make_customer(), sunday_noon)
        assert ThisWeekend().matches(make_event(starts_at=ist(2026, 11, 22, 20, 0)), ctx)
        assert not ThisWeekend().matches(make_event(starts_at=ist(2026, 11, 29, 20, 0)), ctx)

    def test_events_that_already_started_are_excluded(self):
        ctx = Context(make_customer(), ist(2026, 11, 21, 18, 0))
        assert not ThisWeekend().matches(make_event(starts_at=ist(2026, 11, 21, 10, 0)), ctx)

    def test_uses_customer_timezone(self):
        # 23:30 Sunday in New York is already Monday in India.
        ny = ZoneInfo("America/New_York")
        event = make_event(starts_at=datetime(2026, 11, 22, 23, 30, tzinfo=ny))
        now = datetime(2026, 11, 18, 9, 0, tzinfo=ny)
        assert ThisWeekend().matches(event, Context(make_customer(tz="America/New_York"), now))
        assert not ThisWeekend().matches(event, Context(make_customer(tz="Asia/Kolkata"), now))

    def test_dst_weekend_keeps_all_of_sunday(self):
        # US clocks go back on Sunday 1 Nov 2026; the weekend is 49 hours long.
        ny = ZoneInfo("America/New_York")
        ctx = Context(make_customer(tz="America/New_York"), datetime(2026, 10, 29, 9, 0, tzinfo=ny))
        late_sunday = make_event(starts_at=datetime(2026, 11, 1, 23, 30, tzinfo=ny))
        monday = make_event(starts_at=datetime(2026, 11, 2, 0, 0, tzinfo=ny))
        assert ThisWeekend().matches(late_sunday, ctx)
        assert not ThisWeekend().matches(monday, ctx)


# --------------------------------------------------------------- PriceUnder


class TestPriceUnder:
    @pytest.mark.parametrize(
        "price, tickets, expected",
        [
            ("49.99", 10, True),
            ("50", 10, False),     # strictly under
            ("0", 10, True),       # free events count
            ("10", 0, False),      # sold out never counts, however cheap
            (None, 10, False),     # unknown price is not "under $50"
        ],
    )
    def test_cases(self, ctx, price, tickets, expected):
        event = make_event(price=price, tickets_left=tickets)
        assert PriceUnder(Decimal("50")).matches(event, ctx) is expected

    @pytest.mark.parametrize("limit", [50, 50.0, Decimal("0"), Decimal("-1")])
    def test_limit_must_be_positive_decimal(self, limit):
        with pytest.raises(ValueError):
            PriceUnder(limit)


# --------------------------------------------------------------- other rules


def test_available(ctx):
    assert Available().matches(make_event(), ctx)
    assert not Available().matches(make_event(tickets_left=0), ctx)
    assert not Available().matches(make_event(starts_at=ist(2026, 11, 17, 10, 0)), ctx)


def test_category_is_case_insensitive(ctx):
    assert InCategory(frozenset({"Music"})).matches(make_event(category="MUSIC"), ctx)
    assert not InCategory(frozenset({"comedy"})).matches(make_event(category="music"), ctx)


def test_matches_interests_reads_from_context_customer():
    rule = MatchesInterests()
    event = make_event(category="comedy")
    assert rule.matches(event, Context(make_customer(interests=["comedy"]), WEDNESDAY))
    assert not rule.matches(event, Context(make_customer(interests=["music"]), WEDNESDAY))


def test_starts_within_is_inclusive_at_both_ends(ctx):
    rule = StartsWithin(timedelta(hours=2))
    assert rule.matches(make_event(starts_at=WEDNESDAY), ctx)
    assert rule.matches(make_event(starts_at=WEDNESDAY + timedelta(hours=2)), ctx)
    assert not rule.matches(make_event(starts_at=WEDNESDAY + timedelta(hours=2, seconds=1)), ctx)


# -------------------------------------------------------------- composition


class TestComposition:
    def test_and_or_not(self, ctx):
        cheap_nearby = Nearby(25) & PriceUnder(Decimal("50"))
        assert cheap_nearby.matches(make_event(price="40"), ctx)
        assert not cheap_nearby.matches(make_event(price="60"), ctx)
        assert (Nearby(25) | PriceUnder(Decimal("50"))).matches(make_event(venue=GOA, price="10"), ctx)
        assert (~Nearby(25)).matches(make_event(venue=GOA), ctx)

    def test_reused_rule_gives_same_answer_in_any_combination(self, ctx):
        weekend = ThisWeekend()
        a = weekend & Nearby(25)
        b = Nearby(25) & weekend
        c = PriceUnder(Decimal("50")) & weekend & Nearby(25)
        event = make_event()
        before = weekend.matches(event, ctx)
        assert a.matches(event, ctx) == b.matches(event, ctx) == c.matches(event, ctx) == before
        assert weekend.matches(event, ctx) == before  # unchanged by being combined

    def test_rule_shared_between_customers_has_no_memory(self):
        rule = Nearby(25)
        jaipur_ctx = Context(make_customer("a", home=JAIPUR), WEDNESDAY)
        goa_ctx = Context(make_customer("b", home=GOA), WEDNESDAY)
        jaipur_event, goa_event = make_event("j", venue=JAIPUR), make_event("g", venue=GOA)
        for _ in range(3):  # alternate to catch any cached state
            assert rule.matches(jaipur_event, jaipur_ctx) and not rule.matches(goa_event, jaipur_ctx)
            assert rule.matches(goa_event, goa_ctx) and not rule.matches(jaipur_event, goa_ctx)

    def test_rules_are_immutable_and_hashable(self):
        rule = Nearby(25)
        with pytest.raises(AttributeError):
            rule.radius_km = 1000
        assert hash(Nearby(25)) == hash(Nearby(25)) and Nearby(25) == Nearby(25)

    def test_combining_with_non_rule_fails_loudly(self):
        with pytest.raises(TypeError):
            Nearby(25) & True

    def test_describe(self):
        rule = (Nearby(25) & ThisWeekend()) | ~PriceUnder(Decimal("50"))
        assert repr(rule) == "((nearby(25km) & this_weekend) | ~price_under(50))"
