// Tree of groups -> buckets with arrow / group-checkbox / bucket-checkbox.
import { fmtMoney } from "./model.js";
import { groupState, bucketEnabled, setBucketEnabled } from "./state.js";
import { rgbCss } from "./colors.js";

export class TreeView {
  // onChange() is called after any toggle that affects the chart.
  constructor(container, { groups, scope, metricKey, colorMap, grandTotal, onChange }) {
    this.container = container;
    this.groups = groups;
    this.scope = scope;
    this.mkey = metricKey;
    this.colorMap = colorMap;
    this.grand = grandTotal || 1;
    this.onChange = onChange;
    this.rowLabels = new Map(); // colorKey -> label element
    this.rowEls = new Map();    // colorKey -> row element (for highlight)
    this._build();
  }

  _swatch(colorKey) {
    const sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = rgbCss(this.colorMap.get(colorKey) || [150, 150, 150]);
    return sw;
  }

  _build() {
    this.container.innerHTML = "";
    this.rowLabels.clear();
    this.rowEls.clear();
    for (const g of this.groups) {
      const gs = groupState(this.scope, this.mkey, g);

      const gframe = document.createElement("div");
      gframe.className = "group";

      const row = document.createElement("div");
      row.className = "row group-row";

      const arrow = document.createElement("button");
      arrow.className = "arrow";
      arrow.textContent = gs.open ? "▼" : "▶";
      arrow.title = "Open/close in tree (does not change the chart)";

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = gs.combined;
      cb.title = "Ticked = one combined slice; untick to split into buckets";

      const gpct = (g.total / this.grand) * 100;
      const label = document.createElement("span");
      label.className = "label";
      label.textContent = `${g.name}  ${fmtMoney(g.total)} · ${gpct.toFixed(0)}%`;
      this.rowLabels.set("group:" + g.key, label);

      row.append(arrow, cb, this._swatch("group:" + g.key), label);
      this.rowEls.set("group:" + g.key, row);

      const child = document.createElement("div");
      child.className = "children";
      child.style.display = gs.open ? "block" : "none";

      for (const b of g.buckets) {
        const brow = document.createElement("div");
        brow.className = "row bucket-row";
        const bcb = document.createElement("input");
        bcb.type = "checkbox";
        bcb.checked = bucketEnabled(this.scope, this.mkey, b.id);
        bcb.title = "Include/exclude this bucket (applies combined or split)";
        const bpct = (b.val / this.grand) * 100;
        const blabel = document.createElement("span");
        blabel.className = "label";
        blabel.textContent = `${b.name}  ${fmtMoney(b.val)} · ${bpct.toFixed(0)}%`;
        this.rowLabels.set("bucket:" + b.id, blabel);
        brow.append(bcb, this._swatch("bucket:" + b.id), blabel);
        this.rowEls.set("bucket:" + b.id, brow);
        child.append(brow);

        bcb.addEventListener("change", () => {
          setBucketEnabled(this.scope, this.mkey, b.id, bcb.checked);
          this.onChange();
        });
      }

      arrow.addEventListener("click", () => {
        gs.open = !gs.open;
        arrow.textContent = gs.open ? "▼" : "▶";
        child.style.display = gs.open ? "block" : "none";
        this.onChange({ treeOnly: true });
      });
      cb.addEventListener("change", () => {
        gs.combined = cb.checked;
        this.onChange();
      });

      gframe.append(row, child);
      this.container.append(gframe);
    }
  }

  setAll(combined) {
    for (const g of this.groups) groupState(this.scope, this.mkey, g).combined = combined;
    this._build();
    this.onChange();
  }

  // Grey out rows whose slice was merged into the "Other" pile.
  applyGrey(otherized) {
    for (const [ck, lbl] of this.rowLabels) {
      lbl.classList.toggle("otherized", otherized.has(ck));
    }
  }

  // Highlight the rows whose colorKey is in `set` (mirrors a pie-slice hover).
  highlight(set) {
    for (const [ck, row] of this.rowEls) {
      row.classList.toggle("hl", set.has(ck));
    }
  }
}
