import { s } from "./dom.js";

/** A small SVG drawing of a route (list of [lat, lng]) scaled to fit a box, keeping its true shape. */
export function routeGlyph(points, w = 64, h = 44, stroke = "var(--pace)") {
  const svg = s("svg", { viewBox: `0 0 ${w} ${h}`, width: w, height: h, class: "glyph", "aria-hidden": "true" });
  if (!points || points.length < 2) return svg;
  const lats = points.map((p) => p[0]), lngs = points.map((p) => p[1]);
  const cos = Math.cos((lats.reduce((a, b) => a + b, 0) / lats.length) * Math.PI / 180);
  const minX = Math.min(...lngs), maxX = Math.max(...lngs), minY = Math.min(...lats), maxY = Math.max(...lats);
  const spanX = (maxX - minX) * cos || 1e-6, spanY = maxY - minY || 1e-6;
  const pad = 4;
  const k = Math.min((w - pad * 2) / spanX, (h - pad * 2) / spanY);
  const ox = (w - spanX * k) / 2, oy = (h - spanY * k) / 2;
  const d = points.map((p, i) => `${i ? "L" : "M"}${(ox + (p[1] - minX) * cos * k).toFixed(1)},${(oy + (maxY - p[0]) * k).toFixed(1)}`).join("");
  svg.append(s("path", { d, fill: "none", stroke, "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round" }));
  return svg;
}
