"""A LifePlan bundles everything about *your life* (income path, spending, events) so whole
plans can be swapped in config.py with one line. Markets and taxes stay in config.py."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from .schema import RETIRE, Expense, Income


@dataclass
class LifePlan:
    name: str
    start_age: int
    start_balance: float  # cash/brokerage at start_age
    start_basis: float
    wedding_age: int | None  # filing status switches to MFJ here (if the config uses MFJ)
    career: list[Income]  # ends with the X segment (years at the high salary)
    expenses: list[Expense]
    alt_careers: dict[str, list[Income]] = field(default_factory=dict)  # other income paths, same spending
    start_roth: float = 0.0  # Roth IRA at start_age (contributions; withdrawable any time, tax-free)
    # The coast job pays core expenses + this: (extra $/yr, years; None = the whole coast, until coast_until).
    coast_margin: tuple[float, float | None] = (10_000.0, None)
    coast_until: int = 60  # the coast job runs from the end of X until this age
    coast_exclude: set[str] = field(default_factory=lambda: {"kids", "events", "big-ticket"})
    partner_income: list[Income] = field(default_factory=list)
    partner_share: float = 1.0  # fraction of the partner's after-tax pay that goes into the shared pot
    taxes: str | list[tuple[float, str]] = "CA, MFJ after wedding"  # config.TAX_VARIANTS key, or [(from_age, key), ...]

    def core_expenses(self, age: int) -> float:
        """Annual spending excluding kids, events and big-ticket items (what the coast job pays).
        The coast job only runs after you leave the high salary, so RETIRE bounds count as passed."""
        core = [e for e in self.expenses if e.category not in self.coast_exclude]
        return annual_total(core, age, retire=-math.inf)

    def with_partner(self, partner: float | list[Income], share: float = 0.5,
                     years: tuple[float, float] = (25, 55), couple: dict[str, float] | None = None,
                     together_from: float | None = None) -> "LifePlan":
        """A joint-household copy: the partner earns `partner` (a flat salary worked over `years`, or a
        ladder of Income segments) and `share` of their take-home goes into the common pool. Their income is
        on the joint return (after the wedding), so it moves the household tax rate.
        couple: {line name or category: factor}, what each line costs for two adults vs one (rent 1.0,
                groceries 1.5, health insurance 2.0, ...). A name beats its category; every line must be covered.
                From `together_from` (default: when their pay starts) the pool pays an extra (factor - 1) × the
                line, as a "Partner: ..." line. Those are the partner's costs, so the coast job doesn't cover them.
        Without `couple`, the partner's costs aren't modeled: `share` is what they put in after paying their way."""
        income = partner if isinstance(partner, list) else [
            Income(partner, start=years[0], until=years[1], label="partner")]
        start = together_from if together_from is not None else min(
            seg.start for seg in income if seg.start is not None)  # default: when their pay starts
        costs = []
        for e in self.expenses if couple is not None else []:
            factor = couple.get(e.name, couple.get(e.category))
            if factor is None:
                raise KeyError(f"with_partner: no couple factor for {e.name!r} (category {e.category!r})")
            if factor != 1:
                costs.append(replace(e, name=f"Partner: {e.name}", amount=(factor - 1) * e.amount,
                                     category="partner", after=max(e.after, start)))
        desc = "ladder" if isinstance(partner, list) else f"${partner / 1e3:g}k"
        return replace(self, name=f"{self.name} + partner {desc} ({share:.0%} shared)",
                       partner_income=income, partner_share=share, expenses=self.expenses + costs,
                       coast_exclude=self.coast_exclude | {"partner"})

    def move_to(self, other: "LifePlan", at_age: float) -> "LifePlan":
        """Live this plan until `at_age`, then `other` (a different city): expenses switch at that age (this plan's
        lines stop, other's start), and so do taxes. Career, events before the move, and money come from this plan."""
        before = [replace(e, before=min(e.before, at_age)) for e in self.expenses]
        after = [replace(e, after=max(e.after, at_age)) for e in other.expenses]
        first = self.taxes if isinstance(self.taxes, list) else [(self.start_age, self.taxes)]
        second = other.taxes if isinstance(other.taxes, list) else [(at_age, other.taxes)]
        taxes = [(a, t) for a, t in first if a < at_age] + [(max(a, at_age), t) for a, t in second]
        return replace(self, name=f"{self.name} → {other.name} at {at_age:g}", expenses=before + after, taxes=taxes)

    def coast(self) -> list[Income]:
        """One segment per age paying that age's core expenses. Segments are laid back to back after
        the X segment, so the ages X already covers come out zero-length."""
        core = [Income(self.core_expenses(a), until=a + 1, label="coast job = core expenses")
                for a in range(self.start_age, self.coast_until)]
        extra, years = self.coast_margin
        if not extra:
            return core
        margin = (Income(extra, start=RETIRE, until=self.coast_until, label="coast margin") if years is None
                  else Income(extra, start=RETIRE, years=years, label="coast margin"))
        return core + [margin]
        return core + margin


def annual_total(expenses: list[Expense], age: int, retire: float | None = None) -> float:
    return sum(e.annual(age, retire) for e in expenses)
