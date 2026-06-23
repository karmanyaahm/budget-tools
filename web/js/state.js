// Persisted view state (localStorage). Category (tree) state is per-year scope.
import { NOGROUP } from "./model.js";

const KEY = "budgetPieView_v1";

function defaults() {
  return {
    range: null,            // [start, end] or null = all time
    tab: 0,
    otherPct: 0,            // "Other" target % of the pie (0 = off)
    includeTransfers: false,
    scopes: {},             // scopeKey -> { metrics: { mkey: {groups, buckets} } }
  };
}

export function loadState() {
  let s;
  try {
    s = JSON.parse(localStorage.getItem(KEY));
  } catch { s = null; }
  if (!s || typeof s !== "object") s = {};
  s = { ...defaults(), ...s };
  // migrate old global metrics -> scope "all"
  if (s.metrics && !Object.keys(s.scopes).length) {
    s.scopes = { all: { metrics: s.metrics } };
  }
  delete s.metrics;
  return s;
}

export function saveState(state) {
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
  } catch (e) {
    console.warn("could not save view state", e);
  }
}

// Get (creating if needed) the per-year scope object.
export function getScope(state, scopeKey) {
  if (!state.scopes) state.scopes = {};
  let sc = state.scopes[scopeKey];
  if (!sc) { sc = { metrics: {} }; state.scopes[scopeKey] = sc; }
  if (!sc.metrics) sc.metrics = {};
  return sc;
}

export function metricState(scope, mkey) {
  let m = scope.metrics[mkey];
  if (!m) { m = { groups: {}, buckets: {} }; scope.metrics[mkey] = m; }
  if (!m.groups) m.groups = {};
  if (!m.buckets) m.buckets = {};
  return m;
}

// combined: one slice (default true, except ungrouped). open: tree row visibility.
export function groupState(scope, mkey, g) {
  const m = metricState(scope, mkey);
  let gs = m.groups[g.key];
  if (!gs) gs = {};
  if (!("combined" in gs)) gs.combined = g.key !== NOGROUP;
  if (!("open" in gs)) gs.open = false;
  m.groups[g.key] = gs;
  return gs;
}

export function bucketEnabled(scope, mkey, id) {
  return metricState(scope, mkey).buckets[id] !== false;
}

export function setBucketEnabled(scope, mkey, id, value) {
  metricState(scope, mkey).buckets[id] = value;
}
