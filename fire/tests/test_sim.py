"""Daily simulation. Unless a test says otherwise: zero tax, 0% growth, so
balance = start + Σ wages − Σ expenses exactly, and day k of the run is age start_age + k/365."""

import math

import pytest

from conftest import DAYS, NO_FICA, fed, flat_cg_regime, flat_income_regime, make_cfg, scen, zero_regime
from firemodel.schema import DAY, MONTH, ONCE, RETIRE, WEEK, YEAR, X, Expense, Growth, Income, TaxRegime
from firemodel.sim import (cg_curve, daily_expenses, daily_wages, day_index, expenses_by_category, lay_out, sell_for,
                           simulate)
from firemodel.tax import NO_STATE_TAX, regime

# ───────────────────────────── day_index ─────────────────────────────


@pytest.mark.parametrize("age, day", [(20, 0), (21, 365), (20.2, 73), (20.4, 146), (20.5, 183), (22.8, 1022)])
def test_day_index(age, day):
    # ceil((age − 20) × 365): 0.2 yr = 73 days exactly; 0.5 yr = 182.5 → day 183.
    assert day_index(age, 20) == day


# ───────────────────────────── lay_out ─────────────────────────────


def test_lay_out_back_to_back_and_x_years():
    # 21 → +2 → 23 → +X(3.5) → 26.5 → until 30.
    sched = [Income(100, years=2, label="a"), Income(300, years=X, label="x"), Income(50, until=30, label="c")]
    spans, x_end = lay_out(sched, 21, 3.5)
    assert spans == [(21, 23, 100, "a"), (23, 26.5, 300, "x"), (26.5, 30, 50, "c")]
    assert x_end == 26.5


def test_lay_out_x_amount():
    spans, x_end = lay_out([Income(X, years=4)], 20, 123_000)
    assert spans == [(20, 24, 123_000, "")]
    assert x_end == 24


def test_lay_out_explicit_start_and_zero_length_after_x():
    # X runs to 33; "until 30" coast comes out zero-length at 33; an explicit start=40 segment is placed at 40.
    sched = [Income(300, years=X), Income(50, until=30), Income(10, start=40, years=5)]
    spans, x_end = lay_out(sched, 20, 13)
    assert spans == [(20, 33, 300, ""), (33, 33, 50, ""), (40, 45, 10, "")]
    assert x_end == 33


def test_lay_out_no_x():
    spans, x_end = lay_out([Income(1, years=1)], 20, 99)
    assert x_end is None and spans == [(20, 21, 1, "")]


def test_lay_out_empty():
    assert lay_out([], 20, 5) == ([], None)


# ───────────────────────────── daily_wages ─────────────────────────────


def test_daily_wages_whole_year_is_salary_over_365():
    w = daily_wages([(20, 21, 36_500, "")], 20, 2 * DAYS)
    assert w[:DAYS] == [100.0] * DAYS and w[DAYS:] == [0.0] * DAYS


def test_daily_wages_fractional_end_prorates_by_days():
    # A job ending at 20.4 pays days [0, 146): 146/365 of the salary.
    w = daily_wages([(20, 20.4, 36_500, "")], 20, DAYS)
    assert sum(w) == pytest.approx(36_500 * 146 / 365)
    assert w[145] == 100 and w[146] == 0


def test_daily_wages_ending_at_half_year_pays_183_days():
    # 20.5 → ceil(182.5) = day 183, so 183 days (not exactly half: 365 is odd).
    w = daily_wages([(20, 20.5, 36_500, "")], 20, DAYS)
    assert sum(w) == pytest.approx(18_300)


def test_daily_wages_overlapping_spans_add_and_clip_to_horizon():
    w = daily_wages([(19, 21, 365, ""), (20.2, 25, 730, "")], 20, DAYS)
    # before 20 clipped; day 73 onward both spans: 1 + 2 per day.
    assert w[0] == 1 and w[72] == 1 and w[73] == 3
    assert sum(w) == pytest.approx(365 + 730 * (365 - 73) / 365)


# ───────────────────────────── daily_expenses ─────────────────────────────


def _exp_cfg(*expenses, start=20, end=25, safety=1.0):
    return make_cfg(start, end, expenses=expenses, safety_factor=safety)


def test_expense_accrues_evenly_per_day():
    # $36,500/yr = $100 every day; $10/day × 365 = $3,650/yr → $10/day.
    d = daily_expenses(_exp_cfg(Expense("a", 36_500, YEAR, 20), Expense("b", 10, DAY, 20)), None)
    assert d == pytest.approx([110.0] * (5 * DAYS))


def test_expense_week_and_month_rates():
    # $73/week × 52 = $3,796/yr → 3796/365 = $10.40/day. $365/month × 12 = $4,380/yr → $12/day.
    d = daily_expenses(_exp_cfg(Expense("w", 73, WEEK, 20), Expense("m", 365, MONTH, 20)), None)
    assert d[0] == pytest.approx(10.4 + 12)
    assert sum(d[:DAYS]) == pytest.approx(3_796 + 4_380)


def test_expense_half_open_range():
    # [21, 23) inside a 20..25 horizon: days 365..1094.
    d = daily_expenses(_exp_cfg(Expense("a", 36_500, YEAR, 21, 23)), None)
    assert d[364] == 0 and d[365] == 100 and d[3 * DAYS - 1] == 100 and d[3 * DAYS] == 0
    assert sum(d) == pytest.approx(73_000)


def test_expense_starting_before_horizon_and_open_ended():
    # Starts at 10 (before the horizon) with no end: every day of the horizon.
    d = daily_expenses(_exp_cfg(Expense("a", 36_500, YEAR, 10)), None)
    assert sum(d) == pytest.approx(5 * 36_500)


def test_expense_fractional_start():
    # Starting at 20.2 = day 73: 292 days in the first year.
    d = daily_expenses(_exp_cfg(Expense("a", 36_500, YEAR, 20.2, 21)), None)
    assert sum(d) == pytest.approx(100 * 292) and d[72] == 0 and d[73] == 100


def test_once_lump_on_its_day():
    # ONCE at 22.4 → day 2×365 + 146 = 876.
    d = daily_expenses(_exp_cfg(Expense("w", 5_000, ONCE, 22.4)), None)
    assert d[876] == 5_000 and sum(d) == 5_000


def test_every_n_lumps_on_first_day_of_age_year():
    # $1,000/month every 2 years from 20: lumps of 12,000 on days 0, 730, 1460 (ages 20, 22, 24).
    d = daily_expenses(_exp_cfg(Expense("c", 1_000, MONTH, 20, every=2)), None)
    assert [i for i, v in enumerate(d) if v] == [0, 730, 1460]
    assert d[0] == 12_000


def test_every_n_with_fractional_start_starts_at_ceil():
    # every 2 from 20.3: first eligible age ceil(20.3) = 21, then 23 → days 365, 1095.
    d = daily_expenses(_exp_cfg(Expense("c", 500, YEAR, 20.3, every=2)), None)
    assert [i for i, v in enumerate(d) if v] == [365, 1095]


def test_safety_factor_scales_every_expense():
    d = daily_expenses(_exp_cfg(Expense("a", 36_500, YEAR, 20), Expense("o", 1_000, ONCE, 21), safety=1.2), None)
    assert d[0] == pytest.approx(120) and d[365] == pytest.approx(120 + 1_200)


def test_retire_bounded_expenses_switch_at_retire_day():
    # Retire at 21.4 → day 365 + 146 = 511. "work food" ends there, "health" starts there.
    cfg = _exp_cfg(Expense("work", 36_500, YEAR, 20, RETIRE), Expense("health", 73_000, YEAR, RETIRE, 24))
    d = daily_expenses(cfg, 21.4)
    assert d[510] == pytest.approx(100) and d[511] == pytest.approx(200)
    assert d[4 * DAYS - 1] == pytest.approx(200) and d[4 * DAYS] == 0
    assert sum(d) == pytest.approx(100 * 511 + 200 * (4 * DAYS - 511))


def test_retire_none_means_never_retires():
    cfg = _exp_cfg(Expense("work", 36_500, YEAR, 20, RETIRE), Expense("health", 73_000, YEAR, RETIRE))
    assert sum(daily_expenses(cfg, None)) == pytest.approx(5 * 36_500)


def test_once_at_retire():
    cfg = _exp_cfg(Expense("party", 999, ONCE, RETIRE))
    d = daily_expenses(cfg, 23)
    assert d[3 * DAYS] == 999 and sum(d) == 999


def test_expenses_by_category_matches_daily_sum_for_integer_bounds():
    exps = [Expense("a", 100, MONTH, 21, 23, category="home"), Expense("b", 50, WEEK, 20, category="food"),
            Expense("c", 7_000, ONCE, 22, category="events"), Expense("d", 1_000, YEAR, 20, every=2)]
    cfg = _exp_cfg(*exps, safety=1.1)
    d = daily_expenses(cfg, None)
    cats = expenses_by_category(cfg)
    assert set(cats) == {"home", "food", "events", "other"}
    for y in range(5):
        by_cat = sum(v[y] for v in cats.values())
        assert by_cat == pytest.approx(sum(d[y * DAYS:(y + 1) * DAYS])), y


# Regression: ONCE lumps outside [start_age, end_age) used to be clamped onto day 0 / the last day.
@pytest.mark.parametrize("when", [15, 25, 30])
def test_once_outside_horizon_is_not_charged(when):
    cfg = _exp_cfg(Expense("x", 5_000, ONCE, when), start=20, end=25)
    assert sum(sum(v) for v in expenses_by_category(cfg).values()) == 0
    assert sum(daily_expenses(cfg, None)) == 0


# ───────────────────────────── balance bookkeeping (zero tax, zero growth) ─────────────────────────────


def test_balance_is_start_plus_wages_minus_expenses():
    # Start 10k. Wage 73k/yr for 3 years. Expense 36.5k/yr for 5 years, $5k ONCE at 22.
    # End = 10k + 219k − 182.5k − 5k = 41.5k.
    cfg = make_cfg(20, 25, balance=10_000, expenses=[Expense("a", 36_500, YEAR, 20), Expense("o", 5_000, ONCE, 22)])
    r = simulate(cfg, scen([Income(73_000, years=3)]), 0)
    assert r.ok
    assert r.end_balance == pytest.approx(41_500)
    assert [row.balance for row in r.rows] == pytest.approx([46_500, 83_000, 114_500, 78_000, 41_500])
    assert [row.gross for row in r.rows] == pytest.approx([73_000] * 3 + [0, 0])
    assert [row.net_income for row in r.rows] == pytest.approx([73_000] * 3 + [0, 0])
    assert [row.expenses for row in r.rows] == pytest.approx([36_500, 36_500, 41_500, 36_500, 36_500])
    assert [row.age for row in r.rows] == [20, 21, 22, 23, 24]
    assert [row.year for row in r.rows] == [2000, 2001, 2002, 2003, 2004]


def test_zero_gain_portfolio_sells_without_tax_and_tracks_basis():
    # basis == value → gain fraction 0 → sale = need, no tax. Invested days raise basis 1:1.
    cfg = make_cfg(20, 22, balance=50_000, expenses=[Expense("a", 36_500, YEAR, 21)],
                   taxes=[flat_cg_regime(0.5)])
    r = simulate(cfg, scen([Income(36_500, years=1)]), 0)
    assert r.rows[0].invested == pytest.approx(36_500) and r.rows[0].basis == pytest.approx(86_500)
    assert r.rows[1].sold == pytest.approx(36_500) and r.rows[1].cg_tax == 0
    assert r.end_balance == pytest.approx(50_000) and r.rows[1].basis == pytest.approx(50_000)


def test_flat_income_tax_rate():
    # 25% flat on wages: 80k gross → 60k net. 1 year: end = 60k.
    cfg = make_cfg(20, 21, taxes=[flat_income_regime(0.25)])
    r = simulate(cfg, scen([Income(80_000, years=1)]), 0)
    assert r.rows[0].net_income == pytest.approx(60_000) and r.end_balance == pytest.approx(60_000)


def test_partial_year_taxed_on_actual_wages():
    # Progressive: 0% to 20k, 50% above. A 73k job ending at 20.2 earns 73k × 73/365 = 14.6k → no tax.
    # A full year of 73k would pay 26.5k.
    reg = regime(0, 200, fed(brackets=[(0, 0.0), (20_000, 0.5)]), NO_FICA, NO_STATE_TAX)
    cfg = make_cfg(20, 21, taxes=[reg])
    r = simulate(cfg, scen([Income(73_000, until=20.2)]), 0)
    assert r.rows[0].gross == pytest.approx(14_600) and r.rows[0].net_income == pytest.approx(14_600)
    full = simulate(cfg, scen([Income(73_000, years=1)]), 0)
    assert full.rows[0].net_income == pytest.approx(73_000 - 26_500)


def test_two_segments_in_one_year_taxed_on_total():
    # Progressive 0% to 20k, 50% above. 36.5k for [20, 20.4) = 14.6k plus 73k for [20.4, 21) = 43.8k → 58.4k gross.
    # Tax 50% × 38.4k = 19.2k → net 39.2k.
    reg = regime(0, 200, fed(brackets=[(0, 0.0), (20_000, 0.5)]), NO_FICA, NO_STATE_TAX)
    cfg = make_cfg(20, 21, taxes=[reg])
    r = simulate(cfg, scen([Income(36_500, until=20.4), Income(73_000, until=21)]), 0)
    assert r.rows[0].gross == pytest.approx(58_400) and r.rows[0].net_income == pytest.approx(39_200)


def test_tax_regime_switches_by_age_year():
    # 10% tax for age 20, 30% for age 21. 100k each year → 90k + 70k.
    cfg = make_cfg(20, 22, taxes=[flat_income_regime(0.1, 0, 21), flat_income_regime(0.3, 21, 200)])
    r = simulate(cfg, scen([Income(100_000, years=2)]), 0)
    assert [row.net_income for row in r.rows] == pytest.approx([90_000, 70_000])


def test_missing_regime_or_growth_raises():
    with pytest.raises(ValueError):
        simulate(make_cfg(20, 22, taxes=[zero_regime(0, 21)]), scen([]), 0)
    with pytest.raises(ValueError):
        simulate(make_cfg(20, 22, growth=[Growth(0, 21, 0.0)]), scen([]), 0)


# ───────────────────────────── growth ─────────────────────────────


@pytest.mark.parametrize("rate, years", [(0.05, 1), (0.05, 3), (0.10, 2), (-0.2, 2)])
def test_growth_compounds_to_annual_rate(rate, years):
    # No flows: 365 daily steps of (1+r)^(1/365) → exactly (1+r) per year.
    cfg = make_cfg(20, 20 + years, balance=1_000, growth=[Growth(0, 200, rate)])
    r = simulate(cfg, scen([]), 0)
    assert r.end_balance == pytest.approx(1_000 * (1 + rate) ** years, rel=1e-9)
    assert r.rows[0].balance == pytest.approx(1_000 * (1 + rate), rel=1e-9)


def test_two_growth_segments():
    # 5% for ages 20–21, 10% for age 22: 1000 × 1.05² × 1.1.
    cfg = make_cfg(20, 23, balance=1_000, growth=[Growth(0, 22, 0.05), Growth(22, 200, 0.10)])
    r = simulate(cfg, scen([]), 0)
    assert r.end_balance == pytest.approx(1_000 * 1.05 ** 2 * 1.10, rel=1e-9)


def test_growth_raises_value_not_basis():
    cfg = make_cfg(20, 22, balance=1_000, growth=[Growth(0, 200, 0.10)])
    r = simulate(cfg, scen([]), 0)
    assert r.rows[-1].basis == 1_000 and r.end_balance == pytest.approx(1_210, rel=1e-9)


def test_deposit_gets_remaining_years_of_growth():
    # A $1000 deposit on the first day of age 21 (of 20..23) grows 2 full years at 10% → 1210.
    cfg = make_cfg(20, 23, growth=[Growth(0, 200, 0.10)])
    r = simulate(cfg, scen([]), 0, deposits=((21, 1_000),))
    assert r.end_balance == pytest.approx(1_210, rel=1e-9)
    assert r.rows[1].invested == pytest.approx(1_000)


def test_negative_balance_does_not_grow():
    # Broke from day 0 with a 50% growth rate: the shortfall just accumulates, no interest.
    cfg = make_cfg(20, 22, expenses=[Expense("a", 36_500, YEAR, 20)], growth=[Growth(0, 200, 0.5)])
    r = simulate(cfg, scen([]), 0)
    assert r.end_balance == pytest.approx(-73_000)
    assert r.fail_age == 20


# ───────────────────────────── gross-up / capital gains ─────────────────────────────


def test_sell_for_zero_gain_fraction():
    assert sell_for(1_000, 0.0, 0, [(0, 0.2)]) == (1_000, 0.0, 0.0)


def test_sell_for_flat_rate_gross_up():
    # Flat t=0.2, gain fraction g=0.5: S = N/(1 − t·g) = 900/0.9 = 1000; tax = t·g·S = 100; gain 500.
    s, tax, g = sell_for(900, 0.5, 0, [(0, 0.2)])
    assert (s, tax, g) == pytest.approx((1_000, 100, 500))


def test_sell_for_crossing_a_bracket():
    # 0% on the first 10k of gain, 20% above; g = 0.5, need 30k.
    # 20k sale fills the 0% band (10k gain, no tax), 10k still needed at 0.2·0.5 = 10% → 10k/0.9.
    s, tax, gain = sell_for(30_000, 0.5, 0, [(0, 0.0), (10_000, 0.2)])
    assert s == pytest.approx(20_000 + 10_000 / 0.9)
    assert tax == pytest.approx(0.2 * (s * 0.5 - 10_000))
    assert gain == pytest.approx(s * 0.5)
    assert s - tax == pytest.approx(30_000)


def test_sell_for_starts_at_cum_gain():
    # 8k of gain already realized: 2k of 0% room left. g = 1. Need 12k: 2k at 0%, 10k at 20% → 10k/0.8 = 12.5k.
    s, tax, gain = sell_for(12_000, 1.0, 8_000, [(0, 0.0), (10_000, 0.2)])
    assert s == pytest.approx(2_000 + 12_500) and tax == pytest.approx(2_500)
    # Already past the break: all at 20%.
    s2, tax2, _ = sell_for(8_000, 1.0, 15_000, [(0, 0.0), (10_000, 0.2)])
    assert s2 == pytest.approx(10_000) and tax2 == pytest.approx(2_000)


def test_sim_gross_up_flat_rate_once_sale():
    # Value 100k, basis 40k → g = 0.6. Flat CG 20%. A $44k ONCE bill on day 0 (no wages):
    # S = 44k / (1 − 0.12) = 50k; tax 6k; value 50k; basis 40k × (1 − 50/100) = 20k.
    cfg = make_cfg(20, 21, balance=100_000, basis=40_000, expenses=[Expense("o", 44_000, ONCE, 20)],
                   taxes=[flat_cg_regime(0.2)])
    r = simulate(cfg, scen([]), 0)
    row = r.rows[0]
    assert row.sold == pytest.approx(50_000) and row.cg_tax == pytest.approx(6_000)
    assert row.balance == pytest.approx(50_000) and row.basis == pytest.approx(20_000)


def test_sim_daily_cg_taxes_sum_to_annual_capgains_tax():
    # Zero growth keeps g = (V − B)/V constant (basis shrinks in proportion to each sale).
    # Brackets: 0% to 10k gain, 15% to 20k, 20% above. $100/day of spending for a year, V=200k, B=50k (g=0.75).
    # The year's per-day taxes add up to capgains_tax(total realized gain).
    reg = regime(0, 200, fed(ltcg=[(0, 0.0), (10_000, 0.15), (20_000, 0.20)]), NO_FICA, NO_STATE_TAX)
    cfg = make_cfg(20, 22, balance=200_000, basis=50_000, expenses=[Expense("a", 36_500, YEAR, 20)], taxes=[reg])
    r = simulate(cfg, scen([]), 0)
    for row in r.rows:
        gain = row.sold * 0.75
        assert row.cg_tax == pytest.approx(reg.capgains_tax(gain, 0), rel=1e-9)
        assert row.sold - row.cg_tax == pytest.approx(36_500)
    # Closed form for each year: realized gain G solves G/0.75 − tax(G) = 36.5k. In the 20% band
    # tax(G) = 1500 + 0.2(G − 20k), so G(4/3 − 0.2) = 36.5k + 1.5k − 4k = 34k → G = 30k (> 20k, consistent).
    # Sold 40k, tax 3.5k, every year (cum_gain resets and g stays 0.75).
    for row in r.rows:
        assert row.sold == pytest.approx(40_000, rel=1e-9) and row.cg_tax == pytest.approx(3_500, rel=1e-9)


def test_sim_cg_sheltered_by_wages_below_std_deduction():
    # Fed std 20k, ltcg 50% (silly, so leaks show). Wages 10k/yr → 10k of deduction left over to shelter gains.
    # All gain (g = 1, basis 0) up to 10k is tax free; spending is 36.5k/yr so net need = 26.5k.
    # First 10k sold at 0%, then 16.5k more needed at 50% → 33k. Sold 43k, tax 16.5k.
    reg = regime(0, 200, fed(std=20_000, ltcg=[(0, 0.5)]), NO_FICA, NO_STATE_TAX)
    cfg = make_cfg(20, 21, balance=1e6, basis=0, expenses=[Expense("a", 36_500, YEAR, 20)], taxes=[reg])
    r = simulate(cfg, scen([Income(10_000, years=1)]), 0)
    # Wages 27.40/day < 100/day spend so every day sells. Income tax: fed brackets default 0 → none.
    assert r.rows[0].sold == pytest.approx(43_000) and r.rows[0].cg_tax == pytest.approx(16_500)


# ───────────────────────────── failure ─────────────────────────────


@pytest.mark.parametrize("start, fail_day", [(1_000, 10), (1_050, 10), (999, 9), (100, 1), (0, 0)])
def test_fail_age_constant_burn(start, fail_day):
    # $100/day, no income: after day i the balance is start − 100(i+1); the first day it's < 0 is
    # i = floor(start/100) (a day ending at exactly $0 is not a failure).
    cfg = make_cfg(20, 22, balance=start, expenses=[Expense("a", 36_500, YEAR, 20)])
    r = simulate(cfg, scen([]), 0)
    assert r.fail_age == pytest.approx(20 + fail_day / 365)
    assert not r.ok


def test_fail_age_in_a_later_year():
    # $200/day burn starting at 21, start 41.5k: fails 207 = floor(41500/200) days into age 21.
    cfg = make_cfg(20, 23, balance=41_500, expenses=[Expense("a", 73_000, YEAR, 21)])
    r = simulate(cfg, scen([]), 0)
    assert r.fail_age == pytest.approx(21 + 207 / 365)


def test_exactly_zero_at_end_is_ok():
    cfg = make_cfg(20, 22, balance=73_000, expenses=[Expense("a", 36_500, YEAR, 20)])
    r = simulate(cfg, scen([]), 0)
    assert r.ok and r.end_balance == pytest.approx(0, abs=1e-6)


def test_stop_balance_and_x_end_age():
    # 73k wage for X = 2.4 years, 36.5k/yr spending, start 1k. X ends at 22.4 = day 876.
    # stop_balance = balance at the start of day 876 = 1000 + (200 − 100) × 876.
    cfg = make_cfg(20, 25, balance=1_000, expenses=[Expense("a", 36_500, YEAR, 20)])
    r = simulate(cfg, scen([Income(73_000, years=X)]), 2.4)
    assert r.x_end_age == pytest.approx(22.4)
    assert r.stop_balance == pytest.approx(1_000 + 100 * 876)


def test_stop_balance_at_integer_age_equals_previous_year_end():
    cfg = make_cfg(20, 25, balance=1_000, expenses=[Expense("a", 36_500, YEAR, 20)])
    r = simulate(cfg, scen([Income(73_000, years=X)]), 3)
    assert r.stop_balance == pytest.approx(r.rows[2].balance)


def test_stop_balance_none_when_x_runs_to_end():
    cfg = make_cfg(20, 22)
    r = simulate(cfg, scen([Income(73_000, years=X)]), 2)
    assert r.x_end_age == 22 and r.stop_balance is None


def test_min_balance_after_x():
    # Work 2 years (+100/day net), then −100/day. Year-end balances: 36.5k, 73k, 36.5k, 0.
    # Rows with age + 1 > 22 are ages 22 and 23 → min 0.
    cfg = make_cfg(20, 24, expenses=[Expense("a", 36_500, YEAR, 20)])
    r = simulate(cfg, scen([Income(73_000, years=X)]), 2)
    assert [row.balance for row in r.rows] == pytest.approx([36_500, 73_000, 36_500, 0], abs=1e-6)
    assert r.min_balance_after_x == pytest.approx(0, abs=1e-6)


# ───────────────────────────── flat_from ─────────────────────────────


def test_flat_from_retire_fails_on_retire_day_with_zero_growth():
    # Zero growth: from the stop day any outflow drops the balance below the floor set that morning.
    cfg = make_cfg(20, 25, balance=0, expenses=[Expense("a", 36_500, YEAR, 20)])
    s = scen([Income(73_000, years=X)], flat_from=RETIRE)
    r = simulate(cfg, s, 2.4)
    assert r.fail_age == pytest.approx(20 + 876 / 365)
    # Without flat_from it only fails when the 87.6k saved runs out: 876 more days at $100 → day 1752.
    plain = simulate(cfg, scen([Income(73_000, years=X)]), 2.4)
    assert plain.fail_age == pytest.approx(20 + math.floor(87_600 / 100 + 876) / 365)


def test_flat_from_allows_earlier_dips():
    # Start 100k; a $50k ONCE at 21 (a dip, allowed). No spending afterwards, so from 23 the balance is flat.
    cfg = make_cfg(20, 25, balance=100_000, expenses=[Expense("o", 50_000, ONCE, 21)])
    r = simulate(cfg, scen([], flat_from=23), 0)
    assert r.ok and r.end_balance == pytest.approx(50_000)


def test_flat_from_numeric_age():
    # Spending starts at 23 and flat_from = 23 → fails on day 3×365 exactly (age 23), though balance > 0.
    cfg = make_cfg(20, 25, balance=100_000, expenses=[Expense("a", 36_500, YEAR, 23)])
    assert simulate(cfg, scen([], flat_from=23), 0).fail_age == pytest.approx(23)
    assert simulate(cfg, scen([]), 0).ok


@pytest.mark.parametrize("mult, ok", [(1.01, True), (0.99, False)])
def test_flat_from_fixed_point_of_growth_vs_spending(mult, ok):
    # Each day: V → (V − e)·G with e = $100 and G = 1.05^(1/365). The balance stays ≥ V iff V ≥ e·G/(G − 1).
    # Just above that fixed point it grows forever; just below it drops under the floor on day 1 of flat_from.
    G = 1.05 ** (1 / 365)
    v_star = 100 * G / (G - 1)
    cfg = make_cfg(20, 25, balance=mult * v_star, expenses=[Expense("a", 36_500, YEAR, 20)],
                   growth=[Growth(0, 200, 0.05)])
    r = simulate(cfg, scen([], flat_from=20), 0)
    assert r.ok is ok
    if not ok:
        assert r.fail_age == 20


# ───────────────────────────── partner / joint ─────────────────────────────

PROG = regime(0, 200, fed(brackets=[(0, 0.0), (100_000, 0.5)]), NO_FICA, NO_STATE_TAX)  # 0% to 100k, 50% above
PROG_JOINT = regime(0, 200, fed(brackets=[(0, 0.0), (100_000, 0.5)]), NO_FICA, NO_STATE_TAX, joint=True)


def test_separate_filing_taxes_each_earner_alone():
    # Two 100k earners, each under the 100k threshold → no tax: 200k net.
    cfg = make_cfg(20, 21, taxes=[PROG])
    r = simulate(cfg, scen([Income(100_000, years=1)], partner=[Income(100_000, years=1)]), 0)
    assert r.rows[0].gross == pytest.approx(200_000) and r.rows[0].net_income == pytest.approx(200_000)


def test_joint_filing_taxes_combined_wages():
    # Joint: 200k household → 50% × 100k = 50k tax → 150k net.
    cfg = make_cfg(20, 21, taxes=[PROG_JOINT])
    r = simulate(cfg, scen([Income(100_000, years=1)], partner=[Income(100_000, years=1)]), 0)
    assert r.rows[0].net_income == pytest.approx(150_000)


def test_partner_share_scales_partner_take_home_only():
    # Separate filing. Me 200k → 150k net; partner 200k → 150k net × 0.5 = 75k. Total 225k.
    cfg = make_cfg(20, 21, taxes=[PROG])
    r = simulate(cfg, scen([Income(200_000, years=1)], partner=[Income(200_000, years=1)], share=0.5), 0)
    assert r.rows[0].gross == pytest.approx(400_000) and r.rows[0].net_income == pytest.approx(225_000)


def test_partner_share_with_joint_filing():
    # Joint, me 150k + partner 50k = 200k → keep 150k/200k = 75% each. Me 112.5k + partner 37.5k × 0.4 = 15k.
    cfg = make_cfg(20, 21, taxes=[PROG_JOINT])
    r = simulate(cfg, scen([Income(150_000, years=1)], partner=[Income(50_000, years=1)], share=0.4), 0)
    assert r.rows[0].net_income == pytest.approx(127_500)


def test_joint_passes_per_earner_wages_for_fica():
    # SS 10% up to a 100k base per earner. Joint, me 150k + partner 50k: SS = 10% × (100k + 50k) = 15k → net 185k.
    from firemodel.tax import Fica
    reg = regime(0, 200, fed(), Fica(0.10, 100_000, 0.0, 0.0, 0.0), NO_STATE_TAX, joint=True)
    cfg = make_cfg(20, 21, taxes=[reg])
    r = simulate(cfg, scen([Income(150_000, years=1)], partner=[Income(50_000, years=1)]), 0)
    assert r.rows[0].net_income == pytest.approx(185_000)


@pytest.mark.parametrize("joint, expected_wages", [(False, 20_000.0), (True, 70_000.0)])
def test_capital_gains_stack_on_my_wages_or_household(joint, expected_wages):
    # Record the wages passed to the CG curve: separate → mine (20k); joint → household (20k + 50k).
    seen = []

    def breaks(w):
        seen.append(w)
        return [0.0]

    reg = TaxRegime(0, 200, lambda g, e=(): g, lambda gain, w: 0.1 * gain, breaks, joint)
    cfg = make_cfg(20, 21, balance=1e6, basis=0, expenses=[Expense("a", 365_000, YEAR, 20)], taxes=[reg])
    simulate(cfg, scen([Income(20_000, years=1)], partner=[Income(50_000, years=1)]), 0)
    assert seen and all(w == pytest.approx(expected_wages) for w in seen)


def test_x_in_partner_schedule_sets_x_end_age():
    cfg = make_cfg(20, 25)
    r = simulate(cfg, scen([Income(10, years=5)], partner=[Income(1_000, years=X)]), 1.4)
    assert r.x_end_age == pytest.approx(21.4)


def test_cg_curve_zero_regime():
    assert cg_curve(zero_regime(), 0) == [(0.0, 0.0)]
