"""Regenerate the README screenshots (docs/*.svg) from a shipped example plan.

  uv run docs/screenshots.py

Runs `fire.py --plan sf_family` with colors on, cuts the output into sections, and saves each one as an SVG
terminal screenshot with rich. Only default_plans/ is used, so no private numbers end up in the images."""

import os
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.text import Text

HERE = Path(__file__).resolve().parent
WIDTH = 140
# file name -> (first line containing, line to stop before containing); None = to the end
SECTIONS = {
    "summary": ("FIRE solutions for plan", "Income plan: Coast"),
    "whatif": ("What-if: extra savings", "What-if: extra savings"),
    "networth": ("Net worth by age", "Expenses per year"),
    "expenses": ("Expenses per year", "Cash flow:"),
    "cashflow": ("Cash flow:", "Accounts:"),
    "accounts": ("Accounts:", None),
}


def main():
    env = {**os.environ, "FORCE_COLOR": "1", "COLUMNS": str(WIDTH), "PYTHONPATH": ""}
    out = subprocess.run([sys.executable, str(HERE.parent / "fire.py"), "--plan", "sf_family"],
                         capture_output=True, text=True, env=env, check=True, cwd=HERE.parent).stdout
    lines = out.splitlines()
    plain = [Text.from_ansi(line).plain for line in lines]
    for name, (start, stop) in SECTIONS.items():
        a = next(i for i, p in enumerate(plain) if start in p)
        b = next((i for i, p in enumerate(plain) if i > a and stop and stop in p), len(lines))
        while b > a and not plain[b - 1].strip():
            b -= 1
        console = Console(record=True, width=WIDTH, force_terminal=True, file=open(os.devnull, "w"))
        for line in lines[a:b]:
            console.print(Text.from_ansi(line), soft_wrap=True)
        console.save_svg(str(HERE / f"{name}.svg"), title=f"uv run fire.py --plan sf_family  ({name})")
        print(f"docs/{name}.svg: lines {a + 1}-{b}")


if __name__ == "__main__":
    main()
