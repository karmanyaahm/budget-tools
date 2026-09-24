"""Plan → Config flows: make_config on every shipped plan, tax variants and schedules, moves, partners,
alt careers, and grid cells vs individually built configs."""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

import grid as grid_cli
from fireint import (COAST, DEFAULT_GRIDS, DEFAULT_PLANS, FLAT, RETIRE0, cells, config, load_grid, plan,  # noqa: F401
                     solved)
from firemodel.plan import annual_total
from firemodel.schema import RETIRE, X, Income
from firemodel.sim import DAYS, daily_expenses, lay_out
from firemodel.solve import x_kind

GOALS = ["Retire to $0", "Coast (core exp→60)", f"Retire, flat from {config.FLAT_FROM_AGE}"]


def covers(regimes, start, end):
    """The regimes tile [start, end) with no gap or overlap."""
    spans = sorted((r.start, r.end) for r in regimes)
    assert spans[0][0] <= start and spans[-1][1] >= end
    for (a, b), (c, d) in zip(spans, spans[1:]):
        assert b == c
    return True


@pytest.mark.parametrize("name", DEFAULT_PLANS)
def test_make_config_on_every_shipped_plan(name):
    p = plan(name)
    cfg = config.make_config(p)
    assert cfg.plan_name == p.name
    assert [s.name for s in cfg.scenarios] == GOALS
    assert [s.flat_from for s in cfg.scenarios] == [None, None, config.FLAT_FROM_AGE]
    assert all(x_kind(s) == "years" for s in cfg.scenarios)
    assert cfg.start_age == p.start_age and cfg.end_age == config.END_AGE
    assert cfg.start_balance == p.start_balance and cfg.expenses == p.expenses
    assert cfg.safety_factor == config.EXPENSE_SAFETY_FACTOR
    assert cfg.accounts == config.ACCOUNTS
    covers(cfg.taxes, p.start_age, config.END_AGE)
    own = next(iter(cfg.tax_variants))
    assert own == (p.taxes if isinstance(p.taxes, str) else " → ".join(n for _, n in p.taxes))
    assert set(config.TAX_VARIANTS) <= set(cfg.tax_variants)
    assert cfg.tax_variants[own] is cfg.taxes
    acc = config.make_config(p, accounts=config.TAX_ADVANTAGED)
    assert acc.accounts == config.TAX_ADVANTAGED and acc.expenses == cfg.expenses


@pytest.mark.parametrize("variant", list(config.TAX_VARIANTS))
def test_each_tax_variant_builds_contiguous_regimes(variant):
    p = plan("sf_family")
    cfg = config.make_config(p, taxes=variant)
    covers(cfg.taxes, p.start_age, config.END_AGE)
    joint = [r.joint for r in cfg.taxes]
    if "single" in variant:
        assert joint == [False]
    else:  # single until the wedding, MFJ from it
        assert joint == [False, True] and cfg.taxes[0].end == p.wedding_age == cfg.taxes[1].start


def test_flat_states_tax_wages_at_their_rate():
    p = plan("sf_family")
    tx = config.make_config(p, "TX, MFJ after wedding").taxes[1]
    for state, rate in (("IL", 0.0495), ("CO", 0.044)):
        reg = config.make_config(p, f"{state}, MFJ after wedding").taxes[1]
        for g in (80_000, 200_000):
            assert tx.income_left(g) - reg.income_left(g) == pytest.approx(rate * g)


def test_mfj_without_partner_is_a_zero_income_spouse():
    """README: MFJ without with_partner acts like a $0-income spouse: better than single at every wage."""
    p = plan("sf_family")
    mfj = config.make_config(p, "CA, MFJ after wedding").taxes[1]
    single = config.make_config(p, "CA, single").taxes[0]
    for g in (60_000, 150_000, 400_000):
        assert mfj.income_left(g) > single.income_left(g)


def test_tax_schedule_list_clips_each_variant_to_its_ages():
    p = replace(plan("sf_family"), taxes=[(22, "CA, single"), (40, "TX, MFJ after wedding")])
    cfg = config.make_config(p)
    covers(cfg.taxes, 22, config.END_AGE)
    assert [(r.start, r.end, r.joint) for r in cfg.taxes] == [(22, 40, False), (40, config.END_AGE, True)]
    assert next(iter(cfg.tax_variants)) == "CA, single → TX, MFJ after wedding"
    ca = config.TAX_VARIANTS["CA, single"](p)[0]
    tx = config.TAX_VARIANTS["TX, MFJ after wedding"](p)[1]
    assert cfg.taxes[0].income_left(150_000) == ca.income_left(150_000)
    assert cfg.taxes[1].income_left(150_000) == tx.income_left(150_000)


# ───────────────────────────── move_to ─────────────────────────────


@pytest.mark.parametrize("retire", [30.5, 45.0, 70.25])
def test_move_plan_expenses_switch_at_the_move_age(retire):
    sf, au, moved = plan("sf_family"), plan("austin_family"), plan("sf_to_austin")
    move = 35
    for age in range(sf.start_age, config.END_AGE):
        want = annual_total((sf if age < move else au).expenses, age, retire)
        assert annual_total(moved.expenses, age, retire) == pytest.approx(want), age
    # and day by day, as the simulation sees them
    c_moved, c_sf, c_au = (config.make_config(p) for p in (moved, sf, au))
    d = (move - sf.start_age) * DAYS
    dm, ds, da = (daily_expenses(c, retire) for c in (c_moved, c_sf, c_au))
    assert dm[:d] == pytest.approx(ds[:d])
    assert dm[d:] == pytest.approx(da[d:])


def test_move_plan_taxes_switch_at_the_move_age():
    moved = plan("sf_to_austin")
    assert moved.taxes == [(22, "CA, MFJ after wedding"), (35, "TX, MFJ after wedding")]
    cfg = config.make_config(moved)
    covers(cfg.taxes, 22, config.END_AGE)
    assert [(r.start, r.end, r.joint) for r in cfg.taxes] == [(22, 28, False), (28, 35, True), (35, 112, True)]
    ca_mfj = config.TAX_VARIANTS["CA, MFJ after wedding"](moved)[1]
    tx_mfj = config.TAX_VARIANTS["TX, MFJ after wedding"](moved)[1]
    assert cfg.taxes[1].income_left(200_000) == ca_mfj.income_left(200_000)
    assert cfg.taxes[2].income_left(200_000) == tx_mfj.income_left(200_000)
    assert moved.career == plan("sf_family").career and moved.start_balance == plan("sf_family").start_balance


def test_move_lands_between_the_two_cities(solved):
    """Earning in SF then moving to cheaper, untaxed Austin: a stop age between the two pure plans."""
    for si in (RETIRE0, COAST, FLAT):
        sf, au, mv = (solved[f"plan:{n}"][si].x for n in ("sf_family", "austin_family", "sf_to_austin"))
        assert au <= mv <= sf


def test_move_charges_the_wedding_once():
    moved = plan("sf_to_austin")
    weddings = [e for e in moved.expenses if e.name == "Wedding"]
    assert len(weddings) == 2  # one from each city
    assert sum(e.annual(28) for e in weddings) == 60_000


# ───────────────────────────── partners ─────────────────────────────


def test_with_partner_defaults():
    sf = plan("sf_family")
    p = sf.with_partner(70_000)
    assert p.partner_share == 0.5
    assert p.partner_income == [Income(70_000, start=25, until=55, label="partner")]
    assert "partner" in p.name and p.expenses == sf.expenses and p.career == sf.career
    cfg = config.make_config(p)
    assert all(s.partner_income == p.partner_income and s.partner_share == 0.5 for s in cfg.scenarios)
    spans, _ = lay_out(cfg.scenarios[0].partner_income, cfg.start_age, 0)
    assert spans == [(25, 55, 70_000, "partner")]


def test_partner_with_zero_share_changes_nothing_when_filing_separately(solved):
    """Separate returns (CA, single): a partner who puts 0% into the pool doesn't move the answer."""
    base = solved["tax:CA, single"][RETIRE0]
    for salary in (70_000, 150_000):
        r = solved[f"p0single:{salary}"][RETIRE0]
        assert r.x == base.x and r.stop_balance == pytest.approx(base.stop_balance)
        assert [row.balance for row in r.rows] == pytest.approx([row.balance for row in base.rows])
        assert r.rows[10].gross == pytest.approx(base.rows[10].gross + salary)  # age 32: the partner's wages are there


def test_partner_with_zero_share_on_a_joint_return_raises_your_tax(solved):
    """MFJ puts both incomes on one return, so even a 0%-share partner raises the household rate on your pay."""
    assert solved["p0mfj:150000"][RETIRE0].x >= solved["plan:sf_family"][RETIRE0].x


def test_partner_half_share_helps(solved):
    """grid_cities: + 55k → 90k partner (50% shared) stops earlier than solo."""
    for city in ("SF", "Austin"):
        for si in (RETIRE0, COAST, FLAT):
            solo = solved[f"grid_cities:{city} | big tech 120 → 175 → 230×X | solo | taxable"][si]
            duo = solved[f"grid_cities:{city} | big tech 120 → 175 → 230×X | + 55k → 90k at 32 | taxable"][si]
            assert duo.x < solo.x


# ───────────────────────────── careers ─────────────────────────────


def test_alt_careers_get_the_same_three_goals():
    from default_plans.ladders import LADDERS
    p = replace(plan("sf_family"), alt_careers={"fast": LADDERS["fast track 200×3 → 320×X"],
                                                 "salary": LADDERS["solve salary: 12 yrs at X"]})
    cfg = config.make_config(p)
    assert [s.name for s in cfg.scenarios] == GOALS + [g + " [fast]" for g in GOALS] + [g + " [salary]" for g in GOALS]
    assert [x_kind(s) for s in cfg.scenarios] == ["years"] * 6 + ["amount"] * 3
    assert all(s.name.endswith("[fast]") == (s.income[:2] == LADDERS["fast track 200×3 → 320×X"][:2])
               for s in cfg.scenarios[:6])


def test_coast_scenario_pays_core_expenses_after_x():
    """Coast = the career, then a job paying that age's core expenses (kids, events, big-ticket excluded)."""
    p = plan("sf_family")
    coast = config.make_config(p).scenarios[COAST]
    assert coast.income[:len(p.career)] == p.career
    x = 10.0  # stop at 22 + 5 + 10 = 37
    spans, x_end = lay_out(coast.income, p.start_age, x)
    assert x_end == 37
    core_rows = [(s, e, a) for s, e, a, label in spans if label == "coast job = core expenses" and e > s]
    assert core_rows and core_rows[0][0] == 37 and core_rows[-1][1] == p.coast_until
    excluded = {"kids", "events", "big-ticket"}
    for s, e, a in core_rows:
        age = math.floor(s)
        want = annual_total([ex for ex in p.expenses if ex.category not in excluded], age, retire=-math.inf)
        assert a == pytest.approx(want)
        assert a == pytest.approx(p.core_expenses(age))


@pytest.mark.xfail(strict=True, reason=(
    "README says the coast goal is 'a job that pays your core expenses until 60', but LifePlan.coast_margin "
    "defaults to (10_000, None), so plan.coast() also pays a $10k/yr 'coast margin' segment from RETIRE to 60"))
def test_coast_job_pays_exactly_core_expenses():
    p = plan("sf_family")
    coast = config.make_config(p).scenarios[COAST]
    spans, x_end = lay_out(coast.income, p.start_age, 10.0)
    for age in range(38, p.coast_until):
        paid = sum(a for s, e, a, _ in spans if s <= age < e)
        assert paid == pytest.approx(p.core_expenses(age)), age


def test_every_n_years_and_once_expenses():
    car = next(e for e in plan("couple_with_car").expenses if e.name.startswith("Car purchase"))
    charged = [a for a in range(21, 112) if car.annual(a)]
    assert charged == list(range(22, 85, 10))
    wedding = next(e for e in plan("sf_family").expenses if e.name == "Wedding")
    assert [a for a in range(22, 112) if wedding.annual(a)] == [28]


def test_retire_bounded_expenses_follow_the_stop_age():
    sf = plan("sf_family")
    by_name = {e.name: e for e in sf.expenses}
    employer, individual = by_name["Health insurance (employer)"], by_name["Health insurance (individual)"]
    assert employer.end is RETIRE and individual.start is RETIRE
    for retire in (35.0, 50.0):
        assert employer.annual(int(retire) - 1, retire) > 0 and employer.annual(int(retire), retire) == 0
        assert individual.annual(int(retire) - 1, retire) == 0 and individual.annual(int(retire), retire) > 0
        assert individual.annual(65, retire) == 0


# ───────────────────────────── grid cells vs individual configs ─────────────────────────────


def assert_same_config(a, b):
    assert (a.start_age, a.end_age, a.start_balance, a.start_basis, a.safety_factor) == \
           (b.start_age, b.end_age, b.start_balance, b.start_basis, b.safety_factor)
    assert a.expenses == b.expenses and a.accounts == b.accounts and a.growth == b.growth
    assert [(s.name, s.income, s.partner_income, s.partner_share, s.flat_from) for s in a.scenarios] == \
           [(s.name, s.income, s.partner_income, s.partner_share, s.flat_from) for s in b.scenarios]
    assert [(r.start, r.end, r.joint) for r in a.taxes] == [(r.start, r.end, r.joint) for r in b.taxes]
    for ra, rb in zip(a.taxes, b.taxes):
        for g in (50_000, 180_000, 450_000):
            assert ra.income_left(g, (g,)) == rb.income_left(g, (g,))
            assert ra.capgains_tax(40_000, g) == rb.capgains_tax(40_000, g)


def test_grid_cities_cells_equal_individual_configs():
    from default_plans.ladders import LADDERS
    from default_plans.partners import PARTNERS
    got = dict(grid_cli.cells(load_grid("grid_cities")))
    assert len(got) == 16
    plans = {"SF": plan("sf_family"), "Austin": plan("austin_family")}
    accounts = {"taxable": config.NO_ACCOUNTS, "401k+Roth+529": config.TAX_ADVANTAGED}
    for (city, ladder, partner, acc), cfg in got.items():
        p = replace(plans[city], career=LADDERS[ladder])
        if PARTNERS[partner] is not None:
            p = p.with_partner(PARTNERS[partner])
            assert cfg.scenarios[0].partner_share == 0.5
        assert_same_config(cfg, config.make_config(p, accounts=accounts[acc]))


def test_grid_taxes_cells_equal_individual_configs():
    got = dict(grid_cli.cells(load_grid("grid_taxes")))
    assert [k[1] for k in got] == list(config.TAX_VARIANTS)
    for (_, variant), cfg in got.items():
        assert_same_config(cfg, config.make_config(plan("sf_family"), taxes=variant))


def test_grid_results_equal_individual_results(solved):
    """Same ladder amounts as the plan's own career → the same answers, cell for cell."""
    same = {
        "grid_profiles:single, lean | big tech 120 → 175 → 230×X": "plan:single_lean",
        "grid_profiles:SF, one kid | big tech 120 → 175 → 230×X": "plan:sf_family",
        "grid_profiles:SF, three kids | big tech 120 → 175 → 230×X": "plan:three_kids",
        "grid_cities:SF | big tech 120 → 175 → 230×X | solo | taxable": "taxable:sf_family",
        "grid_cities:Austin | big tech 120 → 175 → 230×X | solo | taxable": "taxable:austin_family",
        "grid_cities:SF | big tech 120 → 175 → 230×X | solo | 401k+Roth+529": "acct:sf_family",
        "grid_cities:Austin | big tech 120 → 175 → 230×X | solo | 401k+Roth+529": "acct:austin_family",
    }
    for g, single in same.items():
        for si, r in solved[single].items():
            assert solved[g][si].x == r.x, (g, si)
            assert solved[g][si].stop_balance == pytest.approx(r.stop_balance), (g, si)
