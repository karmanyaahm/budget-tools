// SQLite access via sql.js (WASM). Mirrors Python fetch_bucket_totals.
import { NOGROUP } from "./model.js";

let sqlPromise = null;

export function loadSqlEngine() {
  if (!sqlPromise) {
    // window.initSqlJs is provided by vendor/sql-wasm.js
    sqlPromise = window.initSqlJs({ locateFile: (f) => `vendor/${f}` });
  }
  return sqlPromise;
}

export async function openDatabase(bytes) {
  const SQL = await loadSqlEngine();
  return new SQL.Database(bytes);
}

export function dataYearSpan(db) {
  const stmt = db.prepare(
    "SELECT MIN(substr(posted,1,4)) AS lo, MAX(substr(posted,1,4)) AS hi " +
    "FROM bucket_transaction"
  );
  stmt.step();
  const row = stmt.getAsObject();
  stmt.free();
  const today = new Date().getFullYear();
  const lo = row.lo ? parseInt(row.lo, 10) : today;
  const hi = row.hi ? parseInt(row.hi, 10) : today;
  return [lo, Math.max(hi, today)];
}

// For the "Quiet Days" tab:
//  - perBucketSpend: Map<bucket_id, Set<day>> of outflow days (non-transfer),
//    so the category tree can choose which buckets count as "spend".
//  - activity: Set<day> with ANY account transaction (in or out).
//  - dataMin / dataMax: the full data window.
export function fetchQuietData(db, { start, end } = {}) {
  const bf = [], bp = {};
  if (start) { bf.push("substr(bt.posted,1,10) >= $start"); bp.$start = start; }
  if (end) { bf.push("substr(bt.posted,1,10) <= $end"); bp.$end = end; }
  const band = bf.length ? " AND " + bf.join(" AND ") : "";

  const perBucketSpend = new Map();
  let st = db.prepare(
    "SELECT bt.bucket_id bid, substr(bt.posted,1,10) d " +
    "FROM bucket_transaction bt JOIN account_transaction at ON at.id = bt.account_trans_id " +
    "WHERE bt.amount < 0 AND COALESCE(at.general_cat,'') != 'transfer'" + band +
    " GROUP BY bid, d"
  );
  st.bind(bp);
  while (st.step()) {
    const r = st.getAsObject();
    let s = perBucketSpend.get(r.bid);
    if (!s) { s = new Set(); perBucketSpend.set(r.bid, s); }
    s.add(r.d);
  }
  st.free();

  const af = [], ap = {};
  if (start) { af.push("substr(posted,1,10) >= $start"); ap.$start = start; }
  if (end) { af.push("substr(posted,1,10) <= $end"); ap.$end = end; }
  const awhere = af.length ? " WHERE " + af.join(" AND ") : "";
  const activity = new Set();
  st = db.prepare("SELECT DISTINCT substr(posted,1,10) d FROM account_transaction" + awhere);
  st.bind(ap);
  while (st.step()) activity.add(st.getAsObject().d);
  st.free();

  const r = db.prepare(
    "SELECT MIN(substr(posted,1,10)) mn, MAX(substr(posted,1,10)) mx FROM account_transaction"
  );
  r.step();
  const { mn, mx } = r.getAsObject();
  r.free();
  return { perBucketSpend, activity, dataMin: mn, dataMax: mx };
}

// Returns one object per bucket with its group + the five metrics (cents).
export function fetchBucketTotals(db, { start, end, includeTransfers } = {}) {
  const where = [];
  const params = {};
  // posted is "2024-07-01 07:00:00-05:00"; lexicographic prefix compare works.
  if (start) { where.push("bt.posted >= $start"); params.$start = start; }
  if (end) { where.push("bt.posted < $end"); params.$end = end + " 99"; }
  const whereSql = where.length ? "WHERE " + where.join(" AND ") : "";

  let allocCond = "bt.account_trans_id IS NULL";
  if (!includeTransfers) allocCond += " AND COALESCE(bt.transfer, 0) = 0";

  const sql = `
    SELECT b.id AS bid, b.name AS bname, g.id AS gid, g.name AS gname,
           SUM(CASE WHEN ${allocCond} THEN bt.amount ELSE 0 END) AS net_alloc,
           SUM(CASE WHEN bt.account_trans_id IS NOT NULL AND bt.amount > 0
                    THEN bt.amount ELSE 0 END) AS actual_pos,
           SUM(CASE WHEN bt.account_trans_id IS NOT NULL AND bt.amount < 0
                    THEN -bt.amount ELSE 0 END) AS actual_neg
    FROM bucket_transaction bt
    JOIN bucket b            ON b.id = bt.bucket_id
    LEFT JOIN bucket_group g ON g.id = b.group_id
    ${whereSql}
    GROUP BY b.id`;

  const stmt = db.prepare(sql);
  stmt.bind(params);
  const out = [];
  while (stmt.step()) {
    const r = stmt.getAsObject();
    const netAlloc = r.net_alloc || 0;
    const actualPos = r.actual_pos || 0; // gross inflow (income + refunds)
    const actualNeg = r.actual_neg || 0; // gross outflow (spending)
    const netActual = actualPos - actualNeg;
    out.push({
      bucket_id: r.bid,
      bucket_name: r.bname || "(unnamed)",
      group_key: r.gid ? r.gid : NOGROUP,
      group_name: r.gid ? r.gname : "(No group)",
      alloc_in: Math.max(netAlloc, 0),
      actual_in: Math.max(netActual, 0),
      activity: Math.max(-netActual, 0),
      gross_spend: actualNeg,
      reimbursement: Math.min(actualPos, actualNeg),
    });
  }
  stmt.free();
  return out;
}
