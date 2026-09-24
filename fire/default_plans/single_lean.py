"""Example expense profile: single, no kids, no wedding, lean (roommates, cheap travel). Built from
sf_family by dropping the family lines and lowering a few budget lines."""

from dataclasses import replace

from default_plans.sf_family import PLAN as SF

CHEAPER = {"Rent": 1_300, "Trips (flight + hotel)": 250, "Eating out": 40, "Social": 35, "Furniture + home": 300}
DROP_CATEGORIES = {"kids", "events", "insurance"}

PLAN = replace(
    SF,
    name="example: single, lean, no kids",
    wedding_age=None,
    taxes="CA, single",
    expenses=[replace(e, amount=CHEAPER.get(e.name, e.amount))
              for e in SF.expenses if e.category not in DROP_CATEGORIES],
)
