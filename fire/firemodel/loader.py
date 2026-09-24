"""Find plans and grids by name. Your own files in custom_plans/ (gitignored) win over the examples in
default_plans/ (shipped). A plan module defines PLAN (a LifePlan); a grid module defines GRID (a dict of axes).
Each package's __init__.py may set DEFAULT_PLAN / DEFAULT_GRID."""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("custom_plans", "default_plans")  # search order


def _packages():
    return [p for p in PACKAGES if (ROOT / p / "__init__.py").exists()]


def module(name: str):
    for pkg in _packages():
        if (ROOT / pkg / f"{name}.py").exists():
            return importlib.import_module(f"{pkg}.{name}")
    raise SystemExit(f"No plan or grid named {name!r} in {' or '.join(_packages())}/ (see --list)")


def load_plan(name: str):
    mod = module(name)
    if not hasattr(mod, "PLAN"):
        raise SystemExit(f"{mod.__name__} has no PLAN")
    return mod.PLAN


def load_grid(name: str) -> dict:
    mod = module(name)
    if not hasattr(mod, "GRID"):
        raise SystemExit(f"{mod.__name__} has no GRID")
    return mod.GRID


def default(kind: str) -> str:
    """kind: "PLAN" or "GRID". The first package (custom first) whose __init__ sets DEFAULT_<kind>."""
    for pkg in _packages():
        name = getattr(importlib.import_module(pkg), f"DEFAULT_{kind}", None)
        if name:
            return name
    raise SystemExit(f"No DEFAULT_{kind} set in {' or '.join(_packages())}/__init__.py")


def available() -> dict[str, list[tuple[str, str]]]:
    """{"plans": [(name, package)], "grids": [...]}; a custom file hides a default one of the same name."""
    seen, out = set(), {"plans": [], "grids": []}
    for pkg in _packages():
        for info in pkgutil.iter_modules([str(ROOT / pkg)]):
            if info.name in seen:
                continue
            mod = importlib.import_module(f"{pkg}.{info.name}")
            if hasattr(mod, "PLAN"):
                out["plans"].append((info.name, pkg))
            if hasattr(mod, "GRID"):
                out["grids"].append((info.name, pkg))
            seen.add(info.name)
    return out
