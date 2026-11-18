import json
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

import pytest

from seatscout import (
    Campaign,
    MatchesInterests,
    Nearby,
    PriceUnder,
    ThisWeekend,
    Tier,
    recommend,
    recommend_many,
)
from seatscout.__main__ import main
from seatscout.loader import SpecError, parse_rule

from .conftest import GOA, JAIPUR, WEDNESDAY, ist, make_customer, make_event

EXAMPLE = Path(__file__).parent.parent / "examples" / "weekend_campaign.json"


def weekend_campaign(limit=3, fallback=None):
    return Campaign(
        name="weekend",
        tiers=(
            Tier("cheap_local_weekend", Nearby(25) & ThisWeekend() & PriceUnder(Decimal("50"))),
            Tier("local_weekend", Nearby(25) & ThisWeekend()),
            Tier("your_interests", MatchesInterests()),
        ),
        limit=limit,
        fallback=fallback,
    )


def ids(recs):
    return [r.event_id for r in recs]


class TestTiersAndLimit:
    def test_tiers_fill_in_order_without_duplicates(self):
        events = [
            make_event("pricey", price="80", starts_at=ist(2026, 11, 21, 18, 0)),
            make_event("cheap", price="20", starts_at=ist(2026, 11, 21, 20, 0)),
            make_event("far_music", venue=GOA, starts_at=ist(2026, 11, 25, 20, 0)),
        ]
        recs = recommend(weekend_campaign(), make_customer(), events, WEDNESDAY)
        assert [(r.event_id, r.tier) for r in recs] == [
            ("cheap", "cheap_local_weekend"),
            ("pricey", "local_weekend"),
            ("far_music", "your_interests"),
        ]

    def test_limit_is_respected(self):
        events = [make_event(f"e{i}", starts_at=ist(2026, 11, 21, 10 + i, 0)) for i in range(6)]
        recs = recommend(weekend_campaign(limit=2), make_customer(), events, WEDNESDAY)
        assert ids(recs) == ["e0", "e1"]

    def test_within_a_tier_order_is_start_time_then_id(self):
        same_time = ist(2026, 11, 21, 19, 0)
        events = [make_event("b", starts_at=same_time), make_event("a", starts_at=same_time),
                  make_event("z", starts_at=ist(2026, 11, 21, 9, 0))]
        assert ids(recommend(weekend_campaign(), make_customer(), events, WEDNESDAY)) == ["z", "a", "b"]

    def test_sold_out_and_past_events_never_recommended(self):
        events = [
            make_event("sold", tickets_left=0, price="5"),
            make_event("past", starts_at=ist(2026, 11, 1, 10, 0)),
        ]
        campaign = weekend_campaign(fallback=MatchesInterests() | ~MatchesInterests())
        assert recommend(campaign, make_customer(), events, WEDNESDAY) == []


class TestFallback:
    def test_fallback_fills_remaining_slots(self):
        events = [
            make_event("local", starts_at=ist(2026, 11, 21, 19, 0)),
            make_event("far_comedy", venue=GOA, category="comedy", starts_at=ist(2026, 11, 26, 19, 0)),
        ]
        campaign = weekend_campaign(fallback=PriceUnder(Decimal("100")))
        recs = recommend(campaign, make_customer(), events, WEDNESDAY)
        assert [(r.event_id, r.tier) for r in recs] == [
            ("local", "cheap_local_weekend"),
            ("far_comedy", "fallback"),
        ]

    def test_customer_with_no_tier_matches_still_gets_fallback(self):
        events = [make_event("far_comedy", venue=GOA, category="comedy", starts_at=ist(2026, 11, 26, 19, 0))]
        customer = make_customer(interests=["theatre"])
        assert recommend(weekend_campaign(), customer, events, WEDNESDAY) == []
        with_fallback = weekend_campaign(fallback=PriceUnder(Decimal("100")))
        assert ids(recommend(with_fallback, customer, events, WEDNESDAY)) == ["far_comedy"]

    def test_fallback_does_not_run_when_tiers_already_fill_the_limit(self):
        events = [make_event(f"e{i}", starts_at=ist(2026, 11, 21, 10 + i, 0)) for i in range(3)]
        events.append(make_event("extra", venue=GOA, category="comedy", starts_at=ist(2026, 11, 26, 10, 0)))
        campaign = weekend_campaign(limit=3, fallback=PriceUnder(Decimal("100")))
        recs = recommend(campaign, make_customer(), events, WEDNESDAY)
        assert "fallback" not in {r.tier for r in recs}


class TestIsolation:
    def test_customers_get_their_own_nearby_events(self):
        events = [make_event("jaipur_gig", venue=JAIPUR), make_event("goa_gig", venue=GOA)]
        campaign = Campaign("local", (Tier("near", Nearby(25)),), limit=5)
        results = recommend_many(
            campaign,
            [make_customer("asha", home=JAIPUR), make_customer("dev", home=GOA)],
            events,
            WEDNESDAY,
        )
        assert ids(results["asha"]) == ["jaipur_gig"]
        assert ids(results["dev"]) == ["goa_gig"]

    def test_repeated_calls_do_not_accumulate(self):
        campaign = weekend_campaign()
        events = [make_event("a")]
        first = recommend(campaign, make_customer("x"), events, WEDNESDAY)
        second = recommend(campaign, make_customer("y", home=GOA, interests=()), events, WEDNESDAY)
        third = recommend(campaign, make_customer("x"), events, WEDNESDAY)
        assert ids(first) == ids(third) == ["a"] and second == []

    def test_concurrent_customers_do_not_see_each_others_results(self):
        campaign = Campaign("local", (Tier("near", Nearby(25)),), limit=5)
        events = [make_event("jaipur_gig", venue=JAIPUR), make_event("goa_gig", venue=GOA)]
        barrier = threading.Barrier(40)

        def run(i):
            home, expected = (JAIPUR, ["jaipur_gig"]) if i % 2 else (GOA, ["goa_gig"])
            barrier.wait()
            return ids(recommend(campaign, make_customer(f"c{i}", home=home), events, WEDNESDAY)) == expected

        with ThreadPoolExecutor(40) as pool:
            assert all(pool.map(run, range(40)))

    def test_events_can_be_a_one_shot_generator(self):
        gen = (make_event(f"e{i}", starts_at=ist(2026, 11, 21, 10 + i, 0)) for i in range(3))
        recs = recommend_many(weekend_campaign(), [make_customer("a"), make_customer("b")], gen, WEDNESDAY)
        assert ids(recs["a"]) == ids(recs["b"]) == ["e0", "e1", "e2"]

    def test_results_are_immutable(self):
        rec = recommend(weekend_campaign(), make_customer(), [make_event()], WEDNESDAY)[0]
        with pytest.raises(AttributeError):
            rec.event_id = "other"


class TestValidation:
    @pytest.mark.parametrize("limit", [0, -1, True, 2.0])
    def test_bad_limit(self, limit):
        with pytest.raises(ValueError):
            weekend_campaign(limit=limit)

    def test_duplicate_tier_names(self):
        with pytest.raises(ValueError):
            Campaign("x", (Tier("a", Nearby(5)), Tier("a", Nearby(9))), limit=1)

    def test_naive_now_rejected(self):
        from datetime import datetime
        with pytest.raises(ValueError):
            recommend(weekend_campaign(), make_customer(), [], datetime(2026, 11, 18, 10, 0))

    def test_duplicate_event_ids_rejected(self):
        with pytest.raises(ValueError):
            recommend(weekend_campaign(), make_customer(), [make_event("a"), make_event("a")], WEDNESDAY)

    @pytest.mark.parametrize(
        "spec",
        [{"nearby": 0}, {"price_under": 50.5}, {"this_weekend": False}, {"all": []}, {"bogus": 1}, "nearby"],
    )
    def test_bad_rule_specs(self, spec):
        with pytest.raises(SpecError):
            parse_rule(spec)


def test_cli_runs_example(capsys):
    assert main([str(EXAMPLE)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out) == {"asha", "dev", "meera"}
    assert out["dev"][0]["event_id"] == "goa-beach-fest"  # shared location wins over home
    assert all(r["event_id"] != "jaipur-sold-out" for recs in out.values() for r in recs)
    assert out["meera"], "fallback must give every customer something"
