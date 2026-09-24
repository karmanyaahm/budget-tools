"""Bracket math and builders that turn bracket tables (from config) into TaxRegimes."""

from __future__ import annotations

from dataclasses import dataclass

from .schema import TaxRegime

# A bracket table is [(threshold, rate), ...] sorted by threshold, starting at 0.
Brackets = list[tuple[float, float]]


def bracket_tax(taxable: float, brackets: Brackets) -> float:
    tax = 0.0
    for i, (lo, rate) in enumerate(brackets):
        hi = brackets[i + 1][0] if i + 1 < len(brackets) else float("inf")
        if taxable <= lo:
            break
        tax += (min(taxable, hi) - lo) * rate
    return tax


def stacked_tax(base: float, extra: float, brackets: Brackets) -> float:
    """Tax on `extra` when it sits on top of `base` in the same brackets."""
    if extra <= 0:
        return 0.0
    return bracket_tax(base + extra, brackets) - bracket_tax(base, brackets)


@dataclass(frozen=True)
class Federal:
    std_deduction: float
    brackets: Brackets
    ltcg_brackets: Brackets  # applied to gains stacked on ordinary taxable income
    niit_rate: float
    niit_threshold: float  # MAGI threshold for net investment income tax


@dataclass(frozen=True)
class Fica:
    ss_rate: float
    ss_wage_base: float  # per earner
    medicare_rate: float
    addl_medicare_rate: float
    addl_medicare_threshold: float  # household wages

    def tax(self, gross: float, earners: tuple[float, ...]) -> float:
        ss = sum(min(w, self.ss_wage_base) for w in earners) * self.ss_rate
        med = gross * self.medicare_rate
        addl = max(0.0, gross - self.addl_medicare_threshold) * self.addl_medicare_rate
        return ss + med + addl


@dataclass(frozen=True)
class State:
    std_deduction: float
    brackets: Brackets  # gains are taxed as ordinary income at the state level
    capgains_brackets: Brackets | None = None  # override if the state treats gains differently
    payroll_rate: float = 0.0  # uncapped employee payroll tax on wages (e.g. CA SDI)


def flat_state(rate: float, std_deduction: float = 0.0) -> State:
    return State(std_deduction, [(0, rate)])


NO_STATE_TAX = flat_state(0.0)


def _gain_tax(gain: float, gross: float, std_deduction: float, brackets: Brackets) -> float:
    """Tax on `gain` stacked on top of this year's ordinary income. Unused standard deduction
    shelters gains first, then gains fill `brackets` above the ordinary taxable income."""
    ordinary = max(0.0, gross - std_deduction)
    taxable_gain = max(0.0, gain - max(0.0, std_deduction - gross))
    return stacked_tax(ordinary, taxable_gain, brackets)


def _gain_breaks(gross: float, std_deduction: float, brackets: Brackets) -> list[float]:
    """Gain levels where _gain_tax(·, gross, ...) changes slope."""
    sheltered = max(0.0, std_deduction - gross)
    ordinary = max(0.0, gross - std_deduction)
    return [sheltered] + [sheltered + t - ordinary for t, _ in brackets if t > ordinary]


def regime(start, end, fed: Federal, fica: Fica, state: State, joint: bool = False) -> TaxRegime:
    """Build a TaxRegime whose functions implement federal + FICA + state rules."""
    state_cg = state.capgains_brackets or state.brackets

    def income_left(gross: float, earners: tuple[float, ...] = (), deferred: float = 0.0) -> float:
        """Take-home before any 401(k) deferral leaves the paycheck. `deferred` lowers the wages
        that federal and state income tax see; FICA and state payroll tax still apply to all of gross."""
        earners = earners or (gross,)
        fed_tax = bracket_tax(max(0.0, gross - deferred - fed.std_deduction), fed.brackets)
        st_tax = bracket_tax(max(0.0, gross - deferred - state.std_deduction), state.brackets)
        return gross - fed_tax - st_tax - fica.tax(gross, earners) - gross * state.payroll_rate

    def ordinary_tax(extra: float, wages: float) -> float:
        """Income tax (no FICA) on `extra` ordinary income, e.g. a 401(k) draw, stacked on `wages`."""
        return (_gain_tax(extra, wages, fed.std_deduction, fed.brackets)
                + _gain_tax(extra, wages, state.std_deduction, state.brackets))

    def ordinary_breaks(wages: float) -> list[float]:
        return sorted({0.0, *_gain_breaks(wages, fed.std_deduction, fed.brackets),
                       *_gain_breaks(wages, state.std_deduction, state.brackets)})

    def capgains_tax(gain: float, gross: float) -> float:
        if gain <= 0:
            return 0.0
        niit = fed.niit_rate * max(0.0, min(gain, gross + gain - fed.niit_threshold))
        return (_gain_tax(gain, gross, fed.std_deduction, fed.ltcg_brackets) + niit
                + _gain_tax(gain, gross, state.std_deduction, state_cg))

    def capgains_breaks(gross: float) -> list[float]:
        return sorted({0.0, max(0.0, fed.niit_threshold - gross),
                       *_gain_breaks(gross, fed.std_deduction, fed.ltcg_brackets),
                       *_gain_breaks(gross, state.std_deduction, state_cg)})

    return TaxRegime(start, end, income_left, capgains_tax, capgains_breaks, joint, ordinary_tax, ordinary_breaks)
