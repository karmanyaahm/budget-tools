"""Solver: bisection to the day (years-X) or to $100 (salary-X), sweep, and what_if.

Base case (zero tax, zero growth, $0 start): ages 20..30 (T = 10 years), spending c = $36.5k/yr ($100/day) the
whole time, salary s for X years. The balance rises while working and falls after, so its minimum is the last
day: s·X − c·T. The minimal X in days is d = ceil(365·c·T / s).
"""

import pytest

from conftest import DAYS, flat_income_regime, make_cfg, scen
from firemodel.schema import RETIRE, YEAR, X, Expense, Income
from firemodel.sim import simulate
from firemodel.solve import Solution, solve, sweep, what_if, x_kind

C, T = 36_500, 10


def base_cfg(**kw):
    kw.setdefault("expenses", [Expense("life", C, YEAR, 20)])
    return make_cfg(20, 20 + T, **kw)


# ───────────────────────────── x_kind ─────────────────────────────


def test_x_kind():
    assert x_kind(scen([Income(1, years=X)])) == "years"
    assert x_kind(scen([Income(X, years=1)])) == "amount"
    assert x_kind(scen([Income(1, years=1)], partner=[Income(X, years=1)])) == "amount"


@pytest.mark.parametrize("income, partner", [
    ([Income(1, years=1)], []),                              # no X
    ([Income(X, years=1), Income(1, years=X)], []),          # two X's
    ([Income(1, years=X)], [Income(X, years=1)]),            # one each side
    ([Income(X, years=X)], []),                              # both on one segment
])
def test_x_kind_rejects(income, partner):
    with pytest.raises(ValueError):
        x_kind(scen(income, partner))


# ───────────────────────────── years-X ─────────────────────────────


@pytest.mark.parametrize("s, days", [
    (100_000, 1333),   # 365 × 365,000 / 100,000 = 1332.25 → 1333
    (73_001, 1825),    # 365 × 365,000 / 73,001 = 1824.98 → 1825 (5 years)
    (365_000, 365),    # 365 × 365,000 / 365,000 = 365 exactly; day sums of $1000 − $100 are exact in float
    (200_000, 667),    # 666.125 → 667
])
def test_solve_years_to_the_day(s, days):
    cfg = base_cfg()
    sc = scen([Income(s, years=X)])
    sol = solve(cfg, sc)
    assert sol.kind == "years" and sol.best is not None
    assert round(sol.best.x * DAYS) == days
    assert sol.best.ok
    assert not simulate(cfg, sc, (days - 1) / DAYS).ok  # one day less fails
    assert sol.best.x_end_age == pytest.approx(20 + days / DAYS)


def test_solve_years_with_flat_income_tax():
    # 20% tax on 125k → 100k net, same as the untaxed 100k case: 1333 days.
    cfg = base_cfg(taxes=[flat_income_regime(0.2)])
    assert round(solve(cfg, scen([Income(125_000, years=X)])).best.x * DAYS) == 1333


def test_solve_years_with_start_balance():
    # Starting with $165.1k leaves 365k − 165.1k = 199.9k to earn: ceil(365 × 199.9k/100k) = ceil(729.6) = 730 days.
    cfg = base_cfg(balance=165_100)
    assert round(solve(cfg, scen([Income(100_000, years=X)])).best.x * DAYS) == 730


def test_solve_years_with_prior_segment():
    # One year at 36.5k first (breaks even), then X at 100k must fund the other 9 years × 36.5k = 328.5k:
    # ceil(365 × 328.5k / 100k) = ceil(1199.03) = 1200 days, ending at 21 + 1200/365.
    cfg = base_cfg()
    sol = solve(cfg, scen([Income(C, years=1), Income(100_000, years=X)]))
    assert round(sol.best.x * DAYS) == 1200
    assert sol.best.x_end_age == pytest.approx(21 + 1200 / DAYS)


def test_solve_years_zero_when_already_rich():
    cfg = base_cfg(balance=C * T)
    sol = solve(cfg, scen([Income(100_000, years=X)]))
    assert sol.best.x == 0 and sol.best.ok


def test_solve_years_none_when_impossible():
    # Salary below spending: even working all 10 years leaves 10 × (30k − 36.5k) < 0.
    cfg = base_cfg()
    sol = solve(cfg, scen([Income(30_000, years=X)]))
    assert sol.best is None


def test_solve_years_flat_from_retire_needs_growth_to_cover_spending():
    # flat_from=RETIRE with zero growth: any day of spending after stopping breaks the floor, so the only
    # passing X is working to the end of the horizon (X = T, and the floor day is never reached).
    cfg = base_cfg()
    sol = solve(cfg, scen([Income(100_000, years=X)], flat_from=RETIRE))
    assert round(sol.best.x * DAYS) == T * DAYS


# ───────────────────────────── salary-X ─────────────────────────────


def test_solve_salary_within_100():
    # 5 years at salary X must fund 10 years × 36.5k → X* = 73,000. Bisection returns hi, with hi − lo ≤ 100.
    cfg = base_cfg()
    sc = scen([Income(X, years=5)])
    sol = solve(cfg, sc)
    assert sol.kind == "amount"
    assert 73_000 <= sol.best.x <= 73_100
    assert sol.best.ok and not simulate(cfg, sc, 72_990).ok


def test_solve_salary_with_tax():
    # 25% flat: net 0.75·X × 5 = 365k → X* = 97,333.33.
    cfg = base_cfg(taxes=[flat_income_regime(0.25)])
    x = solve(cfg, scen([Income(X, years=5)])).best.x
    assert 365_000 / 5 / 0.75 <= x <= 365_000 / 5 / 0.75 + 100


def test_solve_salary_capped():
    # max_x_amount 50k < 73k needed → no solution.
    cfg = base_cfg(max_x_amount=50_000)
    assert solve(cfg, scen([Income(X, years=5)])).best is None


def test_solve_salary_zero_when_not_needed():
    cfg = base_cfg(balance=C * T)
    assert solve(cfg, scen([Income(X, years=5)])).best.x == 0


# ───────────────────────────── what_if ─────────────────────────────


def test_what_if_zero_deposit_is_zero():
    cfg = base_cfg()
    base = solve(cfg, scen([Income(100_000, years=X)]))
    assert what_if(cfg, base, 0, 20) == 0
    assert what_if(cfg, base, 0, 25) == 0


@pytest.mark.parametrize("age", [20, 21.5, 23])
def test_what_if_deposit_saves_days(age):
    # A $50k deposit (while still working, so the balance never dips earlier) cuts the need to 315k:
    # new X = ceil(365 × 315,000 / 100,000) = ceil(1149.75) = 1150. Saved 1333 − 1150 = 183 days.
    # (A deposit D shortens X by D/s years, i.e. one year of *gross salary*, since spending continues regardless.)
    cfg = base_cfg()
    base = solve(cfg, scen([Income(100_000, years=X)]))
    assert what_if(cfg, base, 50_000, age) == 183


def test_what_if_one_year_of_salary_saves_a_year():
    # s = 365k: base 365 days (1 year). A $182.5k deposit halves it: 365 × 182.5k/365k = 182.5 → 183 → saves 182.
    cfg = base_cfg()
    base = solve(cfg, scen([Income(365_000, years=X)]))
    assert round(base.best.x * DAYS) == 365
    assert what_if(cfg, base, 182_500, 20) == 182
    assert what_if(cfg, base, 365_000, 20) == 365  # X → 0


def test_what_if_salary_kind():
    # Salary-X: a $50k deposit lowers the needed salary by 50k/5 = 10k (each answer within $100).
    cfg = base_cfg()
    base = solve(cfg, scen([Income(X, years=5)]))
    assert what_if(cfg, base, 50_000, 20) == pytest.approx(10_000, abs=100)


def test_what_if_none_without_base_solution():
    cfg = base_cfg()
    base = solve(cfg, scen([Income(30_000, years=X)]))
    assert what_if(cfg, base, 1_000, 20) is None


# ───────────────────────────── sweep ─────────────────────────────


def test_sweep_years():
    # best = 1333 days ≈ 3.65 years → whole years 0..min(10, ceil(3.65) + 5 = 9), plus the best itself.
    cfg = base_cfg()
    sol = solve(cfg, scen([Income(100_000, years=X)]))
    runs = sweep(cfg, sol)
    xs = [r.x for r in runs]
    assert xs == sorted(xs)
    assert xs == sorted(list(range(10)) + [1333 / DAYS])
    # Balance at the end is linear in X: 100k·X − 365k.
    for r in runs:
        assert r.end_balance == pytest.approx(100_000 * r.x - 365_000, abs=1e-6)
        assert r.ok == (r.x >= 1333 / DAYS)


def test_sweep_salary():
    cfg = base_cfg()
    sol = solve(cfg, scen([Income(X, years=5)]))
    runs = sweep(cfg, sol)
    top = sol.best.x * 2
    assert len(runs) == 21  # 21 grid points; best (= top/2 = grid point 10) is deduplicated by x
    assert runs[0].x == 0 and runs[-1].x == pytest.approx(top)
    assert sol.best in runs


def test_solution_dataclass_defaults():
    sol = Solution(scen([]), "years", None)
    assert sol.sweep == []
