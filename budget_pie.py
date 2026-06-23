#!/usr/bin/env python3
"""
Interactive pie-chart explorer for a Buckets app database (*.buckets, SQLite).

Two distinct money flows in Buckets are kept separate:

  * ALLOCATIONS ("balance rain") -- you budgeting money into buckets.
        rows with account_trans_id IS NULL (and transfer = 0)
  * ACTUAL transactions          -- real bank activity categorized into buckets.
        rows with account_trans_id IS NOT NULL

Three tabs, each a NET per group/bucket:

  * "Allocations (rain) — Net In" -> net of allocation rows (in - de-allocated)
  * "Actual transactions — Net In"-> actual-transaction net, POSITIVE part
  * "Activity"                    -> actual-transaction net, NEGATIVE part, i.e.
                                     spending NET of reimbursements.

Each tab shows a TREE of bucket groups -> buckets, with three controls per group:
  * ▶/▼ arrow  -- opens the group in the tree to reveal its bucket rows. This is
                  tree-only; it does NOT change the chart.
  * group ☑    -- TICKED = the group is ONE combined slice; UNTICKED = the group
                  is split into one slice per bucket.
  * bucket ☑   -- include/exclude an individual bucket. Applies either way: an
                  excluded bucket is dropped from the combined slice's total and
                  omitted when split. Unticking every bucket hides the group.
  * Ungrouped buckets live under "(No group)" (split by default).
  * Percentage labels are always each slice's share of the metric's ORIGINAL
    total, so combining/splitting never inflates the others.
  * Every group and bucket keeps a fixed color across toggles, tabs and dates.

Date bar: Start/End Year-Month-Day dropdowns (set start day = 01 to auto-fill the
end with that month's last day) plus presets This month / Last month / YTD /
All time and one button per year (current year = YTD). Defaults to YTD.

The whole view (date range, which groups are ticked/expanded, selected tab) is
AUTOSAVED to budget_pie_view.json and restored on next launch.

Usage:
  python3 budget_pie.py [--db "My Budget.buckets"] [--include-transfers]
"""
import argparse
import calendar
import json
import sqlite3
import sys
import textwrap
import tkinter as tk
from tkinter import ttk
from datetime import date
from pathlib import Path

import colorsys

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.colors as mcolors
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

NOGROUP = "__nogroup__"
# (key, short title, methodology blurb shown under the title)
METRICS = [
    ("alloc_in", "Allocations · Net In",
     "Money budgeted into buckets from the balance rain, net of de-allocations. "
     "Real bank transactions and bucket-to-bucket transfers are excluded."),
    ("actual_in", "Actual Income · Net In",
     "Real income from bank transactions categorized into buckets (net positive "
     "only). Allocations from the rain are excluded."),
    ("activity", "Activity · Net Spending",
     "Spending from real bank transactions, net of reimbursements/refunds "
     "(net negative only). Allocations are excluded. = Gross spend − Reimbursements."),
    ("gross_spend", "Gross Spend",
     "All spending from real bank transactions before any reimbursement is "
     "applied. = Activity + Reimbursements."),
    ("reimbursement", "Reimbursements Received",
     "Inflows that offset spending (refunds, paybacks), capped per bucket at that "
     "bucket's spending so genuine income is not miscounted as a reimbursement."),
]
STATE_FILE = "budget_pie_view.json"


def build_color_map(keys):
    """Assign each key (group/bucket) a stable, vibrant, well-separated color.

    Hues are stepped by the golden ratio so even 80+ keys stay distinct, with a
    small saturation/value cycle to push neighbouring colors further apart.
    """
    golden = 0.6180339887498949
    sv_cycle = [(0.72, 0.93), (0.88, 0.78), (0.58, 0.99), (0.95, 0.66)]
    out = {}
    for i, k in enumerate(sorted(keys)):
        h = (i * golden) % 1.0
        s, v = sv_cycle[i % len(sv_cycle)]
        out[k] = colorsys.hsv_to_rgb(h, s, v)
    return out


def fetch_bucket_totals(db_path, start=None, end=None, include_transfers=False):
    """Return one dict per bucket with its group + the three metrics (cents)."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    where, params = [], []
    # posted is "2024-07-01 07:00:00-05:00"; lexicographic prefix compare works.
    if start:
        where.append("bt.posted >= ?"); params.append(start)
    if end:
        where.append("bt.posted < ?"); params.append(end + " 99")  # whole end day
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    alloc_cond = "bt.account_trans_id IS NULL"
    if not include_transfers:
        alloc_cond += " AND COALESCE(bt.transfer, 0) = 0"

    sql = f"""
        SELECT b.id, b.name, g.id, g.name,
               SUM(CASE WHEN {alloc_cond} THEN bt.amount ELSE 0 END) AS net_alloc,
               SUM(CASE WHEN bt.account_trans_id IS NOT NULL AND bt.amount > 0
                        THEN bt.amount ELSE 0 END)                   AS actual_pos,
               SUM(CASE WHEN bt.account_trans_id IS NOT NULL AND bt.amount < 0
                        THEN -bt.amount ELSE 0 END)                  AS actual_neg
        FROM bucket_transaction bt
        JOIN bucket b            ON b.id = bt.bucket_id
        LEFT JOIN bucket_group g ON g.id = b.group_id
        {where_sql}
        GROUP BY b.id
    """
    rows = con.execute(sql, params).fetchall()
    con.close()

    out = []
    for bid, bname, gid, gname, net_alloc, actual_pos, actual_neg in rows:
        net_alloc = net_alloc or 0
        actual_pos = actual_pos or 0   # gross actual inflow (income + refunds)
        actual_neg = actual_neg or 0   # gross actual outflow (spending)
        net_actual = actual_pos - actual_neg
        out.append({
            "bucket_id": bid,
            "bucket_name": bname or "(unnamed)",
            "group_key": gid if gid else NOGROUP,
            "group_name": gname if gid else "(No group)",
            "alloc_in": max(net_alloc, 0),
            "actual_in": max(net_actual, 0),           # net income
            "activity": max(-net_actual, 0),           # net spend (after refunds)
            "gross_spend": actual_neg,                 # spend before refunds
            "reimbursement": min(actual_pos, actual_neg),  # inflow offsetting spend
        })
    return out


def build_groups(bucket_rows, metric):
    """Group bucket rows for one metric -> ordered list of group dicts.

    Each group: {key, name, total, buckets:[{id,name,val} ...]} largest first.
    Only positive values (and non-empty groups) are kept.
    """
    groups = {}
    for r in bucket_rows:
        val = r[metric]
        if val <= 0:
            continue
        g = groups.setdefault(r["group_key"],
                              {"key": r["group_key"], "name": r["group_name"],
                               "total": 0, "buckets": []})
        g["buckets"].append({"id": r["bucket_id"], "name": r["bucket_name"], "val": val})
        g["total"] += val
    for g in groups.values():
        g["buckets"].sort(key=lambda b: b["val"], reverse=True)
    return sorted(groups.values(), key=lambda g: g["total"], reverse=True)


def month_range(offset=0):
    """(start, end) for the month `offset` months back (0 = current)."""
    today = date.today()
    y, m = today.year, today.month - offset
    while m <= 0:
        m += 12
        y -= 1
    last_day = calendar.monthrange(y, m)[1]
    return f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-{last_day:02d}"


def data_year_span(db_path):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    row = con.execute("SELECT MIN(substr(posted,1,4)), MAX(substr(posted,1,4)) "
                      "FROM bucket_transaction").fetchone()
    con.close()
    today = date.today().year
    lo = int(row[0]) if row and row[0] else today
    hi = int(row[1]) if row and row[1] else today
    return lo, max(hi, today)


class ScrollFrame(ttk.Frame):
    """A vertically scrollable frame; put content in `self.inner`."""

    def __init__(self, master, width=460):
        super().__init__(master)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0, width=width)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfig(self._win, width=e.width))
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.bind_all(seq, self._wheel)

    def _wheel(self, e):
        delta = -1 if getattr(e, "num", None) == 4 or e.delta > 0 else 1
        self.canvas.yview_scroll(delta, "units")


class PieTab:
    """One tab: a pie chart + a group/bucket tree with breakdown toggles."""

    def __init__(self, notebook, key, title, methodology, span, groups, color_map,
                 state, on_change, other_pct=0):
        self.key = key
        self.title = title
        self.methodology = methodology
        self.span = span
        self.groups = groups
        self.color_map = color_map
        self.state = state            # {"groups": {...}, "buckets": {...}}
        self.on_change = on_change
        self.other_pct = other_pct    # pile slices <= this % of the visible pie
        self.grand_total = sum(g["total"] for g in groups) or 1
        self.gvars = []
        self._wedge_info = []
        self.annot = None

        frame = ttk.Frame(notebook)
        notebook.add(frame, text=title.split("·")[0].strip()[:22] or title)

        self.fig = Figure(figsize=(7.4, 6.6), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.fig.subplots_adjust(top=0.80, bottom=0.02, left=0.02, right=0.70)
        # Bold metric heading (persists across ax.clear()); methodology + totals
        # go in the per-redraw axes title below it.
        self.fig.suptitle(title, fontsize=14, fontweight="bold", y=0.97)
        canvas = FigureCanvasTkAgg(self.fig, master=frame)
        canvas.get_tk_widget().pack(side="left", fill="both", expand=True)
        canvas.mpl_connect("motion_notify_event", self._on_hover)
        self.canvas = canvas

        side = ttk.Frame(frame)
        side.pack(side="right", fill="y", padx=4, pady=4)
        head = ttk.Frame(side)
        head.pack(anchor="w")
        ttk.Button(head, text="Combine all", width=11,
                   command=lambda: self._set_all(True)).pack(side="left")
        ttk.Button(head, text="Split all", width=11,
                   command=lambda: self._set_all(False)).pack(side="left")
        ttk.Label(side, text="▶ open a group · ☑ = one slice (untick to split)\n"
                             "untick a bucket to exclude it either way",
                  font=("", 8), justify="left").pack(anchor="w")

        sf = ScrollFrame(side)
        sf.pack(fill="both", expand=True)
        self._build_tree(sf.inner)
        self.redraw()

    # ---- state helpers ----
    def _gstate(self, g):
        # "combined": True  -> the group is a single slice (checkbox ticked)
        #             False -> the group is split into its bucket slices.
        # "open":     whether the tree shows this group's bucket rows.
        # Ungrouped buckets start split. Migrate/repair any older entry.
        gs = self.state["groups"].get(g["key"], {})
        if "combined" not in gs:
            gs["combined"] = g["key"] != NOGROUP
        gs.setdefault("open", False)
        self.state["groups"][g["key"]] = gs
        return gs

    def _benabled(self, bid):
        return self.state["buckets"].get(bid, True)

    def _hex(self, colorkey):
        return mcolors.to_hex(self.color_map.get(colorkey, (0.6, 0.6, 0.6)))

    # ---- tree ----
    def _build_tree(self, parent):
        self._childframes = {}
        self._row_labels = {}   # colorkey -> name label widget (for grey-out)
        for g in self.groups:
            gs = self._gstate(g)
            gframe = ttk.Frame(parent)
            gframe.pack(fill="x", anchor="w")

            row = ttk.Frame(gframe)
            row.pack(fill="x", anchor="w")
            child = ttk.Frame(gframe)

            # Arrow opens the tree (reveals bucket rows); it does NOT change the pie.
            arrow = ttk.Button(row, width=2, text="▼" if gs["open"] else "▶")
            arrow.configure(command=lambda gg=g, b=arrow, c=child: self._toggle_open(gg, b, c))
            arrow.pack(side="left")

            # Group checkbox: ticked = one combined slice, unticked = split.
            gvar = tk.BooleanVar(value=gs["combined"])
            self.gvars.append((g, gvar))
            ttk.Checkbutton(row, variable=gvar,
                            command=lambda gg=g, v=gvar: self._toggle_combined(gg, v)
                            ).pack(side="left")
            tk.Label(row, text="  ", bg=self._hex("group:" + g["key"])).pack(side="left")
            gpct = g["total"] / self.grand_total * 100
            glbl = ttk.Label(row, text=f"{g['name']}  ${g['total']/100:,.0f}  ·  {gpct:.0f}%")
            glbl.pack(side="left")
            self._row_labels["group:" + g["key"]] = glbl

            for b in g["buckets"]:
                brow = ttk.Frame(child)
                brow.pack(fill="x", anchor="w")
                bvar = tk.BooleanVar(value=self._benabled(b["id"]))
                ttk.Checkbutton(brow, variable=bvar,
                                command=lambda bb=b, v=bvar: self._toggle_bucket(bb, v)
                                ).pack(side="left", padx=(28, 0))
                tk.Label(brow, text="  ", bg=self._hex("bucket:" + b["id"])).pack(side="left")
                bpct = b["val"] / self.grand_total * 100
                blbl = ttk.Label(brow, text=f"{b['name']}  ${b['val']/100:,.0f}  ·  {bpct:.0f}%")
                blbl.pack(side="left")
                self._row_labels["bucket:" + b["id"]] = blbl

            if gs["open"]:
                child.pack(fill="x", anchor="w")
            self._childframes[g["key"]] = child

    def _toggle_open(self, g, btn, child):
        gs = self._gstate(g)
        gs["open"] = not gs["open"]
        btn.configure(text="▼" if gs["open"] else "▶")
        child.pack(fill="x", anchor="w") if gs["open"] else child.pack_forget()
        self.on_change()  # remember tree state; pie is unaffected

    def _toggle_combined(self, g, var):
        self._gstate(g)["combined"] = var.get()
        self.on_change()
        self.redraw()

    def _toggle_bucket(self, b, var):
        self.state["buckets"][b["id"]] = var.get()
        self.on_change()
        self.redraw()

    def _set_all(self, combined):
        for g, var in self.gvars:
            var.set(combined)
            self._gstate(g)["combined"] = combined
        self.on_change()
        self.redraw()

    # ---- chart ----
    def redraw(self):
        self.ax.clear()
        slices = []  # (label, cents, colorkey)
        for g in self.groups:
            gs = self._gstate(g)
            enabled = [b for b in g["buckets"] if self._benabled(b["id"])]
            if not enabled:
                continue  # whole group excluded (all its buckets unticked)
            if gs["combined"]:
                total = sum(b["val"] for b in enabled)
                slices.append((g["name"], total, "group:" + g["key"]))
            else:
                for b in enabled:
                    slices.append((b["name"], b["val"], "bucket:" + b["id"]))

        grand = self.grand_total
        method = textwrap.fill(self.methodology, 78)

        if not slices:
            self.ax.set_title(f"{method}\n\n{self.span}  ·  nothing selected",
                              fontsize=8.5, color="#333")
            self.ax.axis("off")
            self._wedge_info = []
            self.annot = None
            self._apply_grey(set())
            self.canvas.draw_idle()
            return

        # Pile slices that are <= other_pct of the CURRENT (visible) pie into one
        # "Other" slice. 0 disables it. Only pile when it merges 2+ slices.
        visible_sum = sum(s[1] for s in slices)
        otherized = set()
        if self.other_pct and visible_sum > 0:
            thresh = self.other_pct / 100.0 * visible_sum
            small = [s for s in slices if s[1] <= thresh]
            if len(small) >= 2:
                big = [s for s in slices if s[1] > thresh]
                other_val = sum(s[1] for s in small)
                big.append((f"Other ({len(small)})", other_val, "__other__"))
                slices = big
                otherized = {s[2] for s in small}
        self._apply_grey(otherized)

        labels = [s[0] for s in slices]
        values = [s[1] for s in slices]
        colors = [self.color_map.get(s[2], (0.6, 0.6, 0.6)) for s in slices]
        visible_sum = sum(values)

        def autopct(pct):
            cents = pct / 100.0 * visible_sum
            tot = cents / grand * 100              # share of the whole metric
            shown_share = f"{pct:.0f}%"            # share of the visible pie
            of_all = "" if abs(pct - tot) < 0.5 else f"  ({tot:.0f}% of all)"
            return f"{shown_share}{of_all}\n${cents/100:,.0f}"

        wedges, _t, _a = self.ax.pie(
            values, autopct=autopct, pctdistance=0.74, colors=colors,
            startangle=90, counterclock=False, textprops={"fontsize": 7.5},
        )
        shown = visible_sum / grand * 100
        self.ax.set_title(
            f"{method}\n\n"
            f"{self.span}  ·  total ${grand/100:,.0f}  ·  "
            f"showing {shown:.0f}%  (${visible_sum/100:,.0f})",
            fontsize=8.5, color="#333",
        )
        self.ax.legend(
            wedges,
            [f"{l}  ${v/100:,.0f}  ·  {v/grand*100:.0f}%"
             for l, v in zip(labels, values)],
            loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=8,
        )
        self.ax.axis("equal")

        # Hover support: remember each wedge so _on_hover can name it.
        self._wedge_info = list(zip(wedges, labels, values))
        self.annot = self.ax.annotate(
            "", xy=(0, 0), xytext=(14, 14), textcoords="offset points",
            bbox=dict(boxstyle="round", fc="#ffffe0", ec="0.4", alpha=0.97),
            fontsize=9, zorder=20, visible=False,
        )
        self.canvas.draw_idle()

    def _apply_grey(self, otherized):
        """Grey out tree rows whose slice was merged into the 'Other' pile."""
        for ck, lbl in getattr(self, "_row_labels", {}).items():
            lbl.configure(foreground="#a0a0a0" if ck in otherized else "black")

    def _on_hover(self, event):
        if not self.annot or event.inaxes is not self.ax:
            if self.annot is not None and self.annot.get_visible():
                self.annot.set_visible(False)
                self.canvas.draw_idle()
            return
        for wedge, label, cents in self._wedge_info:
            if wedge.contains_point((event.x, event.y)):
                tot = cents / self.grand_total * 100
                self.annot.xy = (event.xdata, event.ydata)
                self.annot.set_text(f"{label}\n${cents/100:,.0f}  ·  {tot:.1f}% of all")
                self.annot.set_visible(True)
                self.canvas.draw_idle()
                return
        if self.annot.get_visible():
            self.annot.set_visible(False)
            self.canvas.draw_idle()


class App:
    def __init__(self, root, db_path, include_transfers, state_path):
        self.root = root
        self.db_path = db_path
        self.include_transfers = include_transfers
        self.state_path = Path(state_path)
        self.year_lo, self.year_hi = data_year_span(db_path)
        self._loading = True
        self._apply_job = None
        self.tabs = []

        self.state = self._load_state()
        self.other_pct = float(self.state.get("other_pct", 3.0))

        # Stable colors from the all-time set of group + bucket keys.
        all_rows = fetch_bucket_totals(db_path, None, None, include_transfers)
        keys = {"group:" + r["group_key"] for r in all_rows}
        keys |= {"bucket:" + r["bucket_id"] for r in all_rows}
        keys.add("group:" + NOGROUP)
        self.color_map = build_color_map(keys)

        self._build_controls()
        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True)
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        rng = self.state.get("range")
        start, end = (rng[0], rng[1]) if rng else self._ytd()
        self._loading = False
        self.set_range(start, end)

    # ---- persistence ----
    def _load_state(self):
        try:
            return json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            return {"range": None, "tab": 0, "metrics": {}}

    def save_state(self):
        if self._loading:
            return
        try:
            self.state_path.write_text(json.dumps(self.state, indent=2))
        except OSError as e:
            print(f"[warn] could not save view: {e}")

    # ---- date helpers ----
    @staticmethod
    def _ytd():
        t = date.today()
        return f"{t.year}-01-01", t.isoformat()

    def _year_range(self, year):
        today = date.today()
        if year == today.year:
            return f"{year}-01-01", today.isoformat()
        return f"{year}-01-01", f"{year}-12-31"

    @staticmethod
    def _month_of(datestr, delta):
        """Whole calendar month `delta` months from datestr's month (today if None)."""
        if datestr:
            y, m, _ = (int(x) for x in datestr.split("-"))
        else:
            t = date.today()
            y, m = t.year, t.month
        m += delta
        while m > 12:
            m -= 12; y += 1
        while m < 1:
            m += 12; y -= 1
        last = calendar.monthrange(y, m)[1]
        return f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-{last:02d}"

    def _shift_month(self, delta):
        rng = self.state.get("range") or [None, None]
        self.set_range(*self._month_of(rng[0], delta))

    def _on_other_change(self, _e=None):
        try:
            pct = max(0.0, min(100.0, float(self.other_var.get())))
        except ValueError:
            return
        self.other_pct = pct
        self.other_var.set(f"{pct:g}")
        self.state["other_pct"] = pct
        self.save_state()
        for tab in self.tabs:          # re-render in place; no DB reload needed
            tab.other_pct = pct
            tab.redraw()

    # ---- controls ----
    def _build_controls(self):
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=6, pady=4)
        years = [str(y) for y in range(self.year_lo, self.year_hi + 1)]
        months = [f"{m:02d}" for m in range(1, 13)]
        days = [f"{d:02d}" for d in range(1, 32)]

        ttk.Label(bar, text="Start").pack(side="left")
        self.s_y = ttk.Combobox(bar, values=years, width=5, state="readonly")
        self.s_m = ttk.Combobox(bar, values=months, width=3, state="readonly")
        self.s_d = ttk.Combobox(bar, values=days, width=3, state="readonly")
        for w in (self.s_y, self.s_m, self.s_d):
            w.pack(side="left", padx=1)
        ttk.Label(bar, text=" End").pack(side="left")
        self.e_y = ttk.Combobox(bar, values=years, width=5, state="readonly")
        self.e_m = ttk.Combobox(bar, values=months, width=3, state="readonly")
        self.e_d = ttk.Combobox(bar, values=days, width=3, state="readonly")
        for w in (self.e_y, self.e_m, self.e_d):
            w.pack(side="left", padx=1)

        for w in (self.s_y, self.s_m, self.s_d):
            w.bind("<<ComboboxSelected>>", self._on_start_change)
        for w in (self.e_y, self.e_m, self.e_d):
            w.bind("<<ComboboxSelected>>", self._on_end_change)

        ttk.Button(bar, text="Apply", command=self._apply).pack(side="left", padx=(8, 2))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(bar, text="◀ Mo", width=5,
                   command=lambda: self._shift_month(-1)).pack(side="left", padx=1)
        ttk.Button(bar, text="Mo ▶", width=5,
                   command=lambda: self._shift_month(1)).pack(side="left", padx=1)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(bar, text="This month",
                   command=lambda: self.set_range(*month_range(0))).pack(side="left", padx=1)
        ttk.Button(bar, text="Last month",
                   command=lambda: self.set_range(*month_range(1))).pack(side="left", padx=1)
        ttk.Button(bar, text="YTD",
                   command=lambda: self.set_range(*self._ytd())).pack(side="left", padx=1)
        ttk.Button(bar, text="All time",
                   command=lambda: self.set_range(None, None)).pack(side="left", padx=1)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
        for y in range(self.year_hi, self.year_lo - 1, -1):
            ttk.Button(bar, text=str(y), width=5,
                       command=lambda yy=y: self.set_range(*self._year_range(yy))
                       ).pack(side="left", padx=1)

        # Right-packed widgets stack right-to-left, so pack in reverse visual order.
        self.status = ttk.Label(bar, text="")
        self.status.pack(side="right", padx=(8, 0))
        ttk.Label(bar, text="%  (0=off)").pack(side="right")
        # "Other" pile threshold (% of the current pie; 0 = off).
        self.other_var = tk.StringVar(value=f"{self.other_pct:g}")
        sp = ttk.Spinbox(bar, from_=0, to=100, increment=0.5, width=4,
                         textvariable=self.other_var, command=self._on_other_change)
        sp.pack(side="right")
        sp.bind("<Return>", self._on_other_change)
        sp.bind("<FocusOut>", self._on_other_change)
        ttk.Label(bar, text="Other ≤").pack(side="right", padx=(6, 1))

    def _clamp_days(self, yw, mw, dw):
        try:
            y, m = int(yw.get()), int(mw.get())
        except ValueError:
            return
        n = calendar.monthrange(y, m)[1]
        dw["values"] = [f"{d:02d}" for d in range(1, n + 1)]
        if dw.get() and int(dw.get()) > n:
            dw.set(f"{n:02d}")

    def _on_start_change(self, _e=None):
        self._clamp_days(self.s_y, self.s_m, self.s_d)
        try:
            y, m, d = int(self.s_y.get()), int(self.s_m.get()), int(self.s_d.get())
        except ValueError:
            self._schedule_apply()
            return
        if d == 1:  # snap end to last day of the start month
            last = calendar.monthrange(y, m)[1]
            self.e_y.set(f"{y}"); self.e_m.set(f"{m:02d}")
            self._clamp_days(self.e_y, self.e_m, self.e_d)
            self.e_d.set(f"{last:02d}")
        self._schedule_apply()

    def _on_end_change(self, _e=None):
        self._clamp_days(self.e_y, self.e_m, self.e_d)
        self._schedule_apply()

    def _schedule_apply(self):
        """Debounce: reload once the user stops changing the date dropdowns."""
        if self._apply_job:
            self.root.after_cancel(self._apply_job)
        self._apply_job = self.root.after(350, self._apply)

    def _read(self, yw, mw, dw):
        try:
            return f"{int(yw.get()):04d}-{int(mw.get()):02d}-{int(dw.get()):02d}"
        except ValueError:
            return None

    def _set_combos(self, yw, mw, dw, datestr):
        if not datestr:
            yw.set(""); mw.set(""); dw.set("")
            return
        y, m, d = datestr.split("-")
        yw.set(str(int(y))); mw.set(m)
        self._clamp_days(yw, mw, dw); dw.set(d)

    def _apply(self):
        self._apply_job = None
        self.set_range(self._read(self.s_y, self.s_m, self.s_d),
                       self._read(self.e_y, self.e_m, self.e_d))

    def set_range(self, start, end):
        self._set_combos(self.s_y, self.s_m, self.s_d, start)
        self._set_combos(self.e_y, self.e_m, self.e_d, end)
        self.state["range"] = [start, end]
        self.save_state()
        self.reload(start, end)

    def _on_tab_changed(self, _e=None):
        if self._loading:
            return
        try:
            self.state["tab"] = self.nb.index("current")
        except tk.TclError:
            return
        self.save_state()

    # ---- (re)build tabs ----
    def reload(self, start, end):
        self._loading = True
        for child in self.nb.winfo_children():
            child.destroy()
        self.tabs = []
        rows = fetch_bucket_totals(self.db_path, start, end, self.include_transfers)
        span = f"{start} → {end}" if (start or end) else "all time"
        metrics_state = self.state.setdefault("metrics", {})
        for key, title, methodology in METRICS:
            mstate = metrics_state.setdefault(key, {"groups": {}, "buckets": {}})
            mstate.setdefault("groups", {})
            mstate.setdefault("buckets", {})
            groups = build_groups(rows, key)
            self.tabs.append(PieTab(self.nb, key, title, methodology, span, groups,
                                    self.color_map, mstate, self.save_state,
                                    other_pct=self.other_pct))
        tab = self.state.get("tab", 0)
        if 0 <= tab < len(METRICS):
            self.nb.select(tab)
        self.status.config(text=span)
        self._loading = False


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default="My Budget.buckets")
    p.add_argument("--include-transfers", action="store_true",
                   help="count bucket<->bucket transfers (default: excluded)")
    p.add_argument("--state-file", default=STATE_FILE,
                   help=f"where to autosave the view (default: {STATE_FILE})")
    args = p.parse_args(argv)

    if not Path(args.db).exists():
        sys.exit(f"DB not found: {args.db}")

    root = tk.Tk()
    root.title("Budget pies")
    root.geometry("1600x850")
    App(root, args.db, args.include_transfers, args.state_file)
    root.mainloop()


if __name__ == "__main__":
    main()
