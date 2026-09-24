"""End-to-end runs of the two CLIs (`uv run fire.py ...`, `uv run grid.py ...`) as subprocesses.

Every fire.py run names a shipped plan with --plan, and every grid.py run names a shipped grid (or --list), so
the private default plan is never the one being run. All commands start at once and run concurrently.
"""

from __future__ import annotations

import functools
import re

import pytest

from fireint import COAST, DEFAULT_GRIDS, DEFAULT_PLANS, FLAT, RETIRE0, cells, config, finish, solved, start_cli, table_rows  # noqa: F401
from firemodel.sim import DAYS
from firemodel.solve import Solution, what_if

R0 = "Retire to"  # -s filter matching only "Retire to $0"

COMMANDS = {
    "basic": ("fire.py", "--plan", "sf_family", "--no-plot", "--no-whatif"),
    "budget": ("fire.py", "--plan", "austin_family", "--budget"),
    "compare": ("fire.py", "--plan", "austin_family", "--compare-taxes", "-s", R0),
    "x_ok": ("fire.py", "--plan", "sf_family", "--x", "20", "-s", R0, "--no-plot"),
    "x_fail": ("fire.py", "--plan", "sf_family", "--x", "1", "-s", R0, "--no-plot"),
    "whatif": ("fire.py", "--plan", "single_lean", "-s", R0, "--no-plot", "-w", "100_000@25", "--whatif", "1000@25"),
    "accounts": ("fire.py", "--plan", "sf_family", "--no-accounts", "-s", R0, "--no-plot", "--no-whatif"),
    "filter": ("fire.py", "--plan", "single_lean", "-s", "flat", "-s", "COAST", "--no-plot", "--no-whatif", "-t"),
    "sweep": ("fire.py", "--plan", "single_lean", "--sweep", "-s", R0, "--no-plot", "--no-whatif"),
    "list": ("fire.py", "--list"),
    "grid_list": ("grid.py", "--list"),
    "grid_taxes": ("grid.py", "grid_taxes"),
    "grid_ladders": ("grid.py", "grid_ladders"),
    "bad_plan": ("fire.py", "--plan", "no_such_plan_xyz", "--no-plot"),
    "bad_grid": ("grid.py", "no_such_grid_xyz"),
}


@functools.cache
def outputs() -> dict:
    procs = {k: start_cli(*args) for k, args in COMMANDS.items()}
    return {k: finish(p) for k, p in procs.items()}


def ok(name):
    r = outputs()[name]
    assert r.returncode == 0, f"{COMMANDS[name]} exited {r.returncode}:\n{r.stderr[-2000:]}"
    return r.stdout


def money(v):
    """fire.py's money() format."""
    return f"${v / 1e6:,.2f}M" if v >= 1e6 else f"${v / 1e3:,.0f}k"


def cell_text(r):
    return f"{r.x_end_age:.1f} (${r.stop_balance / 1e6:.2f}M)"


def test_solve_summary_matches_api(solved):
    out = ok("basic")
    assert "FIRE solutions for plan: example: SF, one kid" in out
    for si, name in ((RETIRE0, "Retire to $0"), (COAST, "Coast (core exp→60)"), (FLAT, "Retire, flat from 100")):
        r = solved["plan:sf_family"][si]
        row = next(line for line in out.splitlines() if line.strip("│ ").startswith(name))
        assert f"stop at age {r.x_end_age:.1f}" in row
        assert money(r.stop_balance) in row
        assert f"Income plan: {name}" in out
    assert "What-if" not in out
    for label in ("new grad", "mid", "senior", "coast job = core expenses"):
        assert label in out


def test_budget_prints_lines_and_exits():
    out = ok("budget")
    assert f"charges ×{config.EXPENSE_SAFETY_FACTOR:g} on top" in out
    rent = table_rows(out, "Rent")
    assert rent and rent[0][3] == "$950" and rent[0][4] == "month" and rent[0][5] == "$950"
    assert "UT Austin" in out and "preschool (4)" in out
    assert "FIRE solutions" not in out and "Income plan" not in out


def test_compare_taxes(solved):
    out = ok("compare")
    rows = [r for r in (table_rows(out, name) for name in config.TAX_VARIANTS) if r]
    assert len(rows) == len(config.TAX_VARIANTS)
    first = next(line for line in out.splitlines() if any(line.strip("│ ").startswith(n) for n in config.TAX_VARIANTS))
    assert first.strip("│ ").startswith("TX, MFJ after wedding"), "the plan's own tax setup is listed first"
    tx = table_rows(out, "TX, MFJ after wedding")[0]
    assert f"stop {solved['plan:austin_family'][RETIRE0].x_end_age:.1f}" in tx[1]
    for ca in ("CA, MFJ after wedding", "CA, single"):
        assert "wk later" in table_rows(out, ca)[0][1]
    assert "Coast" not in out  # -s restricted it to one goal


def test_x_flag_simulates_one_x():
    out = ok("x_ok")
    assert "Year by year: Retire to $0 (X=20)" in out
    assert "Retire to $0: solvent" in out
    ages = [int(r[0]) for r in table_rows(out, "") if r and r[0].isdigit()]
    assert ages[0] == 22 and ages[-1] == config.END_AGE - 1
    bad = ok("x_fail")
    assert re.search(r"Retire to \$0: runs out at age \d+\.\d", bad)
    assert "FIRE solutions" not in out + bad


def test_whatif_flag_matches_api(cells, solved):
    out = ok("whatif")
    got = {}
    for m in re.finditer(r"Retire to \$0: save (\$[\d,.]+k) extra at 25 → ([\d.]+) wk", out):
        got[m.group(1)] = float(m.group(2))
    assert set(got) == {"$100k", "$1k"}
    assert got["$1k"] <= got["$100k"]
    cfg = cells["plan:single_lean"][0]
    base = Solution(cfg.scenarios[RETIRE0], "years", solved["plan:single_lean"][RETIRE0])
    assert got["$100k"] == float(f"{what_if(cfg, base, 100_000, 25) / 7:.1f}")


def test_no_accounts_flag(solved):
    out = ok("accounts")
    r = solved["taxable:sf_family"][RETIRE0]
    assert f"stop at age {r.x_end_age:.1f}" in out
    assert "No 401(k)/Roth/529" not in out
    assert solved["acct:sf_family"][RETIRE0].x_end_age < r.x_end_age


def test_scenario_filter_is_case_insensitive_substring():
    out = ok("filter")
    summary = out.split("Income plan")[0]
    assert "Coast (core exp→60)" in summary and "Retire, flat from 100" in summary
    assert "Retire to $0" not in out
    assert "Year by year: Coast" in out and "Year by year: Retire, flat from 100" in out


def test_sweep_flag(solved):
    out = ok("sweep")
    assert "Sweep: Retire to $0" in out
    answer = solved["plan:single_lean"][RETIRE0].x
    rows = [r for r in table_rows(out, "") if r and re.fullmatch(r"\d+\.\d\d", r[0])]
    assert len(rows) >= 5
    for r in rows:
        x = float(r[0])
        if x >= round(answer, 2):
            assert "✓ solvent" in r[2]
        else:
            assert re.fullmatch(r"\d+\.\d", r[2]), r  # the age it runs out
    assert f"{answer:.2f}" in [r[0] for r in rows]


def test_list_shows_default_plans_and_grids():
    out = ok("list")
    lines = dict(line.split(": ", 1) for line in out.strip().splitlines())
    assert set(lines) == {"plans", "grids"}
    for p in DEFAULT_PLANS:
        assert re.search(rf"\b{p} \(", lines["plans"])
    for g in DEFAULT_GRIDS:
        assert re.search(rf"\b{g} \(", lines["grids"])
    for helper in ("ladders", "partners"):  # no PLAN/GRID: not listed
        assert not re.search(rf"(^|, ){helper} \(", lines["plans"] + ", " + lines["grids"])
    assert ok("grid_list") == out


def test_grid_taxes_cells_equal_individual_configs(solved):
    """Each grid cell equals solving make_config(plan, taxes=variant) on its own."""
    out = ok("grid_taxes")
    assert "Grid grid_taxes" in out
    rows = table_rows(out, "SF family")
    assert [r[1] for r in rows] == list(config.TAX_VARIANTS)
    for r in rows:
        want = [cell_text(solved[f"tax:{r[1]}"][si]) for si in (RETIRE0, COAST, FLAT)]
        assert r[2:5] == want


def test_grid_ladders_includes_salary_x(solved):
    out = ok("grid_ladders")
    rows = {r[1]: r[2:5] for r in table_rows(out, "SF family")}
    assert len(rows) == 4
    salary = rows["solve salary: 12 yrs at X"]
    assert all(re.fullmatch(r"\$[\d,]+k/yr", c) for c in salary)
    assert all(re.fullmatch(r"\d+\.\d \(\$\d+\.\d\dM\)", c) for k, v in rows.items() if "solve salary" not in k
               for c in v)
    # same amounts as sf_family's own career → same answers
    assert rows["big tech 120 → 175 → 230×X"] == [cell_text(solved["plan:sf_family"][si]) for si in (RETIRE0, COAST, FLAT)]


@pytest.mark.parametrize("name,msg", [("bad_plan", "No plan or grid named 'no_such_plan_xyz'"),
                                      ("bad_grid", "No plan or grid named 'no_such_grid_xyz'")])
def test_unknown_names_fail_cleanly(name, msg):
    r = outputs()[name]
    assert r.returncode != 0
    assert msg in r.stderr
    assert "Traceback" not in r.stderr
