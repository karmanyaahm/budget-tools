"""Example income ladders for grids. Each is a list of Income segments laid back to back from the plan's
start age; exactly one segment has X (usually years=X at the last salary). Illustrative numbers."""

from firemodel.schema import X, Income

LADDERS = {
    "steady 110 → 150×X": [Income(110_000, years=4), Income(150_000, years=X)],
    "big tech 120 → 175 → 230×X": [Income(120_000, years=3), Income(175_000, years=2), Income(230_000, years=X)],
    "fast track 200×3 → 320×X": [Income(200_000, years=3), Income(320_000, years=X)],
    # X can also be a salary: work exactly 12 years, and solve for the salary needed
    "solve salary: 12 yrs at X": [Income(X, years=12)],
}
