"""Example grid: one plan under every tax setup in config.TAX_VARIANTS (state × filing status).
Run with: uv run grid.py grid_taxes"""

from config import TAX_VARIANTS
from default_plans.sf_family import PLAN as SF_FAMILY

GRID = {
    "plans": {"SF family": SF_FAMILY},
    "taxes": {name: name for name in TAX_VARIANTS},
}
