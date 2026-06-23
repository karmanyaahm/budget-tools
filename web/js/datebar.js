// Date range controls: Y/M/D selects, presets, month nav, year buttons,
// other-% input, include-transfers. Mirrors the Python control bar.
import { pad, lastDay, monthRange, ytd, yearRange, monthOf } from "./model.js";

function makeSelect(cls) {
  const s = document.createElement("select");
  s.className = cls;
  return s;
}

function fill(sel, values) {
  sel.innerHTML = "";
  const blank = document.createElement("option");
  blank.value = ""; blank.textContent = "–";
  sel.append(blank);
  for (const v of values) {
    const o = document.createElement("option");
    o.value = String(v); o.textContent = String(v);
    sel.append(o);
  }
}

export class DateBar {
  constructor(container, opts) {
    this.opts = opts; // {yearLo, yearHi, otherPct, includeTransfers, onRange, onOther, onTransfers}
    this.container = container;
    this._applyTimer = null;
    this._build();
  }

  _build() {
    const { yearLo, yearHi } = this.opts;
    const years = [];
    for (let y = yearLo; y <= yearHi; y++) years.push(y);
    const months = Array.from({ length: 12 }, (_, i) => pad(i + 1));
    const days = Array.from({ length: 31 }, (_, i) => pad(i + 1));
    this.container.innerHTML = "";

    const mk = (txt) => { const s = document.createElement("span"); s.textContent = txt; s.className = "lbl"; return s; };

    // start
    this.sY = makeSelect("y"); this.sM = makeSelect("m"); this.sD = makeSelect("d");
    fill(this.sY, years); fill(this.sM, months); fill(this.sD, days);
    // end
    this.eY = makeSelect("y"); this.eM = makeSelect("m"); this.eD = makeSelect("d");
    fill(this.eY, years); fill(this.eM, months); fill(this.eD, days);

    this.container.append(mk("Start"), this.sY, this.sM, this.sD,
                          mk("End"), this.eY, this.eM, this.eD);

    for (const w of [this.sY, this.sM, this.sD]) w.addEventListener("change", () => this._onStartChange());
    for (const w of [this.eY, this.eM, this.eD]) w.addEventListener("change", () => { this._clampDays(this.eY, this.eM, this.eD); this._scheduleApply(); });

    const btn = (txt, fn, cls = "") => {
      const b = document.createElement("button");
      b.textContent = txt; b.className = "btn " + cls;
      b.addEventListener("click", fn);
      return b;
    };

    this.container.append(btn("Apply", () => this._apply()));
    this.container.append(this._sep());
    this.container.append(btn("◀ Mo", () => this._shiftMonth(-1)));
    this.container.append(btn("Mo ▶", () => this._shiftMonth(1)));
    this.container.append(this._sep());
    this.container.append(btn("This month", () => this.setRange(...monthRange(0))));
    this.container.append(btn("Last month", () => this.setRange(...monthRange(1))));
    this.container.append(btn("YTD", () => this.setRange(...ytd())));
    this.container.append(btn("All time", () => this.setRange(null, null)));
    this.container.append(this._sep());
    for (let y = yearHi; y >= yearLo; y--) {
      this.container.append(btn(String(y), () => this.setRange(...yearRange(y)), "year"));
    }

    // right side: other %, include transfers, status
    const right = document.createElement("div");
    right.className = "right";

    const otherWrap = document.createElement("span");
    otherWrap.className = "lbl otherctl";
    otherWrap.append(document.createTextNode("Other ≤ "));
    const stepDown = document.createElement("button");
    stepDown.className = "btn step"; stepDown.textContent = "−";
    stepDown.title = "Release the largest hidden category back to the pie";
    stepDown.addEventListener("click", () => this.opts.onOtherStep(-1));
    this.otherInput = document.createElement("input");
    this.otherInput.type = "number"; this.otherInput.min = "0"; this.otherInput.max = "100";
    this.otherInput.step = "0.5"; this.otherInput.value = String(this.opts.otherPct);
    this.otherInput.className = "other no-spin";
    this.otherInput.title = "Absorb the smallest categories until 'Other' is just under this % of the pie";
    this.otherInput.addEventListener("change", () => {
      let v = parseFloat(this.otherInput.value);
      if (isNaN(v)) return;
      v = Math.max(0, Math.min(100, v));
      this.otherInput.value = String(v);
      this.opts.onOtherTarget(v);
    });
    const stepUp = document.createElement("button");
    stepUp.className = "btn step"; stepUp.textContent = "+";
    stepUp.title = "Absorb the smallest visible category into 'Other'";
    stepUp.addEventListener("click", () => this.opts.onOtherStep(1));
    otherWrap.append(stepDown, this.otherInput, stepUp, document.createTextNode(" %  (0=off)"));

    const txWrap = document.createElement("label");
    txWrap.className = "lbl";
    this.txInput = document.createElement("input");
    this.txInput.type = "checkbox";
    this.txInput.checked = this.opts.includeTransfers;
    this.txInput.addEventListener("change", () => this.opts.onTransfers(this.txInput.checked));
    txWrap.append(this.txInput, document.createTextNode(" transfers"));

    this.status = document.createElement("span");
    this.status.className = "status";

    right.append(otherWrap, txWrap, this.status);
    this.container.append(right);
  }

  _sep() { const s = document.createElement("span"); s.className = "sep"; return s; }

  _clampDays(yW, mW, dW) {
    const y = parseInt(yW.value, 10), m = parseInt(mW.value, 10);
    if (!y || !m) return;
    const n = lastDay(y, m);
    const cur = parseInt(dW.value, 10);
    fill(dW, Array.from({ length: n }, (_, i) => pad(i + 1)));
    if (cur) dW.value = pad(Math.min(cur, n));
  }

  _onStartChange() {
    this._clampDays(this.sY, this.sM, this.sD);
    const y = parseInt(this.sY.value, 10), m = parseInt(this.sM.value, 10), d = parseInt(this.sD.value, 10);
    if (y && m && d === 1) { // snap end to last day of the start month
      this.eY.value = String(y); this.eM.value = pad(m);
      this._clampDays(this.eY, this.eM, this.eD);
      this.eD.value = pad(lastDay(y, m));
    }
    this._scheduleApply();
  }

  _read(yW, mW, dW) {
    const y = parseInt(yW.value, 10), m = parseInt(mW.value, 10), d = parseInt(dW.value, 10);
    if (!y || !m || !d) return null;
    return `${y}-${pad(m)}-${pad(d)}`;
  }

  _setCombos(yW, mW, dW, dateStr) {
    if (!dateStr) { yW.value = ""; mW.value = ""; dW.value = ""; return; }
    const [y, m, d] = dateStr.split("-");
    yW.value = String(parseInt(y, 10)); mW.value = m;
    this._clampDays(yW, mW, dW); dW.value = d;
  }

  _scheduleApply() {
    clearTimeout(this._applyTimer);
    this._applyTimer = setTimeout(() => this._apply(), 350);
  }

  _apply() {
    clearTimeout(this._applyTimer);
    const start = this._read(this.sY, this.sM, this.sD);
    const end = this._read(this.eY, this.eM, this.eD);
    this.opts.onRange(start, end);
  }

  _shiftMonth(delta) {
    const start = this._read(this.sY, this.sM, this.sD);
    this.setRange(...monthOf(start, delta));
  }

  // Public: set the dropdowns and fire onRange.
  setRange(start, end) {
    this._setCombos(this.sY, this.sM, this.sD, start);
    this._setCombos(this.eY, this.eM, this.eD, end);
    this.opts.onRange(start, end);
  }

  setStatus(text) { this.status.textContent = text; }

  setOther(v) { this.otherInput.value = (Math.round(v * 10) / 10).toString(); }
}
