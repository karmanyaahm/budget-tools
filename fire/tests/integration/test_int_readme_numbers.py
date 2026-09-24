"""The concrete numbers README.md prints, recomputed through the public API."""

from __future__ import annotations

import pytest

import grid as grid_cli
from fireint import cells, solved, COAST, FLAT, README_SAFETY_FACTOR, RETIRE0, config, load_grid, plan
from firemodel.plan import annual_total
from firemodel.tax import regime


def cell_text(r):
    """Same format as the README tables / grid.py: 'stop age (portfolio $M)'."""
    return f"{r.x_end_age:.1f} (${r.stop_balance / 1e6:.2f}M)"


# ───────────────────────────── SF vs Austin: taxes ─────────────────────────────

TAKE_HOME = {  # gross: (CA single, CA MFJ, TX single, TX MFJ) as ($k take-home, effective %)
    100_000: ((72.7, 27.3), (81.0, 19.0), (79.2, 20.8), (84.7, 15.3)),
    150_000: ((102.0, 32.0), (115.4, 23.1), (113.8, 24.1), (123.2, 17.9)),
    200_000: ((131.8, 34.1), (146.3, 26.8), (148.9, 25.5), (159.3, 20.3)),
    250_000: ((160.8, 35.7), (179.2, 28.3), (183.2, 26.7), (197.5, 21.0)),
    300_000: ((187.5, 37.5), (210.7, 29.8), (215.2, 28.3), (234.3, 21.9)),
    400_000: ((239.3, 40.2), (273.7, 31.6), (277.8, 30.5), (307.9, 23.0)),
}


@pytest.mark.parametrize("gross", sorted(TAKE_HOME))
def test_take_home_table(gross):
    regimes = [regime(0, 1, config.FED_SINGLE, config.FICA_SINGLE, config.CA_SINGLE),
               regime(0, 1, config.FED_MFJ, config.FICA_MFJ, config.CA_MFJ, joint=True),
               regime(0, 1, config.FED_SINGLE, config.FICA_SINGLE, config.NO_INCOME_TAX),
               regime(0, 1, config.FED_MFJ, config.FICA_MFJ, config.NO_INCOME_TAX, joint=True)]
    for reg, (k, pct) in zip(regimes, TAKE_HOME[gross]):
        net = reg.income_left(gross, (gross,))
        assert round(net / 1e3, 1) == k
        assert round(100 * (1 - net / gross), 1) == pct


def test_tax_variants_match_readme_list():
    assert list(config.TAX_VARIANTS) == ["CA, MFJ after wedding", "CA, single", "TX, MFJ after wedding",
                                         "TX, single", "IL, MFJ after wedding", "CO, MFJ after wedding"]


def test_ca_marginal_rate_about_10_points_above_tx_over_200k():
    """README: 'Above $200k, California adds roughly 10 points' (single)."""
    ca = regime(0, 1, config.FED_SINGLE, config.FICA_SINGLE, config.CA_SINGLE)
    tx = regime(0, 1, config.FED_SINGLE, config.FICA_SINGLE, config.NO_INCOME_TAX)
    for g in (250_000, 300_000, 350_000, 420_000):
        mca = (ca.income_left(g) - ca.income_left(g + 1_000)) / 1_000
        mtx = (tx.income_left(g) - tx.income_left(g + 1_000)) / 1_000
        assert 0.09 <= mca - mtx <= 0.12


@pytest.mark.xfail(strict=True, reason=(
    "README says 'Every expense is padded by a safety factor (1.2×)' and 'EXPENSE_SAFETY_FACTOR = 1.2 in "
    "config.py', but config.EXPENSE_SAFETY_FACTOR is 1.1"))
def test_readme_safety_factor():
    assert config.EXPENSE_SAFETY_FACTOR == README_SAFETY_FACTOR


def test_markets_and_safety_settings():
    assert config.END_AGE == 112
    assert [(g.start, g.end, g.rate) for g in config.GROWTH] == [(0, 60, 0.05), (60, 112, 0.04)]
    assert config.FLAT_FROM_AGE == 100


GRID_TAXES = {  # README "SF vs Austin: taxes" table (uv run grid.py grid_taxes)
    "CA, MFJ after wedding": ("46.0 ($2.26M)", "41.8 ($1.65M)", "47.1 ($2.46M)"),
    "CA, single": ("49.6 ($2.28M)", "46.5 ($1.87M)", "51.3 ($2.52M)"),
    "TX, MFJ after wedding": ("42.7 ($2.30M)", "38.2 ($1.58M)", "43.6 ($2.46M)"),
    "TX, single": ("44.4 ($2.31M)", "40.5 ($1.72M)", "45.5 ($2.50M)"),
    "IL, MFJ after wedding": ("45.1 ($2.33M)", "40.9 ($1.69M)", "46.2 ($2.52M)"),
    "CO, MFJ after wedding": ("44.8 ($2.33M)", "40.6 ($1.68M)", "45.9 ($2.52M)"),
}


def test_readme_numbers_reproduce_under_readme_settings(solved):
    """With the settings README states (safety factor 1.2, coast job = core expenses), the engine reproduces
    README's sf_family row (CA, MFJ after wedding; also the 'SF, one kid' and SF/big tech/solo rows)."""
    got = tuple(cell_text(solved["readme-settings:sf_family"][si]) for si in (RETIRE0, COAST, FLAT))
    assert got == GRID_TAXES["CA, MFJ after wedding"]


# ───────────────────────────── example expenses ─────────────────────────────

SF_TABLE = {  # category group: (age 25, age 35)
    "housing": ({"housing"}, 24_900, 24_900),
    "kids + term life": ({"kids", "insurance"}, 0, 59_340),
    "food": ({"food"}, 8_320, 8_320),
    "travel": ({"travel"}, 7_200, 7_200),
    "health": ({"health"}, 3_600, 3_600),
    "transport": ({"transport"}, 2_560, 2_560),
}


def test_sf_family_expense_table():
    sf = plan("sf_family")
    listed = set().union(*(cats for cats, _, _ in SF_TABLE.values())) | {"events"}
    for age, col in ((25, 1), (35, 2)):
        for label, row in SF_TABLE.items():
            cats = row[0]
            got = annual_total([e for e in sf.expenses if e.category in cats], age)  # still at the career job
            assert got == row[col], (label, age)
        rest = annual_total([e for e in sf.expenses if e.category not in listed], age)
        assert rest == 8_900, ("everything else", age)
        assert annual_total(sf.expenses, age) == {25: 55_480, 35: 114_820}[age]


def test_sf_family_description():
    sf = plan("sf_family")
    names = {e.name: e for e in sf.expenses}
    assert names["Rent"].amount == 1_900 and names["Wedding"].amount == 60_000 and names["Wedding"].start == 28
    assert names["Kid 1: daycare (1-3)"].amount == 2_250 and names["Kid 1: daycare (infant)"].start == 33
    assert names["Late-life care"].amount == 3_000 and names["Late-life care"].start == 88
    assert names["Medicare + supplement"].start == 65
    assert names["Kid 1: college (UC in-state)"].amount == 45_000
    assert sf.taxes == "CA, MFJ after wedding"


def test_austin_family_overrides():
    au, sf = plan("austin_family"), plan("sf_family")
    names = {e.name: e for e in au.expenses}
    assert names["Rent"].amount == 950
    assert names["Kid 1: daycare (1-3)"].amount == 1_650
    assert any("UT Austin" in n for n in names) and not any("UC in-state" in n for n in names)
    assert any("preschool (4)" in n for n in names)
    assert any("Extra rideshare with kids" in n for n in names)
    assert au.taxes == "TX, MFJ after wedding"
    assert au.career == sf.career
    assert annual_total(au.expenses, 25) == pytest.approx(45_000, abs=1_000)  # "about $45k/yr at 25"


# ───────────────────────────── example results ─────────────────────────────

GRID_PROFILES = {
    "single, lean": ("35.1 ($1.42M)", "30.7 ($0.74M)", "35.9 ($1.55M)"),
    "SF, one kid": ("46.0 ($2.26M)", "41.8 ($1.65M)", "47.1 ($2.46M)"),
    "SF, three kids": ("67.3 ($1.95M)", "67.3 ($1.95M)", "70.9 ($2.57M)"),
    "couple with car": ("55.1 ($2.47M)", "52.1 ($2.05M)", "57.4 ($2.93M)"),
}


BT, FT = "big tech 120 → 175 → 230×X", "fast track 200×3 → 320×X"
SOLO, PARTNER = "solo", "+ 55k → 90k at 32"
GRID_CITIES = {  # taxable rows
    ("SF", BT, SOLO): ("46.0 ($2.26M)", "41.8 ($1.65M)", "47.1 ($2.46M)"),
    ("SF", BT, PARTNER): ("41.1 ($2.03M)", "36.6 ($1.36M)", "42.1 ($2.20M)"),
    ("SF", FT, SOLO): ("37.2 ($2.42M)", "33.3 ($1.71M)", "37.8 ($2.55M)"),
    ("SF", FT, PARTNER): ("34.3 ($2.09M)", "30.7 ($1.27M)", "34.9 ($2.20M)"),
    ("Austin", BT, SOLO): ("38.4 ($2.02M)", "33.9 ($1.31M)", "39.1 ($2.14M)"),
    ("Austin", BT, PARTNER): ("34.3 ($1.62M)", "29.9 ($0.77M)", "34.8 ($1.71M)"),
    ("Austin", FT, SOLO): ("32.8 ($2.13M)", "29.4 ($1.19M)", "33.2 ($2.23M)"),
    ("Austin", FT, PARTNER): ("30.3 ($1.54M)", "26.9 ($0.74M)", "30.6 ($1.63M)"),
}


def readme_table_mismatches(solved) -> dict:
    """Every README result-table cell (grid_taxes, grid_profiles, grid_cities taxable rows) vs the current defaults."""
    tables = {f"grid_taxes/{k}": (f"tax:{k}", v) for k, v in GRID_TAXES.items()}
    tables |= {f"grid_profiles/{k}": (f"grid_profiles:{k} | {BT}", v) for k, v in GRID_PROFILES.items()}
    tables |= {"grid_cities/" + "/".join(k): ("grid_cities:" + " | ".join((*k, "taxable")), v)
               for k, v in GRID_CITIES.items()}
    bad = {}
    for label, (cell, want) in tables.items():
        got = tuple(cell_text(solved[cell][si]) for si in (RETIRE0, COAST, FLAT))
        if got != want:
            bad[label] = (want, got)
    return bad


@pytest.mark.xfail(strict=True, reason=(
    "README's result tables (SF vs Austin taxes, Example results: grid_profiles and grid_cities) were made with "
    "a 1.2 safety factor and a coast job paying core expenses only; with the current defaults (1.1, +$10k coast "
    "margin) all 18 rows differ, e.g. sf_family CA MFJ: README 46.0 ($2.26M) / 41.8 ($1.65M) / 47.1 ($2.46M), now 43.1 ($2.12M) / 37.6 ($1.34M) / 44.1 ($2.28M)"))
def test_readme_result_tables_match_current_defaults(solved):
    bad = readme_table_mismatches(solved)
    assert not bad, f"{len(bad)} README rows differ: {bad}"


def _cities_deltas(solved):
    out = {}
    for key in GRID_CITIES:
        tax = solved["grid_cities:" + " | ".join((*key, "taxable"))]
        acc = solved["grid_cities:" + " | ".join((*key, "401k+Roth+529"))]
        for si in (RETIRE0, COAST, FLAT):
            out[(*key, si)] = tax[si].x_end_age - acc[si].x_end_age
    return out


def test_grid_cities_accounts_rows_stop_earlier(solved):
    """README: the 401k+Roth+529 rows stop earlier than the taxable ones, most in SF."""
    d = _cities_deltas(solved)
    assert all(v > 0 for v in d.values())
    sf = [v for k, v in d.items() if k[0] == "SF"]
    au = [v for k, v in d.items() if k[0] == "Austin"]
    assert max(sf) > max(au) and sum(sf) > sum(au)


def test_grid_cities_accounts_gain_is_0_1_to_1_2_years(solved):
    """README: 'The full grid's 401k+Roth+529 rows stop 0.1–1.2 years earlier than these' (± rounding).
    Holds with the current defaults (deltas 0.104–1.049 yr; the low end sits right at 0.1, so small model changes
    can flip it). Under README's own settings it does not hold: see the xfail below."""
    d = _cities_deltas(solved)
    bad = {k: round(v, 2) for k, v in d.items() if not 0.1 - 0.05 <= v <= 1.2 + 0.05}
    assert not bad, bad


def _readme_settings_deltas(solved):
    tax, acc = solved["readme-settings:sf_family"], solved["readme-settings-acct:sf_family"]
    return {si: round(tax[si].x_end_age - acc[si].x_end_age, 2) for si in (RETIRE0, COAST, FLAT)}


@pytest.mark.xfail(strict=True, reason=(
    "README says the grid_cities 401k+Roth+529 rows stop 0.1–1.2 years earlier than the taxable ones, but under "
    "README's own settings (safety 1.2, coast = core expenses) the SF / big tech / solo Coast cell stops 1.33 "
    "years earlier (41.79 → 40.46); Retire to $0 gains 1.13, flat from 100 gains 1.30"))
def test_grid_cities_accounts_gain_under_readme_settings(solved):
    d = _readme_settings_deltas(solved)
    assert all(0.1 - 0.05 <= v <= 1.2 + 0.05 for v in d.values()), d


def test_grid_cities_axes():
    cities = list(grid_cli.cells(load_grid("grid_cities")))
    labels = [lab for lab, _ in cities]
    assert len(labels) == 2 * 2 * 2 * 2
    assert {lab[0] for lab in labels} == {"SF", "Austin"}
    assert {lab[3] for lab in labels} == {"taxable", "401k+Roth+529"}
