// "Quiet Days" view: contiguous periods with no spending / no activity.
import { computeGaps, pad } from "./model.js";

function fmtRun(r) {
  if (r.days === 1) return r.start;
  // shorten the end if same year/month
  const [sy, sm] = r.start.split("-");
  const [ey, em, ed] = r.end.split("-");
  const end = ey === sy ? (em === sm ? ed : `${em}-${ed}`) : r.end;
  return `${r.start} → ${end}`;
}

function section(title, desc, present, winStart, winEnd, hue) {
  const runs = computeGaps(present, winStart, winEnd);
  const totalDays = computeGaps(new Set(), winStart, winEnd)[0]?.days || 0;
  const absent = runs.reduce((a, r) => a + r.days, 0);
  const longest = runs.reduce((m, r) => Math.max(m, r.days), 0) || 1;
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
    // Color by length: longest = strong/dark, 1-day = faint.
    const t = r.days / longest;            // 0..1
    const light = 95 - 45 * t;             // 95% (faint) -> 50% (strong)
    row.style.background = `hsl(${hue} 80% ${light}%)`;
    if (light < 62) row.style.color = "#fff";
    row.innerHTML = `<span class="rundate">${fmtRun(r)}</span>` +
                    `<span class="runlen">${r.days}d</span>`;
    list.append(row);
  }
  el.append(list);
  return el;
}

// Calendar heatmap: one row per month, 31 day cells. Quiet days are shaded by
// the length of the streak they belong to (so streaks read as solid blocks);
// spend days are faint grey. Color hue matches the matching list.
function buildCalendar(present, winStart, winEnd, hue, title) {
  const runs = computeGaps(present, winStart, winEnd);
  const maxLen = runs.reduce((m, r) => Math.max(m, r.days), 0) || 1;
  const len = new Map();
  for (const r of runs) {
    let t = Date.UTC(...r.start.split("-").map(Number).map((v, i) => i === 1 ? v - 1 : v));
    const endMs = Date.UTC(...r.end.split("-").map(Number).map((v, i) => i === 1 ? v - 1 : v));
    for (; t <= endMs; t += 86400000) {
      const d = new Date(t);
      len.set(`${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`, r.days);
    }
  }

  const wrap = document.createElement("div");
  wrap.className = "cal";
  wrap.innerHTML = `<h3>${title}</h3><p class="sub">color = streak length · hover a cell for the date</p>`;
  const grid = document.createElement("div");
  grid.className = "calgrid";

  let [y, m] = winStart.split("-").map(Number);
  const [ey, em] = winEnd.split("-").map(Number);
  while (y < ey || (y === ey && m <= em)) {
    const row = document.createElement("div");
    row.className = "calrow";
    const lab = document.createElement("span");
    lab.className = "calmonth";
    lab.textContent = `${y}-${pad(m)}`;
    row.append(lab);
    const dim = new Date(Date.UTC(y, m, 0)).getUTCDate();
    let quiet = 0;
    for (let d = 1; d <= 31; d++) {
      const cell = document.createElement("span");
      cell.className = "calcell";
      const iso = `${y}-${pad(m)}-${pad(d)}`;
      if (d > dim || iso < winStart || iso > winEnd) {
        cell.classList.add("blank");
      } else if (len.has(iso)) {
        const t = len.get(iso) / maxLen;
        cell.style.background = `hsl(${hue} 80% ${92 - 42 * t}%)`;
        cell.title = `${iso} · ${len.get(iso)}d no-spend streak`;
        quiet++;
      } else {
        cell.classList.add("spend");
        cell.title = `${iso} · spent`;
      }
      row.append(cell);
    }
    const cnt = document.createElement("span");
    cnt.className = "calcount";
    cnt.textContent = quiet || "";
    row.append(cnt);
    grid.append(row);
    m++; if (m > 12) { m = 1; y++; }
  }
  wrap.append(grid);
  return wrap;
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
  const lists = document.createElement("div");
  lists.className = "streak-lists";
  lists.append(
    section("No-spend days", "no outflow in the ticked categories (transfers excluded)", dayData.spend, start, end, 150),
    section("No-activity days", "no transactions at all — in or out (all categories)", dayData.activity, start, end, 215),
  );
  container.append(
    buildCalendar(dayData.spend, start, end, 150, "No-spend calendar"),
    lists,
  );
}
