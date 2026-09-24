# FIRE model: design document

> Public, anonymized design log. The owner's private plan numbers and results live in custom_plans/DESIGN_private.md (gitignored).

A year-by-year Financial Independence / Retire Early simulator. It finds how
many years you need to work at the terminal salary before you can
(a) retire to $0 income, or (b) drop to a "coast FIRE" salary, without the
portfolio going below zero before age 110.

Run it with `uv run fire.py` (see `uv run fire.py --help`).

---

## 1. Requests (everything the user asked for)

Requests came in conversationally, often several messages at a time while work was in progress. Personal
details (the owner's salaries, budget, life events and ages) are generalized here; the unredacted list is in
the private log.

Request #1 (2026-09-23), itemized:

1. Build a FIRE model in **Python**, managed with **uv**.
2. Inputs are files with:
   - **Tax schedules**: per year range, a state, and a function that returns the amount left after tax.
   - **Interest schedules**: per year, a function that takes the balance and returns the updated amount.
   - **Expenses**: a list of entries giving the amount, the time period
     (day/week/month/year constants, like /7 or /30), which years it applies to, etc.
3. Keep a **design document** listing every request the user made, and in a
   **separate, clearly marked section, every decision** Claude made while planning.
4. Fill it with a **regular FIRE schedule** that runs to **age 110**, where the money never runs out.
5. Have a **start-age variable**.
6. Put **the variables and the schedules in one file**, separate from the logic, so they're easy to change.
7. **Two kids** at a given age, including **college**.
8. A **wedding lump sum** at a given age.
9. **Ignore tax-advantaged accounts** for now. Every sale pays **capital gains tax**,
   which is **configurable**, and the rate should be **smart: based on that year's income**.
10. Support a **second income schedule for a partner**, **empty by default**.
11. The quantity being solved for is **how long to work at the terminal salary** (the
    last income in the list) before you can **retire to $0** or **retire to a coast-FIRE salary**.
    In effect, sweep one X-year period in the income schedule. Example shape: salary A for two years,
    salary B for two years, salary C for X years, then a lower coast salary until 60.
12. Optionally support an **X in the income amount** when the years are fixed. Drop
    ("table") this if it makes the design much more complex.
13. Use **few dependencies**, but make a **nice CLI/TUI graph**, probably with a library.
14. **Document the coding process** thoroughly in the design doc.

Request #2 (2026-09-23, several follow-up messages sent while the work was in progress):

15. **Calculate on a daily basis** "instead of weeks". The model was yearly; Claude read this as
    "use a daily time step and solve X to the day" (D31).
16. **What-if estimates:** "if I saved $X at age Y, I can coast N weeks earlier" (D40).
17. **Use California for the worst case** (D38).
18. **Build an expenses-per-year chart** (D42).
19. **"Why not pay taxes per day too"**: pay capital gains tax on each day's sale, not at year end (D34).
20. **Make every decision conservative.** The user also asked what the plan's current early-career expenses are,
    compared with their target budget (answered privately).
21. **Assume filing single to be conservative**, and **report how much difference it makes** (D39).
22. **The coast salary should equal your daily expenses, excluding increases from the kids, the wedding,
    savings, and other special things. Then X is the number of years needed at the high salary** (D41).
23. **"Do you think this would be better as a web app than a CLI?"** (answered in §7).
24. **"Keep it CLI, not a web app."** Settled: it stays a CLI (§7).
25. **Stop showing the sweep output by default** ("why are you showing me all the stupid things from sweep") (D44).
26. **Include a safety factor. Don't end at $1k, "that's scary"** (D45–D47).
27. **Show the coast earning amount**: it wasn't printed anywhere (D49). **Keep the 1.2 safety factor** (confirms D45).
28. **The default car price is absurd. What does a used Sienna cost?** (D48).
29. **The answer seemed like a lot of years**: explain why, and which levers matter (sensitivity analysis, no code change).
30. **Read two earlier budgeting chats** (shared links, not reproduced here). Read with Claude in Chrome after plain fetches failed.
31. From those chats: **model only the user's own share of spending** (a partner covers theirs). **File jointly.**
    **Keep the wedding as planned.** **Keep the current coast-salary implementation.** **Don't save this to memory.**
    **Make the life plan swappable**: a class or file that is assigned in the default config.py (D50).
32. **Stay solvent to 112 instead of 110.** That should replace the reserve logic (D52).
33. **Break down the individual base spending so it can be edited in the plan** (D53).
34. **Check the plan for realism** (D54).
35. **"Why cut life insurance at 18? Keep it going until they're 25"** (D54).
36. **`/simplify`:** review the code, including model features that could trade accuracy for less bug surface and
    easier understanding. **Be conservative and ask before any change.** Approved: M1 (bills accrue evenly per day), M2
    (growth as a rate), all zero-effect cleanups, exact dollars in the income table. **Declined:** dropping salary-X (D56–D61).
37. **Set the real starting age and starting balance** (D58).
39. **Explain the difference between retire-to-$0 and coast** (answered with the private results, no code change).
40. **A scenario with identical spending but a higher, earlier income path for X years** (D63).
41. **"Never shrinks" only needs to hold in the endgame, e.g. 100–112, where it should stay flat** (D64).
42. **Try two higher salaries for that alternate career** (D63).
43. **"Go back to the original cycle"** and try a lower terminal salary for X instead. The higher alternate paths were
    removed and a lower-X alternate path was added (answered privately).
44. **Run that lower-salary path under Texas taxes** (`--compare-taxes`, no code change). Spending was **not**
    adjusted for Texas prices yet.
45. **"Do that too in that scenario"**: Texas prices as well (D65).
46. **Compare several city × salary combinations** (ad hoc script, no code change; results private).
47. **Verify every expense number with subagents.** Four web-research agents covered housing, health/insurance, kids, and daily life.
    The user then decided which suggestions to take: keep the budgeted rent, don't rely on ACA subsidies (the model never did),
    keep the car-rental line, keep the wedding amount. Suggested fixes were measured on copies of the plans (scratch script
    `verified.py`) before touching the plan files. Findings that generalize:
    - With the verified numbers, the plan failed **on the wedding day** by a small margin (the padded wedding exceeded savings).
    - An extra bedroom while kids live at home was the biggest single lever (several years in SF, less in Austin).
    - In Austin, car-free with kids plus a rideshare budget came out slightly cheaper than owning a used car.
48. **"We can move the wedding a year if it doesn't hit. Keep the 1.2 flat on everything; don't make edge cases."** (D66)
49. **Keep the extra bedroom unsplit** (charged in full to you). **A joint-income household simulation will come later**, so no ad-hoc splits for now (tabled, §3).
50. **Do the joint simulation with a couple of partner salaries. Assume they keep some for personal savings: maybe 50% of their
    post-tax pay goes to joint expenses and savings** (D67).
51. **Spawn a subagent to write lots of unit tests with simplified scenarios that can be checked by hand** (D68).
52. **"Just assume the partner works a fixed span. It's just 50% of their post-tax income contributed to the common pool."** (D67, revised)
53. **Clarified that a salary label means the whole ladder**, not a flat salary from the start age (answered, no change).
54. **A new ladder with a higher terminal salary. Sweep Austin and SF. Also: is there a framework for running sweeps over
    arbitrary combinations of expenses, taxes and incomes?** There wasn't (all earlier sweeps were throwaway scratch scripts), so D69 adds one.
56. **Implement tax-advantaged accounts as an option in the sweep.** Don't max them out: big expenses like the wedding
    or a car need liquid money (or have a way to correct if a withdrawal exceeds what's available). **Is a 529 tax-advantaged?** (yes)
    **Ask Fable, to avoid overcomplicating it** (D70).
57. **Spawn a README agent.** The README should say this is a vibe-coded FIRE tool, and **describe it** (D71).
58. **Don't prematurely optimize** (the user rejected a hot-loop optimization; the ~3× slowdown was left in).
59. **How is the contribution amount decided? Don't overcontribute.** Contribute only what's certain to be needed after 59½,
    frontloaded, and keep as much taxable as possible. Check whether 401(k)+Roth alone survive the 59+ path **to $0 at 112**,
    and stop contributing once it's settled (D72).
60. **Reorganize:** a gitignored `custom_plans/` autoloaded by the tools, and `default_plans/` shipped with plenty of anonymized
    examples (grids, taxes, income ladders, expense profiles). Re-run the README agent with Austin-vs-SF tax charts and default
    expenses, without private info (D73; README agent re-run).
61. **Is there no generalizable tax setup calculator? Ask Fable.** Work backward for both the wedding and the bridge in one
    general method (in progress: a Fable design for "liability matching" replacing the reserve and target rules).
62. **Don't prematurely optimize** (repeat of request 58; again, no hot-loop optimization).
55. **"The partner is a ladder, right?"** It wasn't (a flat salary). Partner income now accepts a ladder: `PARTNER_LADDER` =
    a lower salary for the first few years, then a higher one until the end of their working span (the switch age is Claude's
    assumption). `make_joint` accepts a flat salary or a ladder. grid.py and config_joint.py use the ladder.
38. **The default analysis should include what's needed for a portfolio that never diminishes and stays flat at its real
    value**, and **how big that portfolio must be** (D62).

63. **Implement the general backward calculator. Show me the code. Split DESIGN.md in a subagent** (D74; split into DESIGN.md (public) and custom_plans/DESIGN_private.md).
64. **"This code is not understandable"**: rewritten for readability with identical results (D75). **"Are we still
    calculating forwards?"** Yes: the backward pass only plans contributions; the forward daily simulation still does everything.
65. **"What salary ladders let me coast at 30?"** (solved with salary-X ladders ending at 30, `grid_coast30`).
66. **"This assumes I earn in SF and retire in SF"**: support moving cities at an age (D76).
67. **Write more integration tests in a subagent, which I then verify; give it only the README and the API, not the history** (in progress).
68. **"The starting money is in a Roth."** `LifePlan.start_roth` / `Config.start_roth` (all contributions, so withdrawable any time
    tax-free; it grows even with accounts off). **"My original chat estimates were much chiller."** **"What if I drop the wedding?"** (D77)
69. **"How much can I trade for 15 years of $10k above the coast income?"** The coast job likely has some margin (D78).
70. **Set the padding to 1.1 everywhere; assume the coast job is core expenses + $10k** (D79).
71. **Partner household model** (D80). Pooling all of the partner's pay and costs was tried and rejected: first a flat
    personal-spending line, then a copy of every expense line ("clearly housing is shared, groceries are prob 1.5x not 2x").
    Doubling expenses with no partner income was considered next. Final: "drop the partner but i want to keep joint for tax purposes".
72. **End the personal plan's coast job earlier** (a plan setting, `coast_until`; no code change).
73. **"Think of a good way to handle partner… i want this to be a joint income calculator"** (D81). Follow-ups: drop the
    partner's separate fun money (the per-person lines already cover it); "build it with these factors"; "does insurance
    really double"; "merge the roth/401k space?"; "am i ever hitting the limit?"; a partner raise.
74. **"Merge the partner 401(k)s and the partner Roths"** into the household's (D82). **"Add total Roth and total 401(k)
    pools to the graph; and model in the default model what happens if I don't have any tax-advantaged accounts"** (D83).
75. **Raise the personal plan's early-career salary** (plan setting only).
76. **Couple rent factors in the personal plan** (a whole 1BR together instead of half a 2BR; per-city line names).
77. **README: mention using Claude Code as the interface, and moving across cities.** Added a "Using it with
    Claude Code" section (generic example prompt, no personal numbers), a moving-cities feature bullet, a
    `sf_to_austin` quickstart line, and a `move_to` bullet under "How to customize". The example already existed.
78. **"Put example output screenshots in the readme"**: `docs/screenshots.py` runs `fire.py --plan sf_family` with
    colors forced, cuts the output into sections (summary + income plan, what-if, net worth, expenses, cash flow,
    accounts) and saves each as an SVG terminal screenshot with rich (140 columns). SVG renders on GitHub and stays
    sharp; only the shipped example plan is used, so nothing private is in the images.
---

## 2. ⚙️ DECISIONS MADE BY CLAUDE (planning and implementation)

> Everything in this section was decided by Claude, not specified by the user.
> Change any of it if it's wrong.

### Modeling

- **D1. Real (inflation-adjusted) dollars throughout.** All amounts are in today's dollars,
  and returns are *real* returns (default 5%/yr, roughly 7% nominal minus 2–2.5% inflation).
  Tax brackets are therefore held at today's values, which matches how the IRS
  inflation-indexes them. Without this choice, a 90-year horizon would quietly assume zero inflation.
- **D2. Everything is keyed by age, not calendar year.** Income, expenses, tax schedules, and
  interest schedules all use ages. The request said "year range" for taxes and "year" for
  interest, so `config.py` has `START_YEAR` and a helper `age_of(year)`. If you'd rather
  write a calendar year (for example a tax law that ends in 2034), write `age_of(2034)`.
  The output table shows both age and calendar year.
- **D3. Ranges are half-open `[start, end)`.** "Salary A for 21–23" means ages 21 and 22 (2 years).
  College from 18 to 22 means ages 18, 19, 20, 21.
- **D4. Horizon.** The simulation covers ages `START_AGE` through `END_AGE - 1` (default 110).
  The balance at the start of age 110 is the "ending balance."
- **D5. Success criterion.** The portfolio can pay every year's shortfall
  (including the tax on the sales) in *every* year through 110. It isn't enough to end ≥ 0.
- **D6. ~~Order of cash flows within one year~~** *(superseded by D31–D35: the model is now daily)*.
  Original:
  gross income → income tax (the "amount left" function) → subtract that year's expenses →
  a surplus is invested (value and basis both go up), a shortfall is covered by selling
  (grossed up for capital gains tax) → the interest function is applied to the balance.
  Money invested at the start of the year gets a full year of growth. That's slightly
  optimistic during accumulation and slightly conservative during drawdown.
- **D7. A single taxable brokerage account with cost-basis tracking** (average-cost method).
  Contributions raise both value and basis. Selling `S` realizes
  `gain = S × (value − basis)/value`, and basis drops in proportion. Growth raises value only.
  (Request 9: no 401k/IRA/Roth/HSA.)
- **D8. Capital gains tax depends on that year's income.** Long-term gains stack on top of
  ordinary taxable income (wages minus the standard deduction). Any unused standard deduction
  shelters gains first. Then 0/15/20% brackets by filing status, plus the 3.8% NIIT above the
  MAGI threshold, plus a state capital gains rate. All of these numbers live in `config.py`.
  Every gain is treated as long-term, and there are no dividends or yearly distributions (all growth is unrealized).
- **D9. Gross-up on withdrawals.** *(Now per day, exactly; see D34.)* When `S` is sold to cover a net need `N`, tax is owed on
  the gain inside `S`, so the model solves `S − cgtax(S) = N` by bisection. That tax depends
  on the wage income earned in the same year. If `S` would exceed the portfolio, the year fails.
- **D10. Household taxation.** *(The default is now filing single for life; see D39.)* Your income and your partner's are added together and taxed as
  one household, using the filing status in effect for that age range (single before the
  wedding, married filing jointly after). The partner schedule is empty by default,
  so after the wedding you're a one-earner MFJ household.
- **D11. Tax schedule shape.** `TaxRegime(start_age, end_age, state, income_left, capgains_tax)`.
  `income_left(gross) → net` is the "function for the amount left" from the request.
  `capgains_tax(gain, gross_wages) → tax` is its partner, needed for D8. The helpers in
  `firemodel/tax.py` build both from bracket tables. The default is federal 2026 brackets
  plus FICA (Social Security up to the wage base, Medicare, and the additional Medicare tax)
  plus state (TX = 0%). A flat-rate state helper is included for moving to a taxed state.
- **D12. Interest schedule shape.** `Growth(start_age, end_age, fn)`, where `fn(balance) → new balance`.
  Default: 5% real until 60, then 4% real (a more conservative allocation in retirement).
- **D13. Expense shape.** `Expense(name, amount, per, start, end, every=1)`. `per` is how many
  times a year it recurs: `DAY=365`, `WEEK=52`, `MONTH=12`, `YEAR=1`, or `ONCE` (charged once,
  at `start`). `every=N` charges it every N years (used for replacing a car).
  Yearly cost = `amount × per`.
- **D14. Kids.** `KID_BIRTH_AGES` is a list. The request gave one birth age for "two kids";
  Claude read that as the first at that age and the second two years later. Repeat the age for twins.
  A helper builds each kid's expenses: childcare/early years ages 0–4,
  school-age costs 5–17, and 4 years of college at 18–21.
- **D15. How the income schedule is represented.** A list of `Income(amount, years=… | until=… | start=…)`
  entries, applied back to back: each one starts where the previous one ended, unless it sets
  an absolute `start`. The sentinel `X` can stand in for **`years`** (sweep how long you work)
  or for **`amount`** (solve for the salary). Each scenario can contain only one `X`.
- **D16. Two scenarios, two answers.** *(The coast salary is now "core expenses"; see D41.)* `CAREER` ends with the X segment
  (the terminal salary for X years). The scenarios are defined in `config.py`:
  - **Retire to $0**: `CAREER` alone. Income stops after the X segment.
  - **Coast FIRE**: `CAREER + COAST` (a fixed coast salary until 60). If X runs past 60,
    the coast segment has zero length.
  "Terminal salary" means the X segment.
- **D17. The solver.** *(Now solves X to the day; see D36.)* For X in years, it scans X = 0, 1, 2, … and returns the first year that
  succeeds. The scan also produces the sweep table and chart. *This assumes the X segment's
  salary is at least what follows it.* An extra X year replaces a coast year, so if the
  terminal salary were *below* the coast salary, more X could hurt and the first success
  might not be the minimum. `--x N` lets you check any single point by hand. More work never hurts
  (monotonic), so the first success is the minimum. For X in the amount, it bisects the
  salary to $100 precision. This was cheap to build, so request 12 was implemented, not tabled.
- **D18. What's left out on purpose** (all conservative or simplifying):
  Social Security (FIRE planners usually leave it out to stay conservative; you can add it as
  an `Income` entry with `start=67`), RMDs, tax-advantaged accounts, market-return randomness
  (the model is deterministic, not Monte Carlo), healthcare costs rising faster than inflation,
  the child tax credit, and itemized deductions.
- **D19. Default example numbers** (a "regular" FIRE plan, today's dollars, invented by Claude): start at 21 with $0,
  an early → mid → high income ladder with X at the high salary, then a coast salary until 60.
  Living expenses rise at the wedding and again when the kids arrive.
  Healthcare costs more before 65 than on Medicare. A car every 10 years. A wedding lump.
  These defaults survive (adjusted) as `default_plans/couple_with_car.py`.

### Software

- **D20. Layout:**
  - `config.py`: **all** variables and schedules (the only file you should need to edit).
  - `firemodel/schema.py`: the dataclasses, the `X` sentinel, and the period constants.
  - `firemodel/tax.py`: bracket math and the builders for tax regimes.
  - `firemodel/sim.py`: the year-by-year simulation (a pure function of a config).
  - `firemodel/solve.py`: the X sweep and solver.
  - `fire.py`: the CLI (argparse), tables, and charts.
  `--config other.py` loads a different config file, so you can keep several scenario files.
- **D21. Dependencies: `plotext`** (pure-Python terminal charts, no dependencies of its own) and
  **`rich`** (tables and colors). Nothing else. Everything else uses the standard library:
  `argparse`, `dataclasses`, `importlib`.
- **D22. Charts:** (1) net worth by age for the minimal X in each scenario, one line per scenario
  on one y-axis with a legend; (2) the sweep: ending balance against X for each scenario;
  (3) for the headline scenario, income against spending by age. No dual axes. Every series
  has a legend label. Plain terminal colors are used.
- **D23. No git commit.** The user didn't ask for one.

### Decisions made during implementation

- **D24. `income_left` also takes `earners`.** Its full signature is
  `income_left(gross, earners=())`, where `earners` lists each person's wages. The Social
  Security wage base applies *per person*, so taxing the household total would undercount
  FICA for two earners. A hand-written lambda can ignore it: `lambda g, e=(): g * 0.7`.
- **D25. `plotext` is pinned to `>=5.3,<6`.** uv installed 6.1.0 at first. That release is an
  API rewrite: `plotext.plot`, `clear_figure`, and friends are gone. The 5.x API is the
  documented, stable one.
- **D26. When the money runs out, the simulation keeps going.** Everything left is sold and the
  unpaid shortfall is carried as a negative balance, which earns no interest. The sweep can
  then show *how badly* an X fails (the age it runs out, how negative it ends), not just pass/fail.
- **D27. The summary's "lowest balance" is measured after the X segment ends.** The lowest
  balance over the whole run is always the first year, which tells you nothing.
- **D28. The salary solver bisects over $0–$5M** (`Config.max_x_amount`). The years solver scans
  `0..END_AGE−START_AGE` (or `Config.max_x_years`) and stops 5 years after the first success.
- **D29. ~~The default config has a third scenario~~** *(removed by D41 and left commented out in config.py)*, "Coast salary after 5y grind", to exercise
  request 12 (X in the salary): the terminal salary for exactly 5 years, then what coast salary is needed until 60?
- **D30. ~~X in years steps by whole years~~** *(superseded by D36)*. Fractional years work (income is prorated within a
  year), but the default sweep uses integers. Because the step is coarse, the minimal passing X
  often leaves a large ending balance (millions at 110, when one year less runs out decades earlier).

---

### Decisions for request #2 (daily model, what-if, CA, single filing, coast = core expenses)

All of these follow the user's instruction to **be conservative**: when in doubt, the pessimistic option wins.

- **D31. Daily time step, 365-day years with no leap days.** Each age-year is 365 days. Order within a day:
  lump-sum deposits → wages in (net of tax) → that day's expense charges out → a surplus is
  invested, or a shortfall is sold with CG tax paid on the spot → one day of growth.
  The balance is checked **every day** against `MIN_BALANCE`, so the failure age is fractional.
  Tables and charts still show one row per age-year (flows summed, balance at year end).
- **D32. Expenses are charged at the start of each period** (conservative, like prepaid rent). `per` is how many
  charges fall in a year: `DAY` every day, `WEEK` 52 times a year (every ~7 days), `MONTH` 12 times (~every
  30.4 days), `YEAR` on the first day of the age-year, `ONCE` on the first day of `start`.
  *The advisor suggested smooth daily accrual instead. Claude chose start-of-period charges because
  the user asked for conservative choices: money leaves earlier and misses growth.*
- **D33. Wages accrue daily** (annual salary ÷ 365), paid in arrears, which is how salaries actually work. Income tax
  is withheld daily at that year's **average** rate: `income_left(annual gross) / annual gross`.
  Summed over the year, that equals the exact annual tax. A year that is partly X and partly coast gets its taxes computed on the real
  total wages for that year.
- **D34. Capital gains tax is paid per day, exactly** (request 19). Given that year's wages, `capgains_tax`
  is piecewise linear in gains, so `cg_curve` turns it into `(breakpoint, marginal rate)` segments. Each
  day's sale is grossed up at the marginal rate on top of the gains *already realized that year*, and
  it splits correctly when a sale crosses a bracket. The daily payments add up **to the cent** to the annual
  `capgains_tax` on the year's total gain (checked in the log). This is conservative: tax leaves
  earlier than an April payment would. `regime()` provides the exact breakpoints (`capgains_breaks`).
  A hand-written tax function is sampled on a geometric grid instead.
- **D35. Daily growth = `fn(1.0) ** (1/365)`.** This assumes the annual `fn` is multiplicative
  (`b * 1.05`). A fixed-fee `fn` wouldn't convert correctly; documented in the code. Mid-year contributions now
  earn only the growth for the rest of the year, which removes D6's small optimism.
- **D36. The solver works to the day.** It scans whole years (for the sweep table and chart), then bisects
  days inside the first year that passes. Answers print like `17y 12w (17.23 yrs)`. It still assumes
  that one more day at the terminal salary never hurts (the D17 caveat).
- **D37. `START_BALANCE = START_BASIS = $15k`.** Because of D32, the first day's bills
  (including a yearly travel charge) come due before any paycheck. With $0 the plan "fails" on
  day 1. $15k stands for cash on hand; **set it to your real number**.
- **D38. California is the default state** (request 17). CA 2025 brackets (the latest published), with capital gains
  taxed as ordinary income. SDI is 1.3% of all wages with no cap (`State.payroll_rate`). The 1% surcharge over $1M is
  folded into the top bracket. CA personal exemption credits are ignored (conservative).
- **D39. Filing single for life is the default** (request 21), for federal, FICA thresholds, and CA.
  `TAX_VARIANTS` in the config lists alternatives. `--compare-taxes` solves every scenario under each
  one and shows the difference in weeks (§5).
- **D40. What-if = an extra after-tax lump sum of $A deposited on the first day of age Y** (both value and
  basis go up). The answer is `baseline X − new X`, in weeks. The grid (`WHATIF_AMOUNTS` × `WHATIF_AGES`
  in the config) runs across CPU cores with `ProcessPoolExecutor` (fork, because the config holds
  lambdas that can't be pickled). `--whatif 10000@25` asks about a single case. If the deposit makes
  X = 0 enough, the cell reads "≥N wk (X→0)". For a salary-X scenario it reports how much lower the salary can be.
  Saving $A is the same as *spending $A less*: a wedding that costs $A less = the "$A at the wedding age" cell.
- **D41. Coast salary = core expenses** (request 22). `Income.amount` can now be a function
  `age -> annual $`. `core_expenses(age)` sums every expense **except** the categories in
  `COAST_EXCLUDE_CATEGORIES = {kids, events, big-ticket}`. The car purchase was moved to
  `big-ticket`. That income is spread evenly over the year's days. **It's the gross salary, not grossed
  up for tax**: the portfolio covers the tax on the coast job, along with the kids, wedding, and cars (conservative).
  "Savings" in the request is read as "the coast job doesn't have to fund savings". X stays the number of years at the terminal salary.
  The "solve for the coast salary" scenario was removed from the defaults (D29).
- **D42. Expenses chart:** stacked bars per age by category. The categories don't depend on X, so there's one chart.
  The legend prints below the chart because plotext's in-chart legend covered the first bars.
- **D43. Speed:** expense arrays per day are precomputed once per config, and wages once per X.
  One 89-year daily run takes about 20 ms. The full default run (both solves plus a 50-cell what-if grid) takes about 4 s.

- **D44. The sweep is opt-in** (request 25). The whole-year sweep table and the "balance at END_AGE vs X" chart
  only appear with `--sweep`. By default you see the summary, the what-if grids, net worth, expenses, and cash flow.
  `--no-sweep` was removed.

- **D45. Two safety margins, both in config.py** (request 26):
  - `EXPENSE_SAFETY_FACTOR = 1.2`: every expense is charged at 120% of its budgeted amount. The coast salary stays
    at 100% of core expenses (conservative: the coast job covers less than the padded spending).
  - `FLOOR_YEARS = 2`: **after the X segment ends**, the balance can never drop below 2 × that year's
    (padded) spending. So the plan ends at 110 with a real cushion (two years of spending), not $1k.
  Claude chose 1.2 and 2 as "conservative" defaults. The factor turned out to be the expensive one (§5).
- **D46. While still working, dipping below $0 is a "cash crunch", not a failure.** The balance is borrowed at
  `BORROW_RATE = 12%` real (a penalty). Found because the padded early car purchase, charged on the
  same day as the yearly travel lump, made *every* X fail on that same day: a plan-independent artifact of
  charging expenses at the start of each period. The summary shows the crunch (age, depth) so it isn't hidden.
  After the X segment ends, the floor in D45 is hard.
- **D47. A negative balance now accrues interest** at `BORROW_RATE`. Before, the unpaid shortfall just
  added up without interest. That's more conservative and affects only failed runs and early crunches.

- **D48. Car = a used Toyota Sienna at $20k every 10 years** (request 28), about 8 years old. Sources (Sep 2026): a 2017
  Sienna averages $19.7k on CARFAX and $20.8k on Cars.com. 2018 listings start around $18k. The all-years average is $29k
  on CarGurus, and a 2026 model runs $49–51k. With the 1.2× padding the model charges $24k. It also removed
  the early cash crunch from D46.
- **D49. An "Income plan" table is printed for each scenario at its solved X.** It lists age ranges, gross/yr,
  after-tax/yr (using that age's tax regime), and a label. Function amounts (the coast salary) are expanded into
  runs of equal dollar value.

- **D50. `LifePlan` class plus a `plans/` folder** (request 31). `firemodel/plan.py` defines `LifePlan`: start age and
  money, wedding age, career (with X), expenses, coast age and exclusions, and partner income. Each file in `plans/`
  exports `PLAN`. `config.py` picks one with a single import line (`from plans.mine import PLAN`). Markets, taxes, and
  safety settings stay in `config.py` because they aren't about your life.
  - `plans/mine.py` (now `custom_plans/`, private) holds the user's own numbers from the chats: **only the user's share of
    spending**, with no couple step-up. Kid costs are counted **in full** (conservative; the partner may share them). No car.
    The user's own income ladder, wedding, and kid ages.
  - `plans/claude_guess.py` keeps the earlier invented plan for comparison.
- **D51. Filing jointly after the wedding is the default** (request 31, reversing D39's single). Caveat, printed in
  config.py: only your income is modeled, so MFJ with an unmodeled partner acts like MFJ with a $0-income partner, which
  is the best case. If the partner earns about as much as you, your share ≈ filing single (see `--compare-taxes`).
  California stays the state.
- **D52. `END_AGE = 112`, `FLOOR_YEARS = 0`** (request 32). Staying solvent two extra years leaves about 2 years of spending at
  110, which is what the floor guaranteed. The floor code stays as an option.
- **D53. Every base-budget line is its own `Expense` in the plan, and `--budget` prints them** with cadence,
  $/month, and $/year (request 33). A "Flexibility" line tops the working-years budget up to a `BUDGET_TARGET`
  (the user's target annual budget). `SHARE_ROOM_UNTIL` halves rent, utilities, and internet before an age (a cheaper
  shared-housing option). Off by default.
- **D54. Realism fixes** (request 34). New `RETIRE` sentinel: an expense can start or end at "the age you leave the high
  salary", resolved per run to the day (`retire_charges` in sim.py; the coast salary treats RETIRE as already passed).
  - **Health insurance:** a cheap employer plan until you leave. Then **individual coverage** (CA silver, before subsidies)
    until 65, then **Medicare** Part B + Medigap/D. An employer premium is only true while employed.
  - **Weekday food:** work feeds you lunch and dinner. After leaving, a weekly groceries line starts.
  - **Daycare:** SF infant/toddler centers cost about **$3k/mo**. CA universal TK (4) and K (5) are free,
    so ages 4–5 are after-care only, not full daycare.
  - Added **term life insurance from the first kid until the youngest is 25**. First
    version ended when the youngest turned 18; the user pointed out that this dropped cover right when college bills start (request 35).
  - Kept: late-life care from 88.
  - Flagged but kept as written: a couple of discretionary lines that looked low for SF, and the wedding amount (above the CA average).
- **D55. The expenses chart folds everything past the 7 largest categories into "other"** (the plan has 14; there are
  only 9 colors, and a 10th crashed plotext).

### Decisions for the `/simplify` pass (request 36)

Four read-only reviewers (reuse, simplification, efficiency, altitude) produced the list. The user picked the items.
Zero-effect changes were checked against a recorded baseline: **every answer, ending balance, what-if and salary-X
result was identical to the dollar** before M1 was applied.

- **D56. M1: recurring bills accrue evenly per day** (supersedes D32). The root-cause review found that start-of-period
  charging made the model sell tens of thousands of dollars of portfolio a year while you were working, buy it back the same
  month, and pay thousands a year of *phantom* capital gains tax. It was also the only reason for the $15k starting cash (D37) and the
  cash-crunch/borrowing rule (D46/D47). ONCE items and `every`-N-year items (cars) stay lumps. Built with a
  difference array (O(days)), per run. **Effect: answers about 30 weeks earlier** (the 1.2× padding was kept, not raised to 1.225).
- **D57. Removed:** the cash-crunch/borrow rule, `borrow_rate`, `min_balance`, `floor_years`/reserve,
  `Config.deposits`, `max_x_years`, labels on `Growth`/`TaxRegime`, `TaxRegime.state`, `LifePlan.notes`, the sampled
  capital gains fallback (`capgains_breaks` is now required), the id(cfg) expense cache, and `retire_charges`.
  **The rule is now:** the plan fails the first day the balance is below $0 (or below the principal, D62).
- **D58. Starting money is the user's real number** (request 37), no longer a workaround.
- **D59. M2: `Growth(start, end, rate)`** replaces `fn(balance)` (supersedes D12/D35). The sim only ever used
  `fn(1.0)`, and a fee-style function would have been silently wrong. Zero effect.
- **D60. Solver:** one bisection over days in [0, horizon] (supersedes D17/D36), which about halves the runs. The whole-year sweep is built
  only for `--sweep` (`solve.sweep()`). The salary solver and `what_if` share the same `_smallest` helper.
- **D61. Smaller cleanups:**
  - `lay_out` substitutes X and returns the X segment's end age (no index zipping).
  - The coast salary is plain per-age `Income` segments instead of a function (supersedes D41's mechanism, same numbers), so `Income.amount` has one type.
  - The income table merges equal rows and shows exact dollars.
  - One `_gain_tax`/`_gain_breaks` helper serves both federal and state.
  - The capital gains curve is cached per run (about 30% faster).
  - `budget_table` uses the schema constants.
  - `runpy` loads the config.
- **D62. New scenario: "Retire, principal never shrinks"** (`Scenario.keep_principal`, request 38). From the day you stop,
  the balance may never drop below its value that day (real dollars): you live off returns forever. Every summary row now shows
  **"Portfolio when you stop"**, which answers "how big". Checked monotonicity by hand over a range of X: every X below
  the answer fails and every X above passes. The tightest point is the years when both kids are in college and individual
  health insurance has started.

- **D63. `LifePlan.alt_careers`**: extra income paths with the same spending. Each career path gets the same three
  scenarios (retire to $0, coast, principal never shrinks), labeled `[tag]`. The private plan adds a higher, earlier
  alternate path. For principal-never-shrinks on that path, X landed on an exact whole number of years. That isn't an
  artifact: any earlier stop fails within a day, because the second kid's daycare years make daily
  spending exceed daily returns. Checked by hand over a range of X.

- **D64. `Scenario.flat_from` replaces `keep_principal`** (request 41). From that age (default `FLAT_FROM_AGE = 100` in
  config.py; `RETIRE` gives the old "from the day you stop") the balance may never drop below its value at that moment.
  Earlier dips (kids, college) are allowed. The scenario is renamed "Retire, flat from 100". Checked: the balance at 100/105/111
  is flat to within about $1k, with real 4% returns covering the padded late-life spending. Monotone over a range of X.

- **D65. Texas as its own plan and config.** `plans/mine_texas.py` = `plans/mine.py` plus an editable `AUSTIN` table
  of exact-name price overrides (rent, utilities, renters insurance, gym, transport, individual health, daycare, college
  at UT Austin). It also adds full-time preschool at age 4 (TX has no universal pre-K, unlike CA's TK), so after-care
  starts at 5. It asserts that every override name exists. (The shipped equivalent of this pattern is
  `default_plans/austin_family.py`.)
  `config_texas.py` = `make_config(PLAN, "TX, MFJ after wedding")`. config.py was refactored into `scenarios_for(plan)` and
  `make_config(plan, taxes_name)` (CA results unchanged).
  Bugs caught during the build: (1) prefix matching turned "Renters insurance" into the rent override. Fixed with exact names plus the assert.
  (2) Age-4 preschool stacked on the inherited after-care. Fixed by shifting after-care to start at 5.

- **D66. Verified numbers written into the plans** (request 48). All suggested fixes were applied except the ones the user
  declined (rent/utilities, car rental, wedding amount), and the 1.2× padding stays on every line.
  - **The wedding moved one year later**, since the original age missed by a small amount under the new numbers. Filing jointly moves with it.
  - Changes, SF plan: employer health; individual health **age-rated** (steps up at 50 and 58); Medicare stepping up at 85;
    vision; kids' coverage (family tier while employed, a separate kids' plan after leaving); an **extra bedroom while kids
    are home** (full cost); babysitting; daycare split into infant and toddler rates; kid extras; school-age costs; UC
    college; and several daily-life lines (trips, dinners, haircut, software, furniture, bike, moving, groceries,
    late-life care tail).
  - The flexibility line (D53) is now $0: the itemized budget exceeds the target.
  - The Austin plan gets matching Austin overrides, plus a rideshare line while kids are home (no car).
  - No ACA subsidies anywhere (unchanged). The SF ELFA daycare credit is not counted.

- **D67. Joint simulation** (request 50).
  - **Tax:** `TaxRegime.joint` marks MFJ regimes. Joint years tax combined wages on one return. Non-joint years tax each earner
    separately, and capital gains then stack on *your* wages only. This fixes the D51 caveat: MFJ no longer implies a $0-income partner.
  - **Partner's contribution:** `Scenario.partner_share` (from `LifePlan.partner_share`) is the fraction of the partner's take-home
    that enters the pot, 50% by default.
  - **`plans/joint.py` `make_joint(base, salary)`** (simplified by request 52): the partner earns `salary` over a fixed working
    span, and **50% of their after-tax pay goes into the pool. Nothing else is added.** Everything of theirs, including their half of housing,
    comes from their other 50%. (Earlier versions: the pool also paid their half of housing, first to 112, which double-counted,
    then only while they worked. Both were dropped.)
  - **`config_joint.py`:** `PARTNER_SALARY` and `IN_TEXAS` settings. No-partner results were checked identical to the dollar.
  - **Finding (earlier housing version):** with the pool paying their half of SF housing, a 50% share *hurt* at a modest partner
    salary. Their marginal take-home on the joint return was small, so half of it was less than their padded half of SF housing.
- **D68. Unit tests** (request 51): a subagent writes `tests/` (pytest) with closed-form scenarios, changing no source files.
  Suspected bugs are marked `xfail(strict)` and reported.

- **D69. Sweep tool: `grid.py` + `firemodel/grid.py`** (request 54). `grid.py` holds editable axes, each a `{label: value}` dict:
  `CITIES` (plan with prices, plus a tax variant name), `LADDERS` (career income paths with X), and `PARTNERS` (partner salary or None).
  It builds one Config per combination via `make_config`, solves every scenario in each Config in parallel (fork pool,
  `solve_grid`), and prints one table. To add a tax axis, add a city entry that uses another `TAX_VARIANTS` name (e.g. SF with
  single filing). 12 combinations × 3 scenarios take about 2.2 s. The original-ladder rows were checked against the earlier ad-hoc results.

- **D70. Tax-advantaged accounts (Fable-reviewed design).** Every account is the same `Pot(value, basis)`; the difference is
  the tax curve used on withdrawal, via one `drain()` that reuses the existing gross-up (`sell_for`) and caps at emptying the account:
  - taxable → capital gains curve (unchanged)
  - 401(k) → ordinary-income curve (basis 0), +10% before `penalty_age` 59.5
  - Roth → pro-rata earnings; tax-free after 59.5, ordinary + 10% before
  - 529 → tax-free when paying expense lines named "college" (it pays them first); otherwise ordinary + 10%

  Mechanics and settings:
  - **Tax:** `income_left(..., deferred)` lowers only the income-tax base (FICA/SDI still apply to all wages). `ordinary_tax`/`ordinary_breaks`
    reuse the capital gains stacking helpers with ordinary brackets. The deferral's tax saving goes to your wages only (it doesn't leak into the
    partner's 50%). Contributions come only from career wages (before X ends).
  - **Settings:** `Accounts` in schema; `Config.accounts` defaults to all limits 0 = off, and no-account results are identical to the dollar.
    `config.TAX_ADVANTAGED` = 401(k) $24,500, Roth $7,500, 529 $16,000/yr (2026 limits; verify). grid.py has an `ACCOUNTS` axis.
  - **Reserve:** each year, room = taxable + take-home − this year's spending − next year's spending. Contributions stay within room, so
    upcoming lumps (the wedding) stay liquid.
  - **529 target:** the present value of all remaining college costs, discounted at the growth rate. It drains to exactly $0 at the end of
    college. The first version targeted the undiscounted cost and overfunded it by about $117k.
  - **Omitted (tabled):** RMDs (optimistic), the Roth conversion ladder / 72(t) / rule of 55, HSA, employer match (a big lever; add it to
    `Accounts` later), partner accounts, mega-backdoor Roth. Roth withdrawals use pro-rata earnings (conservative vs contributions-first).
- **D71. README.md** (subagent): a vibe-coded disclaimer, "What is this?", quickstart, layout, customization, limitations, tests.
  No personal numbers.
- **D72. 401(k)/Roth = only the after-59½ need, frontloaded** (request 59, replacing D70's fill-to-limit rule).
  `retirement_target()` works backward over years: each year's post-penalty-age shortfall (spending − take-home) is grossed up to pre-tax with
  that year's ordinary-income curve, then discounted at the growth rate (mid-year) → `target[y]`. Each year the contribution is capped at
  `target[y] − (401k + Roth)`: the 401(k) limit first, and Roth only for any remainder. After 59½ the 401(k) is drawn first (it's earmarked),
  then Roth, then taxable. Before 59½ taxable pays.
  - **Result:** 401(k)+Roth end within a few thousand dollars of $0 at 112. Early-withdrawal penalties are zero or a few thousand
    dollars (in SF the minimal stop age can empty taxable a few months before 59½). Stop ages improve slightly versus both
    taxable-only and fill-to-limit.
  - Tests: `tests/test_accounts.py` (14, hand-derived, e.g. the 401(k) gets exactly $7,300, not its $20k limit, and ends at $0).

- **D73. `default_plans/` (shipped) + `custom_plans/` (gitignored), autoloaded** (request 60). `firemodel/loader.py` finds
  a module by name in custom_plans/ first, then default_plans/. A module with `PLAN` is a plan, one with `GRID` is a grid.
  Each package's `__init__.py` may set `DEFAULT_PLAN`/`DEFAULT_GRID`.
  - `LifePlan.taxes` names its tax setup, and `LifePlan.with_partner(...)` replaces plans/joint.py.
  - config.py: `TAX_VARIANTS` are now *functions of the plan* (they need its start and wedding ages): CA/TX × single/MFJ,
    plus IL (flat 4.95%) and CO (flat ~4.4%, approx.) examples. `make_config(plan, taxes=None, accounts=None)`. `CONFIG` = the default plan.
  - `fire.py --plan NAME / --accounts / --list` replace config_texas.py and config_joint.py (deleted).
  - `grid.py [NAME] / --list`: a generic runner over GRID axes (plans, ladders, partners, taxes, accounts). A salary-X ladder shows the salary.
  - custom_plans/: mine, mine_texas, mine_joint, grid_mine (the private plans).
  - default_plans/:
    - Plans: sf_family (1 kid, a $60k wedding at 28, an illustrative 120→175→230 ladder), austin_family (the override pattern),
      single_lean, three_kids, couple_with_car (Claude's first invented defaults; its wedding was changed to $40k at 27 because a
      larger one failed on day 1 for every X).
    - Building blocks: ladders.py, partners.py.
    - Grids: grid_cities, grid_taxes, grid_profiles, grid_ladders.
  - Private results are identical to the dollar after the move. The smoke tests now cover every shipped plan and grid (191 tests).
  - **Privacy note:** DESIGN.md used to hold the private plan's numbers and results. It was split: this public, anonymized
    version, and the unredacted log in `custom_plans/DESIGN_private.md` (gitignored).

- **D74. One general backward calculator for all accounts (`plan_accounts`, Fable-designed; replaces the D70 reserve,
  the D72 retirement target and the 529 PV target).** Walking backward from END_AGE, every day's shortfall
  (spending − take-home; surpluses count negative) is assigned to the account allowed to pay it: after the penalty age the
  401(k)/Roth (grossed up for income tax); college lines the 529; everything else taxable (grossed up for capital-gains
  tax as if all gain). Each account: `need[i] = max(0, shortfall[i] + need[i+1] / daily growth)`.
  - **Contributions:** each year 401(k) → Roth up to `need_K − balances`, then the 529 up to its need, from career wages.
  - **Two daily caps:** `cap_t` = taxable alone still covers every non-college need (a 529 can't pay a wedding); `cap_ta` = taxable +
    what the 529 really holds still covers every need incl. college, so an underfunded 529 can't hide college costs.
  - **Bug found and fixed:** the first single-cap version raided the 401(k)/Roth with penalties in a three-kids plan whose 529 couldn't be
    fully funded. The two caps fixed it.
  - **Result on every shipped plan:** $0 pre-59½ penalties, and 401(k)+Roth end at exactly $0 at 112 (retire/coast).
    Stop ages within ±0.1 yr of D72, or better. New hand-checked tests: a lump 2 years out (the old 1-year reserve paid a
    penalty there), and an underfunded 529.
  - **Also fixed:** a variable-name clash (`need`) crashed the first version.

- **D75. Readable account planner** (request 64). Split into `required_balance(gaps, growth)` (the whole backward
  idea in 5 lines: `need[day] = max(0, gap[day] + need[day+1] / growth)`), `plan_accounts` (assigns each day's gap
  to taxable / taxable incl. college / 401(k)+Roth / 529, and returns an `AccountPlan`), and `max_contribution` (the most
  that can leave taxable while it stays at or above its need on every day). Results were checked identical on every plan
  (with accounts), and all tests pass. Forward vs backward: the backward pass runs once per simulation, as a lookup table for
  contributions. The forward daily loop still pays taxes and bills, grows the money, and decides pass/fail.

- **D76. Moving cities: `LifePlan.move_to(other, at_age)`.** `Expense` gets `after`/`before` clip fields: `bounds()` is clipped;
  ONCE items outside the window are dropped (not moved); every-N cadence counts from the original start. `move_to` clips this plan's
  expenses to `before=at_age` and the other's to `after=at_age`. `plan.taxes` may be a schedule `[(from_age, variant), ...]`, and
  `config.tax_schedule` clips each variant's regimes to its ages (e.g. CA until the move, TX after). Default example
  `sf_to_austin` (move at 35). Tests: tests/test_move.py (7). Plans without a move are identical to the dollar.

- **D77. `start_roth`** (request 68): a starting Roth balance, counted as contributions (tax/penalty-free), included in totals and
  growth even when accounts are off. Test added. Sensitivity of the conservative choices (toggling each one off):
  the 1.2× padding is by far the biggest lever, then the extra bedroom for kids, then the wedding, late-life care and
  post-employment health, each roughly a year. Turning them all off roughly matches the chat-era estimates.

- **D78. Income can start at `RETIRE`; `LifePlan.coast_margin = (extra $/yr, years)`.** `lay_out` resolves `start=RETIRE` to the X
  segment's end (an error if it comes before X). Overlapping segments add up in `daily_wages`, so the coast job pays core
  expenses + the margin for its first N years. Tests added. Finding: a margin of $10k/yr × 15 yrs moves coast only ~0.5–0.6 yr
  earlier ($5k: ~0.3, $20k: ~1.1), the same in every city and with accounts on or off: $150k of extra gross over 15 years ≈ half
  a year of high-salary savings.

- **D79. Defaults changed** (request 70): `EXPENSE_SAFETY_FACTOR = 1.1` (was 1.2), and `LifePlan.coast_margin = (10_000, None)`: every
  coast job pays core expenses + $10k/yr until coast_until. Unit tests that check core-only coast pin `coast_margin=(0, None)`; a
  margin test was added. The README's example tables were produced under the old defaults and need regenerating.

- **D80. Partner = joint tax return only** (request 71). `with_partner` loses `mirror`/`extra`: the partner's costs aren't
  modeled, and `share` is what they put in the pool after paying their own way. A self-funding partner is `share=0`: their
  pay is only on the joint return, where it raises the household's average rate on your wages. So this is *more*
  conservative than MFJ with a $0-income partner, the old best case. Copying your costs for the partner made them a
  net drain in every year (padded costs above their take-home, and costs for life while their pay stops at 55);
  doubling with no partner income was never solvent.

- **D81. Joint household with per-line couple factors** (request 73; replaces D80's tax-only partner). `with_partner(...,
  couple={line name or category: factor}, together_from=age)`: from that age the pool pays an extra (factor − 1) × each line
  as a "Partner: …" line (category "partner", so the coast job still covers only your own core). A name beats its category;
  every line must be covered (KeyError otherwise), so no line gets a factor silently. Chosen factors: shared housing,
  furniture, software, car rental 1.0; food, household, laundry 1.5; flight + hotel 1.6; per-person lines (health, phone,
  transport, personal, social, stuff, dinners out) 2.0; kids/events/insurance 1.0. Sanity check: the household costs
  ~1.5× one person, in line with the OECD equivalence scale. Partner Social Security and their own 401(k)/IRA room are not
  modeled (conservative). Scratch-script note: a plan pickled into a worker process breaks the RETIRE sentinel's `is` check;
  pass indexes to workers instead (the integration suite forks, so it's unaffected).

- **D82. Household 401(k)/Roth** (request 74). One 401(k) pot and one Roth pot for the household. Each working earner adds
  their own yearly limit, capped at their pay: min(limit, your pay before X ends) + min(limit, partner's pooled pay).
  Contributions come from the pooled pay (your career wages + the partner's pooled share), per paycheck. The 401(k)
  deferral is split between earners by pay; its tax saving (joint return: on household wages; single: per earner)
  goes into the pool on paydays (it used to be folded into your take-home rate, which divided by your wages). One
  penalty age for both (same-age assumption). `max_contribution` now checks the whole year, not just up to X, which is
  slightly stricter in the stop year. New unit test: a working partner doubles the 401(k) room.
- **D83. Accounts on by default** (request 74). `config.ACCOUNTS = TAX_ADVANTAGED`; `fire.py --no-accounts` replaces
  `--accounts`. When accounts are on, the summary adds a "No 401(k)/Roth/529" column (each scenario solved again with
  `Accounts()`, about double the solve time). New chart after the cash flow: end-of-year balances of taxable, 401(k),
  Roth and 529 for the first scenario. Integration tests updated: "plan:" cells now have accounts on; new "taxable:"
  cells for the grid taxable rows and the --no-accounts CLI check; the README-settings cells pin NO_ACCOUNTS. README
  updated (flag, default, joint household, household pots); its stale "liquidity reserve" text was replaced (D74).

## 3. Tabled / future work

- ~~Joint household simulation~~: done in request 50 (D67); full joint household with couple factors in D81.

- ~~Tax-advantaged accounts: 401(k), Roth IRA, 529, withdrawal ordering~~: done (D70–D75; household pots D82; on by
  default D83). Still missing:
  - Roth conversion ladder / 72(t) / rule of 55 (early 401(k) access without the 10% penalty; the model funds the
    pre-59½ years from taxable instead, which is conservative).
  - Employer 401(k) match (a big lever; leaving it out is conservative).
  - RMDs (leaving them out is optimistic), HSA, separate 59½ dates for partners of different ages.
- Monte Carlo or historical-sequence returns.
- More than one X per scenario (a 2-D sweep).

---

## 4. Coding log

The process, in order.

1. Looked at the repo. `fire/` was empty; uv 0.9.21 was available. Read the whole request
   and itemized it (section 1).
2. Drafted the plan and got a design review from a second model. It pointed out the need
   for: real dollars (D1), per-year success rather than only at the end (D5), cost-basis
   tracking (D7), the withdrawal gross-up (D9, flagged as the most likely correctness bug),
   and a clear definition of X and the two scenarios (D16).
3. Wrote this document (requests and decisions) **before any code**.
4. `uv init --bare`, then `uv add plotext rich`.
5. Wrote `firemodel/schema.py`: period constants, the `X` sentinel, the `Income`/`Expense`/
   `TaxRegime`/`Growth`/`Scenario`/`Config` dataclasses, and `substitute_x`.
6. Wrote `firemodel/tax.py`: `bracket_tax`, `stacked_tax`, the `Federal`/`Fica`/`State` tables,
   and `regime()`, which builds the `income_left` and `capgains_tax` closures (D8, D11).
7. Wrote `firemodel/sim.py`: `lay_out` (back-to-back income segments),
   `income_at` (prorated), `gross_up_sale` (bisection, D9), and `simulate` (D6).
   *Bug caught on self-review:* the first version found the X segment by comparing
   segments *after* X was substituted in, which never matches. Rewrote it to pair the
   original and resolved segments by index.
8. Wrote `firemodel/solve.py`: `x_kind` checks there is exactly one X, then a linear scan
   over years or a bisection over salary.
9. Wrote `config.py` with the default plan (D19), 2026 federal/FICA tables, TX, and
   5%→4% real growth.
10. Wrote `fire.py`: argparse, rich tables (summary, sweep, year-by-year), and three
    plotext charts.
11. First run with `--no-plot` on Claude's invented defaults: all three scenarios solved (retire, coast, and the
    salary-X "coast after a 5-year grind").
12. **Checked the tax math by hand** (scratch script):
    - MFJ, $0 wages, $200k gain → `(200k − 32.2k SD − 98.9k) × 15% = $10,335`. ✓
    - High wages, $10k gain → `10k × (15% + 3.8% NIIT) = $1,880`. ✓
    - Gross-up with $0 wages and an 80% gain fraction: a $400k net need → sell $436,482, pay
      $36,482 tax, net exactly $400,000. ✓ Smaller needs fit entirely in the 0% LTCG
      bracket, so `S = need`. ✓
    - A high single-earner MFJ salary in TX → a plausible take-home. ✓
13. First run with charts crashed: `plotext 6.1.0` has no `clear_figure`. Pinned to 5.x (D25). Charts rendered.
14. Changed the summary's "lowest balance" to "lowest after X ends" (D27).
15. Tested a partner config loaded from outside the repo via `--config`
    (a partner salary for a 20-year span). Retire to $0 dropped sharply, and coast/salary
    solve to 0, as expected. Tested the `--x N` yearly table: the run-out age matched the sweep.
16. Final review: fixed a college-overlap description, added the monotonicity caveat to D17, and made the sweep table
    also bold the solved salary row. Nothing committed (D23).

16. **Request #2 work started.** Wrote the plan (daily step, what-if). The advisor reviewed it and pointed out:
    performance (precompute per-day arrays), bisection instead of a linear scan, and smooth
    expense accrual (Claude kept start-of-period charges because of the "be conservative" instruction, D32).
17. More messages arrived mid-work: CA worst case, an expenses chart, per-day taxes, "be conservative",
    single filing plus a report, coast = core expenses, and the web-app question. All were folded into the same pass.
18. `tax.py`: added `State.payroll_rate` (CA SDI), and `capgains_breaks(wages)` giving the exact slope
    changes of the CG tax function. `schema.py`: `TaxRegime.capgains_breaks`, `Config.deposits`,
    `tax_variants`, `whatif_*`, and income `amount` can be a function.
19. Rewrote `sim.py` to be daily: `daily_wages`, `charge_days`, `daily_expenses` (cached),
    `expenses_by_category`, `cg_curve`, `sell_for` (piecewise gross-up), and the day loop.
20. First daily run failed **on day 1**: $0 start balance, with the first-day bills charged before any
    paycheck. Added the $15k starting cash (D37).
21. Rewrote `solve.py`: whole-year scan then day bisection, and `what_if()`. Timing: 20 ms per run and 0.5 s per solve.
    Checked that a $0 what-if gives 0 days.
22. Rewrote `config.py`: CA single for life, `TAX_VARIANTS`, `core_expenses` coast, `WHATIF_*` grid.
    Cached the callable coast amount once per year (it was being called 365 times a year).
23. `fire.py`: to-the-day answers, what-if tables (parallel; 3.8 s wall time, 27 s of CPU),
    `--whatif A@Y`, `--compare-taxes`, and the expenses stacked-bar chart.
24. **Checks:**
    - Daily CG gross-up: 365 sales of $400 net each, 70% gain. The sum of daily taxes equals
      `capgains_tax(total gain)` exactly at several wage levels (for example $13,146.26 = $13,146.26), and
      `sale − tax = 400` every day.
    - The what-if grid is monotone: more money, or money saved earlier, always gives ≥ weeks.
    - `--compare-taxes` ranks as expected: CA single > CA MFJ > TX single > TX MFJ.
25. The expense chart legend covered the first bars, so it now prints below the chart (D42).
26. The user said to keep it a CLI (§7) and to stop showing the sweep. Made it opt-in with `--sweep` (D44).
27. The user asked for a safety factor, not a plan that ends at $1k. Added `safety_factor` (applied in `daily_expenses`
    and in the category chart) and a `floor_years` reserve that is checked daily after the X segment ends (D45).
28. First run with the margins: **no solution for any X**. Debugged it: every X failed on exactly the same day.
    The padded car, the travel lump, and the month's bills on the same day exceeded what had been saved. Added the
    cash-crunch rule with borrowing interest (D46, D47) and a "Cash crunch while working" column.
29. Measured each margin separately (3×3 grid of factor × floor): the floor costs about a month of
    work, while the factor costs about 4 years per extra 10%.
30. The user asked for the coast amount (it was only a function in the config) and a realistic car. Car changed to $20k
    after searching current used-Sienna prices (D48). Added the income-plan table (D49). It showed the coast job's
    take-home falls well short of padded core spending; the gap comes out of the portfolio.
31. Read the two shared chats. WebFetch and curl only got the page shell (JS-rendered, Cloudflare on the API). The
    DevTools browser wasn't logged in. After the user ran `/chrome`, read them with Claude in Chrome
    (`get_page_text` caps at 50k chars and JS output at ~1k, so the tail was reinserted as the page body and read again).
    Saved a memory with the figures, then deleted it at the user's request.
32. Built `LifePlan` and `plans/mine.py` / `plans/claude_guess.py`, and rewired config.py. END_AGE 112, floor off, MFJ default.
33. Realism review → `RETIRE` sentinel (schema: `Expense.bounds`, `uses_retire`; sim: `retire_charges`, excluded from
    the cached daily array). First version crashed on `math.ceil(-inf)` and `math.floor(-inf)` for the coast
    (retire = −∞), so it now guards with `isfinite`.
34. Added `--budget`. Checked that the working-years budget equals `BUDGET_TARGET` exactly (the flexibility line fills the gap)
    and that core spending after leaving looks right. The expenses chart crashed with 14 categories and 9 colors, so it now
    folds small categories into "other" (D55).
35. Verified: default run, `--compare-taxes`, and swapping to `plans/claude_guess.py` via a temporary config copy.
36. `/simplify`: ran four read-only review agents in parallel (reuse, simplification, efficiency, altitude), merged
    duplicate findings, and asked the user which to apply (M1, M2, cleanups, and display approved; salary-X kept).
37. Recorded a regression baseline (all tax variants × scenarios, a what-if, salary-X). Rewrote schema, sim, solve,
    tax, plan, config, and the CLI for the zero-effect cleanups plus M2. The regression diff was **identical**.
    Hiccup: a regex that stripped `label=` from `regime()` calls also matched the Growth lines, so the script stopped before
    writing anything. Fixed the order and reran.
38. Applied M1 (difference-array daily accrual) and the real starting balance. Both answers moved about 30 weeks earlier.
39. Added `keep_principal` and the "Portfolio when you stop" column. Checked monotonicity by hand. Smoke-tested every CLI
    mode (default, --budget, --compare-taxes, --sweep, --x, -w). The full default run takes 5.6 s wall (3 scenarios × what-if grid).

## 5. Results

Results for the owner's private plan are in custom_plans/DESIGN_private.md.

Below: the shipped example grids in `default_plans/` (run from `fire/` with `uv run grid.py NAME`). Each cell is the
stop age for **retire to $0 / coast (core expenses until 60) / retire, flat from 100**, with the portfolio at the stop
age in parentheses for retire to $0. All use the 1.2× expense padding and solvency to 112.

**`grid_cities`** (SF vs Austin plans × two example ladders × solo vs a partner laddering $55k → $90k at 32 × taxable-only vs
401k+Roth+529):

| City | Ladder | Partner | Accounts | Retire / Coast / Flat |
|---|---|---|---|---|
| SF | big tech 120 → 175 → 230×X | solo | taxable | 46.0 ($2.26M) / 41.8 / 47.1 |
| SF | big tech 120 → 175 → 230×X | solo | 401k+Roth+529 | 44.8 ($2.35M) / 40.6 / 45.9 |
| SF | big tech 120 → 175 → 230×X | partner | taxable | 41.1 ($2.03M) / 36.6 / 42.1 |
| SF | big tech 120 → 175 → 230×X | partner | 401k+Roth+529 | 40.1 ($2.05M) / 35.7 / 41.0 |
| SF | fast track 200×3 → 320×X | solo | taxable | 37.2 ($2.42M) / 33.3 / 37.8 |
| SF | fast track 200×3 → 320×X | solo | 401k+Roth+529 | 36.6 ($2.47M) / 32.8 / 37.1 |
| SF | fast track 200×3 → 320×X | partner | taxable | 34.3 ($2.09M) / 30.7 / 34.9 |
| SF | fast track 200×3 → 320×X | partner | 401k+Roth+529 | 33.8 ($2.11M) / 30.3 / 34.3 |
| Austin | big tech 120 → 175 → 230×X | solo | taxable | 38.4 ($2.02M) / 33.9 / 39.1 |
| Austin | big tech 120 → 175 → 230×X | solo | 401k+Roth+529 | 38.0 ($2.06M) / 33.5 / 38.6 |
| Austin | big tech 120 → 175 → 230×X | partner | taxable | 34.3 ($1.62M) / 29.9 / 34.8 |
| Austin | big tech 120 → 175 → 230×X | partner | 401k+Roth+529 | 33.9 ($1.63M) / 29.6 / 34.4 |
| Austin | fast track 200×3 → 320×X | solo | taxable | 32.8 ($2.13M) / 29.4 / 33.2 |
| Austin | fast track 200×3 → 320×X | solo | 401k+Roth+529 | 32.5 ($2.15M) / 29.2 / 32.9 |
| Austin | fast track 200×3 → 320×X | partner | taxable | 30.3 ($1.54M) / 26.9 / 30.6 |
| Austin | fast track 200×3 → 320×X | partner | 401k+Roth+529 | 30.1 ($1.55M) / 26.8 / 30.4 |

**`grid_profiles`** (expense profiles, all on the big tech 120 → 175 → 230×X ladder):

| Plan | Retire / Coast / Flat |
|---|---|
| single, lean | 35.1 ($1.42M) / 30.7 / 35.9 |
| SF, one kid | 46.0 ($2.26M) / 41.8 / 47.1 |
| SF, three kids | 67.3 ($1.95M) / 67.3 / 70.9 |
| couple with car | 55.1 ($2.47M) / 52.1 / 57.4 |

**`grid_taxes`** (the SF family plan under each tax setup):

| Taxes | Retire / Coast / Flat |
|---|---|
| CA, MFJ after wedding | 46.0 ($2.26M) / 41.8 / 47.1 |
| CA, single | 49.6 ($2.28M) / 46.5 / 51.3 |
| TX, MFJ after wedding | 42.7 ($2.30M) / 38.2 / 43.6 |
| TX, single | 44.4 ($2.31M) / 40.5 / 45.5 |
| IL, MFJ after wedding | 45.1 ($2.33M) / 40.9 / 46.2 |
| CO, MFJ after wedding | 44.8 ($2.33M) / 40.6 / 45.9 |

**Lessons that held across plans** (from the development runs):

- The expense padding factor is the big lever: about 4 years of work per extra 10%, because it pads every year of spending
  for ~90 years. A reserve floor of 1–2 years of spending is nearly free (about a month of work), because a cushion kept
  mid-life compounds into what the late years need.
- Assuming single filing instead of MFJ costs a few years of work in CA, mostly from the 0%/15% LTCG brackets and a
  bigger standard deduction during drawdown, plus lower wage tax while working.
- Retire-to-$0 and coast need about the same portfolio at 60 and are identical after that; coast stops earlier because
  the coast job covers part of spending while the portfolio keeps compounding.
- The binding constraint is usually the kids' peak years (overlapping college, plus individual health insurance after
  leaving work). In retirement, a married couple can realize a lot of gains at 0% federal tax (standard deduction plus the
  0% LTCG bracket), so CG tax matters less than wage tax.
- What-if: money saved in your twenties shortens work by a few days per $1k; the coast scenario gains a bit more per dollar.
- Tax-advantaged accounts (D72) help modestly (a few months to about a year and a half in the grids above); a partner and
  a cheaper city matter much more.

## 6. Usage

```
uv run fire.py --budget             # every expense line in the plan ($/mo, $/yr)
uv run fire.py --compare-taxes      # CA/TX × single/MFJ comparison
uv run fire.py --plan NAME          # pick a plan from custom_plans/ or default_plans/ (--list shows them)
uv run fire.py -w 10000@25          # one what-if instead of the grid
uv run fire.py --no-whatif          # skip the what-if grid
uv run fire.py                      # solve all scenarios: summary, what-if, charts
uv run fire.py -s coast             # only scenarios whose name contains "coast"
uv run fire.py -t                   # add a year-by-year table for each solution
uv run fire.py -s "Retire" --x 11   # simulate one X value, print the yearly table
uv run fire.py --config mine.py     # use a different config file
uv run fire.py --sweep              # also show the whole-year X sweep table + chart
uv run fire.py --no-plot --no-whatif # summary only
uv run grid.py grid_cities          # run a grid (grid.py --list shows them)
```

## 7. Web app vs CLI (request 23)

**Decision (user, request 24): keep it a CLI.** No web front end is planned. The notes below are only
the reasoning Claude gave before the user decided.

Claude's opinion: **the engine should stay a Python library, and a web front end would be worth adding for
exploring.** This hasn't been built yet. The user asked a question; they didn't ask for a build.
- What the web would do better: sliders for the salary, expenses, and returns with an instantly recomputed answer (a run is 20 ms);
  hover tooltips on the charts; comparing scenarios side by side; easy sharing.
- What the CLI does better: the config is real Python (lambdas, helper functions like `kid_expenses`), which a form
  can't easily represent. It's also scriptable and diffable, and you can keep several config files.
- A cheap path: `fire.py --html report.html` writes a static page with interactive charts from the same results,
  or a small local server. There's already a sibling `web/` folder in this repo. Running Python in the browser
  (Pyodide) would also work with no server, but it's heavier.
