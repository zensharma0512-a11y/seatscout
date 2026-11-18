from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from seatscout import Context, Customer, Event, Location

IST = ZoneInfo("Asia/Kolkata")

JAIPUR = Location("Jaipur", 26.9124, 75.7873)
DELHI = Location("Delhi", 28.6139, 77.2090)  # ~240 km from Jaipur
GOA = Location("Goa", 15.4909, 73.8278)

# Wednesday 18 Nov 2026, 10:00 IST. The coming weekend is Sat 21 - Sun 22 Nov.
WEDNESDAY = datetime(2026, 11, 18, 10, 0, tzinfo=IST)


def ist(*args) -> datetime:
    return datetime(*args, tzinfo=IST)


def make_event(
    id="e1",
    *,
    starts_at=None,
    venue=JAIPUR,
    price="40",
    tickets_left=100,
    category="music",
    name=None,
) -> Event:
    return Event(
        id=id,
        name=name or f"Event {id}",
        category=category,
        venue=venue,
        starts_at=starts_at or ist(2026, 11, 21, 19, 0),
        price=None if price is None else Decimal(price),
        tickets_left=tickets_left,
    )


def make_customer(id="c1", *, home=JAIPUR, shared=None, tz="Asia/Kolkata", interests=("music",)):
    return Customer(id=id, home=home, timezone=tz, interests=frozenset(interests), shared_location=shared)


@pytest.fixture
def ctx():
    return Context(customer=make_customer(), now=WEDNESDAY)
