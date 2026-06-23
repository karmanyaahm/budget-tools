# Budget Pies — web app

Browser version of the Buckets pie-chart explorer. Vanilla JS/HTML/CSS, no build
step. Your `.buckets` file is read entirely in the browser (via sql.js WASM) and
**never uploaded anywhere**.

## Run

It must be served over HTTP (ES modules + the WASM file can't load from
`file://`). Use the Makefile from the repo root:

```bash
make                          # serves http://buckets.localhost:8137/
make FILE="My Budget.buckets" # same, but auto-loads that file (default)
make clean                    # remove generated PNGs + the default symlink
```

`make` symlinks `FILE` to `web/default.buckets`; the app fetches that on startup
and **auto-loads** it — no manual upload. If `FILE` doesn't exist, just open the
page and **Upload .buckets** (or **Open file (remember)** in Chromium browsers,
which keeps a handle so you can "Refresh data" / reconnect next visit).

Any static server also works (e.g. `cd web && python3 -m http.server`). The host
`*.localhost` resolves to loopback automatically and counts as a secure context,
so the File System Access API still works.

## Features (parity with the desktop app)

- Five tabs: Allocations · Actual Income · Activity · Gross Spend · Reimbursements,
  each with a methodology blurb and `total · showing %` line.
- Group → bucket **tree**: ▶ opens a group (tree only); the group checkbox =
  one combined slice (ticked) vs split into buckets (unticked); a bucket checkbox
  includes/excludes that bucket either way. Percentages shown per row.
- **Pie** (Chart.js): stable per-group/bucket colors, on-slice `visible% (total%)`
  + dollar labels. Hover a slice for a tooltip with its name, `% of chart` and
  `% of total`; the matching tree row(s) highlight — a combined group highlights
  its whole category (group + buckets), "Other" highlights everything it absorbed.
- **"Other" pile** as a per-slice threshold: every category **≤ the set %** of the
  chart is merged into one "Other" slice. The **+** button absorbs the smallest
  visible category; **−** releases the largest hidden one. `0` = off. Otherized
  rows are greyed in the tree.
- **Date bar**: Start/End Y-M-D (start day = 01 auto-fills the month end),
  debounced auto-apply, presets (This/Last month, YTD, All time), ◀/▶ month nav,
  per-year buttons.
- **Per-year category state** + date range, tab, and Other threshold are autosaved
  to `localStorage` and restored on reload.

## Files

- `index.html`, `css/styles.css`
- `js/model.js` — metrics, date helpers, `buildGroups`, `scopeKey`
- `js/db.js` — sql.js load + `fetchBucketTotals`
- `js/colors.js` — stable color map
- `js/state.js` — localStorage, per-year scopes
- `js/pie.js` — `computeSlices` / `baseSlices` / Other-target math + `PieView`
- `js/tree.js` — `TreeView`
- `js/datebar.js` — `DateBar`
- `js/fileaccess.js` — File System Access API + IndexedDB handle
- `js/app.js` — orchestrator
- `vendor/` — sql.js (`sql-wasm.js` + `.wasm`), Chart.js
