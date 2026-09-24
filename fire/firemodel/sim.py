"""Day-by-day simulation. Pure: takes a Config + Scenario + X value, returns a Result.

Order within a day (see DESIGN.md): lump-sum deposits land → wages come in (already net of that
year's average income tax) → that day's expenses go out (recurring bills accrue evenly per day) → a surplus is invested, or a shortfall is
sold, paying capital gains tax on that sale at the exact marginal rate → one day of growth.
The plan fails the first day the balance is below $0 (or, for flat_from scenarios, below its value
at the flat_from age).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import accumulate

from .schema import ONCE, RETIRE, X, Config, Income, Scenario, TaxRegime, find_in_range, substitute_x

DAYS = 365  # no leap days


@dataclass
class Row:
    """One age-year, aggregated from its days."""

    age: int
    year: int
    gross: float  # household wages (self + partner)
    net_income: float  # after income tax, FICA, state payroll tax
    expenses: float
    sold: float  # portfolio sold (covers the shortfall plus the CG tax on that sale)
    cg_tax: float
    invested: float  # surplus + lump-sum deposits added to the portfolio
    balance: float  # end of year: all accounts together (401(k) dollars are pre-tax)
    basis: float  # taxable account's cost basis
    k401: float = 0.0  # end-of-year balances of the tax-advantaged accounts (included in balance)
    roth: float = 0.0
    c529: float = 0.0
    ord_tax: float = 0.0  # income tax + 10% penalties on 401(k)/Roth/529 withdrawals
    contributed: float = 0.0  # into 401(k) + Roth + 529 this year


@dataclass
class Result:
    scenario: str
    x: float
    rows: list[Row] = field(default_factory=list)
    fail_age: float | None = None  # fractional age when the balance first went below $0
    x_end_age: float | None = None  # age at which the X segment ends ("retire" age)
    stop_balance: float | None = None  # portfolio on the day the X segment ends

    @property
    def ok(self) -> bool:
        return self.fail_age is None

    @property
    def end_balance(self) -> float:
        return self.rows[-1].balance if self.rows else 0.0

    @property
    def min_balance_after_x(self) -> float:
        """Lowest year-end balance once the X segment is over (the tightest point of the drawdown)."""
        start = self.x_end_age if self.x_end_age is not None else -1
        return min((r.balance for r in self.rows if r.age + 1 > start), default=self.end_balance)


# ───────────────────────────── schedules → per-day arrays ─────────────────────────────


def lay_out(schedule: list[Income], start_age: float, x: float) -> tuple[list[tuple[float, float, float, str]], float | None]:
    """Substitute X, then resolve back-to-back segments into (start, end, amount, label) spans.
    Also returns the end age of the X segment (None if the schedule has no X)."""
    spans, cursor, x_end = [], start_age, None
    for orig, seg in zip(schedule, substitute_x(schedule, x)):
        if seg.start is RETIRE:
            if x_end is None:
                raise ValueError(f"Income {seg} starts at RETIRE but comes before the X segment")
            s = x_end
        else:
            s = cursor if seg.start is None else seg.start
        e = s + seg.years if seg.years is not None else seg.until
        e = max(s, e)  # e.g. coast "until 60" when X already ran past 60
        spans.append((s, e, seg.amount, seg.label))
        if orig.amount is X or orig.years is X:
            x_end = e
        cursor = e
    return spans, x_end


def day_index(age: float, start_age: int) -> int:
    return math.ceil(round((age - start_age) * DAYS, 6))


def daily_wages(spans, start_age: int, n_days: int) -> list[float]:
    out = [0.0] * n_days
    for s, e, amount, _ in spans:
        for i in range(max(0, day_index(s, start_age)), min(n_days, day_index(e, start_age))):
            out[i] += amount / DAYS
    return out


def daily_expenses(cfg: Config, retire: float | None, only=None) -> list[float]:
    """Per-day expenses for one run (RETIRE bounds resolved to `retire`), × safety factor.
    Recurring bills accrue evenly: amount × per / 365 each day in [start, end). ONCE items, and
    `every`-N-years items (e.g. a car), land as a lump on their day."""
    n_years = cfg.end_age - cfg.start_age
    n_days = n_years * DAYS
    rate = [0.0] * (n_days + 1)  # difference array of the per-day accrual rate
    lumps = [0.0] * n_days

    def clamp(age: float) -> int:
        return min(n_days, max(0, day_index(age, cfg.start_age))) if math.isfinite(age) else (0 if age < 0 else n_days)

    for ex in cfg.expenses:
        if only is not None and not only(ex):
            continue
        s, e = ex.bounds(retire)
        amount = ex.amount * cfg.safety_factor
        if ex.per == ONCE:
            at = ex.once_at(retire)
            if at is not None and cfg.start_age <= at < cfg.end_age:  # outside the horizon: not charged
                lumps[min(n_days - 1, clamp(at))] += amount
        elif ex.every > 1:
            for y in range(n_years):
                if ex.annual(cfg.start_age + y, retire):
                    lumps[y * DAYS] += amount * ex.per
        else:
            lo, hi = clamp(s), clamp(e)
            if lo < hi:
                rate[lo] += amount * ex.per / DAYS
                rate[hi] -= amount * ex.per / DAYS
    return [r + l for r, l in zip(accumulate(rate), lumps)]


def expenses_by_category(cfg: Config, retire: float | None = None) -> dict[str, list[float]]:
    """Annual expense totals per category, indexed by years since START_AGE."""
    n_years = cfg.end_age - cfg.start_age
    cats: dict[str, list[float]] = {}
    for ex in cfg.expenses:
        for y in range(n_years):
            v = ex.annual(cfg.start_age + y, retire)
            if v:
                cats.setdefault(ex.category or "other", [0.0] * n_years)[y] += v * cfg.safety_factor
    return cats


# ───────────────────────────── capital gains curve ─────────────────────────────


def make_curve(tax_fn, breaks_fn, wages: float, add: float = 0.0) -> list[tuple[float, float]]:
    """A piecewise-linear tax_fn(amount, wages) as [(amount_from, marginal_rate + add), ...]."""
    pts = sorted(set(p for p in breaks_fn(wages) if p >= 0) | {0.0})
    curve = []
    for i, b in enumerate(pts):
        nxt = pts[i + 1] if i + 1 < len(pts) else b + 1_000_000
        curve.append((b, (tax_fn(nxt, wages) - tax_fn(b, wages)) / (nxt - b) + add))
    return curve


def cg_curve(reg: TaxRegime, wages: float) -> list[tuple[float, float]]:
    """capgains_tax(gain, wages), which is piecewise linear, as [(gain_from, marginal_rate), ...]."""
    return make_curve(reg.capgains_tax, reg.capgains_breaks, wages)


ZERO_CURVE = [(0.0, 0.0)]


def curve_tax(curve, g0: float, dg: float) -> float:
    """Tax on taxable amount dg stacked on g0 already realized this year."""
    tax = 0.0
    for i, (b, rate) in enumerate(curve):
        hi = curve[i + 1][0] if i + 1 < len(curve) else math.inf
        lo_, hi_ = max(b, g0), min(hi, g0 + dg)
        if hi_ > lo_:
            tax += (hi_ - lo_) * rate
    return tax


@dataclass
class Pot:
    """One account: market value and cost basis (a 401(k) keeps basis 0: every dollar out is taxable)."""

    value: float = 0.0
    basis: float = 0.0


def drain(pot: Pot, need: float, cum: float, curve) -> tuple[float, float, float, float]:
    """Sell from `pot` until the after-tax proceeds cover `need`, or it's empty.
    Tax follows `curve` on the gain share of the sale, stacked on `cum`. Returns (net, sale, tax, gained)."""
    if pot.value <= 0 or need <= 0:
        return 0.0, 0.0, 0.0, 0.0
    gain_frac = max(0.0, (pot.value - pot.basis) / pot.value)
    full_gain = pot.value * gain_frac
    full_tax = curve_tax(curve, cum, full_gain)
    if pot.value - full_tax <= need:
        sale, tax, gained = pot.value, full_tax, full_gain
    else:
        sale, tax, gained = sell_for(need, gain_frac, cum, curve)
    pot.basis = pot.basis * (1 - sale / pot.value) if sale < pot.value else 0.0
    pot.value -= sale
    return sale - tax, sale, tax, gained


def sell_for(need: float, gain_frac: float, cum_gain: float, curve) -> tuple[float, float, float]:
    """Find the sale S whose after-tax proceeds equal `need`. CG tax is paid at the marginal
    rate(s) on top of the `cum_gain` already realized this year. Returns (S, tax, realized gain)."""
    if gain_frac <= 0:
        return need, 0.0, 0.0
    sale = tax = gained = 0.0
    g0, i = cum_gain, 0
    while i + 1 < len(curve) and curve[i + 1][0] <= g0:
        i += 1
    while need > 1e-9:
        rate = curve[i][1]
        room = curve[i + 1][0] - g0 if i + 1 < len(curve) else math.inf
        s = need / (1 - rate * gain_frac)
        g = s * gain_frac
        if g <= room:
            return sale + s, tax + rate * g, gained + g
        # This sale crosses into the next bracket: fill the current one, then continue.
        s = room / gain_frac
        sale, tax, gained = sale + s, tax + rate * room, gained + room
        need -= s - rate * room
        g0 += room
        i += 1
    return sale, tax, gained


# ───────────────────────────── the simulation ─────────────────────────────


def take_home_rates(reg: TaxRegime, me: float, them: float, share: float) -> tuple[float, float]:
    """This year's take-home per dollar of your wages and of the partner's (× the share they put in the pot).
    Joint regime: one return for both earners. Otherwise each earner is taxed on their own wages."""
    if reg.joint:
        gross = me + them
        keep = reg.income_left(gross, tuple(w for w in (me, them) if w > 0)) / gross if gross > 0 else 0.0
        return keep, keep * share
    keep_me = reg.income_left(me, (me,)) / me if me > 0 else 0.0
    keep_them = reg.income_left(them, (them,)) / them if them > 0 else 0.0
    return keep_me, keep_them * share


def required_balance(gaps: list[float], growth: list[float]) -> list[float]:
    """What an account must hold at the start of each day to pay every later gap.

    Walk backward from the last day: what you need today = today's gap + what you'll need tomorrow,
    shrunk by one day of growth. It never goes below 0 (a surplus can't pay a bill that already passed).
    """
    need = [0.0] * (len(gaps) + 1)
    for day in range(len(gaps) - 1, -1, -1):
        need[day] = max(0.0, gaps[day] + need[day + 1] / growth[day])
    return need


@dataclass
class AccountPlan:
    """Per-day gaps (spending − take-home; negative = surplus) split by which account pays them, and the
    balance each account must hold (from required_balance). "all" = taxable including college."""

    taxable_gap: list[float]            # everything before the penalty age except college
    taxable_gap_all: list[float]        # the same, including college
    need_taxable: list[float]
    need_taxable_all: list[float]
    need_retirement: list[float]        # 401(k) + Roth: gaps after the penalty age, grossed up for income tax
    need_college: list[float]           # 529: college lines


def plan_accounts(cfg: Config, scenario: Scenario, w_me, w_them, spend, college, penalty_day: int) -> AccountPlan:
    """Give every future day's gap to the account allowed to pay it that day, then compute required balances.

    after the penalty age   → 401(k)/Roth (if they're on)
    college lines           → 529 (if it's on)
    everything else         → taxable (the wedding, the years before 59½, ...)
    Taxes are added once per year on the mid-year day: income tax on the year's 401(k) draws, and capital-gains
    tax on the year's taxable sales (as if every dollar sold were gain: conservative).
    """
    acc = cfg.accounts
    retirement_on, college_on = acc.k401_limit > 0 or acc.roth_limit > 0, acc.c529_limit > 0
    n = len(spend)
    taxable_gap, taxable_gap_all = [0.0] * n, [0.0] * n
    retirement_gap, college_gap = [0.0] * n, [0.0] * n
    taxable_tax, taxable_tax_all = [0.0] * n, [0.0] * n
    growth = [1.0] * n

    for y in range(n // DAYS):
        age, first, last = cfg.start_age + y, y * DAYS, (y + 1) * DAYS
        reg = find_in_range(cfg.taxes, age, "tax regime")
        me, them = sum(w_me[first:last]), sum(w_them[first:last])
        keep_me, keep_them = take_home_rates(reg, me, them, scenario.partner_share)
        daily_growth = (1 + find_in_range(cfg.growth, age, "growth schedule").rate) ** (1 / DAYS)
        retirement_this_year = 0.0
        for day in range(first, last):
            growth[day] = daily_growth
            gap = spend[day] - w_me[day] * keep_me - w_them[day] * keep_them
            if retirement_on and day >= penalty_day:
                retirement_this_year += gap
            else:
                college_gap[day] = college[day] if college_on else 0.0
                taxable_gap_all[day] = gap
                taxable_gap[day] = gap - college_gap[day]

        mid, wages = first + DAYS // 2, (me + them) if reg.joint else me
        if retirement_this_year > 0:  # the pre-tax 401(k) draw whose after-tax amount covers the year's gap
            ordinary = make_curve(reg.ordinary_tax, reg.ordinary_breaks, wages)
            retirement_gap[mid] = sell_for(retirement_this_year, 1.0, 0.0, ordinary)[0]
        cg = cg_curve(reg, wages)
        taxable_tax[mid] = curve_tax(cg, 0.0, max(0.0, sum(taxable_gap[first:last])))
        taxable_tax_all[mid] = curve_tax(cg, 0.0, max(0.0, sum(taxable_gap_all[first:last])))

    return AccountPlan(
        taxable_gap, taxable_gap_all,
        need_taxable=required_balance([g + t for g, t in zip(taxable_gap, taxable_tax)], growth),
        need_taxable_all=required_balance([g + t for g, t in zip(taxable_gap_all, taxable_tax_all)], growth),
        need_retirement=required_balance(retirement_gap, growth),
        need_college=required_balance(college_gap, growth),
    )


def max_contribution(balance: float, gaps, need_tomorrow, pay, career: float) -> float:
    """The most that can move out of `balance` this year while it still holds its required balance at the end
    of every day. Contributions leave with each paycheck (a share pay/career of the year's total), so on
    each day:  balance − gaps so far − contribution × (pay so far / career) ≥ need tomorrow."""
    most, gaps_so_far, pay_so_far = math.inf, 0.0, 0.0
    for gap, need, p in zip(gaps, need_tomorrow, pay):
        gaps_so_far += gap
        pay_so_far += p
        if pay_so_far > 0:
            most = min(most, (balance - gaps_so_far - need) * career / pay_so_far)
    return max(0.0, most)


def simulate(cfg: Config, scenario: Scenario, x: float, deposits: tuple[tuple[float, float], ...] = ()) -> Result:
    n_years = cfg.end_age - cfg.start_age
    n_days = n_years * DAYS
    acc = cfg.accounts
    mine, x_end = lay_out(scenario.income, cfg.start_age, x)
    partner, x_end_partner = lay_out(scenario.partner_income, cfg.start_age, x)
    res = Result(scenario.name, x, x_end_age=x_end if x_end is not None else x_end_partner)

    w_me, w_them = daily_wages(mine, cfg.start_age, n_days), daily_wages(partner, cfg.start_age, n_days)
    spend = daily_expenses(cfg, res.x_end_age)
    college = (daily_expenses(cfg, res.x_end_age, only=lambda e: "college" in e.name.lower())  # the 529 pays these
               if acc.active else [0.0] * n_days)
    lumps: dict[int, float] = {}
    for age, amount in deposits:
        i = min(n_days - 1, max(0, day_index(age, cfg.start_age)))
        lumps[i] = lumps.get(i, 0.0) + amount
    curves: dict[tuple, list] = {}  # tax curves per (kind, regime, wages, penalty); few distinct per run

    def curve(kind: str, reg: TaxRegime, wages: float, add: float) -> list:
        key = (kind, id(reg), wages, add)
        if key not in curves:
            curves[key] = (cg_curve(reg, wages) if kind == "cg"
                           else make_curve(reg.ordinary_tax, reg.ordinary_breaks, wages, add))
        return curves[key]

    stop_day = day_index(res.x_end_age, cfg.start_age) if res.x_end_age is not None else -1
    career_end = stop_day if stop_day >= 0 else n_days  # contributions only from career wages
    penalty_day = day_index(acc.penalty_age, cfg.start_age)
    flat_age = res.x_end_age if scenario.flat_from is RETIRE else scenario.flat_from
    flat_day = day_index(flat_age, cfg.start_age) if flat_age is not None else -1
    floor = 0.0  # becomes the total balance on flat_day for flat_from scenarios
    taxable, k401, roth, c529 = Pot(cfg.start_balance, cfg.start_basis), Pot(), Pot(cfg.start_roth, cfg.start_roth), Pot()
    plan = plan_accounts(cfg, scenario, w_me, w_them, spend, college, penalty_day) if acc.active else None
    for y in range(n_years):
        age = cfg.start_age + y
        lo, hi = y * DAYS, (y + 1) * DAYS
        me, them = sum(w_me[lo:hi]), sum(w_them[lo:hi])
        gross = me + them
        reg = find_in_range(cfg.taxes, age, "tax regime")
        earners = tuple(w for w in (me, them) if w > 0)
        # Income tax is withheld daily at this year's average rate, so the days add up to the exact annual tax.
        keep_me, keep_them = take_home_rates(reg, me, them, scenario.partner_share)

        # Contributions this year, from the household's pooled pay: your wages before X ends plus the partner's
        # pooled share. One household 401(k) and one Roth; each earner adds their own limit (capped at their pay).
        # 401(k), then Roth, up to what they still need for after the penalty age; then the 529 up to what college
        # still needs. What leaves taxable is capped so taxable alone still covers every non-college need (a 529
        # can't pay a wedding), and taxable plus the 529 still covers everything including college.
        k401_c = roth_c = c529_c = saving = 0.0
        pay = [(w_me[i] if i < career_end else 0.0) + w_them[i] * scenario.partner_share for i in range(lo, hi)]
        my_pay = sum(w_me[lo:min(hi, career_end)])
        their_pay = them * scenario.partner_share
        career = my_pay + their_pay
        if acc.active and career > 0:
            can_leave = max_contribution(taxable.value, plan.taxable_gap[lo:hi], plan.need_taxable[lo + 1:hi + 1],
                                         pay, career)
            in_529 = min(c529.value, plan.need_college[lo])
            can_leave_all = max_contribution(taxable.value + in_529, plan.taxable_gap_all[lo:hi],
                                             plan.need_taxable_all[lo + 1:hi + 1], pay, career)
            room = min(can_leave, can_leave_all)
            retirement_short = max(0.0, plan.need_retirement[lo] - k401.value - roth.value)
            k401_limit = min(acc.k401_limit, my_pay) + min(acc.k401_limit, their_pay)
            roth_limit = min(acc.roth_limit, my_pay) + min(acc.roth_limit, their_pay)
            k401_c = min(k401_limit, career, retirement_short, room)
            roth_c = min(roth_limit, career - k401_c, retirement_short - k401_c, room - k401_c)
            if age >= acc.c529_from_age:
                college_short = max(0.0, plan.need_college[lo] - c529.value)
                c529_c = max(0.0, min(acc.c529_limit, career - k401_c - roth_c, college_short,
                                      can_leave - k401_c - roth_c))
        # The 401(k) deferral is split between the earners by pay; its income-tax saving goes into the pool.
        mine_deferred = k401_c * my_pay / career if career > 0 else 0.0
        if k401_c > 0 and reg.joint:
            saving = reg.income_left(gross, earners, deferred=k401_c) - reg.income_left(gross, earners)
        elif k401_c > 0:
            for wages, d in ((me, mine_deferred), (them, k401_c - mine_deferred)):
                if d > 0:
                    saving += reg.income_left(wages, (wages,), deferred=d) - reg.income_left(wages, (wages,))
        tax_wages = gross - k401_c if reg.joint else me - mine_deferred  # ordinary income that withdrawals stack on
        per_career_dollar = [c / career if career > 0 else 0.0 for c in (k401_c, roth_c, c529_c, saving)]

        grow = (1 + find_in_range(cfg.growth, age, "growth schedule").rate) ** (1 / DAYS)
        cum_gain = cum_ord = 0.0
        y_net = y_spend = y_sold = y_cg = y_inv = y_ord = y_contrib = 0.0
        # Withdrawal order for a shortfall. Before the penalty age: taxable, then Roth (only its earnings pay
        # tax + 10%), then the 401(k) (+10%). After it: the 401(k) first (it was funded for exactly this),
        # then the tax-free Roth, then taxable. A 529 used for anything but college is last (earnings taxed + 10%).
        cg = curve("cg", reg, tax_wages, 0.0)
        penalized = curve("ord", reg, tax_wages, 0.10)
        order_early = [(taxable, cg), (roth, penalized), (k401, penalized), (c529, penalized)]
        order_late = [(k401, curve("ord", reg, tax_wages, 0.0)), (roth, ZERO_CURVE), (taxable, cg), (c529, penalized)]
        others = (k401, roth, c529) if acc.active else ((roth,) if cfg.start_roth else ())

        for i in range(lo, hi):
            if i == stop_day or i == flat_day:
                total = taxable.value + sum(p.value for p in others)
                if i == stop_day:
                    res.stop_balance = total
                if i == flat_day:
                    floor = total
            if i in lumps:
                taxable.value += lumps[i]
                taxable.basis += lumps[i]
                y_inv += lumps[i]
            d, r, a, tax_saved = (pay[i - lo] * f for f in per_career_dollar)
            net = w_me[i] * keep_me + w_them[i] * keep_them + tax_saved
            y_net += net
            if career > 0:
                k401.value += d
                roth.value += r
                roth.basis += r
                c529.value += a
                c529.basis += a
                net -= d + r + a
                y_contrib += d + r + a
            cost = spend[i]
            y_spend += cost
            if college[i] > 0 and c529.value > 0:  # qualified: tax-free
                got, sale, _, _ = drain(c529, college[i], 0.0, ZERO_CURVE)
                cost -= got
                y_sold += sale
            cash = net - cost
            if cash >= 0:
                taxable.value += cash
                taxable.basis += cash
                y_inv += cash
            else:
                need = -cash
                for pot, crv in (order_early if i < penalty_day else order_late):
                    if pot.value <= 0:
                        continue
                    if crv is cg:
                        got, sale, tax, gained = drain(pot, need, cum_gain, cg)
                        cum_gain += gained
                        y_cg += tax
                    else:
                        got, sale, tax, gained = drain(pot, need, cum_ord, crv)
                        if crv is not ZERO_CURVE:
                            cum_ord += gained
                        y_ord += tax
                    need -= got
                    y_sold += sale
                    if need <= 1e-9:
                        break
                if need > 1e-9:
                    taxable.value -= need  # everything is empty: keep a running total of the unpaid shortfall
            if taxable.value > 0:
                taxable.value *= grow
            total = taxable.value
            for pot in others:
                if pot.value > 0:
                    pot.value *= grow
                total += pot.value
            if res.fail_age is None and total < floor:
                res.fail_age = age + (i - lo) / DAYS

        total = taxable.value + k401.value + roth.value + c529.value
        res.rows.append(Row(age, cfg.start_year + y, gross, y_net, y_spend, y_sold, y_cg, y_inv, total, taxable.basis,
                            k401.value, roth.value, c529.value, y_ord, y_contrib))
    return res
