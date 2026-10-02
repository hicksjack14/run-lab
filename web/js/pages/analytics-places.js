// Places: where your runs have taken place, how it spread over time, how much new ground you cover.
// Everything is computed from your own GPS on this machine. Map tiles are the only thing fetched from outside (like the run map).
import { api } from "../lib/api.js";
import { h, s, skeleton, reducedMotion } from "../lib/dom.js";
import { fmtDay, parseLocal } from "../lib/fmt.js";

const lerp = (a, b, f) => a + (b - a) * f;
const TIME_RAMP = [[0.62, 0.13, 250], [0.87, 0.16, 112], [0.8, 0.17, 45]];
function ramp(f) {
  f = Math.min(1, Math.max(0, f));
  const i = Math.min(TIME_RAMP.length - 2, Math.floor(f * (TIME_RAMP.length - 1))), l = f * (TIME_RAMP.length - 1) - i;
  const [a, b] = [TIME_RAMP[i], TIME_RAMP[i + 1]];
  return `oklch(${lerp(a[0], b[0], l).toFixed(3)} ${lerp(a[1], b[1], l).toFixed(3)} ${lerp(a[2], b[2], l).toFixed(1)})`;
}
const SQ_MI_PER_CELL = (250 / 1609.344) ** 2;

export async function render(view, ctx) {
  view.replaceChildren(h("div", { class: "page" }, skeleton(8)));
  const data = await api.get("/api/places");
  const routes = data.routes;
  if (!routes.length) {
    view.replaceChildren(h("div", { class: "page" }, h("div", { class: "empty-state" }, h("p", { class: "eyebrow" }, "Analytics · Places"), h("h1", {}, "No GPS runs yet"),
      h("p", {}, "Runs recorded with GPS show up here as a map of everywhere you've run. Treadmill runs don't have a route."))));
    return;
  }

  const ex = data.exploration, last = ex.monthly[ex.monthly.length - 1];
  const sqMi = ex.cells_total * SQ_MI_PER_CELL;
  const atHome = routes.length ? Math.round((data.home.runs / routes.length) * 100) : 0;

  // ---------- map ----------
  const mapEl = h("div", { id: "places-map", role: "img", "aria-label": "Map of every place you have run" });
  const dateLabel = h("span", { class: "mono pl-date" });
  const slider = h("input", { type: "range", min: 1, max: routes.length, value: routes.length, "aria-label": "Show runs up to this date", class: "pl-slider" });
  const playBtn = h("button", { type: "button", class: "btn btn-quiet" }, "Replay");
  const mapWrap = h("section", { class: "pl-map", "aria-label": "Route map" }, mapEl,
    h("div", { class: "pl-controls" }, playBtn, slider, dateLabel));

  // ---------- side ----------
  const stat = (big, label, extra) => h("div", { class: "pl-stat" }, h("span", { class: "big mono" }, big), h("span", { class: "label" }, label), extra || null);
  const areaItems = data.areas.map((a, i) => h("li", {}, h("button", { type: "button", class: "area-btn", onclick: () => map.flyTo([a.lat, a.lng], 15, { duration: 0.8 }) },
    h("span", { class: "area-rank mono" }, String(i + 1)),
    h("span", { class: "area-name" }, i === 0 ? "Home base" : `Start area ${i + 1}`, h("small", { class: "muted" }, ` last ${fmtDay(a.last)}`)),
    h("span", { class: "mono" }, `${a.runs} runs`), h("span", { class: "mono muted" }, `${a.miles.toFixed(0)} mi`))));
  const side = h("aside", { class: "pl-side" },
    h("div", { class: "pl-stats" },
      stat(`${sqMi.toFixed(1)}`, "sq mi of ground covered", h("p", { class: "hint" }, `${ex.cells_total.toLocaleString()} squares of ${ex.cell_m} m`)),
      stat(`${data.farthest.miles.toFixed(1)}`, "miles from home, furthest", h("a", { class: "link", href: `#/runs/${data.farthest.run_id}` }, fmtDay(data.farthest.date, { month: "short", day: "numeric" }) + " →")),
      stat(`${atHome}%`, "of runs start at home base")),
    h("section", {}, h("h2", { class: "label" }, "Ground covered over time"), groundChart(ex)),
    h("section", {}, h("h2", { class: "label" }, "New ground each month"), newGroundChart(ex.monthly),
      last ? h("p", { class: "muted pl-note" }, `${monthName(last.month)}: ${Math.round(last.share_new * 100)}% of the ground you covered was new to you.`) : null),
    h("section", {}, h("h2", { class: "label" }, "Where your runs start"), h("ul", { class: "area-list" }, areaItems),
      h("p", { class: "hint" }, "Places are shown as start areas, not street names: Run Lab never sends your locations to a lookup service.")));

  view.replaceChildren(h("div", { class: "page places" },
    h("header", { class: "page-head" }, h("div", {}, h("p", { class: "eyebrow" }, "Analytics · Places"), h("h1", {}, "Where you run")),
      h("p", { class: "muted pl-lede" }, `${routes.length} runs, ${sqMi.toFixed(1)} square miles of ground since ${fmtDay(routes[0].date, { month: "long", day: "numeric" })}.`)),
    h("div", { class: "pl-main" }, mapWrap, side)));

  // ---------- leaflet ----------
  const map = L.map(mapEl, { zoomControl: true });
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors', maxZoom: 19 }).addTo(map);
  const lines = routes.map((r, i) => {
    const line = L.polyline(r.pts, { color: ramp(routes.length > 1 ? i / (routes.length - 1) : 1), weight: 2.5, opacity: 0.2, lineCap: "round", lineJoin: "round" }).addTo(map);
    line.bindTooltip(`${fmtDay(r.date, { weekday: "short", month: "short", day: "numeric" })} · ${r.miles} mi`, { sticky: true });
    line.on("click", () => { location.hash = `#/runs/${r.id}`; });
    return line;
  });
  const bounds = L.latLngBounds(routes.flatMap((r) => r.pts));
  map.fitBounds(bounds, { padding: [40, 40] });
  L.circleMarker([data.home.lat, data.home.lng], { radius: 9, color: "#fff", weight: 2, fillColor: "#000", fillOpacity: 0.55 }).addTo(map).bindTooltip("Home base", { permanent: false });
  L.circleMarker([data.farthest.lat, data.farthest.lng], { radius: 7, color: "#fff", weight: 2, fillColor: "#e8654a", fillOpacity: 0.9 }).addTo(map)
    .bindTooltip(`Furthest: ${data.farthest.miles.toFixed(1)} mi from home`, { permanent: false });
  setTimeout(() => map.invalidateSize(), 0);

  // ---------- time slider ----------
  let timer = 0;
  function show(n) {
    n = Math.max(1, Math.min(routes.length, n));
    lines.forEach((line, i) => {
      const visible = i < n, newest = i === n - 1;
      line.setStyle({ opacity: visible ? (newest && n < routes.length ? 1 : 0.2) : 0, weight: newest && n < routes.length ? 5 : 2.5 });
      if (newest && n < routes.length) line.bringToFront();
    });
    slider.value = String(n);
    dateLabel.textContent = n === routes.length ? `All ${n} runs` : `${fmtDay(routes[n - 1].date, { month: "short", day: "numeric" })} · run ${n} of ${routes.length}`;
  }
  slider.addEventListener("input", () => { clearInterval(timer); playBtn.textContent = "Replay"; show(Number(slider.value)); });
  playBtn.addEventListener("click", () => {
    clearInterval(timer);
    if (reducedMotion()) { show(routes.length); return; }
    let n = 0;
    playBtn.textContent = "Playing…";
    timer = setInterval(() => { n += 1; show(n); if (n >= routes.length) { clearInterval(timer); playBtn.textContent = "Replay"; } }, Math.max(40, Math.min(160, 6000 / routes.length)));
  });
  show(routes.length);

  return () => { clearInterval(timer); map.remove(); };
}

const monthName = (ym) => parseLocal(`${ym}-01`).toLocaleDateString(undefined, { month: "long" });

function groundChart(ex) {
  const W = 360, H = 140, pad = { l: 34, r: 8, t: 8, b: 20 }, pts = ex.cumulative;
  const maxV = Math.max(...pts.map((p) => p.cells * SQ_MI_PER_CELL), 1);
  const t0 = parseLocal(pts[0].date).getTime(), t1 = parseLocal(pts[pts.length - 1].date).getTime() || t0 + 1;
  const X = (d) => pad.l + ((parseLocal(d).getTime() - t0) / (t1 - t0 || 1)) * (W - pad.l - pad.r);
  const Y = (v) => pad.t + (1 - v / maxV) * (H - pad.t - pad.b);
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, class: "mini-chart", role: "img", "aria-label": "Square miles of ground covered, growing over time" });
  for (const v of [0, maxV / 2, maxV]) svg.append(s("line", { x1: pad.l, x2: W - pad.r, y1: Y(v), y2: Y(v), stroke: "var(--line-soft)" }), s("text", { class: "ax", x: pad.l - 6, y: Y(v) + 4, "text-anchor": "end" }, v.toFixed(v < 10 ? 1 : 0)));
  let d = `M${X(pts[0].date)},${Y(pts[0].cells * SQ_MI_PER_CELL)}`;
  for (const p of pts) d += ` L${X(p.date).toFixed(1)},${Y(p.cells * SQ_MI_PER_CELL).toFixed(1)}`;
  svg.append(s("path", { d: `${d} L${X(pts[pts.length - 1].date)},${Y(0)} L${X(pts[0].date)},${Y(0)}Z`, fill: "var(--pace)", opacity: 0.12 }),
    s("path", { d, fill: "none", stroke: "var(--pace)", "stroke-width": 2.5, "stroke-linejoin": "round" }),
    s("text", { class: "ax", x: pad.l, y: H - 4 }, fmtDay(pts[0].date)), s("text", { class: "ax", x: W - pad.r, y: H - 4, "text-anchor": "end" }, fmtDay(pts[pts.length - 1].date)));
  return svg;
}

function newGroundChart(monthly) {
  const W = 360, H = 120, pad = { l: 34, r: 8, t: 8, b: 20 }, n = monthly.length, bw = (W - pad.l - pad.r) / n;
  const Y = (f) => pad.t + (1 - f) * (H - pad.t - pad.b);
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, class: "mini-chart", role: "img", "aria-label": "Share of each month's ground that was new" });
  for (const f of [0, 0.5, 1]) svg.append(s("line", { x1: pad.l, x2: W - pad.r, y1: Y(f), y2: Y(f), stroke: "var(--line-soft)" }), s("text", { class: "ax", x: pad.l - 6, y: Y(f) + 4, "text-anchor": "end" }, `${f * 100}%`));
  monthly.forEach((m, i) => {
    const x = pad.l + i * bw + bw * 0.18, w = bw * 0.64;
    svg.append(s("rect", { x, y: Y(m.share_new), width: w, height: Y(0) - Y(m.share_new), rx: 2, fill: "var(--works)" }, s("title", {}, `${monthName(m.month)}: ${Math.round(m.share_new * 100)}% new ground`)),
      s("text", { class: "ax", x: x + w / 2, y: H - 4, "text-anchor": "middle" }, monthName(m.month).slice(0, 3)));
  });
  return svg;
}
