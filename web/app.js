const MI = 1609.344;
const FT = 3.28084;
const PAUSE_GAP = 60; // seconds between samples that counts as a watch pause
const SPEEDS = [10, 30, 60, 120];
const SVG_NS = "http://www.w3.org/2000/svg";

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const state = { runs: [], model: null, tau: 0, playing: false, speed: 30, metric: "pace", lastFrame: 0 };
let map, runnerMarker, segments = [], segIndex = [], litUpTo = 0, raf = 0;

// ---------- tiny DOM helpers (no innerHTML: run names come from Strava) ----------
function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) k === "class" ? (e.className = v) : e.setAttribute(k, v);
  e.append(...kids);
  return e;
}
function sv(tag, attrs = {}, ...kids) {
  const e = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  e.append(...kids);
  return e;
}
function setVal(node, value, unit) {
  node.replaceChildren(String(value));
  if (unit) node.append(el("small", {}, unit));
}
function iconSvg(d) {
  return sv("svg", { viewBox: "0 0 24 24", "aria-hidden": "true" }, sv("path", { d }));
}
const ICON_PLAY = "M8 5v14l11-7z";
const ICON_PAUSE = "M7 5h4v14H7zM13 5h4v14h-4z";

// ---------- formatting ----------
const pad = (n) => String(n).padStart(2, "0");
function fmtDur(s) {
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h}:${pad(m)}:${pad(s % 60)}` : `${m}:${pad(s % 60)}`;
}
function paceFromSpeed(v) { return v && v >= 0.8 ? MI / v / 60 : null; } // min per mile
function fmtPace(p) {
  if (p == null) return "--";
  let m = Math.floor(p), s = Math.round((p - m) * 60);
  if (s === 60) { m += 1; s = 0; }
  return `${m}:${pad(s)}`;
}
const miles = (m) => m / MI;
const avgPace = (moving_s, dist_m) => (moving_s && dist_m ? moving_s / miles(dist_m) / 60 : null);
function fmtDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" });
}
function fmtTimeOfDay(local) {
  const [h, m] = local.split("T")[1].split(":").map(Number);
  return `${((h + 11) % 12) + 1}:${pad(m)} ${h < 12 ? "AM" : "PM"}`;
}

// ---------- colour ramps (OKLCH) ----------
const lerp = (a, b, f) => a + (b - a) * f;
function ramp(stops, f) {
  f = Math.min(1, Math.max(0, f));
  const i = Math.min(stops.length - 2, Math.floor(f * (stops.length - 1)));
  const local = f * (stops.length - 1) - i;
  const [a, b] = [stops[i], stops[i + 1]];
  return `oklch(${lerp(a[0], b[0], local).toFixed(3)} ${lerp(a[1], b[1], local).toFixed(3)} ${lerp(a[2], b[2], local).toFixed(1)})`;
}
const PACE_RAMP = [[0.58, 0.13, 255], [0.72, 0.12, 200], [0.87, 0.16, 112]]; // slow cool -> fast lime
const HR_RAMP = [[0.74, 0.1, 215], [0.76, 0.16, 85], [0.68, 0.22, 28]]; // calm -> hot

async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

// ---------- run list ----------
function renderList() {
  const nav = $("#run-list");
  nav.replaceChildren();
  let month = "";
  for (const r of state.runs) {
    const m = new Date(r.start_local).toLocaleDateString(undefined, { month: "long", year: "numeric" });
    if (m !== month) { month = m; nav.append(el("div", { class: "month" }, m)); }
    const day = new Date(r.start_local).toLocaleDateString(undefined, { month: "short", day: "numeric" });
    const b = el("button", { type: "button", class: "run-item", "data-id": r.id },
      el("span", { class: "t" }, r.name || "Run"),
      el("span", { class: "d" }, `${miles(r.distance_m).toFixed(2)} mi`),
      el("span", { class: "s" }, `${day} · ${fmtPace(avgPace(r.moving_s, r.distance_m))}/mi`),
      el("span", { class: "h" }, r.avg_hr ? `${Math.round(r.avg_hr)} bpm` : ""));
    b.addEventListener("click", () => openRun(r.id));
    nav.append(b);
  }
}

// ---------- run model ----------
function buildModel({ run, streams, laps }) {
  const n = streams.t.length;
  const pts = [];
  for (let i = 0; i < n; i++) {
    pts.push({
      t: streams.t[i], hr: streams.hr[i], v: streams.speed[i], cad: streams.cadence[i],
      d: streams.dist[i], moving: streams.moving[i], lat: streams.lat[i], lng: streams.lng[i],
    });
  }
  // smoothed pace for the chart: rolling mean of speed over moving samples, then convert
  const W = 2;
  pts.forEach((p, i) => {
    let sum = 0, c = 0;
    for (let j = Math.max(0, i - W); j <= Math.min(n - 1, i + W); j++) {
      const q = pts[j];
      if (q.v && q.v >= 0.8 && q.moving !== false) { sum += q.v; c++; }
    }
    p.pace = c >= 2 ? paceFromSpeed(sum / c) : null;
  });
  const pauses = [];
  for (let i = 1; i < n; i++) if (pts[i].t - pts[i - 1].t > PAUSE_GAP) pauses.push([pts[i - 1].t, pts[i].t]);
  return { run, laps, pts, pauses, t0: pts[0].t, t1: pts[n - 1].t, hasGps: run.has_gps && pts.some((p) => p.lat != null) };
}

function sampleAt(model, tau) {
  const { pts } = model;
  tau = Math.min(model.t1, Math.max(model.t0, tau));
  let lo = 0, hi = pts.length - 1;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (pts[mid].t <= tau) lo = mid; else hi = mid; }
  const a = pts[lo], b = pts[hi];
  const paused = b.t - a.t > PAUSE_GAP;
  const f = paused || b.t === a.t ? 0 : (tau - a.t) / (b.t - a.t);
  const mix = (x, y) => (x == null ? y : y == null ? x : lerp(x, y, f));
  return {
    idx: lo, paused, t: tau,
    lat: mix(a.lat, b.lat), lng: mix(a.lng, b.lng), hr: mix(a.hr, b.hr),
    v: paused ? 0 : mix(a.v, b.v), cad: paused ? 0 : mix(a.cad, b.cad), d: mix(a.d, b.d),
  };
}

// ---------- open a run ----------
async function openRun(id) {
  pause();
  const data = await api(`/api/runs/${id}`);
  state.model = buildModel(data);
  state.tau = state.model.t0;
  history.replaceState(null, "", `#run=${id}`);
  $$(".run-item").forEach((b) => b.setAttribute("aria-current", String(b.dataset.id === id)));
  $("#empty").hidden = true;
  $("#run-view").hidden = false;
  renderHeader();
  renderLaps();
  setupMap();
  renderChart();
  update();
}

function renderHeader() {
  const { run } = state.model;
  $("#run-name").textContent = run.name || "Run";
  $("#run-when").textContent = `${fmtDate(run.start_local)} · ${fmtTimeOfDay(run.start_local)}`;
  const items = [
    ["Distance", miles(run.distance_m).toFixed(2), "mi"],
    ["Moving time", fmtDur(run.moving_s)],
    ["Avg pace", fmtPace(avgPace(run.moving_s, run.distance_m)), "/mi"],
    ["Avg HR", run.avg_hr ? Math.round(run.avg_hr) : "--", run.avg_hr ? "bpm" : ""],
    ["Cadence", run.avg_cadence_spm ? Math.round(run.avg_cadence_spm) : "--", run.avg_cadence_spm ? "spm" : ""],
    ["Elevation", run.elevation_gain_m != null ? Math.round(run.elevation_gain_m * FT) : "--", run.elevation_gain_m != null ? "ft" : ""],
  ];
  $("#stats").replaceChildren(...items.map(([label, value, unit]) => {
    const dd = el("dd");
    setVal(dd, value, unit);
    return el("div", {}, el("dt", {}, label), dd);
  }));
}

function renderLaps() {
  const head = el("thead", {}, el("tr", {}, ...["Mile", "Pace", "Avg HR", "Max HR"].map((h) => el("th", {}, h))));
  const body = el("tbody", {}, ...state.model.laps.map((l, i) => {
    const full = l.distance_m > MI * 0.95;
    return el("tr", {},
      el("td", {}, full ? String(i + 1) : `${miles(l.distance_m).toFixed(2)} mi`),
      el("td", { class: "pace" }, fmtPace(avgPace(l.moving_s, l.distance_m))),
      el("td", { class: "hr" }, l.avg_hr ? String(Math.round(l.avg_hr)) : "--"),
      el("td", {}, l.max_hr ? String(Math.round(l.max_hr)) : "--"));
  }));
  $("#laps").replaceChildren(head, body);
}

// ---------- map ----------
function setupMap() {
  const { pts, hasGps } = state.model;
  $("#no-gps").hidden = hasGps;
  $(".map-toggle").hidden = !hasGps;
  if (!map) {
    map = L.map("map", { zoomControl: true, attributionControl: true });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
    }).addTo(map);
  }
  segments.forEach((s) => s.remove());
  segments = []; segIndex = []; litUpTo = 0;
  if (runnerMarker) { runnerMarker.remove(); runnerMarker = null; }
  if (!hasGps) { map.setView([43.04, -76.13], 13); return; }

  const gps = pts.map((p, i) => ({ p, i })).filter(({ p }) => p.lat != null);
  for (let k = 1; k < gps.length; k++) {
    segments.push(L.polyline([[gps[k - 1].p.lat, gps[k - 1].p.lng], [gps[k].p.lat, gps[k].p.lng]], {
      weight: 6, opacity: 0.3, lineCap: "round", lineJoin: "round", interactive: false,
    }).addTo(map));
    segIndex.push(gps[k].i);
  }
  recolor();
  map.invalidateSize();
  map.fitBounds(L.latLngBounds(gps.map(({ p }) => [p.lat, p.lng])), { padding: [48, 48] });
  const start = gps[0].p;
  runnerMarker = L.marker([start.lat, start.lng], {
    icon: L.divIcon({ className: "", html: '<div class="runner"></div>', iconSize: [18, 18], iconAnchor: [9, 9] }),
    interactive: false, zIndexOffset: 1000,
  }).addTo(map);
}

function recolor() {
  const { pts } = state.model;
  const key = state.metric === "pace" ? "pace" : "hr";
  const vals = pts.map((p) => p[key]).filter((v) => v != null).sort((a, b) => a - b);
  const lo = vals[Math.floor(vals.length * 0.05)], hi = vals[Math.floor(vals.length * 0.95)];
  segments.forEach((seg, k) => {
    const val = pts[segIndex[k]][key];
    let f = val == null ? 0 : (val - lo) / (hi - lo || 1);
    if (key === "pace") f = 1 - f; // faster (smaller) pace = brighter
    seg.setStyle({ color: ramp(key === "pace" ? PACE_RAMP : HR_RAMP, f) });
  });
}

// ---------- chart ----------
const PAD = { l: 44, r: 44, t: 14, b: 24 };
let chartGeom = null;

function renderChart() {
  const host = $("#chart");
  const { pts, pauses, t0, t1 } = state.model;
  const W = host.clientWidth, H = host.clientHeight;
  if (!W || !H) return;
  const iw = W - PAD.l - PAD.r, ih = H - PAD.t - PAD.b;
  const x = (t) => PAD.l + ((t - t0) / (t1 - t0)) * iw;

  const hrs = pts.map((p) => p.hr).filter((v) => v != null);
  const hrLo = Math.floor(Math.min(...hrs) / 10) * 10, hrHi = Math.ceil(Math.max(...hrs) / 10) * 10;
  const paces = pts.map((p) => p.pace).filter((v) => v != null).sort((a, b) => a - b);
  const pLo = Math.floor(paces[Math.floor(paces.length * 0.02)] * 2) / 2 - 0.5;
  const pHi = Math.ceil(paces[Math.floor(paces.length * 0.98)] * 2) / 2 + 0.5;
  const yHr = (v) => PAD.t + (1 - (v - hrLo) / (hrHi - hrLo)) * ih;
  const yPace = (p) => PAD.t + ((Math.min(pHi, Math.max(pLo, p)) - pLo) / (pHi - pLo)) * ih; // faster = up

  const pathD = (key, y) => {
    let d = "", pen = false;
    pts.forEach((p, i) => {
      if (p[key] == null || (i > 0 && p.t - pts[i - 1].t > PAUSE_GAP)) pen = false;
      if (p[key] == null) return;
      d += `${pen ? "L" : "M"}${x(p.t).toFixed(1)},${y(p[key]).toFixed(1)}`;
      pen = true;
    });
    return d;
  };

  const svg = sv("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Heart rate and pace over the run" });
  svg.append(sv("defs", {}, sv("pattern", { id: "hatch", width: 6, height: 6, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" },
    sv("line", { x1: 0, y1: 0, x2: 0, y2: 6, stroke: "var(--faint)", "stroke-opacity": 0.35, "stroke-width": 2 }))));

  const text = (cls, tx, ty, anchor, label) => sv("text", { class: cls, x: tx, y: ty, "text-anchor": anchor }, label);
  const hrStep = hrHi - hrLo > 60 ? 20 : 10;
  for (let v = hrLo; v <= hrHi; v += hrStep) {
    svg.append(sv("line", { x1: PAD.l, x2: W - PAD.r, y1: yHr(v), y2: yHr(v), stroke: "var(--line)", "stroke-opacity": 0.55 }),
      text("hr-ax", PAD.l - 8, yHr(v) + 4, "end", String(v)));
  }
  for (let p = Math.ceil(pLo); p <= pHi; p += 1) svg.append(text("pace-ax", W - PAD.r + 8, yPace(p) + 4, "start", `${p}:00`));
  const totalMin = (t1 - t0) / 60, tickEvery = totalMin > 40 ? 10 : 5;
  for (let m = 0; m <= totalMin; m += tickEvery) svg.append(text("", x(t0 + m * 60), H - 6, "middle", `${m}m`));

  for (const [a, b] of pauses) {
    svg.append(sv("rect", { x: x(a), y: PAD.t, width: Math.max(2, x(b) - x(a)), height: ih, fill: "url(#hatch)" }));
  }
  svg.append(
    sv("path", { d: pathD("pace", yPace), fill: "none", stroke: "var(--pace)", "stroke-width": 2, "stroke-linejoin": "round", opacity: 0.95 }),
    sv("path", { d: pathD("hr", yHr), fill: "none", stroke: "var(--hr)", "stroke-width": 2.4, "stroke-linejoin": "round" }),
    sv("line", { id: "ph-line", y1: PAD.t, y2: PAD.t + ih, stroke: "var(--text)", "stroke-width": 1.5 }),
    sv("circle", { id: "ph-hr", r: 4.5, fill: "var(--hr)", stroke: "var(--bg)", "stroke-width": 2 }),
    sv("circle", { id: "ph-pace", r: 4.5, fill: "var(--pace)", stroke: "var(--bg)", "stroke-width": 2 }));
  host.replaceChildren(svg);
  chartGeom = { x, yHr, yPace };
}

function movePlayhead(s) {
  if (!chartGeom || !$("#ph-line")) return;
  const px = chartGeom.x(s.t);
  $("#ph-line").setAttribute("x1", px); $("#ph-line").setAttribute("x2", px);
  $("#ph-hr").setAttribute("cx", px);
  $("#ph-hr").setAttribute("cy", s.hr != null ? chartGeom.yHr(s.hr) : -20);
  const p = state.model.pts[s.idx].pace;
  $("#ph-pace").setAttribute("cx", px);
  $("#ph-pace").setAttribute("cy", !s.paused && p != null ? chartGeom.yPace(p) : -20);
}

// ---------- playback ----------
function update() {
  const m = state.model;
  if (!m) return;
  const s = sampleAt(m, state.tau);
  $("#r-time").textContent = fmtDur(s.t - m.t0);
  setVal($("#r-dist"), miles(s.d || 0).toFixed(2), "mi");
  s.paused ? setVal($("#r-pace"), "paused") : setVal($("#r-pace"), fmtPace(paceFromSpeed(s.v)), "/mi");
  s.hr != null ? setVal($("#r-hr"), Math.round(s.hr), "bpm") : setVal($("#r-hr"), "--");
  s.cad ? setVal($("#r-cad"), Math.round(s.cad), "spm") : setVal($("#r-cad"), "--");
  movePlayhead(s);

  if (m.hasGps && runnerMarker && s.lat != null) {
    runnerMarker.setLatLng([s.lat, s.lng]);
    if (!map.getBounds().pad(-0.12).contains([s.lat, s.lng])) map.panTo([s.lat, s.lng], { animate: true, duration: 0.6 });
    // brighten the stretch already run; dim it again if the user scrubs backwards
    let k = litUpTo;
    while (k > 0 && segIndex[k - 1] > s.idx) { segments[k - 1].setStyle({ opacity: 0.3 }); k--; }
    while (k < segments.length && segIndex[k] <= s.idx) { segments[k].setStyle({ opacity: 1 }); k++; }
    litUpTo = k;
  }
}

function frame(now) {
  if (!state.playing) return;
  const dt = Math.min(0.1, (now - state.lastFrame) / 1000);
  state.lastFrame = now;
  state.tau += dt * state.speed;
  if (state.tau >= state.model.t1) { state.tau = state.model.t1; update(); pause(); return; }
  update();
  raf = requestAnimationFrame(frame);
}
function setPlayIcon(path, label) {
  $("#play").replaceChildren(iconSvg(path));
  $("#play").setAttribute("aria-label", label);
}
function play() {
  if (!state.model) return;
  if (state.tau >= state.model.t1) state.tau = state.model.t0;
  state.playing = true;
  state.lastFrame = performance.now();
  setPlayIcon(ICON_PAUSE, "Pause replay");
  $(".map-wrap").classList.remove("is-paused");
  raf = requestAnimationFrame(frame);
}
function pause() {
  state.playing = false;
  cancelAnimationFrame(raf);
  setPlayIcon(ICON_PLAY, "Play replay");
  $(".map-wrap").classList.add("is-paused");
}
const toggle = () => (state.playing ? pause() : play());

// ---------- wiring ----------
function scrubFromEvent(e) {
  const rect = $("#chart").getBoundingClientRect();
  const { t0, t1 } = state.model;
  const f = Math.min(1, Math.max(0, (e.clientX - rect.left - PAD.l) / (rect.width - PAD.l - PAD.r)));
  state.tau = t0 + f * (t1 - t0);
  update();
}
function init() {
  setPlayIcon(ICON_PLAY, "Play replay");
  $(".map-wrap").classList.add("is-paused");
  $("#speed").replaceChildren(...SPEEDS.map((s) =>
    el("button", { type: "button", "data-speed": s, "aria-pressed": String(s === state.speed) }, `${s}x`)));
  $("#speed").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    state.speed = Number(b.dataset.speed);
    $$("#speed button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  });
  $("#play").addEventListener("click", toggle);
  $(".map-toggle").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    state.metric = b.dataset.metric;
    $$(".map-toggle button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    recolor();
  });

  const chart = $("#chart");
  let dragging = false;
  chart.addEventListener("pointerdown", (e) => { if (!state.model) return; dragging = true; chart.setPointerCapture(e.pointerId); scrubFromEvent(e); });
  chart.addEventListener("pointermove", (e) => { if (dragging) scrubFromEvent(e); });
  chart.addEventListener("pointerup", () => (dragging = false));
  chart.addEventListener("keydown", (e) => {
    if (!state.model) return;
    if (e.key === "ArrowRight") { state.tau = Math.min(state.model.t1, state.tau + 30); update(); e.preventDefault(); }
    if (e.key === "ArrowLeft") { state.tau = Math.max(state.model.t0, state.tau - 30); update(); e.preventDefault(); }
  });
  document.addEventListener("keydown", (e) => {
    if (e.code === "Space" && !["BUTTON", "INPUT"].includes(document.activeElement.tagName)) { toggle(); e.preventDefault(); }
  });
  new ResizeObserver(() => { if (state.model) { renderChart(); update(); } }).observe(chart);
}

async function main() {
  init();
  state.runs = await api("/api/runs");
  renderList();
  const hash = new URLSearchParams(location.hash.slice(1)).get("run");
  const first = state.runs.find((r) => r.id === hash) || state.runs[0];
  if (first) await openRun(first.id);
}
main().catch((err) => {
  console.error(err);
  $("#empty").replaceChildren(el("p", {}, `Could not load runs: ${err.message}`));
});
