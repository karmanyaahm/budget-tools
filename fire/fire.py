"""FIRE model CLI. Usage: uv run fire.py [--config config.py] [--table] [--x N] [--whatif 10000@25] [--compare-taxes]"""

from __future__ import annotations

import argparse
import multiprocessing as mp
import runpy
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import plotext as plt
from rich.console import Console
from rich.table import Table

from firemodel.schema import DAY, MONTH, ONCE, RETIRE, WEEK, YEAR, Accounts, Config, Scenario, find_in_range
from firemodel.sim import DAYS, Result, expenses_by_category, lay_out, simulate
from firemodel.solve import Solution, solve, sweep, what_if, x_kind

console = Console()
SERIES_COLORS = ["cyan", "orange", "magenta", "green"]  # fixed order, by scenario
CATEGORY_COLORS = ["blue", "cyan", "green", "orange", "magenta", "red", "gray", "white", "green+"]  # plotext names
# (plotext's "orange" is ANSI yellow, and its "yellow" prints uncolored, so "yellow" isn't used)


def load_config(path: Path, plan: str | None = None, no_accounts: bool = False) -> Config:
    """CONFIG from the config file, or the named plan built with its make_config. --no-accounts: NO_ACCOUNTS."""
    mod = runpy.run_path(str(path))
    if plan is None and not no_accounts:
        return mod["CONFIG"]
    from firemodel.loader import load_plan
    return mod["make_config"](load_plan(plan) if plan else mod["PLAN"],
                              accounts=mod["NO_ACCOUNTS"] if no_accounts else None)


def money(v: float) -> str:
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1e6:
        return f"{sign}${v / 1e6:,.2f}M"
    if v >= 1e3:
        return f"{sign}${v / 1e3:,.0f}k"
    return f"{sign}${v:,.0f}"


def yw(years: float) -> str:
    """12.493 -> '12y 26w'"""
    days = round(years * DAYS)
    y, d = divmod(days, DAYS)
    return f"{y}y {d // 7}w" if d // 7 else f"{y}y"


def describe(sol: Solution) -> str:
    r = sol.best
    if r is None:
        return "[red]no solution within cap[/]"
    if sol.kind == "years":
        return f"work [bold]{yw(r.x)}[/] ({r.x:.2f} yrs) at terminal salary → stop at age [bold]{r.x_end_age:.1f}[/]"
    return f"needs salary of [bold]{money(r.x)}[/]/yr in the X segment"


def summary_table(sols: list[Solution], title: str | None = None, without: list[Solution] = ()) -> Table:
    """`without`: the same scenarios solved with no 401(k)/Roth/529, shown as an extra column."""
    t = Table(title=title or "FIRE solutions", caption="minimum X that stays solvent every day to END_AGE",
              header_style="bold")
    cols = ["Scenario", "Answer", "Portfolio when you stop", "Lowest after", "Balance at end"]
    for col in cols + (["No 401(k)/Roth/529"] if without else []):
        t.add_column(col, justify="left" if col in ("Scenario", "Answer") else "right")
    for i, s in enumerate(sols):
        r = s.best
        w = without[i].best if without else None
        extra = [] if not without else ["never" if w is None else f"${w.x / 1e3:,.0f}k/yr"
                                        if without[i].kind == "amount" else f"stop at {w.x_end_age:.1f}"]
        if r is None:
            t.add_row(s.scenario.name, describe(s), "", "", "", *extra)
            continue
        stop = money(r.stop_balance) if r.stop_balance is not None else ""
        t.add_row(s.scenario.name, describe(s), stop, money(r.min_balance_after_x), money(r.end_balance), *extra)
    return t


def income_plan(cfg: Config, sol: Solution) -> Table:
    """The solved income schedule in exact dollars. Consecutive segments with the same label and
    amount (e.g. the per-age coast salary) are merged into one row."""
    t = Table(title=f"Income plan: {sol.scenario.name}", header_style="bold")
    for col in ("Who", "Ages", "Before tax / yr", "After tax / yr", "What"):
        t.add_column(col, justify="left" if col in ("Who", "What") else "right")
    for who, sched in (("you", sol.scenario.income), ("partner", sol.scenario.partner_income)):
        rows: list[list] = []  # [start, end, amount, label]
        for s, e, amount, label in lay_out(sched, cfg.start_age, sol.best.x)[0]:
            if e <= s:
                continue
            if rows and rows[-1][3] == label and abs(rows[-1][2] - amount) < 0.5:
                rows[-1][1] = e
            else:
                rows.append([s, e, amount, label])
        for s, e, v, label in rows:
            net = find_in_range(cfg.taxes, int(s), "tax regime").income_left(v, (v,)) if v > 0 else 0
            t.add_row(who, f"{s:.1f}–{e:.1f}", f"${v:,.0f}", f"${net:,.0f}", label)
    return t


PER_NAME = {DAY: "day", WEEK: "week", MONTH: "month", YEAR: "year", ONCE: "once"}


def budget_table(cfg: Config) -> Table:
    """Every expense line in the plan, with its cadence and monthly/yearly equivalents."""
    t = Table(title="Budget (as written in the plan; the model charges ×"
              f"{cfg.safety_factor:g} on top)", header_style="bold")
    for c in ("Item", "Category", "Ages", "Amount", "Per", "$/month", "$/year"):
        t.add_column(c, justify="left" if c in ("Item", "Category", "Per") else "right")

    def edge(v, default):
        return "leave" if v is RETIRE else (default if v is None else f"{v:g}")

    for e in sorted(cfg.expenses, key=lambda e: (e.category == "kids", e.category, e.name)):
        once = e.per == ONCE
        yearly = e.amount * e.per / e.every  # averaged over the `every`-year cycle
        per = PER_NAME.get(e.per, f"{e.per}×/yr") + (f" /{e.every}yrs" if e.every > 1 else "")
        ages = edge(e.start, "") if once else f"{edge(e.start, '')}–{edge(e.end, 'end')}"
        t.add_row(e.name, e.category, ages, money(e.amount), per,
                  "" if once else f"${yearly / 12:,.0f}", "" if once else f"${yearly:,.0f}")
    return t


def sweep_table(sol: Solution) -> Table:
    t = Table(title=f"Sweep: {sol.scenario.name}", header_style="bold")
    label = "X (years)" if sol.kind == "years" else "X (salary)"
    for col in (label, "X ends at age", "Runs out at age", "Balance at end"):
        t.add_column(col, justify="right")
    for r in sol.sweep:
        mark = "[green]✓ solvent[/]" if r.ok else f"[red]{r.fail_age:.1f}[/]"
        x = f"{r.x:.2f}" if sol.kind == "years" else money(r.x)
        style = "bold" if sol.best is not None and r.x == sol.best.x else ""
        t.add_row(x, f"{r.x_end_age:.1f}", mark, money(r.end_balance), style=style)
    return t


def yearly_table(r: Result) -> Table:
    t = Table(title=f"Year by year: {r.scenario} (X={r.x:g})", header_style="bold")
    cols = ("Age", "Year", "Gross", "Take-home", "Expenses", "Invested", "Sold", "CG tax", "Balance", "Basis")
    for c in cols:
        t.add_column(c, justify="right")
    for row in r.rows:
        t.add_row(
            str(row.age), str(row.year), money(row.gross), money(row.net_income), money(row.expenses),
            money(row.invested), money(row.sold), money(row.cg_tax), money(row.balance), money(row.basis),
            style="red" if row.balance < 0 else "",
        )
    return t


# ───────────────────────────── what-if (parallel) ─────────────────────────────

_CTX: tuple[Config, list[Solution]] | None = None  # set before forking workers


def _whatif_job(job):
    si, amount, age = job
    cfg, sols = _CTX
    return job, what_if(cfg, sols[si], amount, age)


def run_whatifs(cfg: Config, sols: list[Solution], jobs) -> dict:
    global _CTX
    _CTX = (cfg, sols)
    # fork: workers inherit the config (which holds lambdas, so it can't be pickled).
    with ProcessPoolExecutor(mp_context=mp.get_context("fork")) as pool:
        return dict(pool.map(_whatif_job, jobs))


def whatif_cell(sol: Solution, v: float | None) -> str:
    if v is None:
        return "-"
    if sol.kind == "years":
        base_days = round(sol.best.x * DAYS)
        s = f"{v / 7:.1f} wk"
        return f"[green]≥{s} (X→0)[/]" if v >= base_days else s
    return f"-{money(v)}/yr"


def whatif_tables(cfg: Config, sols: list[Solution]) -> list[Table]:
    amounts, ages = cfg.whatif_amounts, cfg.whatif_ages
    jobs = [(si, a, g) for si, s in enumerate(sols) if s.best for g in ages for a in amounts]
    res = run_whatifs(cfg, sols, jobs)
    out = []
    for si, s in enumerate(sols):
        if not s.best:
            continue
        unit = "weeks sooner you can stop" if s.kind == "years" else "lower salary needed"
        t = Table(title=f"What-if: extra savings → {unit}\n{s.scenario.name}", header_style="bold")
        t.add_column("Saved at age", justify="right")
        for a in amounts:
            t.add_column(money(a), justify="right")
        for g in ages:
            t.add_row(f"{g:g}", *[whatif_cell(s, res[(si, a, g)]) for a in amounts])
        out.append(t)
    return out


# ───────────────────────────── tax comparison ─────────────────────────────


def compare_taxes(cfg: Config, scenarios: list[Scenario]) -> Table:
    t = Table(title="Tax assumptions: how much do they change the answer?", header_style="bold")
    t.add_column("Tax variant")
    for s in scenarios:
        t.add_column(s.name, justify="right")
    base = None
    for name, taxes in cfg.tax_variants.items():
        v = replace(cfg, taxes=taxes)
        sols = [solve(v, s) for s in scenarios]
        base = base or sols
        cells = []
        for s, b in zip(sols, base):
            if s.best is None:
                cells.append("no solution")
                continue
            if s.kind == "years":
                d = (b.best.x - s.best.x) * DAYS / 7 if b.best else 0
                delta = f" ([green]{d:.0f} wk sooner[/])" if d > 0.5 else (f" ([red]{-d:.0f} wk later[/])" if d < -0.5 else "")
                cells.append(f"{yw(s.best.x)} → stop {s.best.x_end_age:.1f}{delta}")
            else:
                cells.append(money(s.best.x))
        t.add_row(name, *cells)
    return t


# ───────────────────────────── charts ─────────────────────────────


def plot_setup(title: str, ylabel: str, xlabel: str = "Age"):
    plt.clear_figure()
    plt.theme("clear")
    plt.plotsize(min(plt.terminal_width() or 100, 120), 24)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)


def plot_trajectories(sols: list[Solution]):
    plot_setup("Net worth by age at the minimum X (real $, millions)", "$M")
    for i, s in enumerate(sols):
        if s.best is None:
            continue
        r = s.best
        color = SERIES_COLORS[i % len(SERIES_COLORS)]
        plt.plot([x.age for x in r.rows], [x.balance / 1e6 for x in r.rows], label=s.scenario.name, color=color)
        if r.x_end_age is not None:
            plt.vline(r.x_end_age, color=color)
    plt.hline(0, "gray")
    plt.show()
    console.print("[dim]Vertical lines mark where each scenario's X segment ends.[/]\n")


def plot_sweeps(sols: list[Solution]):
    year_sols = [(i, s) for i, s in enumerate(sols) if s.kind == "years"]
    if not year_sols:
        return
    plot_setup("Sweep: balance at END_AGE vs years at terminal salary ($M; below 0 = ran out)", "$M",
               "X (years at terminal salary)")
    for i, s in year_sols:
        plt.plot([r.x for r in s.sweep], [r.end_balance / 1e6 for r in s.sweep],
                 label=s.scenario.name, color=SERIES_COLORS[i % len(SERIES_COLORS)], marker="dot")
    plt.hline(0, "gray")
    plt.show()
    print()


def plot_expenses(cfg: Config, retire: float | None = None):
    """Stacked bars: annual expenses by category, per age (RETIRE-bound items use `retire`)."""
    cats = expenses_by_category(cfg, retire)
    order = sorted(cats, key=lambda c: -sum(cats[c]))  # biggest category at the bottom
    if len(order) > 8:  # fold the small ones into "other" (one color per category, no cycling)
        rest = order[7:]
        cats = {c: cats[c] for c in order[:7]} | {"other": [sum(v) for v in zip(*(cats[c] for c in rest))]}
        order = order[:7] + ["other"]
    ages = list(range(cfg.start_age, cfg.end_age))
    pad = f", incl. ×{cfg.safety_factor:g} safety factor" if cfg.safety_factor != 1 else ""
    plot_setup(f"Expenses per year by category ($k, today's dollars{pad})", "$k")
    colors = CATEGORY_COLORS[: len(order)]
    plt.stacked_bar(ages, [[v / 1e3 for v in cats[c]] for c in order], color=colors, width=0.8)
    plt.show()
    # Legend below the chart (plotext's in-plot legend covers the first bars), drawn with plotext's own colors.
    print("  ".join(f"{plt.colorize('██', c)} {cat}" for c, cat in zip(colors, order)) + "\n")


def plot_cashflow(r: Result):
    plot_setup(f"Cash flow: {r.scenario} (X={r.x:.2f}), $k/yr", "$k")
    ages = [x.age for x in r.rows]
    plt.plot(ages, [x.gross / 1e3 for x in r.rows], label="Gross income", color="cyan")
    plt.plot(ages, [x.net_income / 1e3 for x in r.rows], label="Take-home", color="blue")
    plt.plot(ages, [x.expenses / 1e3 for x in r.rows], label="Expenses", color="orange")
    plt.plot(ages, [x.sold / 1e3 for x in r.rows], label="Portfolio sold", color="magenta")
    plt.show()
    print()


def plot_accounts(r: Result):
    plot_setup(f"Accounts: {r.scenario} (X={r.x:.2f}), $M at the end of each year", "$M")
    ages = [x.age for x in r.rows]
    plt.plot(ages, [(x.balance - x.k401 - x.roth - x.c529) / 1e6 for x in r.rows], label="Taxable", color="cyan")
    plt.plot(ages, [x.k401 / 1e6 for x in r.rows], label="401(k) (pre-tax)", color="orange")
    plt.plot(ages, [x.roth / 1e6 for x in r.rows], label="Roth", color="green")
    if any(x.c529 for x in r.rows):
        plt.plot(ages, [x.c529 / 1e6 for x in r.rows], label="529", color="magenta")
    plt.show()
    print()


def parse_whatif(s: str) -> tuple[float, float]:
    amount, _, age = s.partition("@")
    return float(amount.replace("_", "").replace(",", "")), float(age)


def main():
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=here / "config.py", help="config file (default: config.py)")
    ap.add_argument("--plan", "-p", help="plan name from custom_plans/ or default_plans/ (default: DEFAULT_PLAN)")
    ap.add_argument("--no-accounts", action="store_true", help="taxable brokerage only: no 401(k) / Roth / 529")
    ap.add_argument("--list", action="store_true", help="list available plans and grids")
    ap.add_argument("--scenario", "-s", action="append", help="only run scenarios whose name contains this (repeatable)")
    ap.add_argument("--x", type=float, help="skip solving; simulate this X and print the yearly table")
    ap.add_argument("--table", "-t", action="store_true", help="print the yearly table for each solution")
    ap.add_argument("--whatif", "-w", action="append", type=parse_whatif, metavar="AMOUNT@AGE",
                    help="how much sooner if I save AMOUNT extra at AGE (repeatable); replaces the grid")
    ap.add_argument("--no-whatif", action="store_true", help="skip the what-if grid")
    ap.add_argument("--compare-taxes", action="store_true", help="solve under each TAX_VARIANTS entry and compare")
    ap.add_argument("--budget", "-b", action="store_true", help="print every expense line in the plan and exit")
    ap.add_argument("--sweep", action="store_true", help="also show the whole-year X sweep table + chart")
    ap.add_argument("--no-plot", action="store_true", help="skip terminal charts")
    args = ap.parse_args()

    if args.list:
        from firemodel.loader import available
        for kind, items in available().items():
            print(f"{kind}: " + ", ".join(f"{n} ({pkg})" for n, pkg in items))
        return
    cfg = load_config(args.config, args.plan, args.no_accounts)
    scenarios: list[Scenario] = cfg.scenarios
    if args.scenario:
        scenarios = [s for s in scenarios if any(q.lower() in s.name.lower() for q in args.scenario)]
    for s in scenarios:
        x_kind(s)  # validate: exactly one X

    if args.budget:
        console.print(budget_table(cfg))
        return

    if args.x is not None:
        for s in scenarios:
            r = simulate(cfg, s, args.x)
            console.print(yearly_table(r))
            console.print(f"{s.name}: " + ("[green]solvent[/]" if r.ok else f"[red]runs out at age {r.fail_age:.1f}[/]"))
            if not args.no_plot:
                plot_cashflow(r)
        return

    if args.compare_taxes:
        console.print(compare_taxes(cfg, scenarios))
        return

    sols = [solve(cfg, s) for s in scenarios]
    if args.sweep:
        for s in sols:
            s.sweep = sweep(cfg, s)
    without = [solve(replace(cfg, accounts=Accounts()), s) for s in scenarios] if cfg.accounts.active else []
    console.print(summary_table(sols, f"FIRE solutions for plan: {cfg.plan_name}" if cfg.plan_name else None, without))
    for s in sols:
        if s.best:
            console.print(income_plan(cfg, s))
    if args.sweep:
        for s in sols:
            console.print(sweep_table(s))
    if args.table:
        for s in sols:
            if s.best:
                console.print(yearly_table(s.best))

    if args.whatif:
        res = run_whatifs(cfg, sols, [(si, a, g) for si, s in enumerate(sols) for a, g in args.whatif])
        for (si, a, g), v in res.items():
            console.print(f"{sols[si].scenario.name}: save {money(a)} extra at {g:g} → {whatif_cell(sols[si], v)}")
    elif not args.no_whatif and cfg.whatif_amounts and cfg.whatif_ages:
        for t in whatif_tables(cfg, sols):
            console.print(t)

    if not args.no_plot:
        plot_trajectories(sols)
        if args.sweep:
            plot_sweeps(sols)
        plot_expenses(cfg, sols[0].best.x_end_age if sols and sols[0].best else None)
        if sols and sols[0].best:
            plot_cashflow(sols[0].best)
            if cfg.accounts.active:
                plot_accounts(sols[0].best)


if __name__ == "__main__":
    main()
