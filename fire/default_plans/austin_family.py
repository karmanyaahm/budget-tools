"""Example plan: the SF family example with rough 2026 Austin, TX prices and Texas taxes. Only the lines in
AUSTIN change; everything else (career, events, kid) comes from sf_family. Shows the override pattern."""

from dataclasses import replace

from default_plans.sf_family import KID_BIRTH_AGES, PLAN as SF
from firemodel.schema import MONTH, Expense

AUSTIN = {  # exact expense name -> Austin amount (same cadence)
    "Rent": 950,
    "Utilities": 115,
    "Renters insurance": 25,
    "Gym": 55,
    "Transit + rideshare": 300,
    "Eating out": 60,
    "Health insurance (individual)": 700,
    "Individual health age step 50+": 250,
    "Individual health age step 58+": 550,
    "Extra bedroom for kids": 900,
    "Kid 1: daycare (infant)": 1_650,
    "Kid 1: daycare (1-3)": 1_650,
    "Kid 1: activities/camp/food (6-17)": 1_150,
    "Kid 1: college (UC in-state)": 34_000,
}
_missing = set(AUSTIN) - {e.name for e in SF.expenses}
assert not _missing, f"AUSTIN names not found in sf_family: {_missing}"

# Texas has no universal pre-K at 4 (California has free TK): full-time preschool at 4, after-care from 5.
_PRESCHOOL = [Expense(f"Kid {n}: preschool (4)", 1_100, MONTH, b + 4, b + 5, category="kids")
              for n, b in enumerate(KID_BIRTH_AGES, 1)]


def _austin(e: Expense) -> Expense:
    if e.name.endswith("TK/K after-care (4-5)"):
        return replace(e, name=e.name.replace("TK/K after-care (4-5)", "K after-care (5)"), start=e.start + 1,
                       amount=700)
    if e.name not in AUSTIN:
        return e
    return replace(e, amount=AUSTIN[e.name], name=e.name.replace("UC in-state", "UT Austin"))


PLAN = replace(
    SF,
    name="example: Austin, one kid",
    taxes="TX, MFJ after wedding",
    expenses=[_austin(e) for e in SF.expenses] + _PRESCHOOL
    + [Expense("Extra rideshare with kids (no car)", 400, MONTH, KID_BIRTH_AGES[0], KID_BIRTH_AGES[-1] + 18,
               category="transport")],
)
