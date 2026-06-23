// "Quiet Days" view: contiguous periods with no spending / no activity.
import { computeGaps } from "./model.js";

function fmtRun(r) {
  if (r.days === 1) return r.start;
  // shorten the end if same year/month
  const [sy, sm] = r.start.split("-");
  const [ey, em, ed] = r.end.split("-");
  const end = ey === sy ? (em === sm ? ed : `${em}-${ed}`) : r.end;
  return `${r.start} → ${end}`;
}

function section(title, desc, present, winStart, winEnd) {
  const runs = computeGaps(present, winStart, winEnd);
  const totalDays = computeGaps(new Set(), winStart, winEnd)[0]?.days || 0;
  const absent = runs.reduce((a, r) => a + r.days, 0);
  const longest = runs.reduce((m, r) => Math.max(m, r.days), 0);
  const pct = totalDays ? Math.round((absent / totalDays) * 100) : 0;

  const el = document.createElement("section");
  el.className = "streak-section";
  el.innerHTML =
    `<h3>${title}</h3>` +
    `<p class="sub">${desc}</p>` +
    `<p class="sub">${winStart} → ${winEnd} · ${totalDays} days · ` +
    `<b>${absent}</b> quiet (${pct}%) · ${runs.length} streaks · longest ${longest}d</p>`;

  const list = document.createElement("div");
  list.className = "runlist";
  for (const r of runs) {
    const row = document.createElement("div");
    row.className = "runrow";
    row.innerHTML = `<span class="rundate">${fmtRun(r)}</span>` +
                    `<span class="runlen">${r.days}d</span>`;
    list.append(row);
  }
  el.append(list);
  return el;
}

// dayData: { spend:Set, activity:Set, dataMin, dataMax } from fetchDaySets.
// range: [start,end] | null  (clamped to the data window).
export function renderStreaks(container, dayData, range) {
  const cmpMax = (a, b) => (a > b ? a : b);
  const cmpMin = (a, b) => (a < b ? a : b);
  const start = range && range[0] ? cmpMax(range[0], dayData.dataMin) : dayData.dataMin;
  const end = range && range[1] ? cmpMin(range[1], dayData.dataMax) : dayData.dataMax;

  container.innerHTML = "";
  if (!start || !end || start > end) {
    container.innerHTML = "<p class='sub'>No transactions in this range.</p>";
    return;
  }
  container.append(
    section("No-spend days", "no outflow in the ticked categories (transfers excluded)", dayData.spend, start, end),
    section("No-activity days", "no transactions at all — in or out (all categories)", dayData.activity, start, end),
  );
}
