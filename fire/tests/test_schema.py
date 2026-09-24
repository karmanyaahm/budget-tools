"""Schema: Income validation, Expense bounds/annual (half-open, ONCE, every-N, RETIRE), X substitution."""

import math

import pytest

from firemodel.schema import (DAY, MONTH, ONCE, RETIRE, WEEK, YEAR, X, Expense, Growth, Income, find_in_range,
                              substitute_x)


def test_period_constants():
    assert (DAY, WEEK, MONTH, YEAR, ONCE) == (365, 52, 12, 1, 0)


# ───────────────────────────── Income ─────────────────────────────

def test_income_needs_exactly_one_of_years_or_until():
    with pytest.raises(ValueError):
        Income(100)
    with pytest.raises(ValueError):
        Income(100, years=2, until=25)
    Income(100, years=2)
    Income(100, until=25)
    Income(X, years=2)
    Income(100, years=X)


def test_substitute_x_amount_and_years():
    sched = [Income(1, years=2), Income(X, years=3), Income(5, years=X)]
    out = substitute_x(sched, 7.0)
    assert [(s.amount, s.years) for s in out] == [(1, 2), (7.0, 3), (5, 7.0)]
    assert sched[1].amount is X  # original untouched (frozen dataclass, replace())


# ───────────────────────────── Expense.bounds ─────────────────────────────

def test_bounds_plain_and_open_end():
    assert Expense("a", 1, YEAR, 20, 30).bounds() == (20, 30)
    assert Expense("a", 1, YEAR, 20).bounds() == (20, math.inf)


def test_bounds_retire_resolved_and_never():
    e = Expense("a", 1, YEAR, RETIRE, 65)
    assert e.uses_retire
    assert e.bounds(33.5) == (33.5, 65)
    assert e.bounds(None) == (math.inf, 65)  # never retires → never starts
    e2 = Expense("b", 1, YEAR, 20, RETIRE)
    assert e2.bounds(33.5) == (20, 33.5)
    assert e2.bounds(None) == (20, math.inf)  # never retires → never ends
    assert not Expense("c", 1, YEAR, 20, 30).uses_retire


# ───────────────────────────── Expense.annual ─────────────────────────────

def test_annual_half_open_and_per():
    # $100/month for [22, 24): ages 22 and 23 pay 1200; 21 and 24 pay 0.
    e = Expense("rent", 100, MONTH, 22, 24)
    assert [e.annual(a) for a in (21, 22, 23, 24)] == [0, 1200, 1200, 0]
    assert Expense("d", 10, DAY, 0).annual(5) == 3650
    assert Expense("w", 10, WEEK, 0).annual(5) == 520


def test_annual_once_charged_at_floor_of_start():
    e = Expense("wedding", 50_000, ONCE, 25.6)
    assert [e.annual(a) for a in (24, 25, 26)] == [0, 50_000, 0]


def test_annual_every_n_counts_from_ceil_start():
    # Car every 3 years from 21 until 31: 21, 24, 27, 30.
    e = Expense("car", 20_000, YEAR, 21, 31, every=3)
    assert [a for a in range(18, 35) if e.annual(a)] == [21, 24, 27, 30]
    # Fractional start 21.4: first eligible age is ceil(21.4) = 22; then 25, 28.
    e2 = Expense("car", 20_000, YEAR, 21.4, 30, every=3)
    assert [a for a in range(18, 35) if e2.annual(a)] == [22, 25, 28]


def test_annual_with_retire():
    e = Expense("health", 500, MONTH, RETIRE, 65)
    assert e.annual(40, retire=35) == 6000
    assert e.annual(34, retire=35) == 0
    assert e.annual(40, retire=None) == 0  # never retires


# ───────────────────────────── find_in_range ─────────────────────────────

def test_find_in_range_half_open():
    gs = [Growth(20, 60, 0.05), Growth(60, 100, 0.04)]
    assert find_in_range(gs, 59, "g").rate == 0.05
    assert find_in_range(gs, 60, "g").rate == 0.04
    with pytest.raises(ValueError):
        find_in_range(gs, 100, "g")
    with pytest.raises(ValueError):
        find_in_range(gs, 19, "g")
