// Explore: every run on a timeline, coloured by heart-rate zone, filterable by effort / zone / distance, click any run for the full stats.
import { api } from "../lib/api.js";
import { h, s, skeleton } from "../lib/dom.js";
import { pace, dur, fmtDay, fmtClock, parseLocal } from "../lib/fmt.js";

const HR_RAMP = [[0.74, 0.1, 215], [0.76, 0.16, 85], [0.68, 0.22, 28]];
const lerp = (a, b, f) => a + (b - a) * f;
function zoneColor(i) {           // i = 0..4
  const f = i / 4, k = Math.min(1, Math.floor(f * 2)), l = f * 2 - k, [a, b] = [HR_RAMP[k], HR_RAMP[k + 1]];
  return `oklch(${lerp(a[0], b[0], l).toFixed(3)} ${lerp(a[1], b[1], l).toFixed(3)} ${lerp(a[2], b[2], l).toFixed(1)})`;
}
const PRESETS = { all: [1, 2, 3, 4, 5], easy: [1, 2], moderate: [3], hard: [4, 5] };
const DIST = { short: [0, 3], medium: [3, 6], long: [6, 999] };
const METRICS = {
  pace: { label: "Pace", get: (r) => r.pace, fmt: (v) => `${pace(v)}/mi`, up: "faster", invert: true, tick: 60 },
  hr: { label: "Average heart rate", get: (r) => r.hr, fmt: (v) => `${Math.round(v)} bpm`, tick: 10 },
  miles: { label: "Distance", get: (r) => r.miles, fmt: (v) => `${v.toFixed(1)} mi`, tick: 2 },
  ef: { label: "Efficiency", get: (r) => r.ef && r.ef * 100, fmt: (v) => v.toFixed(2), up: "more efficient", tick: 0.25 },
  cadence: { label: "Cadence", get: (r) => r.cadence, fmt: (v) => `${Math.round(v)} spm`, tick: 5 },
};
const DAY = 86400000;
const GUTTER = 40;   // room on the left of the timeline for the axis labels

export async function render(view, ctx) {
  view.replaceChildren(h("div", { class: "page" }, skeleton(8)));
  const data = await api.get("/api/analytics");
  const runs = (data.series && data.series.runs) || [];
  if (!runs.length) { view.replaceChildren(h("div", { class: "page" }, h("div", { class: "empty-state" }, h("h1", {}, "No runs to explore yet"), h("p", {}, "Sync your runs first.")))); return; }
  const bands = data.series.zones.bands || [];
  const hasZones = bands.length === 5 && runs.some((r) => r.dominant);

  const st = { zones: new Set(PRESETS.all), dist: new Set(Object.keys(DIST)), metric: "pace", share: false, selected: null, hovered: null };
  const day = (r) => parseLocal(r.date).getTime() / DAY;
  const d0 = day(runs[0]), d1 = day(runs[runs.length - 1]);
  const passes = (r) => {
    const zoneOk = !hasZones || (r.dominant ? st.zones.has(r.dominant) : st.zones.size === 5);
    const distOk = Object.entries(DIST).some(([k, [lo, hi]]) => st.dist.has(k) && r.miles >= lo && r.miles < hi);
    return zoneOk && distOk;
  };

  // ---------- controls ----------
  const summary = h("p", { class: "ex-summary mono", "aria-live": "polite" });
  const presetBtns = Object.keys(PRESETS).map((k) => h("button", { type: "button", dataset: { preset: k },
    onclick: () => { st.zones = new Set(PRESETS[k]); sync(); } }, k[0].toUpperCase() + k.slice(1)));
  const zoneChips = [1, 2, 3, 4, 5].map((z) => h("button", { type: "button", class: "zchip", dataset: { zone: z }, "aria-pressed": "true",
    onclick: () => { st.zones.has(z) ? st.zones.delete(z) : st.zones.add(z); if (!st.zones.size) st.zones = new Set(PRESETS.all); sync(); } },
    h("span", { class: "zdot", style: { background: zoneColor(z - 1) }, "aria-hidden": "true" }), `Z${z}`, bands[z - 1] ? h("small", {}, `${bands[z - 1].lo}-${bands[z - 1].hi}`) : null));
  const distBtns = Object.keys(DIST).map((k) => h("button", { type: "button", dataset: { dist: k }, "aria-pressed": "true",
    onclick: () => { st.dist.has(k) ? st.dist.delete(k) : st.dist.add(k); if (!st.dist.size) st.dist = new Set(Object.keys(DIST)); sync(); } },
    k === "short" ? "Short <3 mi" : k === "medium" ? "Medium 3-6" : "Long 6+"));
  const metricSel = h("select", { class: "input", id: "ex-metric", "aria-label": "Scatter plot measure", onchange: (e) => { st.metric = e.target.value; drawScatter(); } },
    Object.entries(METRICS).map(([k, m]) => h("option", { value: k }, m.label)));
  const modeBtns = [["Minutes", false], ["Share", true]].map(([label, val]) => h("button", { type: "button", "aria-pressed": String(st.share === val),
    onclick: () => { st.share = val; modeBtns.forEach((b, i) => b.setAttribute("aria-pressed", String(i === (val ? 1 : 0)))); drawBars(); } }, label));

  const filters = h("section", { class: "ex-filters", "aria-label": "Filters" },
    hasZones ? h("div", { class: "ex-group" }, h("span", { class: "label" }, "Effort"), h("div", { class: "seg", role: "group", "aria-label": "Effort preset" }, presetBtns)) : null,
    hasZones ? h("div", { class: "ex-group" }, h("span", { class: "label" }, "Heart-rate zone"), h("div", { class: "zchips", role: "group", "aria-label": "Heart-rate zones" }, zoneChips)) : null,
    h("div", { class: "ex-group" }, h("span", { class: "label" }, "Distance"), h("div", { class: "seg", role: "group", "aria-label": "Distance" }, distBtns)));

  // ---------- zone timeline (stacked bars) ----------
  const barsHost = h("div", { class: "ztl", tabindex: "-1" });
  const barsFig = h("figure", { class: "ex-fig" },
    h("figcaption", { class: "ex-cap" }, h("div", {}, h("h2", {}, "Time in zones, run by run"), h("p", { class: "hint" }, "Each bar is a run. Colour shows how its time split across heart-rate zones; a run's zone is where most of it was spent.")),
      hasZones ? h("div", { class: "seg", role: "group", "aria-label": "Bar height" }, modeBtns) : null), barsHost,
    hasZones ? h("ul", { class: "zlegend" }, bands.map((b, i) => h("li", {}, h("span", { class: "zdot", style: { background: zoneColor(i) } }), `Z${b.zone} ${b.name}`, h("span", { class: "muted mono" }, ` ${b.lo}-${b.hi}`)))) : h("p", { class: "hint" }, "Heart-rate zones need heart-rate data and a max HR."));

  // ---------- scatter ----------
  const scatterHost = h("div", { class: "scatter" });
  const scatterFig = h("figure", { class: "ex-fig" },
    h("figcaption", { class: "ex-cap" }, h("div", {}, h("h2", {}, "Every run over time"), h("p", { class: "hint" }, "Bigger dots are longer runs. Colour is the run's main heart-rate zone.")),
      h("div", { class: "field inline" }, h("label", { class: "label", for: "ex-metric" }, "Measure"), metricSel)), scatterHost);

  const detail = h("aside", { class: "ex-detail", "aria-live": "polite" });
  const page = h("div", { class: "page explore" },
    h("header", { class: "page-head" }, h("div", {}, h("p", { class: "eyebrow" }, "Analytics · Explore"), h("h1", {}, "Every run, by effort"))),
    filters, summary, h("div", { class: "ex-main" }, h("div", { class: "ex-charts" }, barsFig, scatterFig), detail));
  view.replaceChildren(page);

  // ---------- drawing ----------
  const barEls = new Map();
  function drawBars() {
    barsHost.replaceChildren(); barEls.clear();
    const width = barsHost.clientWidth || 900, days = Math.max(1, d1 - d0 + 1);
    const px = Math.max(5, Math.floor((width - GUTTER - 16) / days));
    const track = h("div", { class: "ztl-track", style: { width: `${days * px + GUTTER + 16}px` } });
    const maxMin = Math.max(...runs.map((r) => r.moving_s / 60), 30);
    const top = st.share ? 100 : Math.ceil(maxMin / 30) * 30;
    for (const v of st.share ? [0, 50, 100] : Array.from({ length: top / 30 + 1 }, (_, i) => i * 30)) {
      track.append(h("div", { class: "ztl-grid", style: { bottom: `${(v / top) * 100}%` } }, h("span", {}, st.share ? `${v}%` : `${v}m`)));
    }
    const first = parseLocal(runs[0].date);
    for (let m = new Date(first.getFullYear(), first.getMonth() + 1, 1); m.getTime() / DAY <= d1; m = new Date(m.getFullYear(), m.getMonth() + 1, 1)) {
      track.append(h("div", { class: "ztl-month", style: { left: `${GUTTER + (m.getTime() / DAY - d0) * px}px` } }, m.toLocaleDateString(undefined, { month: "short" })));
    }
    const perDay = new Map();
    runs.forEach((r) => {
      const k = perDay.get(r.date) || 0; perDay.set(r.date, k + 1);
      const total = r.zone_secs.reduce((a, b) => a + b, 0) || r.moving_s;
      const heightPct = st.share ? 100 : ((r.moving_s / 60) / top) * 100;
      const bar = h("button", { type: "button", class: "zbar", style: { left: `${GUTTER + (day(r) - d0) * px + k * (px / 2)}px`, width: `${Math.max(4, px - 1)}px`, height: `${heightPct}%` },
        "aria-label": `${fmtDay(r.date, { weekday: "short", month: "short", day: "numeric" })}, ${r.miles} miles, ${pace(r.pace)} per mile${r.hr ? `, ${r.hr} bpm` : ""}`,
        onmouseenter: () => hover(r.id), onfocus: () => hover(r.id), onmouseleave: () => hover(null), onblur: () => hover(null), onclick: () => select(r.id) },
        r.zone_secs.some((v) => v > 0)
          ? r.zone_secs.map((v, i) => v ? h("span", { class: "zseg", style: { flexGrow: String(v / total), background: zoneColor(i), order: i } }) : null)
          : h("span", { class: "zseg nozone", style: { flexGrow: 1 } }));
      barEls.set(r.id, bar); track.append(bar);
    });
    barsHost.append(track);
    paint();
  }

  const dotEls = new Map();
  function drawScatter() {
    const m = METRICS[st.metric];
    const pts = runs.filter((r) => m.get(r) != null);
    scatterHost.replaceChildren(); dotEls.clear();
    if (pts.length < 2) { scatterHost.append(h("p", { class: "muted" }, "Not enough data for this measure.")); return; }
    const W = 860, H = 340, pad = { l: 58, r: 16, t: 14, b: 32 };
    const vals = pts.map(m.get).sort((a, b) => a - b);
    const lo0 = vals[Math.floor(vals.length * 0.02)], hi0 = vals[Math.floor(vals.length * 0.98)];
    const lo = Math.floor(lo0 / m.tick) * m.tick - m.tick, hi = Math.ceil(hi0 / m.tick) * m.tick + m.tick;
    const X = (d) => pad.l + ((d - d0) / (d1 - d0 || 1)) * (W - pad.l - pad.r);
    const frac = (v) => (Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo);
    const Y = (v) => pad.t + (m.invert ? frac(v) : 1 - frac(v)) * (H - pad.t - pad.b);
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `${m.label} of every run over time. Use the bars above for keyboard access.` });
    const step = (hi - lo) / 5;
    for (let v = lo; v <= hi + 1e-6; v += Math.max(m.tick, Math.round(step / m.tick) * m.tick)) {
      svg.append(s("line", { x1: pad.l, x2: W - pad.r, y1: Y(v), y2: Y(v), stroke: "var(--line-soft)" }), s("text", { class: "ax", x: pad.l - 8, y: Y(v) + 4, "text-anchor": "end" }, m.fmt(v).replace(/\/mi| bpm| mi| spm/, "")));
    }
    const first = parseLocal(runs[0].date);
    for (let mo = new Date(first.getFullYear(), first.getMonth() + 1, 1); mo.getTime() / DAY <= d1; mo = new Date(mo.getFullYear(), mo.getMonth() + 1, 1)) {
      svg.append(s("text", { class: "ax", x: X(mo.getTime() / DAY), y: H - 10, "text-anchor": "middle" }, mo.toLocaleDateString(undefined, { month: "short" })));
    }
    if (m.up) svg.append(s("text", { class: "ax-title", x: 14, y: (pad.t + H - pad.b) / 2, "text-anchor": "middle", transform: `rotate(-90 14 ${(pad.t + H - pad.b) / 2})` }, `${m.up} is up`));
    pts.forEach((r) => {
      const dot = s("circle", { class: "sdot", cx: X(day(r)), cy: Y(m.get(r)), r: 3 + Math.min(5, r.miles / 2.2), fill: r.dominant ? zoneColor(r.dominant - 1) : "var(--muted)",
        onmouseenter: () => hover(r.id), onmouseleave: () => hover(null), onclick: () => select(r.id) });
      dotEls.set(r.id, dot); svg.append(dot);
    });
    scatterHost.append(svg);
    paint();
  }

  // ---------- state -> view ----------
  const byId = new Map(runs.map((r) => [r.id, r]));
  function paint() {
    for (const r of runs) {
      const on = passes(r), sel = r.id === st.selected;
      for (const el of [barEls.get(r.id), dotEls.get(r.id)]) {
        if (!el) continue;
        el.classList.toggle("dim", !on); el.classList.toggle("sel", sel);
        el.tabIndex = on ? 0 : -1;
      }
    }
  }
  function hover(id) { st.hovered = id; showDetail(); }
  function select(id) { st.selected = st.selected === id ? null : id; paint(); showDetail(); }
  function showDetail() {
    const r = byId.get(st.hovered || st.selected);
    if (!r) { detail.replaceChildren(h("div", { class: "ex-detail-empty" }, h("p", { class: "label" }, "Run details"), h("p", { class: "muted" }, "Hover or tap a run to see its full stats. Click to pin it."))); return; }
    const total = r.zone_secs.reduce((a, b) => a + b, 0);
    const stat = (k, v, cls = "") => h("div", {}, h("dt", {}, k), h("dd", { class: `mono ${cls}` }, v));
    const meanEf = runs.filter((x) => x.ef).reduce((t, x) => t + x.ef, 0) / Math.max(1, runs.filter((x) => x.ef).length);
    const effRel = r.ef && meanEf ? (r.ef / meanEf - 1) * 100 : null;
    detail.replaceChildren(
      h("p", { class: "label" }, st.hovered && st.hovered !== st.selected ? "Run details" : st.selected ? "Pinned run" : "Run details"),
      h("h2", {}, r.name || "Run"), h("p", { class: "muted" }, `${fmtDay(r.date, { weekday: "long", month: "long", day: "numeric" })} · ${fmtClock(r.start)}`),
      h("dl", { class: "ex-stats" }, stat("Distance", `${r.miles.toFixed(2)} mi`), stat("Time", dur(r.moving_s)), stat("Pace", `${pace(r.pace)}/mi`, "pace-c"),
        r.hr ? stat("Avg HR", `${r.hr} bpm`, "hr-c") : null, r.max_hr ? stat("Max HR", `${r.max_hr} bpm`) : null, r.cadence ? stat("Cadence", `${r.cadence} spm`) : null,
        stat("Climb", `${r.elev_ft} ft`), effRel != null ? stat("Efficiency", `${effRel >= 0 ? "+" : ""}${effRel.toFixed(1)}% vs avg`) : null,
        r.fade != null ? stat("Pacing", r.fade > 0.01 ? `${(r.fade * 100).toFixed(1)}% slower 2nd half` : r.fade < -0.01 ? `${(Math.abs(r.fade) * 100).toFixed(1)}% faster 2nd half` : "even") : null,
        r.drift != null && r.moving_s >= 3000 ? stat("Drift", `${(r.drift * 100).toFixed(1)}%`) : null, r.gear ? stat("Shoes", r.gear) : null),
      total > 0 ? h("div", { class: "ex-zonemix" }, h("p", { class: "label" }, "Time in zones"),
        h("div", { class: "zone-bar" }, r.zone_secs.map((v, i) => h("div", { class: "zone-seg", style: { flex: String(v), background: zoneColor(i) }, title: `Z${i + 1}: ${dur(v)}` }))),
        h("ul", { class: "zlist" }, r.zone_secs.map((v, i) => v >= 30 ? h("li", {}, h("span", { class: "zdot", style: { background: zoneColor(i) } }), `Z${i + 1}`, h("span", { class: "mono" }, dur(v))) : null))) : null,
      h("a", { class: "btn btn-primary", href: `#/runs/${r.id}` }, "Open run and replay"));
  }

  function sync() {
    const preset = Object.entries(PRESETS).find(([, z]) => z.length === st.zones.size && z.every((x) => st.zones.has(x)));
    presetBtns.forEach((b) => b.setAttribute("aria-pressed", String(!!preset && preset[0] === b.dataset.preset)));
    zoneChips.forEach((b) => b.setAttribute("aria-pressed", String(st.zones.has(Number(b.dataset.zone)))));
    distBtns.forEach((b) => b.setAttribute("aria-pressed", String(st.dist.has(b.dataset.dist))));
    const shown = runs.filter(passes);
    const miles = shown.reduce((t, r) => t + r.miles, 0), secs = shown.reduce((t, r) => t + r.moving_s, 0);
    const hrRuns = shown.filter((r) => r.hr);
    summary.textContent = shown.length
      ? `${shown.length} of ${runs.length} runs · ${miles.toFixed(0)} mi · ${dur(secs)} on feet · avg pace ${pace(secs / miles)}/mi${hrRuns.length ? ` · avg HR ${Math.round(hrRuns.reduce((t, r) => t + r.hr, 0) / hrRuns.length)}` : ""}`
      : "No runs match these filters.";
    paint();
  }

  drawBars(); drawScatter(); sync(); showDetail();
  const ro = new ResizeObserver(() => drawBars());
  ro.observe(barsHost);
  return () => ro.disconnect();
}
