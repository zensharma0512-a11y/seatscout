# SeatScout

[![CI](https://github.com/zensharma0512-a11y/seatscout/actions/workflows/ci.yml/badge.svg)](https://github.com/zensharma0512-a11y/seatscout/actions/workflows/ci.yml)

Event recommendation campaigns built from small, reusable rules.

A campaign is a list of tiers, a limit and a fallback. Each tier is a rule such as "nearby **and** this weekend **and** under ₹50". Rules are tiny frozen objects that combine with `&`, `|` and `~`. Because they hold no state, the same rule can be reused across campaigns, customers and threads.

```python
from decimal import Decimal
from seatscout import Campaign, Tier, Nearby, ThisWeekend, PriceUnder, MatchesInterests, StartsWithin, recommend_many
from datetime import timedelta

campaign = Campaign(
    name="weekend-picks",
    tiers=(
        Tier("cheap_local_weekend", Nearby(25) & ThisWeekend() & PriceUnder(Decimal("50"))),
        Tier("local_weekend",       Nearby(25) & ThisWeekend()),
        Tier("your_interests",      MatchesInterests()),
    ),
    limit=3,
    fallback=StartsWithin(timedelta(days=14)),
)

results = recommend_many(campaign, customers, events, now)
```

## Why it's built this way

Recommendation rules break in ways that are easy to miss. These are the bugs this design rules out, each with a test:

| Bug | Cause | How SeatScout avoids it |
| --- | --- | --- |
| A customer's shared location is ignored in favour of their home city | The rule reads `customer.home` directly | One `effective_location` property that every location rule uses |
| "This weekend" never shows Sunday events | The window ends at Sunday 00:00, or a `weekday()` off-by-one | Window is `[Sat 00:00, Mon 00:00)` in the customer's timezone, built from wall-clock midnights so DST weekends still work |
| Sold-out tickets count as "Under ₹50" | Only the price is checked | `PriceUnder` also needs tickets left and a known price |
| Customers receive each other's events | A mutable default argument or a module-level cache shared between calls | Frozen rules, the customer passed in through a per-call `Context`, and fresh result lists |
| Some customers get no recommendations at all | The fallback never runs when the tiers come back empty | Fallback fills any remaining slots after the tiers |
| Results differ between runs | Iterating over sets or dicts in arbitrary order | Stable sort by `(starts_at, event_id)` |

[SPEC.md](SPEC.md) has the exact definition of every rule and the test that covers each clause. I wrote the spec first and then built the tests from it, so "correct" means "matches a written definition", not "seems to work".

## Rules

| Rule | Meaning |
| --- | --- |
| `Nearby(km)` | Venue within `km` (inclusive) of the shared location, or the home city if none is shared |
| `ThisWeekend()` | Starts Saturday 00:00 to before Monday 00:00 in the customer's timezone, and hasn't started yet |
| `PriceUnder(Decimal)` | Known price strictly under the limit, with tickets left |
| `Available()` | Tickets left and not started (the default eligibility filter) |
| `InCategory({...})` | Category match, case-insensitive |
| `MatchesInterests()` | Category is one of the customer's interests |
| `StartsWithin(timedelta)` | Starts between now and now + window |
| `a & b`, `a \| b`, `~a` | Composition |

## Running it

```bash
pip install -e ".[dev]"
pytest                                            # 62 tests
python -m seatscout examples/weekend_campaign.json
```

The example has three customers. Asha in Jaipur gets local weekend gigs. Dev lives in Delhi but has shared that he's in Goa, so the Goa beach fest comes first. Meera's interests match nothing, so the fallback gives her upcoming events instead of an empty list. The sold-out show never appears, even though it costs ₹10.

Campaigns can also be written as JSON. Rule specs are one-key objects:

```json
{"all": [{"nearby": 25}, {"this_weekend": true}, {"price_under": "50"}]}
```

Prices are strings or integers, never floats, so `"49.99"` stays exact.

## Layout

```
seatscout/
  models.py       Location, Event, Customer, Context (frozen, validated)
  rules.py        Rule base class, combinators and the built-in rules
  recommender.py  Campaign, Tier, recommend, recommend_many
  loader.py       JSON → rules, campaigns, customers, events
  __main__.py     CLI
tests/            boundary, composition, isolation and concurrency tests
SPEC.md           written requirements that the tests check
```
