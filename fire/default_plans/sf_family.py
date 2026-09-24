"""Example plan: a San Francisco tech worker, one kid, a mid-size wedding. All numbers are illustrative
(rough 2026 SF prices), not anyone's real budget. Copy this file to custom_plans/ and make it yours.

Spending is YOUR share only (a partner covers their own; see plan.with_partner). No car.
"""

from firemodel.plan import LifePlan, annual_total
from firemodel.schema import MONTH, ONCE, RETIRE, WEEK, YEAR, X, Expense, Income

START_AGE = 22
WEDDING_AGE = 28
KID_BIRTH_AGES = [33]

BASE = [
    # housing: half of a 2BR
    Expense("Rent", 1_900, MONTH, START_AGE, category="housing"),
    Expense("Utilities", 70, MONTH, START_AGE, category="housing"),
    Expense("Internet", 35, MONTH, START_AGE, category="housing"),
    Expense("Renters insurance", 20, MONTH, START_AGE, category="housing"),
    Expense("Moving (amortized)", 50, MONTH, START_AGE, category="housing"),
    Expense("Phone", 45, MONTH, START_AGE, category="bills"),
    # health: employer plan while at the career job; unsubsidized, age-rated individual plan after; then Medicare
    Expense("Health insurance (employer)", 150, MONTH, START_AGE, RETIRE, category="health"),
    Expense("Health insurance (individual)", 600, MONTH, RETIRE, 65, category="health"),
    Expense("Individual health age step 50+", 400, MONTH, 50, 65, category="health"),
    Expense("Individual health age step 58+", 250, MONTH, 58, 65, category="health"),
    Expense("Medicare + supplement", 450, MONTH, 65, category="health"),
    Expense("Dental + vision", 70, MONTH, START_AGE, category="health"),
    Expense("Gym", 80, MONTH, START_AGE, category="health"),
    # getting around, travel
    Expense("Transit + rideshare", 180, MONTH, START_AGE, category="transport"),
    Expense("Bike upkeep", 400, YEAR, START_AGE, category="transport"),
    Expense("Trips (flight + hotel)", 600, MONTH, START_AGE, category="travel"),
    # food: the office feeds you on weekdays until you leave
    Expense("Groceries", 90, WEEK, START_AGE, category="food"),
    Expense("Weekday groceries (after leaving)", 100, WEEK, RETIRE, category="food"),
    Expense("Eating out", 70, WEEK, START_AGE, category="food"),
    # personal / household / fun
    Expense("Personal care", 80, MONTH, START_AGE, category="personal"),
    Expense("Household supplies", 40, MONTH, START_AGE, category="household"),
    Expense("Social", 60, WEEK, START_AGE, category="social"),
    Expense("Tech", 900, YEAR, START_AGE, category="stuff"),
    Expense("Clothes", 800, YEAR, START_AGE, category="stuff"),
    Expense("Subscriptions", 600, YEAR, START_AGE, category="stuff"),
    Expense("Gifts", 800, YEAR, START_AGE, category="stuff"),
    Expense("Furniture + home", 700, YEAR, START_AGE, category="stuff"),
]


def kid(n: int, born: int) -> list[Expense]:
    return [
        Expense(f"Kid {n}: daycare (infant)", 3_000, MONTH, born, born + 1, category="kids"),
        Expense(f"Kid {n}: daycare (1-3)", 2_250, MONTH, born + 1, born + 4, category="kids"),
        Expense(f"Kid {n}: TK/K after-care (4-5)", 1_000, MONTH, born + 4, born + 6, category="kids"),
        Expense(f"Kid {n}: baby/toddler costs (0-5)", 600, MONTH, born, born + 6, category="kids"),
        Expense(f"Kid {n}: activities/camp/food (6-17)", 1_300, MONTH, born + 6, born + 18, category="kids"),
        # the word "college" in the name lets a 529 pay this line
        Expense(f"Kid {n}: college (UC in-state)", 45_000, YEAR, born + 18, born + 22, category="kids"),
    ]


KIDS_HOME = (KID_BIRTH_AGES[0], KID_BIRTH_AGES[-1] + 18)
FAMILY = [
    Expense("Extra bedroom for kids", 1_800, MONTH, *KIDS_HOME, category="kids"),
    Expense("Kids on employer plan", 250, MONTH, KID_BIRTH_AGES[0], RETIRE, category="kids"),
    Expense("Kids' health coverage after leaving", 400, MONTH, RETIRE, KIDS_HOME[1], category="kids"),
    Expense("Term life insurance", 45, MONTH, KID_BIRTH_AGES[0], KID_BIRTH_AGES[-1] + 25, category="insurance"),
]

PLAN = LifePlan(
    name="example: SF, one kid",
    start_age=START_AGE,
    start_balance=5_000,
    start_basis=5_000,
    wedding_age=WEDDING_AGE,
    taxes="CA, MFJ after wedding",
    career=[  # an illustrative ladder; X = years at the last salary
        Income(120_000, years=3, label="new grad"),
        Income(175_000, years=2, label="mid"),
        Income(230_000, years=X, label="senior"),
    ],
    expenses=[
        *BASE,
        Expense("Wedding", 60_000, ONCE, WEDDING_AGE, category="events"),
        *[e for i, b in enumerate(KID_BIRTH_AGES, 1) for e in kid(i, b)],
        *FAMILY,
        Expense("Late-life care", 3_000, MONTH, 88, category="health"),
    ],
)

BASE_BUDGET = annual_total(BASE, START_AGE)  # ≈ what you spend per year before kids (shown by --budget)
