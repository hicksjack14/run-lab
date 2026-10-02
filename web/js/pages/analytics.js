import { api } from "../lib/api.js";
import { h, s, skeleton, reducedMotion } from "../lib/dom.js";
import { pace, parseLocal, fmtDay, isoDate, addDays } from "../lib/fmt.js";
import { findingBlock, FINDING_KINDS } from "../lib/findings.js";

const lerp = (a, b, f) => a + (b - a) * f;
const oklch = (stops, f) => {
  f = Math.min(1, Math.max(0, f));
  const i = Math.min(stops.length - 2, Math.floor(f * (stops.length - 1)));
  const l = f * (stops.length - 1) - i;
  const [a, b] = [stops[i], stops[i + 1]];
  return `oklch(${lerp(a[0], b[0], l).toFixed(3)} ${lerp(a[1], b[1], l).toFixed(3)} ${lerp(a[2], b[2], l).toFixed(1)})`;
};
const TIME_RAMP = [[0.62, 0.13, 250], [0.87, 0.16, 112], [0.8, 0.17, 45]];             // old (cool) -> new (warm) route
const HR_RAMP = [[0.74, 0.1, 215], [0.76, 0.16, 85], [0.68, 0.22, 28]];                // calm -> hot
const EFF_RAMP = [[0.68, 0.17, 30], [0.78, 0.03, 80], [0.82, 0.15, 150]];              // worse -> par -> better
const hourLabel = (hr) => `${((hr + 11) % 12) + 1}${hr < 12 ? " AM" : " PM"}`;
const ease = (t) => 1 - Math.pow(1 - t, 3);

function countUp(node, to, { decimals = 0, duration = 1800, suffix = "" } = {}) {
  if (reducedMotion()) { node.textContent = to.toFixed(decimals) + suffix; return; }
  const t0 = performance.now();
  const tick = (now) => {
    const f = Math.min(1, (now - t0) / duration);
    node.textContent = (to * ease(f)).toFixed(decimals) + suffix;
    if (f < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

export async function render(view, _params, ctx) {
  view.replaceChildren(h("div", { class: "page" }, skeleton(8)));
  const data = await api.get("/api/analytics");
  if (!data.summary) {
    view.replaceChildren(h("div", { class: "page" }, h("div", { class: "empty-state" }, h("h1", {}, "Nothing to analyze yet"), h("p", {}, "Sync your runs and this page turns them into a story."))));
    return;
  }
  const sm = data.summary, series = data.series;
  const byId = Object.fromEntries(data.findings.map((f) => [f.id, f]));
  const cleanups = [];
  const scenes = [];

  const add = (sc) => { if (sc) scenes.push(sc); };
  add(heroScene(data, cleanups));
  add(buildScene(data, byId));
  if (series.runs.filter((r) => r.hr).length >= 12) add(engineScene(data, byId));
  if (series.runs.length >= 6) add(clockScene(data, byId));
  if (series.zones.seconds.reduce((a, b) => a + b, 0) > 600) add(heartScene(data, byId));
  add(calendarScene(data, byId));
  add(verdictScene(data, ctx));

  const dots = h("nav", { class: "scene-dots", "aria-label": "Jump to a section" },
    scenes.map((sc) => h("button", { type: "button", "aria-label": sc.name, title: sc.name, onclick: () => sc.el.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth" }) })));
  const root = h("div", { class: "an" }, ...scenes.map((sc) => sc.el), dots);
  view.replaceChildren(root);

  const reduce = reducedMotion();
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      const sc = scenes.find((x) => x.el === e.target);
      if (e.isIntersecting && sc && !sc.played) { sc.played = true; sc.el.classList.add("in"); if (sc.play) sc.play(); }
      if (e.isIntersecting) [...dots.children].forEach((d, i) => d.classList.toggle("on", scenes[i].el === e.target));
    }
  }, { threshold: reduce ? 0.01 : 0.3 });
  scenes.forEach((sc) => io.observe(sc.el));
  return () => { io.disconnect(); cleanups.forEach((fn) => fn()); };
}

function sceneShell(id, name, num, title, lede, viz, extra = null) {
  const el = h("section", { class: `scene scene-${id}`, id: `scene-${id}`, "aria-labelledby": `h-${id}` },
    h("div", { class: "scene-inner" },
      h("div", { class: "scene-copy" }, h("p", { class: "scene-num" }, `${num} · ${name}`), h("h2", { id: `h-${id}`, class: "scene-title" }, title), h("p", { class: "scene-lede" }, lede), extra),
      h("div", { class: "scene-viz" }, viz)));
  return { el, name };
}

// ====================================================================== 01 season (hero)
function heroScene(data, cleanups) {
  const sm = data.summary, routes = data.series.routes;
  const numEl = h("span", { class: "hero-num" }, "0.0");
  const canvas = h("canvas", { class: "constellation", role: "img", "aria-label": `${routes.length} runs drawn on top of one another, brighter where you run the same roads` });
  const replay = h("button", { class: "btn btn-quiet", type: "button" }, "Replay season");
  const stat = (k, v) => h("div", {}, h("dt", {}, k), h("dd", {}, v));
  const el = h("section", { class: "scene scene-hero in", id: "scene-hero", "aria-labelledby": "h-hero" },
    canvas,
    h("div", { class: "scene-inner hero-inner" },
      h("div", { class: "scene-copy" },
        h("p", { class: "scene-num" }, `Your season · since ${fmtDay(sm.since, { month: "long", day: "numeric" })}`),
        h("h1", { id: "h-hero", class: "hero-title" }, numEl, h("span", { class: "hero-unit" }, "miles")),
        h("dl", { class: "hero-stats" },
          stat("Runs", String(sm.runs)), stat("Time on feet", `${sm.hours} h`),
          stat("Pace", `${pace(sm.first_pace)} → ${pace(sm.recent_pace)} /mi`), stat("Longest", `${sm.longest_mi} mi`)),
        replay)));
  const view = constellation(canvas, routes);
  const play = () => { countUp(numEl, sm.miles, { decimals: 1, duration: 2200 }); view.play(); };
  replay.addEventListener("click", play);
  requestAnimationFrame(() => requestAnimationFrame(play));
  const ro = new ResizeObserver(() => view.relayout());
  ro.observe(canvas);
  cleanups.push(() => { ro.disconnect(); view.stop(); });
  return { el, name: "Season", played: true };
}

function constellation(canvas, routes) {
  const ctx = canvas.getContext("2d");
  let segs = [], drawn = 0, raf = 0, W = 0, H = 0, duration = 4500, t0 = 0, playing = false;

  function layout() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = canvas.clientWidth; H = canvas.clientHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    segs = [];
    const all = routes.flatMap((r) => r.pts);
    if (all.length < 2) return;
    const lats = all.map((p) => p[0]), lngs = all.map((p) => p[1]);
    const cos = Math.cos((lats.reduce((a, b) => a + b, 0) / lats.length) * Math.PI / 180);
    const minX = Math.min(...lngs), maxX = Math.max(...lngs), minY = Math.min(...lats), maxY = Math.max(...lats);
    const spanX = (maxX - minX) * cos || 1e-6, spanY = maxY - minY || 1e-6;
    // the route art lives on the right ~62% of the screen; the headline sits on the left
    const boxX = W * 0.36, boxW = W * 0.6, boxY = H * 0.08, boxH = H * 0.84;
    const k = Math.min(boxW / spanX, boxH / spanY);
    const ox = boxX + (boxW - spanX * k) / 2, oy = boxY + (boxH - spanY * k) / 2;
    routes.forEach((r, i) => {
      const f = routes.length > 1 ? i / (routes.length - 1) : 1;
      const color = oklch(TIME_RAMP, f);
      for (let j = 1; j < r.pts.length; j++) {
        const a = r.pts[j - 1], b = r.pts[j];
        segs.push([ox + (a[1] - minX) * cos * k, oy + (maxY - a[0]) * k, ox + (b[1] - minX) * cos * k, oy + (maxY - b[0]) * k, color, i === routes.length - 1]);
      }
    });
    duration = Math.min(7000, Math.max(3200, routes.length * 60));
  }
  function paint(from, to) {
    ctx.globalCompositeOperation = "lighter";
    ctx.lineCap = "round"; ctx.lineJoin = "round";
    for (let i = from; i < to; i++) {
      const [x1, y1, x2, y2, color, latest] = segs[i];
      ctx.strokeStyle = color;
      ctx.globalAlpha = latest ? 0.95 : 0.26;
      ctx.lineWidth = latest ? 2.4 : 1.5;
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }
  function clear() { ctx.globalCompositeOperation = "source-over"; ctx.clearRect(0, 0, W, H); drawn = 0; }
  function frame(now) {
    if (!playing) return;
    const p = Math.min(1, (now - t0) / duration);
    const target = Math.floor(p * segs.length);
    paint(drawn, target); drawn = target;
    if (p < 1) raf = requestAnimationFrame(frame); else playing = false;
  }
  layout();
  return {
    play() {
      cancelAnimationFrame(raf); layout(); clear();
      if (reducedMotion()) { paint(0, segs.length); drawn = segs.length; return; }
      playing = true; t0 = performance.now(); raf = requestAnimationFrame(frame);
    },
    relayout() { const was = playing; layout(); clear(); if (!was) { paint(0, segs.length); drawn = segs.length; } else { t0 = performance.now(); } },
    stop() { playing = false; cancelAnimationFrame(raf); },
  };
}

// ====================================================================== 02 build (weekly mileage)
function buildScene(data) {
  const weeks = data.series.weekly;
  const W = 1000, H = 380, pad = { l: 40, r: 10, t: 36, b: 34 };
  const max = Math.max(...weeks.map((w) => w.miles), 10);
  const bw = (W - pad.l - pad.r) / weeks.length;
  const y = (v) => pad.t + (1 - v / max) * (H - pad.t - pad.b);
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, class: "build-chart", role: "img", "aria-label": "Miles per week across the season" });
  for (const v of [0, Math.round(max / 2 / 5) * 5, Math.round(max / 5) * 5]) {
    svg.append(s("line", { x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v), stroke: "var(--line-soft)" }), s("text", { x: pad.l - 8, y: y(v) + 4, "text-anchor": "end", class: "ax" }, String(v)));
  }
  let peak = 0;
  weeks.forEach((w, i) => { if (w.miles > weeks[peak].miles) peak = i; });
  weeks.forEach((w, i) => {
    const prev = weeks[i - 1];
    const spike = prev && prev.miles >= 5 && w.miles > prev.miles * 1.3 && w.miles - prev.miles >= 4;
    const down = prev && prev.miles >= 5 && w.miles < prev.miles * 0.85;
    const x = pad.l + i * bw + bw * 0.15, width = bw * 0.7, hgt = Math.max(0, y(0) - y(w.miles));
    svg.append(s("rect", { class: `bar${spike ? " spike" : ""}${down ? " down" : ""}`, x, y: y(w.miles), width, height: hgt, rx: 2, style: { "--i": i } },
      s("title", {}, `Week of ${fmtDay(w.start)}: ${w.miles.toFixed(1)} mi, ${w.runs} runs${spike ? ` (+${((w.miles / prev.miles - 1) * 100).toFixed(0)}%)` : ""}`)));
    if (spike) svg.append(s("text", { class: "bar-note spike", x: x + width / 2, y: y(w.miles) - 8, "text-anchor": "middle", style: { "--i": i } }, `+${((w.miles / prev.miles - 1) * 100).toFixed(0)}%`));
    if (weeks.length <= 40 ? i % 4 === 0 : i % 8 === 0) svg.append(s("text", { class: "ax", x: x + width / 2, y: H - 10, "text-anchor": "middle" }, fmtDay(w.start)));
  });
  svg.append(s("text", { class: "bar-note peak", x: pad.l + peak * bw + bw / 2, y: y(weeks[peak].miles) - 10, "text-anchor": "middle" }, `peak ${weeks[peak].miles.toFixed(0)} mi`));

  const act = weeks.filter((w) => w.miles > 0);
  const first = act.slice(0, 4), last = act.slice(-4);
  const avg = (a) => a.reduce((t, w) => t + w.miles, 0) / Math.max(1, a.length);
  const spikes = weeks.filter((w, i) => i && weeks[i - 1].miles >= 5 && w.miles > weeks[i - 1].miles * 1.3 && w.miles - weeks[i - 1].miles >= 4).length;
  return sceneShell("build", "Build", "02", `From ${avg(first).toFixed(0)} to ${avg(last).toFixed(0)} miles a week`,
    `Every bar is a week. ${spikes ? `The ${spikes === 1 ? "bar" : spikes + " bars"} in coral jumped more than 30% over the week before: that is where bodies break.` : "No week jumped more than 30% over the one before. That is how volume is built without getting hurt."}`,
    svg);
}

// ====================================================================== 03 engine (pace vs heart rate)
function linfit(pts) {
  const n = pts.length, mx = pts.reduce((a, p) => a + p[0], 0) / n, my = pts.reduce((a, p) => a + p[1], 0) / n;
  let sxx = 0, sxy = 0;
  for (const [x, yv] of pts) { sxx += (x - mx) ** 2; sxy += (x - mx) * (yv - my); }
  const b = sxx ? sxy / sxx : 0;
  return { a: my - b * mx, b };
}

function engineScene(data, byId) {
  // Each run is turned into "the pace you would have held at a fixed heart rate" (speed per heartbeat x that heart rate),
  // so the dots and the trend line show fitness directly, with no regression noise to explain.
  const runs = data.series.runs.filter((r) => r.ef && r.hr);
  const hrSorted = runs.map((r) => r.hr).sort((a, b) => a - b);
  const refHr = Math.round(hrSorted[Math.floor(hrSorted.length / 2)] / 5) * 5;
  const pts = runs.map((r) => ({ day: parseLocal(r.date).getTime() / 86400000, y: (1609.344 / (r.ef * refHr)) * 60, r }));
  const W = 760, H = 460, pad = { l: 56, r: 24, t: 20, b: 44 };
  const d0 = pts[0].day, d1 = pts[pts.length - 1].day || d0 + 1;
  const ys = pts.map((p) => p.y).sort((a, b) => a - b);
  const p0 = Math.floor(ys[Math.floor(ys.length * 0.02)] / 30) * 30 - 30, p1 = Math.ceil(ys[Math.floor(ys.length * 0.98)] / 30) * 30 + 30;
  const X = (d) => pad.l + ((d - d0) / (d1 - d0 || 1)) * (W - pad.l - pad.r);
  const Y = (v) => pad.t + ((Math.min(p1, Math.max(p0, v)) - p0) / (p1 - p0)) * (H - pad.t - pad.b);   // faster pace = higher
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, class: "engine-chart", role: "img",
    "aria-label": `Each run's pace converted to a fixed heart rate of ${refHr} beats per minute, over time. The dots rise as you get fitter.` });
  for (let v = Math.ceil(p0 / 60) * 60; v <= p1; v += 60) svg.append(s("line", { x1: pad.l, x2: W - pad.r, y1: Y(v), y2: Y(v), stroke: "var(--line-soft)" }), s("text", { class: "ax", x: pad.l - 8, y: Y(v) + 4, "text-anchor": "end" }, pace(v)));
  const first = parseLocal(runs[0].date);
  for (let m = new Date(first.getFullYear(), first.getMonth() + 1, 1); m.getTime() / 86400000 <= d1; m = new Date(m.getFullYear(), m.getMonth() + 1, 1)) {
    const x = X(m.getTime() / 86400000);
    svg.append(s("line", { x1: x, x2: x, y1: pad.t, y2: H - pad.b, stroke: "var(--line-soft)" }), s("text", { class: "ax", x, y: H - pad.b + 18, "text-anchor": "middle" }, m.toLocaleDateString(undefined, { month: "short" })));
  }
  svg.append(s("text", { class: "ax-title", x: 14, y: (pad.t + H - pad.b) / 2, "text-anchor": "middle", transform: `rotate(-90 14 ${(pad.t + H - pad.b) / 2})` }, `pace at ${refHr} bpm (min/mi), faster is up`));

  pts.forEach((p, i) => svg.append(s("circle", { class: "dot", cx: X(p.day), cy: Y(p.y), r: 4.5, fill: oklch(TIME_RAMP, pts.length > 1 ? i / (pts.length - 1) : 1), style: { "--i": i } },
    s("title", {}, `${fmtDay(p.r.date)}: ${p.r.miles} mi at ${pace(p.r.pace)}/mi (${p.r.hr} bpm) is the same as ${pace(p.y)}/mi at ${refHr} bpm`))));

  const fit = linfit(pts.map((p) => [p.day, p.y]));
  const yStart = fit.a + fit.b * d0, yEnd = fit.a + fit.b * d1, gain = yStart - yEnd;
  const lineDelay = pts.length * 22 + 300;
  svg.append(s("line", { class: "fit late", x1: X(d0), x2: X(d1), y1: Y(yStart), y2: Y(yEnd), pathLength: 1, style: { "--d": `${lineDelay}ms` } }));
  if (gain > 5) {
    svg.append(s("g", { class: "gain", style: { "--d": `${lineDelay + 900}ms` } },
      s("line", { x1: X(d0), x2: X(d1), y1: Y(yStart), y2: Y(yStart), stroke: "var(--faint)", "stroke-dasharray": "4 4" }),
      s("line", { x1: X(d1) - 6, x2: X(d1) - 6, y1: Y(yStart), y2: Y(yEnd), stroke: "var(--text)", "stroke-width": 1.5 }),
      s("text", { x: X(d1) - 14, y: (Y(yStart) + Y(yEnd)) / 2 + 5, class: "gain-label", "text-anchor": "end" }, `${Math.round(gain)} s/mi faster`)));
  }
  const f = byId["fitness-trend"];
  return sceneShell("engine", "Engine", "03", gain > 5 ? `${Math.round(gain)} seconds a mile faster at the same heartbeat` : "Your engine, run by run",
    `Every dot is a run, converted to the pace you would have held at ${refHr} bpm. Dots rising means the same effort now buys more speed.` +
      (f ? " The careful version, holding distance, time of day and rest steady, is in the verdict below." : ""), svg,
    h("p", { class: "key" }, h("span", { class: "key-dot", style: { background: oklch(TIME_RAMP, 0) } }), "early runs", h("span", { class: "key-dot", style: { background: oklch(TIME_RAMP, 1) } }), "recent runs"));
}

// ====================================================================== 04 clock (time of day)
function clockScene(data, byId) {
  const hours = data.series.hours;
  const S = 460, c = S / 2, r0 = 78, R = c - 36;
  const maxRuns = Math.max(...hours.map((x) => x.runs), 1);
  const withEf = hours.filter((x) => x.ef);
  const meanEf = withEf.reduce((t, x) => t + x.ef * x.runs, 0) / Math.max(1, withEf.reduce((t, x) => t + x.runs, 0));
  const svg = s("svg", { viewBox: `0 0 ${S} ${S}`, class: "clock-chart", role: "img", "aria-label": "When you run, by hour of day, coloured by how efficient those runs were" });
  const pt = (rad, ang) => [c + rad * Math.cos(ang), c + rad * Math.sin(ang)];
  svg.append(s("circle", { cx: c, cy: c, r: r0 - 6, fill: "none", stroke: "var(--line)" }));
  [["12a", 0], ["6a", 6], ["12p", 12], ["6p", 18]].forEach(([lab, hr]) => {
    const [x, y] = pt(R + 20, (hr / 24) * Math.PI * 2 - Math.PI / 2);
    svg.append(s("text", { class: "ax", x, y: y + 4, "text-anchor": "middle" }, lab));
  });
  hours.forEach((x, i) => {
    const a0 = (i / 24) * Math.PI * 2 - Math.PI / 2 + 0.02, a1 = ((i + 1) / 24) * Math.PI * 2 - Math.PI / 2 - 0.02;
    const rad1 = x.runs ? r0 + 14 + (x.runs / maxRuns) * (R - r0 - 14) : r0 + 3;
    const [ax, ay] = pt(r0, a0), [bx, by] = pt(rad1, a0), [cx, cy] = pt(rad1, a1), [dx, dy] = pt(r0, a1);
    const rel = x.ef && meanEf ? x.ef / meanEf - 1 : 0;
    const fill = !x.runs ? "var(--line-soft)" : x.runs < 3 || !x.ef ? "var(--faint)" : oklch(EFF_RAMP, (rel + 0.03) / 0.06);
    svg.append(s("path", { class: "wedge", d: `M${ax},${ay} L${bx},${by} A${rad1},${rad1} 0 0 1 ${cx},${cy} L${dx},${dy} A${r0},${r0} 0 0 0 ${ax},${ay}Z`, fill,
      style: { "--i": i, transformOrigin: `${c}px ${c}px` } },
      s("title", {}, `${hourLabel(i)}: ${x.runs} run${x.runs === 1 ? "" : "s"}, ${x.miles} mi${x.ef && x.runs >= 3 ? `, efficiency ${(rel * 100 >= 0 ? "+" : "") + (rel * 100).toFixed(1)}% vs your average` : ""}`)));
  });
  const busiest = hours.reduce((a, b) => (b.runs > a.runs ? b : a));
  svg.append(s("text", { class: "clock-big", x: c, y: c - 2, "text-anchor": "middle" }, hourLabel(busiest.hour)),
    s("text", { class: "ax", x: c, y: c + 20, "text-anchor": "middle" }, "busiest hour"));
  const f = byId["time-of-day"];
  return sceneShell("clock", "Clock", "04", f ? f.title : `You mostly run around ${hourLabel(busiest.hour).toLowerCase()}`,
    f ? f.body : "Each wedge is an hour of the day, longer meaning more runs. Not enough runs yet to say which time of day suits you best.", svg,
    h("p", { class: "key" }, h("span", { class: "key-dot", style: { background: oklch(EFF_RAMP, 0) } }), "less efficient", h("span", { class: "key-dot", style: { background: oklch(EFF_RAMP, 1) } }), "more efficient",
      h("span", { class: "hint key-note" }, "Colours are raw averages; the headline accounts for effort and distance.")));
}

// ====================================================================== 05 heart (zones)
function heartScene(data, byId) {
  const secs = data.series.zones.seconds, bands = data.series.zones.bands || [], total = secs.reduce((a, b) => a + b, 0);
  const shares = secs.map((v) => (v / total) * 100);
  const S = 420, c = S / 2, r = 150;
  const avgHr = data.summary.avg_hr || 150;
  const svg = s("svg", { viewBox: `0 0 ${S} ${S}`, class: "heart-chart", role: "img", "aria-label": "Share of running time in each heart-rate zone" });
  svg.append(s("circle", { class: "pulse", cx: c, cy: c, r: r - 36, style: { "--beat": `${(120 / avgHr).toFixed(3)}s` } }));
  let acc = 0;
  shares.forEach((sh, i) => {
    const arc = s("circle", { class: "zarc", cx: c, cy: c, r, fill: "none", stroke: oklch(HR_RAMP, i / 4), "stroke-width": 34, pathLength: 100,
      "stroke-dasharray": `${Math.max(0, sh - 0.6)} ${100 - Math.max(0, sh - 0.6)}`, "stroke-dashoffset": -acc, transform: `rotate(-90 ${c} ${c})`, style: { "--i": i } },
      s("title", {}, `Zone ${i + 1}: ${sh.toFixed(0)}% of time`));
    svg.append(arc); acc += sh;
  });
  svg.append(s("text", { class: "heart-big", x: c, y: c + 6, "text-anchor": "middle" }, String(avgHr)), s("text", { class: "ax", x: c, y: c + 30, "text-anchor": "middle" }, "avg bpm"));
  const hours = (v) => `${Math.floor(v / 3600)}h ${String(Math.round((v % 3600) / 60)).padStart(2, "0")}m`;
  const legend = h("ul", { class: "zone-legend big-legend" }, secs.map((v, i) => h("li", {},
    h("span", { class: "zone-key", style: { background: oklch(HR_RAMP, i / 4) } }),
    h("span", {}, `Z${i + 1} ${bands[i] ? bands[i].name : ""}`), h("span", { class: "mono muted" }, bands[i] ? `${bands[i].lo}-${bands[i].hi}` : ""),
    h("span", { class: "mono" }, `${shares[i].toFixed(0)}%`), h("span", { class: "mono muted" }, hours(v)))));
  const f = byId.intensity;
  const hard = shares[3] + shares[4];
  return sceneShell("heart", "Heart", "05", f ? f.title : `${hard.toFixed(0)}% of your time is hard`,
    f ? f.body : `Easy running (zones 1 and 2) should be most of what you do. You spend ${(shares[0] + shares[1]).toFixed(0)}% of your time there and ${hard.toFixed(0)}% in zones 4 and 5.`,
    svg, legend);
}

// ====================================================================== 06 calendar (consistency)
function calendarScene(data, byId) {
  const cal = data.series.calendar, weeks = data.series.weekly;
  const start = weeks[0].start, nWeeks = weeks.length;
  const max = Math.max(...Object.values(cal), 1);
  const cells = [];
  let activeDays = 0;
  for (let w = 0; w < nWeeks; w++) for (let d = 0; d < 7; d++) {
    const iso = addDays(start, w * 7 + d), mi = cal[iso] || 0;
    if (mi) activeDays++;
    cells.push(h("div", { class: `cal-cell${mi ? " on" : ""}`, title: `${fmtDay(iso, { weekday: "short", month: "short", day: "numeric" })}: ${mi ? mi.toFixed(1) + " mi" : "rest"}`,
      style: { gridColumn: w + 1, gridRow: d + 1, "--w": w, "--a": mi ? (0.28 + 0.72 * Math.min(1, mi / max)).toFixed(2) : 0 } }));
  }
  const totalDays = nWeeks * 7;
  const months = [];
  for (let w = 0; w < nWeeks; w += 1) { const d = parseLocal(addDays(start, w * 7)); if (d.getDate() <= 7) months.push(h("span", { class: "cal-month", style: { gridColumn: w + 1 } }, d.toLocaleDateString(undefined, { month: "short" }))); }
  const grid = h("div", { class: "cal-grid", style: { "--cols": nWeeks }, role: "img", "aria-label": `Calendar of ${activeDays} run days out of ${totalDays}` },
    h("div", { class: "cal-months" }, months), h("div", { class: "cal-cells" }, cells));
  const f = byId.consistency;
  return sceneShell("calendar", "Rhythm", "06", `${activeDays} days out of ${totalDays}`,
    f ? f.body : `You ran on ${Math.round((activeDays / totalDays) * 100)}% of days. Each square is a day; brighter means more miles.`, grid);
}

// ====================================================================== 07 verdict
function verdictScene(data, ctx) {
  const columns = [
    ["Going well", "good", data.findings.filter((f) => f.kind === "good")],
    ["Fix next", "improve", data.findings.filter((f) => f.kind === "improve")],
    ["Your patterns", "works", data.findings.filter((f) => f.kind === "works" || f.kind === "doesnt")],
  ];
  const cols = columns.map(([title, kind, items], ci) => h("div", { class: `verdict-col vc-${kind}`, style: { "--ci": ci } },
    h("h3", { class: "vc-title" }, title, h("span", { class: "vc-count mono" }, String(items.length))),
    items.length ? items.map((f, i) => h("div", { class: "vc-item", style: { "--i": i + ci } }, findingBlock(f)))
      : h("p", { class: "muted" }, data.findings.length ? "Nothing here yet." : "More runs needed.")));
  const unclear = data.unclear && data.unclear.length ? h("section", { class: "unclear" }, h("h3", { class: "label" }, "Can't tell yet"),
    h("ul", {}, data.unclear.map((u) => h("li", {}, u.text)))) : null;
  const method = h("details", { class: "method" }, h("summary", {}, "How these findings are worked out"),
    h("p", {}, "Efficiency means speed per heartbeat. Run Lab compares every run's efficiency while holding steady the things that would otherwise muddy the answer: how hard you were working, how far you went, time of day, whether you rested the day before, which shoes, and how hilly the route was. A pattern is only reported when the data backs it up; the dots under each finding show how confident that is and how many runs it rests on."),
    h("p", {}, "With a few months of running these are strong hints, not laws. Treat anything marked low confidence as a question to test, not an answer."));
  const music = ctx.meta.plays ? null : h("p", { class: "music-teaser" }, h("strong", {}, "Music findings are waiting. "), "Import your Spotify history and this page adds which songs, artists and tempos line up with your fastest and easiest miles.");
  return {
    el: h("section", { class: "scene scene-verdict", id: "scene-verdict", "aria-labelledby": "h-verdict" },
      h("div", { class: "scene-inner verdict-inner" },
        h("p", { class: "scene-num" }, "07 · Verdict"), h("h2", { id: "h-verdict", class: "scene-title wide" }, "What you're doing well, what to fix, what works for you"),
        h("p", { class: "scene-lede" }, data.status),
        h("div", { class: "verdict-cols" }, cols), unclear, music, method)),
    name: "Verdict",
  };
}
