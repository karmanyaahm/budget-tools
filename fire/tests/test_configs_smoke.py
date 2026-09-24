"""Smoke tests: config.py and every shipped example plan/grid load, and plans solve. Not hand-checked, just
'it runs'. Only default_plans/ is tested (custom_plans/ is private and may not exist)."""

import importlib
import os
import pkgutil
import runpy

import pytest

from conftest import ROOT
from firemodel.schema import Config
from firemodel.sim import Result
from firemodel.solve import solve

MODULES = [m.name for m in pkgutil.iter_modules([os.path.join(ROOT, "default_plans")])]
PLANS = [m for m in MODULES if hasattr(importlib.import_module(f"default_plans.{m}"), "PLAN")]
GRIDS = [m for m in MODULES if hasattr(importlib.import_module(f"default_plans.{m}"), "GRID")]


def test_config_solves(monkeypatch):
    monkeypatch.chdir(ROOT)
    cfg = runpy.run_path(os.path.join(ROOT, "config.py"))["CONFIG"]
    assert isinstance(cfg, Config) and cfg.scenarios
    sol = solve(cfg, cfg.scenarios[0])
    assert isinstance(sol.best, Result) and sol.best.ok


@pytest.mark.parametrize("name", PLANS)
def test_default_plan_solves(name):
    from config import make_config
    plan = importlib.import_module(f"default_plans.{name}").PLAN
    cfg = make_config(plan)
    sol = solve(cfg, cfg.scenarios[0])
    assert isinstance(sol.best, Result) and sol.best.ok
    assert cfg.start_age < sol.best.x_end_age < cfg.end_age


@pytest.mark.parametrize("name", GRIDS)
def test_default_grid_builds(name):
    import grid
    cells = list(grid.cells(importlib.import_module(f"default_plans.{name}").GRID))
    assert cells and all(isinstance(cfg, Config) for _, cfg in cells)


def test_plans_and_grids_found():
    assert {"sf_family", "austin_family"} <= set(PLANS)
    assert "grid_cities" in GRIDS
