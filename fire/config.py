"""FIRE model configuration: markets, taxes, safety settings, and how a plan becomes a Config.

Your life (income ladder, expenses, events, which tax setup) lives in a plan file:
  custom_plans/   your own plans and grids (gitignored), searched first
  default_plans/  shipped examples
The default plan is DEFAULT_PLAN in custom_plans/__init__.py (or default_plans/__init__.py).
Pick another with:  uv run fire.py --plan NAME   (list them with --list)

Conventions (see DESIGN.md "Decisions"):
  * Real (today's) dollars everywhere; growth rates are real returns.
  * Everything keyed by AGE; ranges are half-open [start, end).
  * X marks the one value being solved for in each scenario.
"""

from dataclasses import replace

from firemodel.loader import default, load_plan
from firemodel.schema import Accounts, Config, Growth, Scenario
from firemodel.tax import Federal, Fica, NO_STATE_TAX, State, flat_state, regime

# ───────────────────────────── Basics ─────────────────────────────
START_YEAR = 2026
END_AGE = 112            # must stay solvent through the year before this age
# Safety margin (conservative): every expense is charged at 110% of the budgeted amount.
# Solvency is checked every day: the plan fails the first day the balance goes below $0.
EXPENSE_SAFETY_FACTOR = 1.1

# ───────────────────────────── Scenarios ─────────────────────────────
# X = years at the high salary. The coast job pays your core expenses (gross, before tax)
# until plan.coast_until. Kids, the wedding and big-ticket items come from the portfolio.
# "Flat" scenario: from this age the portfolio must hold its real value (stay flat or grow), so it
# isn't running down at the end. RETIRE instead means "flat from the day you stop working".
FLAT_FROM_AGE = 100


def scenarios_for(plan) -> list[Scenario]:
    """Each career path (plan.career plus any plan.alt_careers) gets the same three scenarios."""
    out = []
    for tag, career in {"": plan.career, **plan.alt_careers}.items():
        sfx = f" [{tag}]" if tag else ""
        out += [
            Scenario("Retire to $0" + sfx, career, plan.partner_income, plan.partner_share),
            Scenario(f"Coast (core exp→{plan.coast_until:g})" + sfx, career + plan.coast(), plan.partner_income,
                     plan.partner_share),
            Scenario(f"Retire, flat from {FLAT_FROM_AGE}" + sfx, career, plan.partner_income, plan.partner_share,
                     flat_from=FLAT_FROM_AGE),
        ]
    return out


# ───────────────────────────── Taxes ─────────────────────────────
# 2026 federal figures (IRS Rev. Proc. 2025-32; verify before relying on them).
FED_SINGLE = Federal(
    std_deduction=16_100,
    brackets=[(0, .10), (12_400, .12), (50_400, .22), (105_700, .24),
              (201_775, .32), (256_225, .35), (640_600, .37)],
    # CAPITAL GAINS: long-term brackets, stacked on ordinary taxable income.
    ltcg_brackets=[(0, 0.0), (49_450, .15), (545_500, .20)],
    niit_rate=.038, niit_threshold=200_000,
)
FED_MFJ = Federal(
    std_deduction=32_200,
    brackets=[(0, .10), (24_800, .12), (100_800, .22), (211_400, .24),
              (403_550, .32), (512_450, .35), (768_700, .37)],
    ltcg_brackets=[(0, 0.0), (98_900, .15), (613_700, .20)],
    niit_rate=.038, niit_threshold=250_000,
)
FICA_SINGLE = Fica(ss_rate=.062, ss_wage_base=184_500, medicare_rate=.0145,
                   addl_medicare_rate=.009, addl_medicare_threshold=200_000)
FICA_MFJ = Fica(ss_rate=.062, ss_wage_base=184_500, medicare_rate=.0145,
                addl_medicare_rate=.009, addl_medicare_threshold=250_000)

# California: 2025 brackets (latest published; verify). CA taxes capital gains as ordinary income.
# SDI payroll tax is 1.3% of all wages, with no cap. The 1% mental-health surcharge over $1M is folded
# into the top bracket. Personal exemption credits are ignored (conservative).
CA_SINGLE = State(
    std_deduction=5_706,
    brackets=[(0, .01), (11_079, .02), (26_264, .04), (41_452, .06), (57_542, .08), (72_724, .093),
              (371_479, .103), (445_771, .113), (742_953, .123), (1_000_000, .133)],
    payroll_rate=.013,
)
CA_MFJ = State(
    std_deduction=11_412,
    brackets=[(0, .01), (22_158, .02), (52_528, .04), (82_904, .06), (115_084, .08), (145_448, .093),
              (742_958, .103), (891_542, .113), (1_000_000, .123), (1_485_906, .133)],
    payroll_rate=.013,
)
NO_INCOME_TAX = NO_STATE_TAX   # TX, FL, NV, WA (WA's capital-gains tax on large gains is ignored)
IL = flat_state(0.0495)        # Illinois flat 4.95%, no standard deduction (exemptions ignored)
CO = flat_state(0.044)         # Colorado flat ~4.4% on federal taxable income (approx.; verify)


def single(state: State):
    """Filing single for life."""
    return lambda plan: [regime(plan.start_age, END_AGE, FED_SINGLE, FICA_SINGLE, state)]


def married(state_single: State, state_mfj: State):
    """Single until plan.wedding_age, then married filing jointly (one return for both earners).
    NOTE: only the incomes in the plan are taxed. MFJ with a partner who isn't modeled acts like MFJ with a
    $0-income partner (best case); use plan.with_partner(...) to put their income on the return."""
    def build(plan):
        wed = plan.wedding_age if plan.wedding_age is not None else END_AGE
        return [regime(plan.start_age, wed, FED_SINGLE, FICA_SINGLE, state_single),
                regime(wed, END_AGE, FED_MFJ, FICA_MFJ, state_mfj, joint=True)]
    return build


# A plan names one of these in plan.taxes. `--compare-taxes` solves the plan under every one.
TAX_VARIANTS = {
    "CA, MFJ after wedding": married(CA_SINGLE, CA_MFJ),
    "CA, single": single(CA_SINGLE),
    "TX, MFJ after wedding": married(NO_INCOME_TAX, NO_INCOME_TAX),
    "TX, single": single(NO_INCOME_TAX),
    "IL, MFJ after wedding": married(IL, IL),
    "CO, MFJ after wedding": married(CO, CO),
}

# ───────────────────────────── Growth ─────────────────────────────
# Growth(start_age, end_age, real annual rate), compounded daily.
GROWTH = [
    Growth(0, 60, 0.05),          # stock-heavy
    Growth(60, END_AGE, 0.04),    # more bonds in retirement
]

# ───────────────────────────── What-if grid ─────────────────────────────
# "If I saved an extra $A at age Y, how many weeks sooner could I stop / coast?"
WHATIF_AMOUNTS = [1_000, 10_000, 25_000, 50_000, 100_000]
WHATIF_AGES = [21, 23, 25, 28, 30, 31]

# ───────────────────────────── Tax-advantaged accounts ─────────────────────────────
# On by default; `fire.py --no-accounts` (or NO_ACCOUNTS) = taxable brokerage only. 2026 limits, per earner (a working
# partner adds their own); verify. See Accounts in firemodel/schema.py.
NO_ACCOUNTS = Accounts()
TAX_ADVANTAGED = Accounts(k401_limit=24_500, roth_limit=7_500, c529_limit=16_000)
ACCOUNTS = TAX_ADVANTAGED


# ───────────────────────────── Assemble ─────────────────────────────
def tax_schedule(plan, schedule) -> list:
    """A TAX_VARIANTS name, or [(from_age, name), ...] for a move: each variant's regimes clipped to its ages."""
    if isinstance(schedule, str):
        return TAX_VARIANTS[schedule](plan)
    out = []
    for k, (start, name) in enumerate(schedule):
        end = schedule[k + 1][0] if k + 1 < len(schedule) else END_AGE
        out += [replace(r, start=max(r.start, start), end=min(r.end, end))
                for r in TAX_VARIANTS[name](plan) if max(r.start, start) < min(r.end, end)]
    return out


def make_config(plan, taxes: str | None = None, accounts: Accounts | None = None) -> Config:
    """Build a Config for `plan`, taxed with `taxes` (a TAX_VARIANTS name) or else plan.taxes (a name or a
    [(from_age, name), ...] schedule, e.g. after a move)."""
    variants = {k: build(plan) for k, build in TAX_VARIANTS.items()}
    name = taxes or (plan.taxes if isinstance(plan.taxes, str) else " → ".join(n for _, n in plan.taxes))
    if name not in variants:
        variants[name] = tax_schedule(plan, plan.taxes)
    return Config(
        start_age=plan.start_age,
        end_age=END_AGE,
        start_year=START_YEAR,
        start_balance=plan.start_balance,
        start_basis=plan.start_basis,
        start_roth=plan.start_roth,
        scenarios=scenarios_for(plan),
        expenses=plan.expenses,
        taxes=variants[name],
        growth=GROWTH,
        safety_factor=EXPENSE_SAFETY_FACTOR,
        plan_name=plan.name,
        tax_variants={name: variants[name], **variants},  # this plan's own setup is listed first
        whatif_amounts=WHATIF_AMOUNTS,
        whatif_ages=WHATIF_AGES,
        accounts=ACCOUNTS if accounts is None else accounts,
    )


PLAN = load_plan(default("PLAN"))
CONFIG = make_config(PLAN)
