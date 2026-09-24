"""LifePlan.core_expenses / coast(), and how coast segments lay out after X."""

import pytest

from conftest import DAYS, make_cfg, scen
from firemodel.plan import LifePlan, annual_total
from firemodel.schema import RETIRE, MONTH, ONCE, RETIRE, YEAR, X, Expense, Income
from firemodel.sim import lay_out, simulate

EXPENSES = [
    Expense("rent", 1_000, MONTH, 20, category="housing"),                 # 12k/yr, always
    Expense("food", 500, MONTH, 20, 25, category="food"),                  # 6k/yr for 20..24
    Expense("daycare", 2_000, MONTH, 22, 24, category="kids"),             # excluded
    Expense("wedding", 30_000, ONCE, 23, category="events"),               # excluded
    Expense("car", 20_000, YEAR, 20, every=5, category="big-ticket"),      # excluded
    Expense("work lunch", 3_650, YEAR, 20, RETIRE, category="food"),       # ends at RETIRE → counted as passed
    Expense("health", 400, MONTH, RETIRE, 26, category="health"),          # starts at RETIRE → active through 25
    Expense("party", 5_000, ONCE, RETIRE, category="fun"),                 # ONCE at −inf → never
]


def plan(**kw):
    kw.setdefault("coast_margin", (0, None))  # these tests check core-only coast; margin tested below
    return LifePlan(name="p", start_age=20, start_balance=0, start_basis=0, wedding_age=None,
                    career=[Income(100_000, years=X)], expenses=EXPENSES, coast_until=27, **kw)


@pytest.mark.parametrize("age, expected", [
    (20, 12_000 + 6_000 + 4_800),  # rent + food + health (RETIRE treated as passed)
    (23, 12_000 + 6_000 + 4_800),  # wedding and daycare excluded
    (25, 12_000 + 4_800),          # food ended at 25
    (26, 12_000),                  # health ended at 26
])
def test_core_expenses(age, expected):
    assert plan().core_expenses(age) == pytest.approx(expected)


def test_core_expenses_custom_exclusions():
    # Excluding only "housing": rent drops out; kids/events/big-ticket come back in at age 20 (car) and 23.
    p = plan(coast_exclude={"housing"})
    assert p.core_expenses(20) == pytest.approx(6_000 + 4_800 + 20_000)
    assert p.core_expenses(23) == pytest.approx(6_000 + 4_800 + 24_000 + 30_000)


def test_annual_total():
    # Age 22, never retiring: rent 12k + food 6k + daycare 24k + work lunch 3.65k.
    assert annual_total(EXPENSES, 22) == pytest.approx(12_000 + 6_000 + 24_000 + 3_650)


def test_coast_segments_one_per_age():
    segs = plan().coast()
    assert [s.until for s in segs] == list(range(21, 28))
    assert [s.amount for s in segs] == pytest.approx([22_800] * 5 + [16_800, 12_000])
    assert all(s.years is None and s.start is None for s in segs)


def test_coast_laid_after_x():
    # X = 2.4 → stop at 22.4. Coast segments "until 21/22" are zero-length at 22.4; "until 23" runs 22.4 → 23.
    p = plan()
    spans, x_end = lay_out(p.career + p.coast(), 20, 2.4)
    assert x_end == pytest.approx(22.4)
    assert spans[0] == (20, pytest.approx(22.4), 100_000, "")
    assert [(s, e) for s, e, _, _ in spans[1:3]] == [(pytest.approx(22.4), pytest.approx(22.4))] * 2
    assert spans[3][:2] == (pytest.approx(22.4), 23)
    assert [(s, e) for s, e, _, _ in spans[4:]] == [(23, 24), (24, 25), (25, 26), (26, 27)]


def test_coast_x_past_coast_until_is_all_zero_length():
    p = plan()
    spans, _ = lay_out(p.career + p.coast(), 20, 8)
    assert all(e == s == 28 for s, e, _, _ in spans[1:])


def test_coast_income_in_sim():
    # Zero tax. Only rent (12k/yr, $32.877/day). Work 100k for X = 1 year, coast pays 12k/yr until 23.
    # Year 0: +100k − 12k = 88k; years 1, 2: coast = rent → flat; years 3, 4: −12k each → 64k.
    p = LifePlan("p", 20, 0, 0, None, [Income(100_000, years=X)], [EXPENSES[0]], coast_until=23, coast_margin=(0, None))
    cfg = make_cfg(20, 25, expenses=p.expenses)
    r = simulate(cfg, scen(p.career + p.coast()), 1)
    assert [row.balance for row in r.rows] == pytest.approx([88_000, 88_000, 88_000, 76_000, 64_000])
    assert [row.gross for row in r.rows] == pytest.approx([100_000, 12_000, 12_000, 0, 0])


def test_coast_starts_mid_year_to_the_day():
    # X = 1.2 → stop on day 438; the "until 22" coast segment covers days [438, 730) = 292 days of 12k/yr.
    p = LifePlan("p", 20, 0, 0, None, [Income(100_000, years=X)], [EXPENSES[0]], coast_until=23, coast_margin=(0, None))
    cfg = make_cfg(20, 25, expenses=p.expenses)
    r = simulate(cfg, scen(p.career + p.coast()), 1.2)
    assert r.rows[1].gross == pytest.approx(100_000 * 73 / DAYS + 12_000 * 292 / DAYS)



def test_coast_margin_adds_extra_income_after_x_until_coast_until():
    # Coast pays core (36,500) + a 10,000 margin from the end of X until 23.
    p = LifePlan("p", 20, 0, 0, None, [Income(100_000, years=X)], [EXPENSES[0]], coast_until=23,
                 coast_margin=(10_000, None))
    margin = p.coast()[-1]
    assert (margin.amount, margin.start, margin.until) == (10_000, RETIRE, 23)
    p = LifePlan("p", 20, 0, 0, None, [Income(100_000, years=X)], [EXPENSES[0]], coast_until=23,
                 coast_margin=(10_000, 2))
    assert p.coast()[-1].years == 2
