"""Data types shared by config and logic. No numbers live here."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Callable

# Expense periods: how many times per year the amount recurs.
DAY = 365
WEEK = 52
MONTH = 12
YEAR = 1
ONCE = 0  # charged a single time, at `start`


class _X:
    """Sentinel for the swept/solved value in an income schedule."""

    def __repr__(self) -> str:
        return "X"


X = _X()


class _Retire:
    """Sentinel for an expense start/end: 'the age you leave the high-salary job' (end of X)."""

    def __repr__(self) -> str:
        return "RETIRE"


RETIRE = _Retire()


@dataclass(frozen=True)
class Income:
    """One segment of an income schedule. Segments are laid end to end.

    Give exactly one of `years` (duration) or `until` (absolute end age).
    `start` overrides the default of beginning where the previous segment ended.
    Either `amount` or `years` may be the sentinel `X`.
    `start=RETIRE` starts it when the X segment ends (put it after the X segment). Overlapping segments add up.
    """

    amount: float | _X
    years: float | _X | None = None
    until: float | None = None
    start: float | _Retire | None = None
    label: str = ""

    def __post_init__(self):
        if (self.years is None) == (self.until is None):
            raise ValueError(f"Income {self}: give exactly one of years= or until=")


@dataclass(frozen=True)
class Expense:
    """`amount` × `per` per year for ages in [start, end), every `every` years.
    With per=ONCE the amount is charged only at `start`.
    `start`/`end` may be RETIRE: the age the X segment ends (e.g. "work stops feeding me").
    `after`/`before` clip it to [after, before) on top of that; LifePlan.move_to uses them for a move."""

    name: str
    amount: float
    per: int
    start: float | _Retire
    end: float | _Retire | None = None
    every: int = 1
    category: str = ""
    after: float = -math.inf   # never charged before this age
    before: float = math.inf   # never charged at or after this age

    @property
    def uses_retire(self) -> bool:
        return self.start is RETIRE or self.end is RETIRE

    def _raw_bounds(self, retire: float | None) -> tuple[float, float]:
        r = math.inf if retire is None else retire
        s = r if self.start is RETIRE else self.start
        e = r if self.end is RETIRE else (math.inf if self.end is None else self.end)
        return s, e

    def bounds(self, retire: float | None = None) -> tuple[float, float]:
        """Resolved [start, end), clipped to [after, before). retire=None with a RETIRE bound means 'never retires'."""
        s, e = self._raw_bounds(retire)
        return max(s, self.after), min(e, self.before)

    def once_at(self, retire: float | None = None) -> float | None:
        """For a ONCE item: the age it's charged, or None if it falls outside [after, before) or never happens."""
        s = self._raw_bounds(retire)[0]
        return s if math.isfinite(s) and self.after <= s < self.before else None

    def annual(self, age: int, retire: float | None = None) -> float:
        if self.per == ONCE:
            at = self.once_at(retire)
            return self.amount if at is not None and age == math.floor(at) else 0.0
        s, e = self.bounds(retire)
        if age < s or age >= e:
            return 0.0
        first = self._raw_bounds(retire)[0]  # every-N cadence counts from the original start, not the clip
        if self.every > 1 and math.isfinite(first) and (age - math.ceil(first)) % self.every:
            return 0.0
        return self.amount * self.per


@dataclass(frozen=True)
class TaxRegime:
    """Tax rules for ages in [start, end).

    income_left(gross_wages, earners) -> take-home pay
    capgains_tax(gain, gross_wages) -> tax owed on `gain` realized in a year
        that also had `gross_wages` of ordinary income.
    capgains_breaks(gross_wages) -> gain levels where capgains_tax's marginal rate changes
        (it's piecewise linear), so the daily sim can pay CG tax exactly.
    joint: True for a married-filing-jointly regime (both earners on one return). Otherwise each
        earner is taxed on their own wages, and capital gains stack on your wages only.
    ordinary_tax(extra, wages) / ordinary_breaks(wages): income tax on extra ordinary income
        (401(k) draws, non-qualified Roth/529 earnings) stacked on wages, and where its rate changes.
    """

    start: float
    end: float
    income_left: Callable[..., float]
    capgains_tax: Callable[[float, float], float]
    capgains_breaks: Callable[[float], list[float]]
    joint: bool = False
    ordinary_tax: Callable[[float, float], float] = lambda extra, wages: 0.0
    ordinary_breaks: Callable[[float], list[float]] = lambda wages: [0.0]


@dataclass(frozen=True)
class Accounts:
    """Tax-advantaged accounts. All limits 0 (the default) = taxable brokerage only.
    Contributions are set each year by backward liability matching (sim.plan_accounts): the 401(k)/Roth get
    only what's needed after penalty_age, the 529 only what college needs, frontloaded, and only while
    taxable still covers everything else on every future day (weddings, the pre-59½ bridge, ...).
    Contributions come only from career wages: yours before X ends, plus a partner's pooled pay. The household has one
    401(k) and one Roth; each working earner adds their own limit (capped at their pay)."""

    k401_limit: float = 0.0     # traditional 401(k) deferral per year (pre-tax for income tax, not FICA)
    roth_limit: float = 0.0     # (backdoor) Roth IRA per year, from after-tax pay
    c529_limit: float = 0.0     # 529 per year, from c529_from_age while it's short of remaining college costs
    c529_from_age: float = 0.0
    penalty_age: float = 59.5   # before this, 401(k) draws and Roth/529 earnings pay +10%

    @property
    def active(self) -> bool:
        return self.k401_limit > 0 or self.roth_limit > 0 or self.c529_limit > 0


@dataclass(frozen=True)
class Growth:
    """Real annual return `rate` for ages in [start, end), compounded daily."""

    start: float
    end: float
    rate: float


@dataclass
class Scenario:
    name: str
    income: list[Income]
    partner_income: list[Income] = field(default_factory=list)
    partner_share: float = 1.0  # fraction of the partner's after-tax pay that goes into the shared pot
    # From this age (or RETIRE: the day the X segment ends) the balance may never drop below its value
    # at that moment (in real dollars): the portfolio stays flat or grows from then on.
    flat_from: float | _Retire | None = None


@dataclass
class Config:
    start_age: int
    end_age: int
    start_year: int
    start_balance: float
    start_basis: float
    scenarios: list[Scenario]
    expenses: list[Expense]
    taxes: list[TaxRegime]
    growth: list[Growth]
    safety_factor: float = 1.0  # every expense is charged × this
    plan_name: str = ""
    tax_variants: dict[str, list[TaxRegime]] = field(default_factory=dict)  # for --compare-taxes
    whatif_amounts: list[float] = field(default_factory=list)
    whatif_ages: list[float] = field(default_factory=list)
    max_x_amount: float = 5_000_000
    accounts: Accounts = field(default_factory=Accounts)
    start_roth: float = 0.0  # Roth IRA at start_age, all contributions (withdrawable any time, tax-free)


def find_in_range(items, age, what):
    for it in items:
        if it.start <= age < it.end:
            return it
    raise ValueError(f"No {what} covers age {age}")


def substitute_x(schedule: list[Income], value: float) -> list[Income]:
    out = []
    for seg in schedule:
        if seg.amount is X:
            seg = replace(seg, amount=value)
        if seg.years is X:
            seg = replace(seg, years=value)
        out.append(seg)
    return out
