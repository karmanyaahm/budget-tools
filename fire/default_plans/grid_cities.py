"""Example grid: SF vs Austin × two career ladders × solo/partner × taxable vs 401(k)+Roth+529.
Run with: uv run grid.py grid_cities"""

from config import NO_ACCOUNTS, TAX_ADVANTAGED
from default_plans.austin_family import PLAN as AUSTIN
from default_plans.ladders import LADDERS
from default_plans.partners import PARTNERS
from default_plans.sf_family import PLAN as SF

GRID = {
    "plans": {"SF": SF, "Austin": AUSTIN},
    "ladders": {k: LADDERS[k] for k in ("big tech 120 → 175 → 230×X", "fast track 200×3 → 320×X")},
    "partners": {k: PARTNERS[k] for k in ("solo", "+ 55k → 90k at 32")},
    "accounts": {"taxable": NO_ACCOUNTS, "401k+Roth+529": TAX_ADVANTAGED},
}
