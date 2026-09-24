"""Solve many configs at once (every combination of the axes in grid.py), in parallel."""

from __future__ import annotations

import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor

from .schema import Config
from .sim import Result
from .solve import solve

_CELLS: list[tuple[tuple[str, ...], Config]] = []  # set before forking workers


def _solve_cell(i: int) -> list[Result | None]:
    cfg = _CELLS[i][1]
    return [solve(cfg, s).best for s in cfg.scenarios]


def solve_grid(cells: list[tuple[tuple[str, ...], Config]]) -> list[tuple[tuple[str, ...], Config, list[Result | None]]]:
    """cells: [(labels, config)]. Returns [(labels, config, best result per scenario)] in the same order.
    Uses fork so workers inherit the configs (they hold closures, so they can't be pickled)."""
    global _CELLS
    _CELLS = cells
    with ProcessPoolExecutor(mp_context=mp.get_context("fork")) as pool:
        results = list(pool.map(_solve_cell, range(len(cells))))
    return [(labels, cfg, res) for (labels, cfg), res in zip(cells, results)]
