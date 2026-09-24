"""Tax math: bracket tables, FICA, and regime()'s income_left / capgains_tax / capgains_breaks."""

import pytest

from conftest import NO_FICA, fed
from firemodel.sim import cg_curve
from firemodel.tax import Fica, NO_STATE_TAX, State, bracket_tax, flat_state, regime, stacked_tax

B = [(0, 0.10), (10_000, 0.20), (30_000, 0.30)]


# ───────────────────────────── bracket_tax / stacked_tax ─────────────────────────────

@pytest.mark.parametrize("taxable, expected", [
    (0, 0.0),
    (-5_000, 0.0),                                   # negative taxable → nothing
    (5_000, 500.0),                                  # 10% × 5k
    (10_000, 1_000.0),                               # exactly at threshold: only the lower bracket
    (20_000, 1_000 + 2_000.0),                       # 10% × 10k + 20% × 10k
    (30_000, 1_000 + 4_000.0),                       # 10% × 10k + 20% × 20k
    (40_000, 1_000 + 4_000 + 3_000.0),               # + 30% × 10k
])
def test_bracket_tax(taxable, expected):
    assert bracket_tax(taxable, B) == pytest.approx(expected)


def test_bracket_tax_single_flat_bracket():
    # One bracket from 0 at 7% → 7% of everything.
    assert bracket_tax(123_456, [(0, 0.07)]) == pytest.approx(0.07 * 123_456)


def test_stacked_tax_is_the_marginal_slice():
    # $15k on top of $5k: 5k@10% + 10k@20% = 500 + 2000.
    assert stacked_tax(5_000, 15_000, B) == pytest.approx(2_500)
    # The same $15k on top of $30k sits entirely in 30%: 4500.
    assert stacked_tax(30_000, 15_000, B) == pytest.approx(4_500)


def test_stacked_tax_nonpositive_extra_is_zero():
    assert stacked_tax(50_000, 0, B) == 0.0
    assert stacked_tax(50_000, -1_000, B) == 0.0


# ───────────────────────────── FICA ─────────────────────────────

FICA = Fica(ss_rate=0.06, ss_wage_base=100_000, medicare_rate=0.01, addl_medicare_rate=0.01,
            addl_medicare_threshold=150_000)


def test_fica_below_everything():
    # 50k: SS 6% × 50k = 3000, Medicare 1% × 50k = 500.
    assert FICA.tax(50_000, (50_000,)) == pytest.approx(3_500)


def test_fica_one_earner_above_wage_base_and_threshold():
    # 200k single earner: SS capped at 100k → 6000; Medicare 2000; addl 1% × (200k − 150k) = 500.
    assert FICA.tax(200_000, (200_000,)) == pytest.approx(8_500)


def test_fica_ss_wage_base_is_per_earner():
    # Two 100k earners: each hits the 100k base exactly → SS 6% × 200k = 12000 (vs 6000 for one 200k earner).
    # Medicare on household 200k = 2000; addl on household over 150k = 500.
    assert FICA.tax(200_000, (100_000, 100_000)) == pytest.approx(14_500)
    assert FICA.tax(200_000, (100_000, 100_000)) - FICA.tax(200_000, (200_000,)) == pytest.approx(6_000)


# ───────────────────────────── regime(): income_left ─────────────────────────────

FED = fed(std=10_000, brackets=[(0, 0.10), (10_000, 0.20)], ltcg=[(0, 0.0), (20_000, 0.15)],
          niit_rate=0.038, niit_threshold=50_000)
ST5 = flat_state(0.05)


def test_income_left_closed_form():
    # 50k gross: fed taxable 40k → 10k@10% + 30k@20% = 7000; state 5% × 50k = 2500;
    # FICA 6% × 50k + 1% × 50k = 3500. Left = 50000 − 13000 = 37000.
    reg = regime(0, 100, FED, FICA, ST5)
    assert reg.income_left(50_000) == pytest.approx(37_000)
    assert reg.income_left(50_000, (50_000,)) == pytest.approx(37_000)


def test_income_left_zero_rates_is_identity():
    reg = regime(0, 100, fed(), NO_FICA, NO_STATE_TAX)
    for g in (0, 1, 12_345.67, 1e6):
        assert reg.income_left(g) == pytest.approx(g)


def test_income_left_below_std_deduction_has_no_income_tax():
    # 8k < 10k std deduction: fed 0; state 5% × 8k = 400; FICA 7% × 8k = 560.
    reg = regime(0, 100, FED, FICA, ST5)
    assert reg.income_left(8_000) == pytest.approx(8_000 - 400 - 560)


def test_income_left_state_std_deduction_and_payroll_rate():
    # State: 10% over a 20k std deduction, plus 1% payroll on all wages. Fed/FICA off.
    # 50k: state 10% × 30k = 3000; payroll 500 → 46500.
    st = State(std_deduction=20_000, brackets=[(0, 0.10)], payroll_rate=0.01)
    reg = regime(0, 100, fed(), NO_FICA, st)
    assert reg.income_left(50_000) == pytest.approx(46_500)


def test_income_left_earners_applies_per_earner_wage_base():
    # Only FICA SS (6%, base 100k). Two 100k earners pay 12000; one 200k earner pays 6000.
    f = Fica(0.06, 100_000, 0.0, 0.0, 0.0)
    reg = regime(0, 100, fed(), f, NO_STATE_TAX, joint=True)
    assert reg.joint is True
    assert reg.income_left(200_000, (100_000, 100_000)) == pytest.approx(188_000)
    assert reg.income_left(200_000, (200_000,)) == pytest.approx(194_000)
    assert reg.income_left(200_000) == pytest.approx(194_000)  # default earners = (gross,)


def test_regime_carries_bounds_and_joint_flag():
    reg = regime(21, 26, fed(), NO_FICA, NO_STATE_TAX)
    assert (reg.start, reg.end, reg.joint) == (21, 26, False)


# ───────────────────────────── regime(): capgains_tax ─────────────────────────────

def test_capgains_flat_rate():
    # ltcg 20% from 0, nothing else: tax = 0.2 × gain regardless of wages.
    reg = regime(0, 100, fed(ltcg=[(0, 0.2)]), NO_FICA, NO_STATE_TAX)
    for wages in (0, 50_000, 1e6):
        assert reg.capgains_tax(10_000, wages) == pytest.approx(2_000)
    assert reg.capgains_tax(0, 0) == 0.0
    assert reg.capgains_tax(-5_000, 0) == 0.0


def test_capgains_sheltered_by_unused_std_deduction():
    # Fed only: std 10k, ltcg 0% to 20k then 15%. Wages 4k leave 6k of deduction unused.
    # Gain 6k: fully sheltered → 0. Gain 30k: 6k sheltered, 24k taxable on top of 0 ordinary:
    # 20k@0% + 4k@15% = 600.
    reg = regime(0, 100, fed(std=10_000, ltcg=[(0, 0.0), (20_000, 0.15)]), NO_FICA, NO_STATE_TAX)
    assert reg.capgains_tax(6_000, 4_000) == pytest.approx(0)
    assert reg.capgains_tax(30_000, 4_000) == pytest.approx(600)


def test_capgains_stack_on_ordinary_income():
    # Wages 25k, std 10k → ordinary taxable 15k. The 0% band runs to 20k, so 5k of gain is at 0%,
    # the rest at 15%. Gain 10k → 5k × 15% = 750.
    reg = regime(0, 100, fed(std=10_000, ltcg=[(0, 0.0), (20_000, 0.15)]), NO_FICA, NO_STATE_TAX)
    assert reg.capgains_tax(10_000, 25_000) == pytest.approx(750)


def test_capgains_niit_threshold():
    # NIIT only (3.8% over MAGI 50k). Wages 40k + gain 20k = MAGI 60k → NIIT on min(20k, 10k) = 10k → 380.
    reg = regime(0, 100, fed(niit_rate=0.038, niit_threshold=50_000), NO_FICA, NO_STATE_TAX)
    assert reg.capgains_tax(20_000, 40_000) == pytest.approx(380)
    # Wages already over the threshold: NIIT on the whole gain.
    assert reg.capgains_tax(20_000, 70_000) == pytest.approx(760)
    # MAGI below the threshold: none.
    assert reg.capgains_tax(5_000, 40_000) == pytest.approx(0)


def test_capgains_state_taxes_gains_as_ordinary():
    # State 5% flat, no deduction; fed off. Gain 30k with 5k wages → 1500.
    reg = regime(0, 100, fed(), NO_FICA, ST5)
    assert reg.capgains_tax(30_000, 5_000) == pytest.approx(1_500)


def test_capgains_state_override_brackets():
    # State ordinary 10% but capgains_brackets 2%: gains use 2%.
    st = State(0, [(0, 0.10)], capgains_brackets=[(0, 0.02)])
    reg = regime(0, 100, fed(), NO_FICA, st)
    assert reg.capgains_tax(10_000, 0) == pytest.approx(200)


def test_capgains_everything_together():
    # FED (std 10k, ltcg 0%→20k, 15% above; NIIT 3.8% over 50k) + 5% flat state. Wages 5k, gain 30k.
    # Fed: 5k sheltered, 25k taxable on 0 ordinary → 20k@0 + 5k@15% = 750. NIIT: MAGI 35k < 50k → 0.
    # State: 5% × 30k = 1500. Total 2250.
    reg = regime(0, 100, FED, FICA, ST5)
    assert reg.capgains_tax(30_000, 5_000) == pytest.approx(2_250)


# ───────────────────────────── regime(): capgains_breaks ─────────────────────────────

def test_capgains_breaks_hand_derived():
    # FED + no state. Wages 5k: shelter = 5k; ltcg kink at 5k + 20k − 0 = 25k; NIIT at 50k − 5k = 45k.
    # The zero-rate state adds its own 0 shelter break (0).
    reg = regime(0, 100, FED, NO_FICA, NO_STATE_TAX)
    assert reg.capgains_breaks(5_000) == pytest.approx([0, 5_000, 25_000, 45_000])
    # Wages 25k: ordinary 15k, no shelter; ltcg kink at 20k − 15k = 5k; NIIT at 25k.
    assert reg.capgains_breaks(25_000) == pytest.approx([0, 5_000, 25_000])


def _slope(f, a, b):
    return (f(b) - f(a)) / (b - a)


@pytest.mark.parametrize("wages", [0, 5_000, 12_000, 25_000, 49_000, 80_000])
def test_capgains_breaks_are_exactly_the_kinks(wages):
    # Between consecutive breaks, capgains_tax is linear (midpoint check); across each nonzero break,
    # the slope changes (or at least the break is a legitimate candidate).
    st = State(3_000, [(0, 0.01), (15_000, 0.04)])
    reg = regime(0, 100, FED, NO_FICA, st)
    f = lambda g: reg.capgains_tax(g, wages)  # noqa: E731
    pts = reg.capgains_breaks(wages) + [reg.capgains_breaks(wages)[-1] + 100_000]
    for a, b in zip(pts, pts[1:]):
        if b - a < 1e-6:
            continue
        m = (a + b) / 2
        assert f(m) == pytest.approx((f(a) + f(b)) / 2, abs=1e-6), (a, b)
    # Every kink of the true function is in the break list: check a dense grid of slopes.
    breaks = set(round(p, 6) for p in reg.capgains_breaks(wages))
    step = 250.0
    g = step
    while g < pts[-1]:
        left, right = _slope(f, g - step, g), _slope(f, g, g + step)
        if abs(left - right) > 1e-9:
            # a kink lies in (g − step, g + step): some break must be there
            assert any(g - step - 1e-6 <= b <= g + step + 1e-6 for b in breaks), (wages, g)
        g += step


@pytest.mark.parametrize("wages", [0, 5_000, 25_000, 80_000])
def test_cg_curve_integrates_to_capgains_tax(wages):
    # Integrating the (breakpoint, marginal rate) curve reproduces capgains_tax on a dense grid.
    st = State(3_000, [(0, 0.01), (15_000, 0.04)])
    reg = regime(0, 100, FED, NO_FICA, st)
    curve = cg_curve(reg, wages)

    def integrate(gain):
        tax = 0.0
        for i, (lo, rate) in enumerate(curve):
            hi = curve[i + 1][0] if i + 1 < len(curve) else float("inf")
            if gain <= lo:
                break
            tax += (min(gain, hi) - lo) * rate
        return tax

    for gain in range(0, 150_001, 1_250):
        assert integrate(gain) == pytest.approx(reg.capgains_tax(gain, wages), abs=1e-6)


def test_cg_curve_marginal_rates_hand_derived():
    # Fed ltcg 0% to 20k, 15% above; std 10k; wages 0 → shelter 10k, kink at 30k. No state.
    # NIIT rate is 0 but its (harmless) break still sits at the 1e12 threshold.
    reg = regime(0, 100, fed(std=10_000, ltcg=[(0, 0.0), (20_000, 0.15)]), NO_FICA, NO_STATE_TAX)
    curve = cg_curve(reg, 0)
    assert [b for b, _ in curve] == pytest.approx([0, 10_000, 30_000, 1e12])
    assert [r for _, r in curve] == pytest.approx([0, 0, 0.15, 0.15])
