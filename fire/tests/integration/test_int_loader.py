"""firemodel.loader: plan/grid lookup, defaults, and the custom-over-default override, using throwaway packages in
tmp_path (custom_plans/ itself is never touched)."""

from __future__ import annotations

import importlib
import sys
import textwrap
import uuid

import pytest

from fireint import DEFAULT_GRIDS, DEFAULT_PLANS, config, loader

PLAN_SRC = """
from dataclasses import replace
from default_plans.single_lean import PLAN as _BASE
PLAN = replace(_BASE, name={name!r}, start_balance={balance})
"""


@pytest.fixture
def pkgs(tmp_path, monkeypatch):
    """Two packages in tmp_path, searched custom first: (custom, default, hidden-without-__init__)."""
    tag = uuid.uuid4().hex[:8]
    custom, default, hidden = f"zz_custom_{tag}", f"zz_default_{tag}", f"zz_noinit_{tag}"

    def write(pkg, files):
        (tmp_path / pkg).mkdir()
        for fname, src in files.items():
            (tmp_path / pkg / fname).write_text(textwrap.dedent(src))

    write(custom, {
        "__init__.py": 'DEFAULT_PLAN = "mine"\n',  # no DEFAULT_GRID: falls through to the next package
        "mine.py": PLAN_SRC.format(name="custom mine", balance=1),
        "shared.py": PLAN_SRC.format(name="custom shared", balance=2),
    })
    write(default, {
        "__init__.py": 'DEFAULT_PLAN = "shared"\nDEFAULT_GRID = "g"\n',
        "shared.py": PLAN_SRC.format(name="default shared", balance=3),
        "only_default.py": PLAN_SRC.format(name="default only", balance=4),
        "g.py": f"from {default}.shared import PLAN as _P\nGRID = {{'plans': {{'x': _P}}}}\n",
        "notaplan.py": "VALUE = 1\n",
    })
    write(hidden, {"hidden.py": PLAN_SRC.format(name="hidden", balance=5)})

    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(loader, "ROOT", tmp_path)
    monkeypatch.setattr(loader, "PACKAGES", (custom, default, hidden))
    importlib.invalidate_caches()
    yield custom, default, hidden
    for mod in [m for m in sys.modules if m.split(".")[0] in (custom, default, hidden)]:
        del sys.modules[mod]


def test_custom_wins_over_same_name_default(pkgs):
    assert loader.load_plan("shared").name == "custom shared"
    assert loader.load_plan("only_default").name == "default only"
    assert loader.load_plan("mine").start_balance == 1


def test_defaults_search_custom_first_and_fall_through(pkgs):
    assert loader.default("PLAN") == "mine"
    assert loader.default("GRID") == "g"
    assert loader.load_grid(loader.default("GRID"))["plans"]["x"].name == "default shared"


def test_available_hides_shadowed_defaults(pkgs):
    custom, default, _ = pkgs
    got = loader.available()
    assert sorted(got["plans"]) == sorted([("mine", custom), ("shared", custom), ("only_default", default)])
    assert got["grids"] == [("g", default)]


def test_package_without_init_is_invisible(pkgs):
    with pytest.raises(SystemExit, match="No plan or grid named 'hidden'"):
        loader.load_plan("hidden")


def test_wrong_kind_and_missing_names(pkgs):
    with pytest.raises(SystemExit, match="has no GRID"):
        loader.load_grid("mine")
    with pytest.raises(SystemExit, match="has no PLAN"):
        loader.load_plan("g")
    with pytest.raises(SystemExit, match="has no PLAN"):
        loader.load_plan("notaplan")
    with pytest.raises(SystemExit, match="No plan or grid named 'nope'"):
        loader.load_plan("nope")


def test_no_default_anywhere(pkgs, monkeypatch):
    custom, default, _ = pkgs
    monkeypatch.setattr(loader, "PACKAGES", (custom,))
    with pytest.raises(SystemExit, match="No DEFAULT_GRID"):
        loader.default("GRID")


def test_loaded_custom_plan_builds_and_solves_like_any_plan(pkgs):
    """A same-name override is what make_config gets: its numbers, not the default's."""
    cfg = config.make_config(loader.load_plan("shared"))
    assert cfg.plan_name == "custom shared" and cfg.start_balance == 2
    assert len(cfg.scenarios) == 3


def test_shipped_package(monkeypatch):
    monkeypatch.setattr(loader, "PACKAGES", ("default_plans",))
    got = loader.available()
    assert sorted(n for n, _ in got["plans"]) == sorted(DEFAULT_PLANS)
    assert sorted(n for n, _ in got["grids"]) == sorted(DEFAULT_GRIDS)
    assert {pkg for _, pkg in got["plans"] + got["grids"]} == {"default_plans"}
    assert loader.default("PLAN") == "sf_family"
    assert loader.default("GRID") == "grid_cities"
    for g in DEFAULT_GRIDS:
        grid = loader.load_grid(g)
        assert "plans" in grid and set(grid) <= {"plans", "ladders", "partners", "taxes", "accounts"}
