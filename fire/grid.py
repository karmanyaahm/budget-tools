"""Sweep every combination of a GRID's axes and print one table.

  uv run grid.py            run DEFAULT_GRID (custom_plans/ first, then default_plans/)
  uv run grid.py NAME       run the grid module NAME
  uv run grid.py --list     list available plans and grids

A grid module defines GRID, a dict of axes. Each axis is {label: value}:
  "plans"     (required) {label: LifePlan}. Each plan brings its own expenses and tax setup (plan.taxes).
  "ladders"   {label: [Income, ...]} replaces the plan's career (must contain one X).
  "partners"  {label: None | salary | [Income, ...] | dict of plan.with_partner(...) arguments}.
  "taxes"     {label: config.TAX_VARIANTS name} overrides plan.taxes.
  "accounts"  {label: Accounts} (config.NO_ACCOUNTS / config.TAX_ADVANTAGED).
"""

import argparse
import itertools
from dataclasses import replace

from rich.console import Console
from rich.table import Table

from config import make_config
from firemodel.grid import solve_grid
from firemodel.loader import available, default, load_grid
from firemodel.solve import x_kind

AXES = ("plans", "ladders", "partners", "taxes", "accounts")


def cells(grid: dict):
    axes = [(a, grid[a]) for a in AXES if a in grid]
    for combo in itertools.product(*(list(values.items()) for _, values in axes)):
        choice = {a: value for (a, _), (_, value) in zip(axes, combo)}
        plan = choice["plans"]
        if "ladders" in choice:
            plan = replace(plan, career=choice["ladders"], alt_careers={})
        else:
            plan = replace(plan, alt_careers={})
        partner = choice.get("partners")
        if partner is not None:  # a salary, a ladder, or a dict of with_partner(...) arguments
            plan = plan.with_partner(**partner) if isinstance(partner, dict) else plan.with_partner(partner)
        cfg = make_config(plan, choice.get("taxes"), choice.get("accounts"))
        yield tuple(label for label, _ in combo), cfg


def cell(scenario, r) -> str:
    """Stop age and portfolio then; for a salary-X ladder, the salary needed instead."""
    if r is None:
        return "never"
    if x_kind(scenario) == "amount":
        return f"${r.x / 1e3:,.0f}k/yr"
    return f"{r.x_end_age:.1f} (${r.stop_balance / 1e6:.2f}M)"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", nargs="?", help="grid module name (default: DEFAULT_GRID)")
    ap.add_argument("--list", action="store_true", help="list available plans and grids")
    args = ap.parse_args()
    if args.list:
        for kind, items in available().items():
            print(f"{kind}: " + ", ".join(f"{n} ({pkg})" for n, pkg in items))
        return

    name = args.name or default("GRID")
    grid = load_grid(name)
    rows = solve_grid(list(cells(grid)))
    t = Table(title=f"Grid {name}: stop age (portfolio when you stop)", header_style="bold")
    for axis in AXES:
        if axis in grid:
            t.add_column(axis.title())
    for s in rows[0][1].scenarios:
        t.add_column(s.name, justify="right")
    for labels, cfg, results in rows:
        t.add_row(*labels, *[cell(s, r) for s, r in zip(cfg.scenarios, results)])
    Console().print(t)


if __name__ == "__main__":
    main()
