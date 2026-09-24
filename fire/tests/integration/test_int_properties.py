"""Documented properties of the solver and simulation, checked on the shipped plans (solved once, in parallel,
by the session `solved` fixture)."""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from fireint import cells, solved, COAST, DEFAULT_PLANS, FLAT, RETIRE0, config, make_cfg, plan, scen
from firemodel.schema import X, Income
from firemodel.sim import DAYS, simulate
from firemodel.solve import Solution, solve, sweep, what_if


def best(solved, cell, si=RETIRE0):
    r = solved[cell][si]
    assert r is not None, f"{cell} scenario {si} has no solution"
    return r


# ───────────────────────────── the solved X ─────────────────────────────


@pytest.mark.parametrize("cell,si", [
    ("plan:sf_family", RETIRE0), ("plan:sf_family", COAST), ("plan:sf_family", FLAT),
    ("plan:couple_with_car", RETIRE0), ("tax:TX, single", RETIRE0), ("acct:sf_family", RETIRE0),
    ("plan:sf_to_austin", FLAT),
])
def test_solved_x_passes_and_one_day_less_fails(cells, solved, cell, si):
    """README: the solver finds the shortest X (to the day) that keeps the balance ≥ $0 (or ≥ the flat floor)."""
    cfg = cells[cell][0]
    r = best(solved, cell, si)
    days = round(r.x * DAYS)
    assert r.x * DAYS == pytest.approx(days, abs=1e-6), "X is a whole number of days"
    assert r.ok and simulate(cfg, cfg.scenarios[si], r.x).ok
    assert days > 0
    shorter = simulate(cfg, cfg.scenarios[si], (days - 1) / DAYS)
    assert not shorter.ok and shorter.fail_age is not None


def test_salary_x_is_minimal_within_100_dollars():
    """Income(X, years=N) solves for the salary. 0% growth, no tax: 10 years must pay 20 years of $36,500."""
    cfg = make_cfg(start_age=20, end_age=40, expenses=[_exp(36_500)])
    s = scen([Income(X, years=10)])
    sol = solve(cfg, s)
    assert sol.kind == "amount"
    assert 73_000 <= sol.best.x <= 73_100
    assert not simulate(cfg, s, sol.best.x - 100).ok


def _exp(per_year):
    from firemodel.schema import YEAR, Expense
    return Expense("living", per_year, YEAR, 0)


@pytest.mark.parametrize("name", DEFAULT_PLANS)
def test_goal_ordering(solved, name):
    """Coast (a job pays core expenses until 60) never needs a later stop than Retire to $0, and 'flat from 100'
    (a stricter goal) never an earlier one."""
    r0, coast, flat = (best(solved, f"plan:{name}", si) for si in (RETIRE0, COAST, FLAT))
    assert coast.x_end_age <= r0.x_end_age + 1e-9
    assert flat.x_end_age >= r0.x_end_age - 1e-9


def test_more_starting_money_never_increases_x(solved):
    for si in (RETIRE0, COAST):
        assert best(solved, "rich", si).x <= best(solved, "plan:sf_family", si).x


def test_higher_safety_factor_never_decreases_x(solved):
    for si in (RETIRE0, COAST):
        assert best(solved, "safety+0.1", si).x >= best(solved, "plan:sf_family", si).x


def test_safety_factor_multiplies_every_expense(cells, solved):
    """README: every expense is padded by the safety factor (config.EXPENSE_SAFETY_FACTOR)."""
    from firemodel.plan import annual_total
    cfg = cells["plan:sf_family"][0]
    r = best(solved, "plan:sf_family")
    sf = plan("sf_family")
    k = config.EXPENSE_SAFETY_FACTOR
    assert cfg.safety_factor == k > 1
    for row in r.rows:
        if row.age + 1 <= r.x_end_age or row.age >= math.ceil(r.x_end_age):  # skip the year you stop
            assert row.expenses == pytest.approx(k * annual_total(sf.expenses, row.age, r.x_end_age), rel=1e-9)


@pytest.mark.parametrize("pair", [("TX, MFJ after wedding", "CA, MFJ after wedding"), ("TX, single", "CA, single")])
def test_texas_needs_no_more_x_than_california(solved, pair):
    tx, ca = pair
    for si in (RETIRE0, COAST, FLAT):
        assert best(solved, f"tax:{tx}", si).x <= best(solved, f"tax:{ca}", si).x


def test_married_filing_never_worse_than_single(solved):
    """MFJ here means a $0-income spouse (README), which can only lower tax."""
    for state in ("CA", "TX"):
        for si in (RETIRE0, COAST, FLAT):
            assert best(solved, f"tax:{state}, MFJ after wedding", si).x <= best(solved, f"tax:{state}, single", si).x


def test_social_security_as_income_from_67_never_increases_x(solved):
    """README: no Social Security by default; add it as an Income with start=67."""
    assert best(solved, "social_security").x <= best(solved, "plan:sf_family").x
    assert best(solved, "social_security").rows[-1].gross == pytest.approx(30_000)


# ───────────────────────────── result invariants ─────────────────────────────


@pytest.mark.parametrize("cell", ["plan:sf_family", "plan:three_kids", "acct:sf_family", "acct:single_lean",
                                  "grid_cities:Austin | fast track 200×3 → 320×X | + 55k → 90k at 32 | 401k+Roth+529"])
def test_rows_are_consistent(cells, solved, cell):
    cfg = cells[cell][0]
    for si, r in solved[cell].items():
        assert r is not None and r.ok
        assert [row.age for row in r.rows] == list(range(cfg.start_age, config.END_AGE))  # "to age 112"
        assert r.end_balance == r.rows[-1].balance
        for row in r.rows:
            assert row.balance >= -1e-6, "solvent every day, so every year-end too"
            others = row.k401 + row.roth + row.c529
            assert min(row.k401, row.roth, row.c529) >= -1e-6
            assert 0 <= row.basis <= row.balance - others + 1e-3, "basis ≤ taxable value = balance − accounts"
            if not cfg.accounts.active:
                assert others == 0 and row.contributed == 0 and row.ord_tax == 0
        # the portfolio the day X ends sits between the neighbouring year-end balances (growth ≥ 0 is small)
        assert r.stop_balance is not None and r.stop_balance > 0
        assert r.min_balance_after_x <= r.stop_balance * 1.06


@pytest.mark.parametrize("cell", ["plan:sf_family", "plan:three_kids", "plan:sf_to_austin", "acct:sf_family",
                                  "tax:TX, single"])
def test_flat_from_keeps_balance_at_or_above_its_value_at_the_flat_age(solved, cell):
    r = best(solved, cell, FLAT)
    at_100 = next(row.balance for row in r.rows if row.age == config.FLAT_FROM_AGE - 1)  # value at the start of 100
    later = [row.balance for row in r.rows if row.age >= config.FLAT_FROM_AGE]
    assert later and min(later) >= at_100 - 1e-6


def test_retire_to_zero_actually_draws_down(solved):
    """Retire to $0 ends far below the flat-from-100 goal's end balance (it spends the money)."""
    for name in DEFAULT_PLANS:
        assert best(solved, f"plan:{name}").end_balance < 0.05 * best(solved, f"plan:{name}", FLAT).end_balance


# ───────────────────────────── accounts ─────────────────────────────


@pytest.mark.parametrize("name", DEFAULT_PLANS)
def test_accounts_no_early_penalty_and_drained_for_retire_to_zero(solved, name):
    """With 401(k)+Roth+529: nothing is drawn with a penalty before 59½, and retire-to-$0 / coast leave ~no
    401(k) or Roth at END_AGE (each account funded only up to the need it matches)."""
    for si in (RETIRE0, COAST):
        r = best(solved, f"acct:{name}", si)
        assert sum(row.ord_tax for row in r.rows if row.age < 59) < 100  # ~0 next to a $2M portfolio
        last = r.rows[-1]
        assert last.k401 + last.roth < 1_000
        assert last.c529 < 1_000


@pytest.mark.parametrize("name", DEFAULT_PLANS)
def test_accounts_never_make_x_larger_on_default_plans(solved, name):
    for si in (RETIRE0, COAST):
        assert best(solved, f"acct:{name}", si).x <= best(solved, f"plan:{name}", si).x + 1e-9


def test_accounts_withdrawal_order(solved):
    """Before 59½ the 401(k)/Roth are never drawn (taxable pays); after it the 401(k) is drawn before the Roth."""
    r = best(solved, "acct:sf_family")
    rows = r.rows
    assert max(row.k401 for row in rows) > 0 and max(row.roth for row in rows) > 0
    for a, b in zip(rows, rows[1:]):
        if b.age <= 59:
            assert b.k401 >= a.k401 - 1e-6 and b.roth >= a.roth - 1e-6
        if b.age >= 60 and b.k401 > 1.0:  # 401(k) still has money at year end: the Roth wasn't touched
            assert b.roth >= a.roth - 1e-6
    # contributions stay within the 2026 limits
    lim = config.TAX_ADVANTAGED
    for row in rows:
        assert row.contributed <= lim.k401_limit + lim.roth_limit + lim.c529_limit + 1e-6


def test_529_pays_college_on_default_plan(solved):
    r = best(solved, "acct:sf_family")
    assert max(row.c529 for row in r.rows) > 0
    kid_college = [row for row in r.rows if 51 <= row.age < 55]  # born at 33, college 51-54
    assert kid_college[-1].c529 < 1_000


def test_accounts_on_is_the_default(cells):
    cfg = cells["plan:sf_family"][0]
    assert cfg.accounts == config.TAX_ADVANTAGED == config.ACCOUNTS
    assert config.TAX_ADVANTAGED.k401_limit == 24_500
    assert config.TAX_ADVANTAGED.roth_limit == 7_500
    assert config.TAX_ADVANTAGED.c529_limit == 16_000


# ───────────────────────────── what-if and sweep ─────────────────────────────


def test_what_if_extra_savings_is_monotone(cells, solved):
    cfg = cells["plan:single_lean"][0]
    base = Solution(cfg.scenarios[RETIRE0], "years", best(solved, "plan:single_lean"))
    small = what_if(cfg, base, 1_000, 25)
    big = what_if(cfg, base, 100_000, 25)
    assert 0 <= small <= big
    assert big > 7 * 20, "$100k at 25 should buy months, not days"
    # the shortened X really passes
    d = round(base.best.x * DAYS) - big
    assert simulate(cfg, base.scenario, d / DAYS, ((25, 100_000),)).ok


def test_sweep_is_monotone_around_the_answer(cells, solved):
    """The solver assumes more X never hurts: in the sweep, every X below the answer fails and every X at or
    above it passes."""
    cfg = cells["plan:single_lean"][0]
    sol = Solution(cfg.scenarios[RETIRE0], "years", best(solved, "plan:single_lean"))
    runs = sweep(cfg, sol)
    assert sol.best in runs or any(r.x == sol.best.x for r in runs)
    assert [r.x for r in runs] == sorted(r.x for r in runs)
    for r in runs:
        assert r.ok == (r.x >= sol.best.x - 1e-12)
    ends = [r.end_balance for r in runs]
    assert ends == sorted(ends)
