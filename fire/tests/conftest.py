"""Builders for tiny, hand-checkable configs.

Defaults: zero tax (take-home = gross, no capital gains tax), 0% growth, no expenses. With those, every
balance is start + Σ wages − Σ expenses, so each test's expected value can be derived by hand.
Amounts are chosen as multiples of $365/yr so daily amounts are whole dollars and float sums stay exact.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from firemodel.schema import Config, Growth, Scenario, TaxRegime  # noqa: E402
from firemodel.tax import Federal, Fica, NO_STATE_TAX, State, regime  # noqa: E402

DAYS = 365
NO_FICA = Fica(ss_rate=0.0, ss_wage_base=0.0, medicare_rate=0.0, addl_medicare_rate=0.0, addl_medicare_threshold=0.0)


def zero_regime(start=0, end=200, joint=False) -> TaxRegime:
    """No income tax, no capital gains tax."""
    return TaxRegime(start, end, lambda g, e=(), deferred=0.0: g, lambda gain, gross: 0.0, lambda gross: [0.0], joint)


def flat_income_regime(t: float, start=0, end=200, joint=False) -> TaxRegime:
    """Wages taxed at a flat t; no capital gains tax."""
    return TaxRegime(start, end, lambda g, e=(), deferred=0.0: g - t * (g - deferred),
                     lambda gain, gross: 0.0, lambda gross: [0.0], joint)


def fed(std=0.0, brackets=((0, 0.0),), ltcg=((0, 0.0),), niit_rate=0.0, niit_threshold=1e12) -> Federal:
    return Federal(std, list(brackets), list(ltcg), niit_rate, niit_threshold)


def flat_cg_regime(t: float, start=0, end=200, joint=False) -> TaxRegime:
    """Built with regime(): no income tax, capital gains at a flat t (no deduction, no NIIT, no state)."""
    return regime(start, end, fed(ltcg=[(0, t)]), NO_FICA, NO_STATE_TAX, joint=joint)


def make_cfg(start_age=20, end_age=30, balance=0.0, basis=None, expenses=(), taxes=None, growth=None,
             scenarios=(), safety_factor=1.0, max_x_amount=5_000_000) -> Config:
    return Config(
        start_age=start_age,
        end_age=end_age,
        start_year=2000,
        start_balance=balance,
        start_basis=balance if basis is None else basis,
        scenarios=list(scenarios),
        expenses=list(expenses),
        taxes=list(taxes) if taxes is not None else [zero_regime()],
        growth=list(growth) if growth is not None else [Growth(0, 200, 0.0)],
        safety_factor=safety_factor,
        max_x_amount=max_x_amount,
    )


def scen(income, partner=(), share=1.0, flat_from=None, name="s") -> Scenario:
    return Scenario(name, list(income), list(partner), share, flat_from)


__all__ = ["ROOT", "DAYS", "NO_FICA", "NO_STATE_TAX", "State", "zero_regime", "flat_income_regime", "fed",
           "flat_cg_regime", "make_cfg", "scen"]
