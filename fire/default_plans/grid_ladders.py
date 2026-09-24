"""Example grid: one plan across every example ladder (incl. solving for a salary).
Run with: uv run grid.py grid_ladders"""

from default_plans.ladders import LADDERS
from default_plans.sf_family import PLAN as SF_FAMILY

GRID = {"plans": {"SF family": SF_FAMILY}, "ladders": LADDERS}
