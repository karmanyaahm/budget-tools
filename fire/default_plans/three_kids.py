"""Example expense profile: the SF family example with three kids (born at 30, 32 and 35)."""

from dataclasses import replace

from default_plans.sf_family import BASE, WEDDING_AGE, kid
from default_plans.sf_family import PLAN as SF
from firemodel.schema import MONTH, ONCE, RETIRE, Expense

KID_BIRTH_AGES = [30, 32, 35]
KIDS_HOME = (KID_BIRTH_AGES[0], KID_BIRTH_AGES[-1] + 18)

PLAN = replace(
    SF,
    name="example: SF, three kids",
    expenses=[
        *BASE,
        Expense("Wedding", 60_000, ONCE, WEDDING_AGE, category="events"),
        *[e for i, b in enumerate(KID_BIRTH_AGES, 1) for e in kid(i, b)],
        Expense("Bigger place for kids (3BR → 4BR)", 2_800, MONTH, *KIDS_HOME, category="kids"),
        Expense("Kids on employer plan", 300, MONTH, KID_BIRTH_AGES[0], RETIRE, category="kids"),
        Expense("Kids' health coverage after leaving", 700, MONTH, RETIRE, KIDS_HOME[1], category="kids"),
        Expense("Term life insurance", 60, MONTH, KID_BIRTH_AGES[0], KID_BIRTH_AGES[-1] + 25, category="insurance"),
        Expense("Late-life care", 3_000, MONTH, 88, category="health"),
    ],
)
