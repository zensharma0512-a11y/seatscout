"""CLI: ``python -m seatscout examples/weekend_campaign.json``"""

import argparse
import json
import sys

from .loader import SpecError, parse_campaign, parse_customer, parse_datetime, parse_event
from .recommender import recommend_many


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run a SeatScout campaign from a JSON file.")
    parser.add_argument("file", help="JSON file with now, campaign, customers and events")
    args = parser.parse_args(argv)

    try:
        with open(args.file, encoding="utf-8") as fh:
            data = json.load(fh)
        campaign = parse_campaign(data["campaign"])
        customers = [parse_customer(c) for c in data["customers"]]
        events = [parse_event(e) for e in data["events"]]
        now = parse_datetime(data["now"])
    except (OSError, json.JSONDecodeError, KeyError, SpecError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    results = recommend_many(campaign, customers, events, now)
    print(json.dumps({cid: [r.to_dict() for r in recs] for cid, recs in results.items()}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
