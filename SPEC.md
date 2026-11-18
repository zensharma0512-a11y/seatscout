# SeatScout rule specification

This is the source of truth. Every clause has at least one test, named in brackets.

## Shared definitions

- **Effective location**: the customer's shared location if they have one, otherwise their home city. [`TestNearby::test_shared_location_takes_priority_over_home`]
- **Local time**: the customer's own IANA timezone, not the server's and not the venue's. [`TestThisWeekend::test_uses_customer_timezone`]
- All datetimes must be timezone-aware. Naive datetimes are rejected. [`TestValidation::test_naive_now_rejected`]
- Money is `Decimal`, never `float`. [`TestPriceUnder::test_limit_must_be_positive_decimal`]

## Rules

| Rule | Matches when | Boundary |
| --- | --- | --- |
| `Nearby(r)` | Great-circle distance from the effective location to the venue is `<= r` km | `r` itself matches [`test_radius_is_inclusive`] |
| `ThisWeekend()` | Event starts in `[Sat 00:00, Mon 00:00)` local time, and at or after `now` | Sat 00:00 in, Sun 23:59:59 in, Mon 00:00 out [`test_boundaries`] |
| `PriceUnder(p)` | Price known, `price < p`, and at least one ticket left | `p` itself does not match. Sold out never matches. Unknown price never matches [`TestPriceUnder::test_cases`] |
| `Available()` | Tickets left and the event hasn't started | [`test_available`] |
| `InCategory(cs)` | Event category is in `cs`, case-insensitive | [`test_category_is_case_insensitive`] |
| `MatchesInterests()` | Event category is in the customer's interests | [`test_matches_interests_reads_from_context_customer`] |
| `StartsWithin(w)` | `now <= starts_at <= now + w` | Inclusive at both ends [`test_starts_within_is_inclusive_at_both_ends`] |

"This weekend" means the weekend you're in on Saturday or Sunday, and the coming one on Monday to Friday. [`test_on_sunday_means_today_not_next_weekend`]

The window is built from local wall-clock midnights, so a weekend with a DST change is 47 or 49 hours long and still includes all of Sunday. [`test_dst_weekend_keeps_all_of_sunday`]

## Composition

- `a & b`, `a | b` and `~a` build new rules. They never modify `a` or `b`. [`test_reused_rule_gives_same_answer_in_any_combination`]
- Rules are frozen and hold no per-call state. One instance can be shared across customers, campaigns and threads. [`test_rule_shared_between_customers_has_no_memory`, `test_concurrent_customers_do_not_see_each_others_results`]
- Combining a rule with something that isn't a rule raises `TypeError`. [`test_combining_with_non_rule_fails_loudly`]

## Campaigns

1. **Eligibility first.** Events that are sold out or already started are never recommended, whichever tier or fallback would have matched them. [`test_sold_out_and_past_events_never_recommended`]
2. **Tiers in order.** Each tier adds its matches sorted by `(starts_at, event_id)`. An event appears once, under the first tier that matched it. [`test_tiers_fill_in_order_without_duplicates`, `test_within_a_tier_order_is_start_time_then_id`]
3. **Limit.** Picking stops at exactly `limit` results. [`test_limit_is_respected`]
4. **Fallback.** If slots remain after every tier, the fallback rule fills them, tagged `"fallback"`. It doesn't run when the tiers already filled the limit. [`TestFallback`]
5. **Isolation.** Each call builds its own state. Results for one customer never include another customer's matches. [`TestIsolation`]
6. **Inputs.** `events` may be a one-shot iterator. It is read exactly once and shared across customers. [`test_events_can_be_a_one_shot_generator`]
