"""Example grid: different expense profiles on the same ladder.
Run with: uv run grid.py grid_profiles"""

from default_plans.couple_with_car import PLAN as COUPLE_CAR
from default_plans.ladders import LADDERS
from default_plans.sf_family import PLAN as SF
from default_plans.single_lean import PLAN as LEAN
from default_plans.three_kids import PLAN as THREE

GRID = {
    "plans": {"single, lean": LEAN, "SF, one kid": SF, "SF, three kids": THREE, "couple with car": COUPLE_CAR},
    "ladders": {k: LADDERS[k] for k in ("big tech 120 → 175 → 230×X",)},
}
