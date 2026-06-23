# budget-analysis

Personal tooling for analyzing data from the [Buckets](https://www.budgetwithbuckets.com/) budgeting app.

> **Note:** the Buckets database (`*.buckets`), rendered charts, and CSV exports contain real financial data and are git-ignored. See `.gitignore`.

## Scripts

- **`budget_pie.py`** — An interactive pie-chart explorer for a Buckets `*.buckets` SQLite database, with a tree of bucket groups and tabs for allocations, actual income, and spending.
- **`venmoToBuckets.py`** — Merges one or more Venmo CSV exports into a deduplicated `buckets.csv` for import.
- **`usageDirectAppToBucketsFile.sql`** — SQL that converts UsageDirect app-usage time into per-application cost rows for analysis.
