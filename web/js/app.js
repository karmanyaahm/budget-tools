// Orchestrator: load DB -> colors -> tabs -> date bar -> render tree + pie.
import { METRICS, NOGROUP, OTHER, buildGroups, fmtMoney, ytd, scopeKey } from "./model.js";
import { openDatabase, fetchBucketTotals, dataYearSpan } from "./db.js";
import { buildColorMap } from "./colors.js";
import { loadState, saveState, getScope, getOtherPct, setOtherPct } from "./state.js";
import { computeSlices, baseSlices, otherizedCount, targetForCount, PieView } from "./pie.js";
import { TreeView } from "./tree.js";
import { DateBar } from "./datebar.js";
import * as fa from "./fileaccess.js";

const $ = (id) => document.getElementById(id);

const state = loadState();
let db = null;
let colorMap = null;
let datebar = null;
let pie = null;
let tree = null;

let activeIdx = Math.min(state.tab || 0, METRICS.length - 1);
let currentRows = [];
let currentGroups = [];
let currentGrand = 1;
let spanText = "";
let currentScope = null;
let currentOtherized = new Set();

// ---------- data load ----------
async function useBytes(bytes, label) {
  db = await openDatabase(bytes);
  rebuildColors();
  const [lo, hi] = dataYearSpan(db);

  datebar = new DateBar($("dateBar"), {
    yearLo: lo, yearHi: hi,
    otherPct: getOtherPct(state, METRICS[activeIdx].key),
    includeTransfers: state.includeTransfers,
    onRange: (s, e) => { state.range = [s, e]; saveState(state); reload(s, e); },
    onOtherTarget: (v) => { setOtherPct(state, METRICS[activeIdx].key, v); saveState(state); recomputeChart(); },
    onOtherStep: (dir) => stepOther(dir),
    onTransfers: (b) => { state.includeTransfers = b; saveState(state); rebuildColors(); reload(...(state.range || ytd())); },
  });

  buildTabs();
  pie = new PieView($("pie"), colorMap);
  pie.onHover = onSliceHover;
  $("status").textContent = label ? `Loaded ${label}` : "Loaded";
  $("app").classList.remove("hidden");
  $("dropHint").classList.add("hidden");

  const range = state.range || ytd();
  datebar.setRange(range[0], range[1]); // fires onRange -> reload
}

function rebuildColors() {
  const allRows = fetchBucketTotals(db, { includeTransfers: state.includeTransfers });
  const keys = new Set(["group:" + NOGROUP]);
  for (const r of allRows) { keys.add("group:" + r.group_key); keys.add("bucket:" + r.bucket_id); }
  colorMap = buildColorMap(keys);
  if (pie) pie.colorMap = colorMap;
}

// ---------- tabs ----------
function buildTabs() {
  const tabs = $("tabs");
  tabs.innerHTML = "";
  METRICS.forEach((m, i) => {
    const b = document.createElement("button");
    b.className = "tab" + (i === activeIdx ? " active" : "");
    b.textContent = m.title.split("·")[0].trim();
    b.addEventListener("click", () => {
      activeIdx = i; state.tab = i; saveState(state);
      [...tabs.children].forEach((c, j) => c.classList.toggle("active", j === i));
      renderActive();
    });
    tabs.append(b);
  });
}

// ---------- reload (DB query for a date range) ----------
function reload(start, end) {
  if (!db) return;
  currentRows = fetchBucketTotals(db, { start, end, includeTransfers: state.includeTransfers });
  currentScope = getScope(state, scopeKey([start, end]));
  spanText = (start || end) ? `${start || "…"} → ${end || "…"}` : "all time";
  if (datebar) datebar.setStatus(spanText);
  renderActive();
}

// ---------- render the active tab ----------
function renderActive() {
  const metric = METRICS[activeIdx];
  currentGroups = buildGroups(currentRows, metric.key);
  currentGrand = currentGroups.reduce((a, g) => a + g.total, 0) || 1;

  $("chartTitle").textContent = metric.title;
  $("methodology").textContent = metric.methodology;
  if (datebar) datebar.setOther(getOtherPct(state, metric.key)); // reflect this tab's threshold

  tree = new TreeView($("tree"), {
    groups: currentGroups,
    scope: currentScope,
    metricKey: metric.key,
    colorMap,
    grandTotal: currentGrand,
    onChange: (opts) => {
      saveState(state);
      if (!opts || !opts.treeOnly) recomputeChart();
    },
  });
  recomputeChart();
}

function recomputeChart() {
  const metric = METRICS[activeIdx];
  const { slices, otherized, visible } = computeSlices(currentGroups, currentScope, metric.key, getOtherPct(state, metric.key));
  currentOtherized = otherized;
  pie.render(slices, currentGrand);
  if (tree) tree.applyGrey(otherized);
  const shown = currentGrand ? (visible / currentGrand) * 100 : 0;
  $("totals").textContent = slices.length
    ? `${spanText} · total ${fmtMoney(currentGrand)} · showing ${shown.toFixed(0)}% (${fmtMoney(visible)})`
    : `${spanText} · nothing selected`;
}

// Highlight the hovered pie slice in the tree. A combined-group slice
// highlights the whole category (group row + its bucket rows); "Other"
// highlights every row it absorbed.
function onSliceHover(colorKey) {
  if (!tree) return;
  if (!colorKey) { tree.highlight(new Set()); return; }
  const set = new Set([colorKey]);
  if (colorKey === OTHER) {
    for (const ck of currentOtherized) set.add(ck);
  } else if (colorKey.startsWith("group:")) {
    const key = colorKey.slice("group:".length);
    const g = currentGroups.find((x) => x.key === key);
    if (g) for (const b of g.buckets) set.add("bucket:" + b.id);
  }
  tree.highlight(set);
}

// Step the "Other" target by one category:
//  dir>0 -> absorb the smallest currently-visible category into Other
//  dir<0 -> release the largest currently-hidden category back to the pie
function stepOther(dir) {
  const metric = METRICS[activeIdx];
  const base = baseSlices(currentGroups, currentScope, metric.key);
  const total = base.reduce((a, s) => a + s.val, 0);
  if (!total) return;
  const sortedAsc = [...base].sort((a, b) => a.val - b.val);
  let k = otherizedCount(sortedAsc, total, getOtherPct(state, metric.key));
  let k2 = k + (dir > 0 ? 1 : -1);
  if (k2 === 1) k2 = dir > 0 ? 2 : 0; // Other needs >=2 members to exist
  k2 = Math.max(0, Math.min(sortedAsc.length, k2));
  const target = k2 >= 2 ? targetForCount(sortedAsc, total, k2) : 0;
  setOtherPct(state, metric.key, target);
  saveState(state);
  datebar.setOther(target);
  recomputeChart();
}

// ---------- file controls ----------
async function handleFileInput(e) {
  const f = e.target.files[0];
  if (!f) return;
  const bytes = new Uint8Array(await f.arrayBuffer());
  await useBytes(bytes, f.name);
}

async function handlePick() {
  try {
    const h = await fa.pickFile();
    await fa.saveHandle(h);
    const { bytes, name } = await fa.readHandle(h);
    window._dbHandle = h;
    await useBytes(bytes, name);
  } catch (e) { if (e.name !== "AbortError") console.warn(e); }
}

async function tryReconnect() {
  const h = await fa.loadHandle();
  if (!h) return;
  const btn = $("reconnectBtn");
  btn.classList.remove("hidden");
  btn.textContent = `Reconnect ${h.name || "last file"}`;
  btn.onclick = async () => {
    if (await fa.ensurePermission(h, true)) {
      const { bytes, name } = await fa.readHandle(h);
      window._dbHandle = h;
      await useBytes(bytes, name);
      btn.classList.add("hidden");
    }
  };
}

// reload button (re-read current FS handle)
async function refreshData() {
  const h = window._dbHandle;
  if (!h) { $("status").textContent = "No persistent file; re-upload to refresh."; return; }
  if (await fa.ensurePermission(h, true)) {
    const { bytes } = await fa.readHandle(h);
    db = await openDatabase(bytes);
    rebuildColors();
    reload(...(state.range || ytd()));
  }
}

// All / Split buttons (operate on the live tree)
function wireTreeButtons() {
  $("combineAll").addEventListener("click", () => tree && tree.setAll(true));
  $("splitAll").addEventListener("click", () => tree && tree.setAll(false));
}

// Try the server-provided default file (web/default.buckets via `make FILE=...`).
async function tryAutoload() {
  try {
    const res = await fetch("default.buckets", { cache: "no-store" });
    if (!res.ok) return false;
    const bytes = new Uint8Array(await res.arrayBuffer());
    if (bytes.length < 16) return false;
    await useBytes(bytes, "default.buckets");
    return true;
  } catch { return false; }
}

function init() {
  $("fileInput").addEventListener("change", handleFileInput);
  tryAutoload();
  if (fa.supportsFS()) {
    $("pickBtn").classList.remove("hidden");
    $("pickBtn").addEventListener("click", handlePick);
    $("refreshBtn").addEventListener("click", refreshData);
    tryReconnect();
  }
  wireTreeButtons();
}

init();
