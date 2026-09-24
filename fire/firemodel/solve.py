"""Find the smallest X (years to the day, or salary) that keeps the portfolio solvent through END_AGE.

Assumes more X never hurts (more years at the high salary, or a higher salary), so bisection works.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .schema import X, Config, Scenario
from .sim import DAYS, Result, simulate


@dataclass
class Solution:
    scenario: Scenario
    kind: str  # "years" or "amount"
    best: Result | None  # minimal passing run, None if nothing up to the cap works
    sweep: list[Result] = field(default_factory=list)  # only filled by sweep()


def x_kind(scenario: Scenario) -> str:
    segs = [s for s in scenario.income + scenario.partner_income if s.amount is X or s.years is X]
    if len(segs) != 1:
        raise ValueError(f"Scenario {scenario.name!r} must contain exactly one X (found {len(segs)})")
    if segs[0].amount is X and segs[0].years is X:
        raise ValueError(f"Scenario {scenario.name!r}: X can't be both amount and years")
    return "amount" if segs[0].amount is X else "years"


def _smallest(run, lo: float, hi: float, tol: float) -> Result | None:
    """Smallest v in [lo, hi] (to within tol) whose run(v) passes; None if even run(hi) fails.
    tol=1 means integer steps (days)."""
    r = run(lo)
    if r.ok:
        return r
    best = run(hi)
    if not best.ok:
        return None
    while hi - lo > tol:
        mid = (lo + hi) // 2 if tol == 1 else (lo + hi) / 2
        r = run(mid)
        if r.ok:
            hi, best = mid, r
        else:
            lo = mid
    return best


def _search(cfg: Config, scenario: Scenario, kind: str, deposits, hi: float) -> Result | None:
    if kind == "years":
        return _smallest(lambda d: simulate(cfg, scenario, d / DAYS, deposits), 0, round(hi * DAYS), 1)
    return _smallest(lambda a: simulate(cfg, scenario, a, deposits), 0.0, hi, 100.0)


def solve(cfg: Config, scenario: Scenario, deposits=()) -> Solution:
    kind = x_kind(scenario)
    cap = cfg.end_age - cfg.start_age if kind == "years" else cfg.max_x_amount
    return Solution(scenario, kind, _search(cfg, scenario, kind, deposits, cap))


def sweep(cfg: Config, sol: Solution) -> list[Result]:
    """Runs around the answer for the --sweep table/chart (whole years, or 20 salary steps)."""
    if sol.kind == "years":
        top = min(cfg.end_age - cfg.start_age, math.ceil(sol.best.x) + 5 if sol.best else cfg.end_age - cfg.start_age)
        xs = list(range(top + 1))
    else:
        top = sol.best.x * 2 if sol.best and sol.best.x > 0 else cfg.max_x_amount
        xs = [top * i / 20 for i in range(21)]
    runs = [simulate(cfg, sol.scenario, x) for x in xs] + ([sol.best] if sol.best else [])
    return sorted({r.x: r for r in runs}.values(), key=lambda r: r.x)


def what_if(cfg: Config, base: Solution, amount: float, age: float) -> float | None:
    """Save an extra `amount` (after tax) at `age`: how much smaller does X get compared with `base`?
    For years-X the answer is in days (divide by 7 for weeks); for salary-X it's $/yr.
    Returns None if the base had no solution."""
    if base.best is None:
        return None
    r = _search(cfg, base.scenario, base.kind, ((age, amount),), base.best.x)
    new = r.x if r else base.best.x  # extra money only helps, so the base answer still passes
    return round((base.best.x - new) * DAYS) if base.kind == "years" else base.best.x - new
