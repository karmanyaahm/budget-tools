"""LifePlan.move_to: expenses and taxes switch cities at an age."""

import math

import pytest

from conftest import make_cfg, scen
from firemodel.plan import LifePlan
from firemodel.schema import ONCE, RETIRE, YEAR, X, Expense, Income
from firemodel.sim import daily_expenses, simulate


def plan(name, rent, taxes, wedding=None, extra=()):
    exps = [Expense("rent", rent, YEAR, 20), *extra]
    if wedding:
        exps.append(Expense("wedding", wedding, ONCE, 22))
    return LifePlan(name, 20, 0, 0, None, [Income(36_500, years=X)], exps, taxes=taxes)


def test_expense_clipping():
    e = Expense("rent", 3_650, YEAR, 20, before=22)
    assert [e.annual(a) for a in (20, 21, 22)] == [3_650, 3_650, 0]
    e = Expense("rent", 3_650, YEAR, 20, after=22)
    assert [e.annual(a) for a in (21, 22, 30)] == [0, 3_650, 3_650]


def test_once_outside_window_is_dropped_not_moved():
    # A wedding at 22 in the destination plan (after=25) must not be charged at 25.
    assert Expense("w", 1_000, ONCE, 22, after=25).annual(25) == 0
    assert Expense("w", 1_000, ONCE, 22, before=25).annual(22) == 1_000


def test_every_n_cadence_keeps_its_original_start():
    # A car every 10 years from 22, clipped to start at 30: still charged at 32 (not 30).
    car = Expense("car", 20_000, YEAR, 22, every=10, after=30)
    assert [a for a in range(20, 45) if car.annual(a)] == [32, 42]


def test_retire_bounds_still_work_with_clipping():
    # Health from RETIRE to 65, only in the new city from 30: retire at 28 → charged from 30.
    h = Expense("health", 1_000, YEAR, RETIRE, 65, after=30)
    assert h.bounds(28) == (30, 65)
    assert h.bounds(40) == (40, 65)


def test_move_switches_expenses_and_taxes():
    sf = plan("sf", 36_500, "CA, MFJ after wedding", wedding=5_000)
    tx = plan("tx", 18_250, "TX, MFJ after wedding", wedding=9_000)
    moved = sf.move_to(tx, 25)
    rent = {a: sum(e.annual(a) for e in moved.expenses if e.name == "rent") for a in (24, 25)}
    assert rent == {24: 36_500, 25: 18_250}
    weddings = [a for a in range(20, 40) for e in moved.expenses if e.name == "wedding" and e.annual(a)]
    assert weddings == [22]  # only SF's wedding (before the move) is charged, once
    assert moved.taxes == [(20, "CA, MFJ after wedding"), (25, "TX, MFJ after wedding")]


def test_move_tax_schedule_in_config():
    from config import make_config
    sf = plan("sf", 36_500, "CA, MFJ after wedding")
    cfg = make_config(sf.move_to(plan("tx", 18_250, "TX, MFJ after wedding"), 25))
    # $100k of wages keeps more in TX than in CA.
    at = lambda age: next(r for r in cfg.taxes if r.start <= age < r.end).income_left(100_000, (100_000,))  # noqa: E731
    assert at(24) < at(25)
    assert min(r.start for r in cfg.taxes) == 20 and max(r.end for r in cfg.taxes) == cfg.end_age


def test_income_starting_at_retire_overlaps_and_adds():
    # Job 36,500 for X=1 year from 20, then 3,650/yr for 2 years starting when X ends (overlapping nothing else).
    from firemodel.sim import lay_out
    spans, x_end = lay_out([Income(36_500, years=X), Income(3_650, start=RETIRE, years=2)], 20, 1)
    assert x_end == 21 and spans[1][:2] == (21, 23)
    cfg = make_cfg(20, 24)
    r = simulate(cfg, scen([Income(36_500, years=X), Income(3_650, start=RETIRE, years=2)]), 1)
    assert r.rows[-1].balance == pytest.approx(36_500 + 7_300)


def test_retire_income_before_x_is_an_error():
    from firemodel.sim import lay_out
    with pytest.raises(ValueError):
        lay_out([Income(1, start=RETIRE, years=1), Income(1, years=X)], 20, 1)
