// Pie chart: slice computation + Chart.js wrapper with dual-% slice labels.
import { OTHER, fmtMoney } from "./model.js";
import { groupState, bucketEnabled } from "./state.js";
import { rgbCss, OTHER_RGB } from "./colors.js";

// Base slices for a metric (combine/split + bucket filter, before "Other").
// Returns [{label, val, colorKey}].
export function baseSlices(groups, scope, mkey) {
  const slices = [];
  for (const g of groups) {
    const gs = groupState(scope, mkey, g);
    const enabled = g.buckets.filter((b) => bucketEnabled(scope, mkey, b.id));
    if (!enabled.length) continue; // whole group excluded
    if (gs.combined) {
      slices.push({
        label: g.name,
        val: enabled.reduce((a, b) => a + b.val, 0),
        colorKey: "group:" + g.key,
      });
    } else {
      for (const b of enabled) {
        slices.push({ label: b.name, val: b.val, colorKey: "bucket:" + b.id });
      }
    }
  }
  return slices;
}

// Per-slice threshold: how many slices are <= threshold% of the total.
// Sorted ascending, so this is the count of the leading (smallest) slices.
export function otherizedCount(sortedAsc, total, thresholdPct) {
  if (thresholdPct <= 0 || total <= 0) return 0;
  const lim = (thresholdPct / 100) * total;
  let k = 0;
  for (const s of sortedAsc) { if (s.val <= lim) k++; else break; }
  return k;
}

// Threshold % that makes exactly the k smallest slices "Other" — i.e. the
// k-th smallest slice's own share (so everything <= it is absorbed).
export function targetForCount(sortedAsc, total, k) {
  if (k <= 0 || total <= 0) return 0;
  const idx = Math.min(k, sortedAsc.length) - 1;
  return (sortedAsc[idx].val / total) * 100;
}

// Merge every slice <= otherThresholdPct of the pie into one "Other" slice.
// Returns { slices, otherized:Set<colorKey>, visible }
export function computeSlices(groups, scope, mkey, otherThresholdPct) {
  let slices = baseSlices(groups, scope, mkey);
  const visible = slices.reduce((a, s) => a + s.val, 0);

  let otherized = new Set();
  if (otherThresholdPct > 0 && visible > 0) {
    const sortedAsc = [...slices].sort((a, b) => a.val - b.val);
    const k = otherizedCount(sortedAsc, visible, otherThresholdPct);
    if (k >= 2) {
      const smallSet = new Set(sortedAsc.slice(0, k).map((s) => s.colorKey));
      const big = slices.filter((s) => !smallSet.has(s.colorKey));
      const otherVal = sortedAsc.slice(0, k).reduce((a, s) => a + s.val, 0);
      big.push({ label: `Other (${k})`, val: otherVal, colorKey: OTHER });
      otherized = smallSet;
      slices = big;
    }
  }
  return { slices, otherized, visible };
}

// Custom plugin: draw "<visible%> (<total%> all)" + "$amount" on each slice.
const dualLabels = {
  id: "dualLabels",
  afterDatasetsDraw(chart) {
    const ds = chart.data.datasets[0];
    const meta = chart.getDatasetMeta(0);
    const visible = ds.data.reduce((a, b) => a + b, 0) || 1;
    const grand = chart.$grand || visible;
    const ctx = chart.ctx;
    ctx.save();
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "#111";
    meta.data.forEach((arc, i) => {
      const val = ds.data[i];
      const ang = arc.endAngle - arc.startAngle;
      if (ang < 0.18) return; // skip tiny slices
      const mid = (arc.startAngle + arc.endAngle) / 2;
      const r = (arc.innerRadius + arc.outerRadius) / 2;
      const x = arc.x + Math.cos(mid) * r;
      const y = arc.y + Math.sin(mid) * r;
      const visPct = (val / visible) * 100;
      const totPct = (val / grand) * 100;
      const l1 = Math.abs(visPct - totPct) < 0.5
        ? `${visPct.toFixed(0)}%`
        : `${visPct.toFixed(0)}% (${totPct.toFixed(0)}% all)`;
      ctx.font = "bold 11px system-ui, sans-serif";
      ctx.fillText(l1, x, y - 7);
      ctx.font = "10px system-ui, sans-serif";
      ctx.fillText(fmtMoney(val), x, y + 7);
    });
    ctx.restore();
  },
};

export class PieView {
  constructor(canvas, colorMap) {
    this.canvas = canvas;
    this.colorMap = colorMap;
    this.chart = null;
    this.onHover = null;   // (colorKey|null) => void
    this._slices = [];
    canvas.addEventListener("mouseleave", () => { if (this.onHover) this.onHover(null); });
  }

  colorFor(colorKey) {
    if (colorKey === OTHER) return rgbCss(OTHER_RGB);
    return rgbCss(this.colorMap.get(colorKey) || [150, 150, 150]);
  }

  render(slices, grandTotal) {
    const labels = slices.map((s) => s.label);
    const data = slices.map((s) => s.val);
    const colors = slices.map((s) => this.colorFor(s.colorKey));

    this._slices = slices;

    if (this.chart) {
      this.chart.data.labels = labels;
      this.chart.data.datasets[0].data = data;
      this.chart.data.datasets[0].backgroundColor = colors;
      this.chart.$grand = grandTotal;
      this.chart.update();
      return;
    }

    this.chart = new window.Chart(this.canvas, {
      type: "pie",
      data: { labels, datasets: [{ data, backgroundColor: colors, borderWidth: 1, borderColor: "#fff" }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        onHover: (e, active) => {
          if (!this.onHover) return;
          const ck = active.length ? (this._slices[active[0].index] || {}).colorKey : null;
          this.onHover(ck || null);
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (c) => {
                const ds = c.chart.data.datasets[0].data;
                const visible = ds.reduce((a, b) => a + b, 0) || c.parsed;
                const grand = c.chart.$grand || visible;
                const visPct = (c.parsed / visible) * 100;
                const totPct = (c.parsed / grand) * 100;
                return `${c.label}: ${fmtMoney(c.parsed)} · ${visPct.toFixed(1)}% of chart · ${totPct.toFixed(1)}% of total`;
              },
            },
          },
        },
      },
      plugins: [dualLabels],
    });
    this.chart.$grand = grandTotal;
    this.chart.update();
  }

  destroy() {
    if (this.chart) { this.chart.destroy(); this.chart = null; }
  }
}
