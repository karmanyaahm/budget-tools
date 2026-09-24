"""Tax-advantaged accounts (401(k), Roth IRA, 529): hand-checkable cases.

Rule under test: the 401(k)/Roth get only what's needed after the penalty age (the backward target),
frontloaded; everything else stays taxable. Most tests use penalty_age=60 so the target is whole years.
"""

from dataclasses import replace

import pytest

from conftest import NO_FICA, NO_STATE_TAX, fed, make_cfg, scen
from firemodel.schema import ONCE, X, YEAR, Accounts, Expense, Income
from firemodel.sim import ZERO_CURVE, Pot, drain, make_curve, simulate
from firemodel.tax import Fica, regime

FLAT20 = regime(0, 200, fed(brackets=[(0, 0.2)]), NO_FICA, NO_STATE_TAX)  # 20% income tax, 0% CG


def one_year_job(amount=36_500):
    return scen([Income(amount, years=X)])  # simulate(..., x=1): the job runs for exactly one year


def retire_cfg(limit=20_000, balance=0.0, taxes=None, extra=(), penalty_age=60, **acc):
    # Ages 58-62. Job at 58 only. Costs of 3,650/yr at 60 and 61 (after the penalty age): zero growth,
    # zero tax → the 401(k) target at 58 is exactly 7,300.
    exps = [Expense("late costs", 3_650, YEAR, 60, 62), *extra]
    return replace(make_cfg(58, 62, balance=balance, expenses=exps, taxes=taxes),
                   accounts=Accounts(k401_limit=limit, penalty_age=penalty_age, **acc))


def test_off_is_identical_to_no_accounts():
    # Accounts off (all limits 0) must give exactly the plain result.
    base = make_cfg(58, 62, expenses=[Expense("late costs", 3_650, YEAR, 60, 62)])
    off = simulate(base, one_year_job(), 1)
    zero = simulate(replace(base, accounts=Accounts()), one_year_job(), 1)
    assert [r.balance for r in zero.rows] == [r.balance for r in off.rows]


def test_deferral_lowers_income_tax_not_fica():
    # 20% income tax, 10% uncapped FICA. Gross 100k, deferred 10k:
    # income tax 0.2 × 90k = 18k, FICA 0.1 × 100k = 10k → take-home (before the deferral leaves) 72k.
    reg = regime(0, 200, fed(brackets=[(0, 0.2)]), Fica(0.10, 1e12, 0.0, 0.0, 0.0), NO_STATE_TAX)
    assert reg.income_left(100_000, (100_000,), deferred=10_000) == pytest.approx(72_000)
    assert reg.income_left(100_000, (100_000,)) == pytest.approx(70_000)


def test_contributes_exactly_the_post_penalty_need():
    # Zero tax, zero growth: the 401(k) gets exactly 7,300 (not its 20,000 limit); the rest stays taxable.
    r = simulate(retire_cfg(), one_year_job(), 1)
    assert r.rows[0].k401 == pytest.approx(7_300)
    assert r.rows[0].balance - r.rows[0].k401 == pytest.approx(36_500 - 7_300)


def test_no_post_penalty_need_means_no_contribution():
    # Costs end before the penalty age → target 0 → nothing is locked away.
    cfg = replace(retire_cfg(), expenses=[Expense("early costs", 3_650, YEAR, 59, 60)])
    assert simulate(cfg, one_year_job(), 1).rows[0].contributed == 0


def test_401k_funds_the_retirement_exactly_and_ends_at_zero():
    # After 60 the 401(k) is drawn first (zero tax): it pays both years and ends at 0; taxable is untouched.
    r = simulate(retire_cfg(), one_year_job(), 1)
    assert r.ok
    assert r.rows[3].k401 == pytest.approx(0, abs=1e-6)
    assert r.rows[3].balance == pytest.approx(36_500 - 7_300)


def test_target_is_grossed_up_for_tax_and_saves_tax():
    # 20% tax on wages and on 401(k) draws. Net need 7,300 → pre-tax 7,300 / 0.8 = 9,125 deferred.
    # Year 58: tax 0.2 × (36,500 − 9,125) = 5,475 → total 36,500 − 5,475 = 31,025 (vs 29,200 without).
    r = simulate(retire_cfg(taxes=[FLAT20]), one_year_job(), 1)
    assert r.rows[0].k401 == pytest.approx(9_125)
    assert r.rows[0].balance == pytest.approx(31_025)
    assert r.ok and r.rows[3].k401 == pytest.approx(0, abs=1e-6)
    assert sum(x.ord_tax for x in r.rows) == pytest.approx(9_125 * 0.2)  # 1,825 paid on the draws


def test_reserve_blocks_contribution_before_a_lump():
    # A 40,000 lump at 59: room = 0 + 36,500 − 0 − 40,000 < 0 → nothing contributed at 58.
    cfg = retire_cfg(extra=[Expense("wedding", 40_000, ONCE, 59)])
    assert simulate(cfg, one_year_job(), 1).rows[0].contributed == 0


def test_reserve_limits_contribution_to_room():
    # A 32,000 lump at 59: room = 36,500 − 32,000 = 4,500 < the 7,300 need → contribute 4,500.
    cfg = retire_cfg(extra=[Expense("car", 32_000, ONCE, 59)])
    assert simulate(cfg, one_year_job(), 1).rows[0].contributed == pytest.approx(4_500)


def test_limit_caps_and_roth_fills_the_rest():
    # 401(k) limit 5,000 < the 7,300 need → Roth takes the other 2,300.
    r = simulate(retire_cfg(limit=5_000, roth_limit=7_500), one_year_job(), 1)
    assert (r.rows[0].k401, r.rows[0].roth) == pytest.approx((5_000, 2_300))


def test_before_penalty_age_taxable_pays_and_401k_untouched():
    # Costs at 59 (before the penalty age of 60) come from taxable; the 401(k) keeps its 7,300 for 60-61.
    cfg = retire_cfg(extra=[Expense("costs at 59", 3_650, YEAR, 59, 60)])
    r = simulate(cfg, one_year_job(), 1)
    assert r.rows[1].k401 == pytest.approx(7_300)
    assert r.rows[1].ord_tax == 0


def test_401k_withdrawal_penalty_gross_up():
    # All of a 401(k) dollar is taxable. 20% ordinary tax (+10% before 59½), need 700 net:
    # early S − 0.3S = 700 → S = 1,000 (tax 300); late S = 700 / 0.8 = 875.
    early = make_curve(FLAT20.ordinary_tax, FLAT20.ordinary_breaks, 0.0, add=0.10)
    late = make_curve(FLAT20.ordinary_tax, FLAT20.ordinary_breaks, 0.0)
    pot = Pot(10_000, 0)
    net, sale, tax, _ = drain(pot, 700, 0.0, early)
    assert (net, sale, tax) == pytest.approx((700, 1_000, 300))
    assert pot.value == pytest.approx(9_000)
    assert drain(Pot(10_000, 0), 700, 0.0, late)[1] == pytest.approx(875)


def test_roth_pro_rata_earnings():
    # Roth worth 1,000 with 500 contributed: half of each withdrawal is earnings.
    # Early: S − 0.3 × 0.5 × S = 425 → S = 500, tax 75. After 59½ it's tax-free: S = 425.
    early = make_curve(FLAT20.ordinary_tax, FLAT20.ordinary_breaks, 0.0, add=0.10)
    net, sale, tax, _ = drain(Pot(1_000, 500), 425, 0.0, early)
    assert (sale, tax) == pytest.approx((500, 75))
    assert drain(Pot(1_000, 500), 425, 0.0, ZERO_CURVE)[1] == pytest.approx(425)


def test_drain_empties_pot_and_reports_shortfall():
    # Need more than the account holds: it's emptied, and the net proceeds are its value minus tax.
    pot = Pot(1_000, 0)
    net, sale, tax, _ = drain(pot, 5_000, 0.0, make_curve(FLAT20.ordinary_tax, FLAT20.ordinary_breaks, 0.0))
    assert (net, sale, tax, pot.value) == pytest.approx((800, 1_000, 200, 0))


def test_529_pays_college_first():
    # Year 20: one year of 36,500 wages, college 3,650 at 21. room = 36,500 − 0 − 3,650 → the 529 takes 3,650
    # (zero growth: present value = cost). Year 21: the 529 pays college, and taxable stays 32,850.
    cfg = replace(make_cfg(20, 22, expenses=[Expense("Kid 1: college", 3_650, YEAR, 21, 22)]),
                  accounts=Accounts(c529_limit=50_000))
    r = simulate(cfg, one_year_job(), 1)
    assert r.rows[0].c529 == pytest.approx(3_650)
    assert r.rows[1].c529 == pytest.approx(0)
    assert r.rows[1].balance == pytest.approx(32_850)
    assert r.rows[1].ord_tax == 0


def test_long_lookahead_protects_a_lump_two_years_out():
    # Ages 58-64, penalty age 62. Job 36,500/yr at 58-59. A 68,000 lump at 61; 3,650/yr of costs at 62-63.
    # Taxable must hold 68,000 on the lump day. Year 58: taxable can end the year at 36,500 and still reach
    # 68,000 by 61 only if it keeps 68,000 − 36,500 (year 59's pay) = 31,500 → slack 36,500 − 31,500 = 5,000.
    # So the 401(k) gets 5,000 (its need is 7,300), year 59 adds 0, taxable has exactly 68,000 on the lump day,
    # and no early-withdrawal penalty is ever paid. (The old 1-year reserve contributed 7,300 at 58 and paid a
    # 10% penalty at 61.) Total resources 73,000 < 75,300 needed, so the plan still fails at 62.
    exps = [Expense("lump", 68_000, ONCE, 61), Expense("late costs", 3_650, YEAR, 62, 64)]
    cfg = replace(make_cfg(58, 64, expenses=exps), accounts=Accounts(k401_limit=20_000, penalty_age=62))
    r = simulate(cfg, one_year_job(), 2)
    assert r.rows[0].k401 == pytest.approx(5_000)
    assert r.rows[1].contributed == pytest.approx(0, abs=1e-6)
    assert sum(x.ord_tax for x in r.rows if x.age < 62) == 0
    assert r.rows[2].balance - r.rows[2].k401 == pytest.approx(68_000)  # taxable at the end of 60 = the lump


def test_underfunded_529_leaves_college_to_taxable_without_penalties():
    # Job 36,500 at 20. College 36,500 at 22, but the 529 may take only 5,000/yr: it gets 5,000 at 20.
    # Taxable must then keep the other 31,500 for college (cap_ta), so a 401(k) with a need at 60+ gets
    # nothing yet (its only room would be taxable's college money). College is paid 5,000 from the 529 +
    # 31,500 from taxable; no penalty.
    exps = [Expense("Kid 1: college", 36_500, YEAR, 22, 23), Expense("late costs", 3_650, YEAR, 60, 61)]
    cfg = replace(make_cfg(20, 61, expenses=exps), accounts=Accounts(k401_limit=20_000, c529_limit=5_000))
    r = simulate(cfg, one_year_job(), 1)
    assert r.rows[0].c529 == pytest.approx(5_000)
    assert r.rows[0].k401 == pytest.approx(0)
    assert sum(x.ord_tax for x in r.rows) == 0
    assert r.rows[2].balance == pytest.approx(0, abs=1e-6)  # everything spent on college; nothing left for 60


def test_start_roth_is_spendable_tax_free_without_accounts():
    # $10k starting Roth (all contributions), accounts off, zero tax/growth, costs 3,650/yr for 2 years:
    # taxable is empty, so the Roth pays; contributions come out tax- and penalty-free → 2,700 left.
    cfg = replace(make_cfg(20, 22, expenses=[Expense("costs", 3_650, YEAR, 20, 22)], taxes=[FLAT20]), start_roth=10_000)
    r = simulate(cfg, scen([Income(0, years=X)]), 0)
    assert r.ok
    assert r.rows[-1].balance == pytest.approx(10_000 - 7_300)
    assert sum(x.ord_tax for x in r.rows) == 0


def test_partner_adds_their_own_limits_to_the_household_pots():
    # 401(k) limit 5,000 per earner, need 7,300. Alone: 5,000 in the 401(k). With a working partner whose pay is
    # pooled, the household 401(k) may take 10,000, so it gets the whole 7,300 (no Roth needed).
    alone = simulate(retire_cfg(limit=5_000, roth_limit=7_500), one_year_job(), 1)
    joint = simulate(retire_cfg(limit=5_000, roth_limit=7_500),
                     scen([Income(36_500, years=X)], partner=[Income(36_500, start=58, until=59)]), 1)
    assert (alone.rows[0].k401, alone.rows[0].roth) == pytest.approx((5_000, 2_300))
    assert (joint.rows[0].k401, joint.rows[0].roth) == pytest.approx((7_300, 0))
