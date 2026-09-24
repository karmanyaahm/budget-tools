"""Example expense profile: a couple sharing costs from the wedding, with a car, and kids at 30 and 32.
(These were Claude's first invented defaults, before any real budget.)"""

from firemodel.plan import LifePlan
from firemodel.schema import DAY, MONTH, ONCE, WEEK, YEAR, X, Expense, Income

START_AGE = 21
WEDDING_AGE = 27
KID_BIRTH_AGES = [30, 32]
M = WEDDING_AGE


def kid(n: int, born: int) -> list[Expense]:
    return [
        Expense(f"Kid {n}: childcare", 1_500, MONTH, born, born + 5, category="kids"),
        Expense(f"Kid {n}: school-age", 1_000, MONTH, born + 5, born + 18, category="kids"),
        Expense(f"Kid {n}: college", 35_000, YEAR, born + 18, born + 22, category="kids"),
    ]


PLAN = LifePlan(
    name="example: couple with a car",
    start_age=START_AGE,
    start_balance=10_000,
    start_basis=10_000,
    wedding_age=WEDDING_AGE,
    career=[
        Income(150_000, years=2, label="early career"),
        Income(200_000, years=2, label="mid"),
        Income(300_000, years=X, label="high salary"),
    ],
    expenses=[
        Expense("Rent (single)",            1_800, MONTH, START_AGE, M, category="housing"),
        Expense("Groceries (single)",         120, WEEK,  START_AGE, M, category="food"),
        Expense("Health (single)",            250, MONTH, START_AGE, M, category="health"),
        Expense("Housing (couple)",         3_000, MONTH, M, category="housing"),
        Expense("Groceries (couple)",         220, WEEK,  M, category="food"),
        Expense("Health pre-Medicare",        900, MONTH, M, 65, category="health"),
        Expense("Health Medicare+supp",       700, MONTH, 65, category="health"),
        Expense("Late-life care",           3_000, MONTH, 88, category="health"),
        Expense("Coffee / eating out",         15, DAY,   START_AGE, category="food"),
        Expense("Utilities / phone / net",    350, MONTH, START_AGE, category="housing"),
        Expense("Car running costs",          400, MONTH, START_AGE, 90, category="transport"),
        Expense("Car purchase (used Sienna)", 20_000, YEAR, START_AGE + 1, 85, every=10, category="big-ticket"),
        Expense("Travel / fun",             8_000, YEAR,  START_AGE, category="fun"),
        Expense("Misc / buffer",              500, MONTH, START_AGE, category="misc"),
        Expense("Wedding",                 40_000, ONCE,  WEDDING_AGE, category="events"),
        *[e for i, b in enumerate(KID_BIRTH_AGES, 1) for e in kid(i, b)],
    ],
)
