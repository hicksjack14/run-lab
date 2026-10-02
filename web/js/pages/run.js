import { api } from "../lib/api.js";
import { h, s, $, $$, skeleton, reducedMotion } from "../lib/dom.js";
import { MI, miles, FT, pace, paceFromSpeed, avgPace, dur, fmtLongDay, fmtClock } from "../lib/fmt.js";

const PAUSE_GAP = 60;   // seconds between samples that counts as a watch pause
const SPEEDS = [10, 30, 60, 120];
const PAD = { l: 44, r: 44, t: 14, b: 24 };
const lerp = (a, b, f) => a + (b - a) * f;

const PACE_RAMP = [[0.5, 0.1, 268], [0.7, 0.11, 242], [0.9, 0.09, 215]];   // slow deep blue -> fast pale sky
const HR_RAMP = [[0.74, 0.1, 215], [0.76, 0.16, 85], [0.68, 0.22, 28]];        // calm -> hot
function ramp(stops, f) {
  f = Math.min(1, Math.max(0, f));
  const i = Math.min(stops.length - 2, Math.floor(f * (stops.length - 1)));
  const local = f * (stops.length - 1) - i;
  const [a, b] = [stops[i], stops[i + 1]];
  return `oklch(${lerp(a[0], b[0], local).toFixed(3)} ${lerp(a[1], b[1], local).toFixed(3)} ${lerp(a[2], b[2], local).toFixed(1)})`;
}
const songColor = (artist = "") => {
  let hash = 0;
  for (const ch of artist) hash = (hash * 31 + ch.charCodeAt(0)) % 360;
  return `oklch(0.72 0.12 ${hash})`;
};
const EFFORT_LABELS = { Fastest400: "400 m", FastestHalfMile: "1/2 mile", Fastest1k: "1 km", FastestMile: "1 mile", Fastest2Mile: "2 mile",
  Fastest5k: "5K", Fastest10k: "10K", Fastest15k: "15K", Fastest10Mile: "10 mile", Fastest20k: "20K", FastestHalfMarathon: "Half marathon" };

function buildModel(data) {
  const { run, streams, laps } = data;
  const n = streams.t.length;
  const pts = [];
  for (let i = 0; i < n; i++) {
    pts.push({ t: streams.t[i], hr: streams.hr[i], v: streams.speed[i], cad: streams.cadence[i], d: streams.dist[i],
      moving: streams.moving[i], lat: streams.lat[i], lng: streams.lng[i] });
  }
  pts.forEach((p, i) => {
    let sum = 0, c = 0;
    for (let j = Math.max(0, i - 2); j <= Math.min(n - 1, i + 2); j++) {
      const q = pts[j];
      if (q.v && q.v >= 0.8 && q.moving !== false) { sum += q.v; c++; }
    }
    p.pace = c >= 2 ? paceFromSpeed(sum / c) : null;   // seconds per mile
  });
  const pauses = [];
  for (let i = 1; i < n; i++) if (pts[i].t - pts[i - 1].t > PAUSE_GAP) pauses.push([pts[i - 1].t, pts[i].t]);
  return { run, laps, pts, pauses, songs: data.songs || [], t0: pts[0].t, t1: pts[n - 1].t,
    hasGps: run.has_gps && pts.some((p) => p.lat != null) };
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
  return { idx: lo, paused, t: tau, lat: mix(a.lat, b.lat), lng: mix(a.lng, b.lng), hr: mix(a.hr, b.hr),
    v: paused ? 0 : mix(a.v, b.v), cad: paused ? 0 : mix(a.cad, b.cad), d: mix(a.d, b.d) };
}

function stat(label, value, unit) {
  return h("div", {}, h("dt", {}, label), h("dd", {}, String(value), unit ? h("small", {}, unit) : null));
}

export async function render(view, [id], ctx) {
  view.replaceChildren(h("div", { class: "page" }, skeleton(10)));
  const data = await api.get(`/api/runs/${id}`);
  const model = buildModel(data);
  const { run } = model;
  const st = { tau: model.t0, playing: false, speed: 30, metric: "pace", last: 0 };
  let map, marker, segments = [], segIndex = [], lit = 0, raf = 0, geom = null;

  // ---------- header ----------
  const movingS = run.moving_s, stopped = (run.elapsed_s || 0) - (movingS || 0);
  const stats = h("dl", { class: "stats" },
    stat("Distance", miles(run.distance_m).toFixed(2), "mi"), stat("Moving time", dur(movingS)),
    stat("Avg pace", pace(avgPace(movingS, run.distance_m)), "/mi"),
    run.avg_hr ? stat("Avg HR", Math.round(run.avg_hr), "bpm") : null, run.max_hr ? stat("Max HR", Math.round(run.max_hr), "bpm") : null,
    run.avg_cadence_spm ? stat("Cadence", Math.round(run.avg_cadence_spm), "spm") : null,
    run.elevation_gain_m != null ? stat("Climb", Math.round(run.elevation_gain_m * FT), "ft") : null,
    stopped > 30 ? stat("Stopped", dur(stopped)) : null, run.effort ? stat("Effort", run.effort) : null);
  const nav = h("nav", { class: "run-nav", "aria-label": "Neighbouring runs" },
    data.prev ? h("a", { href: `#/runs/${data.prev}`, class: "btn btn-quiet" }, "← Earlier") : h("span"),
    h("a", { href: "#/runs", class: "btn btn-quiet" }, "All runs"),
    data.next ? h("a", { href: `#/runs/${data.next}`, class: "btn btn-quiet" }, "Later →") : null);
  const head = h("header", { class: "run-head" },
    h("div", {}, nav, h("p", { class: "eyebrow" }, `${fmtLongDay(run.start_local)} · ${fmtClock(run.start_local)}`),
      h("h1", {}, run.name || "Run"), run.gear ? h("p", { class: "muted" }, run.gear) : null), stats);

  // ---------- map + transport + chart ----------
  const mapEl = h("div", { id: "map", role: "img", "aria-label": "Map of the run route" });
  const songCard = h("div", { class: "song-card", hidden: true });
  const metricBtns = ["pace", "hr"].map((m) => h("button", { type: "button", "aria-pressed": String(m === st.metric), dataset: { metric: m },
    onclick: () => { st.metric = m; metricBtns.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.metric === m))); recolor(); } },
    m === "pace" ? "Pace" : "Heart rate"));
  const mapWrap = h("section", { class: "map-wrap is-paused", "aria-label": "Route replay" }, mapEl,
    model.hasGps ? h("div", { class: "map-toggle", role: "group", "aria-label": "Colour route by" }, metricBtns) : null, songCard,
    model.hasGps ? null : h("p", { class: "no-gps" }, "No GPS on this run, so there is no route to replay."));

  const playBtn = h("button", { type: "button", class: "play", "aria-label": "Play replay" });
  const speedBtns = SPEEDS.map((v) => h("button", { type: "button", "aria-pressed": String(v === st.speed), dataset: { v },
    onclick: () => { st.speed = v; speedBtns.forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.v) === v))); } }, `${v}x`));
  const live = {
    time: h("span", { class: "v" }), dist: h("span", { class: "v" }), pace: h("span", { class: "v" }), hr: h("span", { class: "v" }), cad: h("span", { class: "v" }),
  };
  const cell = (label, node, cls = "") => h("div", { class: `cell ${cls}` }, h("span", { class: "lbl" }, label), node);
  const transport = h("section", { class: "transport", "aria-label": "Replay controls" }, playBtn,
    h("div", { class: "speed", role: "group", "aria-label": "Replay speed" }, speedBtns),
    h("div", { class: "live" }, cell("Time", live.time), cell("Distance", live.dist), cell("Pace", live.pace, "pace"),
      cell("Heart rate", live.hr, "hr"), cell("Cadence", live.cad)));

  const chart = h("div", { class: "chart", tabindex: "0", "aria-label": "Timeline. Left and right arrow keys scrub, space plays." });
  const songLane = h("div", { class: "songs-lane" }, h("span", { class: "lane-label" }, "Songs"));
  const timeline = h("section", { class: "timeline", "aria-label": "Pace and heart rate over time" }, chart, songLane);

  // ---------- lower: splits, zones, efforts ----------
  const splits = h("table", { class: "mini-table" },
    h("thead", {}, h("tr", {}, ["Mile", "Pace", "Avg HR", "Max HR"].map((t) => h("th", {}, t)))),
    h("tbody", {}, model.laps.map((l, i) => h("tr", {},
      h("td", {}, l.distance_m > MI * 0.95 ? String(i + 1) : `${miles(l.distance_m).toFixed(2)} mi`),
      h("td", { class: "pace-c" }, pace(avgPace(l.moving_s, l.distance_m))),
      h("td", { class: "hr-c" }, l.avg_hr ? String(Math.round(l.avg_hr)) : "--"), h("td", {}, l.max_hr ? String(Math.round(l.max_hr)) : "--")))));
  const lower = h("div", { class: "run-lower" },
    h("section", {}, h("h2", { class: "label" }, "Splits"), splits),
    h("section", { class: "run-lower-side" }, zoneBlock(data), effortsBlock(data)));

  const seekTo = (t) => { st.tau = Math.max(model.t0, t); update(); window.scrollTo({ top: mapWrap.getBoundingClientRect().top + scrollY - 80, behavior: reducedMotion() ? "auto" : "smooth" }); };
  const songsSection = model.songs.length ? h("section", { class: "songs-table-wrap", "aria-label": "Songs on this run" },
    h("h2", { class: "label" }, "Songs on this run"),
    h("table", { class: "mini-table songs-table" },
      h("thead", {}, h("tr", {}, ["Song", "At", "Pace", "HR", "Cadence"].map((t) => h("th", {}, t)))),
      h("tbody", {}, model.songs.map((sg) => h("tr", { class: "song-row" },
        h("td", {}, h("button", { type: "button", class: "song-link", title: "Jump the replay to this song", onclick: () => seekTo(sg.start_s) },
          h("span", { class: "song-dot", style: { background: songColor(sg.artist) } }), h("span", { class: "song-text" }, h("strong", {}, sg.track), h("span", { class: "muted" }, sg.artist || "")))),
        h("td", { class: "mono" }, dur(sg.start_s - model.t0)),
        h("td", { class: "pace-c" }, sg.avg_pace ? pace(sg.avg_pace) : "--"),
        h("td", { class: "hr-c" }, sg.avg_hr ? String(Math.round(sg.avg_hr)) : "--"),
        h("td", {}, sg.avg_cadence ? String(Math.round(sg.avg_cadence)) : "--")))))) : null;

  view.replaceChildren(h("div", { class: "page run-page" }, head, mapWrap, transport, timeline, lower, songsSection));

  // songs lane (filled once the Spotify import exists)
  if (model.songs.length) {
    const span = model.t1 - model.t0;
    for (const song of model.songs) {
      songLane.append(h("button", { type: "button", class: "song-band", title: `${song.track} · ${song.artist}`,
        style: { left: `${((song.start_s - model.t0) / span) * 100}%`, width: `${Math.max(0.6, ((song.end_s - song.start_s) / span) * 100)}%`, background: songColor(song.artist) },
        onclick: () => { st.tau = Math.max(model.t0, song.start_s); update(); } }, h("span", {}, song.track)));
    }
  } else {
    songLane.append(h("span", { class: "lane-empty" }, ctx.meta.plays ? "No songs overlap this run." : "Import your Spotify history to see what was playing at each point."));
  }

  // ---------- map ----------
  function setupMap() {
    if (!model.hasGps) return;
    map = L.map(mapEl, { zoomControl: true, attributionControl: true });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors', maxZoom: 19 }).addTo(map);
    const gps = model.pts.map((p, i) => ({ p, i })).filter(({ p }) => p.lat != null);
    for (let k = 1; k < gps.length; k++) {
      segments.push(L.polyline([[gps[k - 1].p.lat, gps[k - 1].p.lng], [gps[k].p.lat, gps[k].p.lng]],
        { weight: 6, opacity: 0.3, lineCap: "round", lineJoin: "round", interactive: false }).addTo(map));
      segIndex.push(gps[k].i);
    }
    recolor();
    map.fitBounds(L.latLngBounds(gps.map(({ p }) => [p.lat, p.lng])), { padding: [48, 48] });
    marker = L.marker([gps[0].p.lat, gps[0].p.lng], { icon: L.divIcon({ className: "", html: '<div class="runner"></div>', iconSize: [18, 18], iconAnchor: [9, 9] }),
      interactive: false, zIndexOffset: 1000 }).addTo(map);
  }
  function recolor() {
    const key = st.metric;
    const vals = model.pts.map((p) => p[key]).filter((v) => v != null).sort((a, b) => a - b);
    const lo = vals[Math.floor(vals.length * 0.05)], hi = vals[Math.floor(vals.length * 0.95)];
    segments.forEach((seg, k) => {
      const v = model.pts[segIndex[k]][key];
      let f = v == null ? 0 : (v - lo) / (hi - lo || 1);
      if (key === "pace") f = 1 - f;
      seg.setStyle({ color: ramp(key === "pace" ? PACE_RAMP : HR_RAMP, f) });
    });
  }

  // ---------- chart ----------
  function renderChart() {
    const W = chart.clientWidth, H = chart.clientHeight;
    if (!W || !H) return;
    const { pts, pauses, t0, t1 } = model;
    const iw = W - PAD.l - PAD.r, ih = H - PAD.t - PAD.b;
    const x = (t) => PAD.l + ((t - t0) / (t1 - t0)) * iw;
    const hrs = pts.map((p) => p.hr).filter((v) => v != null);
    const paces = pts.map((p) => p.pace).filter((v) => v != null).sort((a, b) => a - b);
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Heart rate and pace over the run" });
    if (!hrs.length || paces.length < 5) { chart.replaceChildren(svg); geom = null; return; }
    const hrLo = Math.floor(Math.min(...hrs) / 10) * 10, hrHi = Math.ceil(Math.max(...hrs) / 10) * 10;
    const pLo = Math.floor(paces[Math.floor(paces.length * 0.02)] / 30) * 30 - 30, pHi = Math.ceil(paces[Math.floor(paces.length * 0.98)] / 30) * 30 + 30;
    const yHr = (v) => PAD.t + (1 - (v - hrLo) / (hrHi - hrLo)) * ih;
    const yPace = (p) => PAD.t + ((Math.min(pHi, Math.max(pLo, p)) - pLo) / (pHi - pLo)) * ih;
    const path = (key, y) => {
      let d = "", pen = false;
      pts.forEach((p, i) => {
        if (p[key] == null || (i > 0 && p.t - pts[i - 1].t > PAUSE_GAP)) pen = false;
        if (p[key] == null) return;
        d += `${pen ? "L" : "M"}${x(p.t).toFixed(1)},${y(p[key]).toFixed(1)}`;
        pen = true;
      });
      return d;
    };
    svg.append(s("defs", {}, s("pattern", { id: "hatch", width: 6, height: 6, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" },
      s("line", { x1: 0, y1: 0, x2: 0, y2: 6, stroke: "var(--faint)", "stroke-opacity": 0.35, "stroke-width": 2 }))));
    const txt = (cls, tx, ty, anchor, label) => s("text", { class: cls, x: tx, y: ty, "text-anchor": anchor }, label);
    const step = hrHi - hrLo > 60 ? 20 : 10;
    for (let v = hrLo; v <= hrHi; v += step) {
      svg.append(s("line", { x1: PAD.l, x2: W - PAD.r, y1: yHr(v), y2: yHr(v), stroke: "var(--line)", "stroke-opacity": 0.55 }), txt("hr-ax", PAD.l - 8, yHr(v) + 4, "end", String(v)));
    }
    for (let p = Math.ceil(pLo / 60) * 60; p <= pHi; p += 60) svg.append(txt("pace-ax", W - PAD.r + 8, yPace(p) + 4, "start", pace(p)));
    const totalMin = (t1 - t0) / 60, every = totalMin > 60 ? 15 : totalMin > 30 ? 10 : 5;
    for (let m = 0; m <= totalMin; m += every) svg.append(txt("", x(t0 + m * 60), H - 6, "middle", `${m}m`));
    for (const [a, b] of pauses) svg.append(s("rect", { x: x(a), y: PAD.t, width: Math.max(2, x(b) - x(a)), height: ih, fill: "url(#hatch)" }));
    svg.append(
      s("path", { d: path("pace", yPace), fill: "none", stroke: "var(--pace)", "stroke-width": 2, "stroke-linejoin": "round", opacity: 0.95 }),
      s("path", { d: path("hr", yHr), fill: "none", stroke: "var(--hr)", "stroke-width": 2.4, "stroke-linejoin": "round" }),
      s("line", { id: "ph-line", y1: PAD.t, y2: PAD.t + ih, stroke: "var(--text)", "stroke-width": 1.5 }),
      s("circle", { id: "ph-hr", r: 4.5, fill: "var(--hr)", stroke: "var(--bg)", "stroke-width": 2 }),
      s("circle", { id: "ph-pace", r: 4.5, fill: "var(--pace)", stroke: "var(--bg)", "stroke-width": 2 }));
    chart.replaceChildren(svg);
    geom = { x, yHr, yPace };
  }

  function movePlayhead(sm) {
    if (!geom) return;
    const px = geom.x(sm.t);
    const line = $("#ph-line", chart), hrDot = $("#ph-hr", chart), paceDot = $("#ph-pace", chart);
    if (!line) return;
    line.setAttribute("x1", px); line.setAttribute("x2", px);
    hrDot.setAttribute("cx", px); hrDot.setAttribute("cy", sm.hr != null ? geom.yHr(sm.hr) : -20);
    const p = model.pts[sm.idx].pace;
    paceDot.setAttribute("cx", px); paceDot.setAttribute("cy", !sm.paused && p != null ? geom.yPace(p) : -20);
  }

  // ---------- playback ----------
  const setLive = (node, value, unit) => { node.replaceChildren(String(value)); if (unit) node.append(h("small", {}, unit)); };
  function update() {
    const sm = sampleAt(model, st.tau);
    setLive(live.time, dur(sm.t - model.t0));
    setLive(live.dist, miles(sm.d || 0).toFixed(2), "mi");
    sm.paused ? setLive(live.pace, "paused") : setLive(live.pace, pace(paceFromSpeed(sm.v)), "/mi");
    sm.hr != null ? setLive(live.hr, Math.round(sm.hr), "bpm") : setLive(live.hr, "--");
    sm.cad ? setLive(live.cad, Math.round(sm.cad), "spm") : setLive(live.cad, "--");
    movePlayhead(sm);
    const song = model.songs.find((x) => sm.t >= x.start_s && sm.t < x.end_s);
    songCard.hidden = !song;
    if (song) songCard.replaceChildren(h("span", { class: "song-dot", style: { background: songColor(song.artist) } }), h("div", {}, h("strong", {}, song.track), h("span", { class: "muted" }, song.artist)));
    if (model.hasGps && marker && sm.lat != null) {
      marker.setLatLng([sm.lat, sm.lng]);
      if (!map.getBounds().pad(-0.12).contains([sm.lat, sm.lng])) map.panTo([sm.lat, sm.lng], { animate: true, duration: 0.6 });
      let k = lit;
      while (k > 0 && segIndex[k - 1] > sm.idx) { segments[k - 1].setStyle({ opacity: 0.3 }); k--; }
      while (k < segments.length && segIndex[k] <= sm.idx) { segments[k].setStyle({ opacity: 1 }); k++; }
      lit = k;
    }
  }
  const iconPath = (d) => s("svg", { viewBox: "0 0 24 24", "aria-hidden": "true" }, s("path", { d }));
  function setIcon(playing) {
    playBtn.replaceChildren(iconPath(playing ? "M7 5h4v14H7zM13 5h4v14h-4z" : "M8 5v14l11-7z"));
    playBtn.setAttribute("aria-label", playing ? "Pause replay" : "Play replay");
    mapWrap.classList.toggle("is-paused", !playing);
  }
  function frame(now) {
    if (!st.playing) return;
    const dt = Math.min(0.1, (now - st.last) / 1000);
    st.last = now;
    st.tau += dt * st.speed;
    if (st.tau >= model.t1) { st.tau = model.t1; update(); pause(); return; }
    update();
    raf = requestAnimationFrame(frame);
  }
  function play() {
    if (st.tau >= model.t1) st.tau = model.t0;
    st.playing = true; st.last = performance.now(); setIcon(true);
    raf = requestAnimationFrame(frame);
  }
  function pause() { st.playing = false; cancelAnimationFrame(raf); setIcon(false); }
  const toggle = () => (st.playing ? pause() : play());
  playBtn.addEventListener("click", toggle);

  // ---------- scrubbing + keys ----------
  function scrub(e) {
    const rect = chart.getBoundingClientRect();
    const f = Math.min(1, Math.max(0, (e.clientX - rect.left - PAD.l) / (rect.width - PAD.l - PAD.r)));
    st.tau = model.t0 + f * (model.t1 - model.t0);
    update();
  }
  let dragging = false;
  chart.addEventListener("pointerdown", (e) => { dragging = true; chart.setPointerCapture(e.pointerId); scrub(e); });
  chart.addEventListener("pointermove", (e) => { if (dragging) scrub(e); });
  chart.addEventListener("pointerup", () => (dragging = false));
  chart.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") { st.tau = Math.min(model.t1, st.tau + 30); update(); e.preventDefault(); }
    if (e.key === "ArrowLeft") { st.tau = Math.max(model.t0, st.tau - 30); update(); e.preventDefault(); }
  });
  const onKey = (e) => { if (e.code === "Space" && !["BUTTON", "INPUT", "SELECT"].includes(document.activeElement.tagName)) { toggle(); e.preventDefault(); } };
  document.addEventListener("keydown", onKey);
  const ro = new ResizeObserver(() => { renderChart(); update(); });
  ro.observe(chart);

  setIcon(false);
  setupMap();
  renderChart();
  update();
  if (map) setTimeout(() => map.invalidateSize(), 0);

  return () => { pause(); ro.disconnect(); document.removeEventListener("keydown", onKey); if (map) map.remove(); };
}

function zoneBlock(data) {
  if (!data.zone_secs || !data.hr_zones) return h("div");
  const total = data.zone_secs.reduce((a, b) => a + b, 0);
  if (total < 60) return h("div");
  return h("div", { class: "zone-block" }, h("h2", { class: "label" }, "Time in heart-rate zones"),
    h("div", { class: "zone-bar", role: "img", "aria-label": "Share of time in each heart-rate zone" },
      data.zone_secs.map((sec, i) => h("div", { class: "zone-seg", style: { flex: String(sec), background: ramp(HR_RAMP, i / 4) },
        title: `Zone ${i + 1}: ${dur(sec)}` }))),
    h("ul", { class: "zone-legend" }, data.hr_zones.map((z, i) => h("li", {},
      h("span", { class: "zone-key", style: { background: ramp(HR_RAMP, i / 4) } }),
      h("span", { class: "zone-name" }, `Z${z.zone} ${z.name}`), h("span", { class: "mono muted" }, `${z.lo}-${z.hi}`),
      h("span", { class: "mono zone-time" }, dur(data.zone_secs[i]))))),
    h("p", { class: "hint" }, `Zones use max HR ${data.max_hr} bpm.`));
}

function effortsBlock(data) {
  const efforts = (data.best_efforts || []).filter((e) => EFFORT_LABELS[e.type]);
  if (!efforts.length) return h("div");
  return h("div", {}, h("h2", { class: "label" }, "Best efforts in this run"),
    h("ul", { class: "efforts" }, efforts.map((e) => h("li", {}, h("span", {}, EFFORT_LABELS[e.type]), h("span", { class: "mono" }, dur(e.seconds))))));
}
