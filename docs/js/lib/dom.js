// Tiny DOM helpers. No innerHTML anywhere: run names and notes come from Strava, so we only ever set text.
const SVG_NS = "http://www.w3.org/2000/svg";

function apply(node, attrs) {
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") node.setAttribute("class", v);
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "style" && typeof v === "object") Object.assign(node.style, v);
    else if (k === "dataset") Object.assign(node.dataset, v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  return node;
}

export function h(tag, attrs, ...kids) {
  const node = apply(document.createElement(tag), attrs);
  node.append(...kids.flat().filter((k) => k != null && k !== false));
  return node;
}

export function s(tag, attrs, ...kids) {
  const node = apply(document.createElementNS(SVG_NS, tag), attrs);
  node.append(...kids.flat().filter((k) => k != null && k !== false));
  return node;
}

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** A value with a small unit, e.g. 4.31 mi */
export function val(value, unit) {
  return h("span", { class: "val" }, String(value), unit ? h("small", {}, unit) : null);
}

let toastTimer;
export function toast(message, ms = 4000) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), ms);
}

export function skeleton(lines = 4) {
  return h("div", { class: "skeleton", "aria-hidden": "true" }, Array.from({ length: lines }, () => h("div", { class: "skel-line" })));
}

export const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
