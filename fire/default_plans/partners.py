"""Example partner incomes for grids: None (solo), a flat salary (worked 25-55), or a ladder of Income
segments. With a partner, 50% of their take-home joins the common pool (see LifePlan.with_partner)."""

from firemodel.schema import Income

PARTNERS = {
    "solo": None,
    "+ $70k flat": 70_000,
    "+ 55k → 90k at 32": [Income(55_000, start=25, until=32, label="partner"),
                          Income(90_000, until=55, label="partner")],
}
