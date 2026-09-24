"""Shared helpers and fixtures for the integration suite (imported by the test modules; there is
deliberately no conftest.py here, so `from conftest import ...` in tests/*.py keeps finding tests/conftest.py).

* Imports config.py with the plan loader restricted to default_plans/ (config.py loads DEFAULT_PLAN at import
  time, and custom_plans/ is private); shipped plans/grids are then imported from default_plans/ directly.
* `solved`: one process-wide batch that solves every (config, scenario) pair the tests need, in parallel
  (fork, like firemodel.grid), so each expensive solve runs exactly once.
* `run_cli`: runs `uv run fire.py/grid.py ...` as a subprocess with a wide, plain terminal.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import firemodel.loader as loader  # noqa: E402

# config.py loads DEFAULT_PLAN at import time; point the loader at default_plans/ only while importing it, so the
# private custom_plans/ is never loaded, then put it back (the unit tests share this process).
_saved_packages = loader.PACKAGES
loader.PACKAGES = ("default_plans",)
try:
    import config  # noqa: E402
    import grid as grid_cli  # noqa: E402  (ROOT/grid.py: the sweep CLI module, for grid.cells)
finally:
    loader.PACKAGES = _saved_packages

import functools  # noqa: E402
import importlib  # noqa: E402
import importlib.util  # noqa: E402

from firemodel.schema import Income  # noqa: E402
from firemodel.solve import solve  # noqa: E402

# tests/conftest.py's hand-checkable builders, loaded under a unique module name
_spec = importlib.util.spec_from_file_location("fire_unit_builders", ROOT / "tests" / "conftest.py")
builders = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(builders)
make_cfg, scen = builders.make_cfg, builders.scen

DEFAULT_PLANS = ["sf_family", "austin_family", "single_lean", "three_kids", "couple_with_car", "sf_to_austin"]
DEFAULT_GRIDS = ["grid_cities", "grid_taxes", "grid_profiles", "grid_ladders"]
README_SAFETY_FACTOR = 1.2  # what README.md says EXPENSE_SAFETY_FACTOR is (only used to test README's own numbers)
RETIRE0, COAST, FLAT = 0, 1, 2  # scenario indices produced by config.scenarios_for


def plan(name):
    """A shipped plan, straight from default_plans/ (never a same-name custom one)."""
    return importlib.import_module(f"default_plans.{name}").PLAN


def load_grid(name):
    return importlib.import_module(f"default_plans.{name}").GRID


def build_cells() -> dict[str, tuple[config.Config, tuple[int, ...]]]:
    """name -> (config, scenario indices to solve)."""
    cells: dict[str, tuple] = {}
    all3 = (RETIRE0, COAST, FLAT)
    for name in DEFAULT_PLANS:
        cells[f"plan:{name}"] = (config.make_config(plan(name)), all3)
        idx = all3 if name == "sf_family" else (RETIRE0, COAST)
        cells[f"acct:{name}"] = (config.make_config(plan(name), accounts=config.TAX_ADVANTAGED), idx)
        if name in ("sf_family", "austin_family"):
            cells[f"taxable:{name}"] = (config.make_config(plan(name), accounts=config.NO_ACCOUNTS), idx)
    sf = plan("sf_family")
    for variant in config.TAX_VARIANTS:
        cells[f"tax:{variant}"] = (config.make_config(sf, taxes=variant), all3)
    base = config.make_config(sf)
    cells["rich"] = (replace(base, start_balance=200_000, start_basis=150_000), (RETIRE0, COAST))
    cells["safety+0.1"] = (replace(base, safety_factor=base.safety_factor + 0.1), (RETIRE0, COAST))
    cells["social_security"] = (config.make_config(replace(
        sf, career=sf.career + [Income(30_000, start=67, until=config.END_AGE, label="Social Security")])),
        (RETIRE0,))
    for salary in (70_000, 150_000):
        cells[f"p0single:{salary}"] = (config.make_config(sf.with_partner(salary, share=0.0), "CA, single"),
                                       (RETIRE0,))
    cells["p0mfj:150000"] = (config.make_config(sf.with_partner(150_000, share=0.0)), (RETIRE0,))
    # README's tables were made with the settings README states: safety factor 1.2, coast job = core expenses only
    readme_sf = replace(sf, coast_margin=(0.0, None)) if hasattr(sf, "coast_margin") else sf
    cells["readme-settings:sf_family"] = (replace(config.make_config(readme_sf, accounts=config.NO_ACCOUNTS), safety_factor=README_SAFETY_FACTOR),
                                          all3)
    cells["readme-settings-acct:sf_family"] = (replace(config.make_config(readme_sf, accounts=config.TAX_ADVANTAGED),
                                                       safety_factor=README_SAFETY_FACTOR), all3)
    for gname in ("grid_cities", "grid_profiles"):
        for labels, cfg in grid_cli.cells(load_grid(gname)):
            cells[f"{gname}:" + " | ".join(labels)] = (cfg, all3)
    return cells


_JOBS: list = []  # (cell name, scenario index, cfg); set before forking


def _solve_job(i):
    name, si, cfg = _JOBS[i]
    return name, si, solve(cfg, cfg.scenarios[si]).best


@functools.cache
def all_cells():
    return build_cells()


@functools.cache
def all_solved():
    """{cell name: {scenario index: Result | None}} for every cell in build_cells(), solved once per process."""
    global _JOBS
    cells = all_cells()
    jobs = [(name, si, cfg) for name, (cfg, idx) in cells.items() for si in idx]
    # slowest first (accounts, coast) so the pool finishes evenly
    jobs.sort(key=lambda j: (not j[2].accounts.active, j[1] != COAST))
    _JOBS = jobs
    out: dict[str, dict[int, object]] = {name: {} for name in cells}
    with ProcessPoolExecutor(mp_context=mp.get_context("fork")) as pool:
        for name, si, res in pool.map(_solve_job, range(len(jobs))):
            out[name][si] = res
    return out


# Fixtures: test modules import these names (no conftest.py here, so tests/conftest.py stays the only `conftest`).
@pytest.fixture
def cells():
    return all_cells()


@pytest.fixture
def solved():
    return all_solved()


# ───────────────────────────── CLI ─────────────────────────────


def _env():
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "FORCE_COLOR")}
    env.update(COLUMNS="250", LINES="60", NO_COLOR="1", TERM="dumb")
    return env


def start_cli(*args: str) -> subprocess.Popen:
    """Start `uv run <args>` in ROOT (args[0] is fire.py or grid.py)."""
    return subprocess.Popen(["uv", "run", *args], cwd=ROOT, env=_env(), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)


def finish(p: subprocess.Popen, timeout=120) -> subprocess.CompletedProcess:
    out, err = p.communicate(timeout=timeout)
    return subprocess.CompletedProcess(p.args, p.returncode, out, err)


def run_cli(*args: str, timeout=120) -> subprocess.CompletedProcess:
    return finish(start_cli(*args), timeout)


def table_rows(text: str, first_cell: str) -> list[list[str]]:
    """Rows of a rich box table whose first cell starts with `first_cell`, split on the │ separators."""
    rows = []
    for line in text.splitlines():
        cols = [c.strip() for c in line.strip().strip("│┃").split("│")]
        if cols and cols[0].startswith(first_cell):
            rows.append(cols)
    return rows
