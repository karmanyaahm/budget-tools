// Pure data + date helpers (mirrors the Python model).

export const NOGROUP = "__nogroup__";
export const OTHER = "__other__";

// (key, short title, methodology blurb)
export const METRICS = [
  {
    key: "alloc_in",
    title: "Allocations · Net In",
    methodology:
      "Money budgeted into buckets from the balance rain, net of de-allocations. " +
      "Real bank transactions and bucket-to-bucket transfers are excluded.",
  },
  {
    key: "actual_in",
    title: "Actual Income · Net In",
    methodology:
      "Real income from bank transactions categorized into buckets (net positive " +
      "only). Allocations from the rain are excluded.",
  },
  {
    key: "activity",
    title: "Activity · Net Spending",
    methodology:
      "Spending from real bank transactions, net of reimbursements/refunds (net " +
      "negative only). Allocations are excluded. = Gross spend − Reimbursements.",
  },
  {
    key: "gross_spend",
    title: "Gross Spend",
    methodology:
      "All spending from real bank transactions before any reimbursement is " +
      "applied. = Activity + Reimbursements.",
  },
  {
    key: "reimbursement",
    title: "Reimbursements Received",
    methodology:
      "Inflows that offset spending (refunds, paybacks), capped per bucket at that " +
      "bucket's spending so genuine income is not miscounted as a reimbursement.",
  },
];

export function fmtMoney(cents) {
  return "$" + Math.round(cents / 100).toLocaleString("en-US");
}

// Category (tree) state is saved per-year. A single-year range -> that year;
// anything spanning multiple years (or all-time) -> "all".
export function scopeKey(range) {
  if (!range || (!range[0] && !range[1])) return "all";
  const [s, e] = range;
  const sy = s && s.slice(0, 4);
  const ey = e && e.slice(0, 4);
  if (sy && (sy === ey || !e)) return sy;
  return "all";
}

export function pad(n) {
  return String(n).padStart(2, "0");
}

export function lastDay(y, m) {
  return new Date(y, m, 0).getDate(); // m is 1-based here
}

function iso(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// Group bucket rows for one metric -> ordered groups, largest first.
// Each group: {key, name, total, buckets:[{id,name,val} ...]}
export function buildGroups(bucketRows, metric) {
  const groups = new Map();
  for (const r of bucketRows) {
    const val = r[metric];
    if (val <= 0) continue;
    let g = groups.get(r.group_key);
    if (!g) {
      g = { key: r.group_key, name: r.group_name, total: 0, buckets: [] };
      groups.set(r.group_key, g);
    }
    g.buckets.push({ id: r.bucket_id, name: r.bucket_name, val });
    g.total += val;
  }
  const out = [...groups.values()];
  for (const g of out) g.buckets.sort((a, b) => b.val - a.val);
  out.sort((a, b) => b.total - a.total);
  return out;
}

// ---- date presets (use the browser's local "today") ----
export function monthRange(offset = 0) {
  const t = new Date();
  let y = t.getFullYear();
  let m = t.getMonth() + 1 - offset;
  while (m <= 0) { m += 12; y -= 1; }
  return [`${y}-${pad(m)}-01`, `${y}-${pad(m)}-${pad(lastDay(y, m))}`];
}

export function ytd() {
  const t = new Date();
  return [`${t.getFullYear()}-01-01`, iso(t)];
}

export function yearRange(year) {
  const today = new Date();
  if (year === today.getFullYear()) return [`${year}-01-01`, iso(today)];
  return [`${year}-01-01`, `${year}-12-31`];
}

// Whole calendar month `delta` months from dateStr's month (today if null).
export function monthOf(dateStr, delta) {
  let y, m;
  if (dateStr) {
    [y, m] = dateStr.split("-").map(Number);
  } else {
    const t = new Date();
    y = t.getFullYear(); m = t.getMonth() + 1;
  }
  m += delta;
  while (m > 12) { m -= 12; y += 1; }
  while (m < 1) { m += 12; y -= 1; }
  return [`${y}-${pad(m)}-01`, `${y}-${pad(m)}-${pad(lastDay(y, m))}`];
}
