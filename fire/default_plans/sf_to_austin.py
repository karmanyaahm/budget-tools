"""Example: earn in SF, then move to Austin at 35 (e.g. when coasting). Expenses and taxes switch cities at 35.
Uses LifePlan.move_to; set the age to your planned move."""

from default_plans.austin_family import PLAN as AUSTIN
from default_plans.sf_family import PLAN as SF

PLAN = SF.move_to(AUSTIN, 35)
