import { api } from "../lib/api.js";
import { h, skeleton } from "../lib/dom.js";
import { miles, pace, avgPace, dur, fmtDay, parseLocal, isoDate } from "../lib/fmt.js";

const FILTERS = [
  ["all", "All"],
  ["30d", "Last 30 days"],
  ["5mi", "5+ miles"],
  ["long", "Long (8+ mi)"],
];

const COLUMNS = [
  { key: "date", label: "Date", get: (r) => r.start_local, align: "left" },
  { key: "name", label: "Run", get: (r) => (r.name || "").toLowerCase(), align: "left" },
  { key: "dist", label: "Distance", get: (r) => r.distance_m },
  { key: "time", label: "Time", get: (r) => r.moving_s },
  { key: "pace", label: "Pace", get: (r) => avgPace(r.moving_s, r.distance_m) },
  { key: "hr", label: "Avg HR", get: (r) => r.avg_hr },
  { key: "cad", label: "Cadence", get: (r) => r.avg_cadence_spm },
  { key: "elev", label: "Climb", get: (r) => r.elevation_gain_m },
];

export async function render(view, _params, ctx) {
  view.replaceChildren(h("div", { class: "page" }, skeleton(8)));
  const runs = await api.get("/api/runs");
  if (!runs.length) { view.replaceChildren(emptyState(ctx)); return; }

  const state = { filter: "all", query: "", sort: "date", dir: -1 };
  const page = h("div", { class: "page runs-page" });
  const summary = h("p", { class: "muted mono runs-summary" });
  const tableHost = h("div", { class: "table-wrap" });
  const search = h("input", { class: "input", type: "search", placeholder: "Search runs", "aria-label": "Search runs",
    oninput: (e) => { state.query = e.target.value.trim().toLowerCase(); draw(); } });
  const chips = h("div", { class: "seg", role: "group", "aria-label": "Filter runs" },
    FILTERS.map(([key, label]) => h("button", { type: "button", "aria-pressed": String(key === state.filter), dataset: { key },
      onclick: () => { state.filter = key; chips.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.key === key))); draw(); } }, label)));

  page.append(
    h("header", { class: "page-head" }, h("div", {}, h("p", { class: "eyebrow" }, "Every run"), h("h1", {}, "Runs")), summary),
    h("div", { class: "toolbar" }, chips, h("div", { class: "toolbar-search" }, search)),
    tableHost);
  view.replaceChildren(page);

  const today = ctx.meta.today;
  function visible() {
    const cutoff = new Date(parseLocal(today)); cutoff.setDate(cutoff.getDate() - 30);
    return runs.filter((r) => {
      const mi = miles(r.distance_m);
      if (state.filter === "30d" && parseLocal(r.start_local) < cutoff) return false;
      if (state.filter === "5mi" && mi < 5) return false;
      if (state.filter === "long" && mi < 8) return false;
      if (state.query && !`${r.name || ""} ${fmtDay(r.start_local)} ${r.gear || ""}`.toLowerCase().includes(state.query)) return false;
      return true;
    });
  }

  function draw() {
    const col = COLUMNS.find((c) => c.key === state.sort);
    const rows = visible().sort((a, b) => {
      const x = col.get(a), y = col.get(b);
      if (x == null) return 1;
      if (y == null) return -1;
      return (x < y ? -1 : x > y ? 1 : 0) * state.dir;
    });
    const totalMi = rows.reduce((s, r) => s + miles(r.distance_m), 0);
    summary.textContent = `${rows.length} run${rows.length === 1 ? "" : "s"} · ${totalMi.toFixed(1)} mi`;
    if (!rows.length) { tableHost.replaceChildren(h("p", { class: "muted", style: { padding: "32px 0" } }, "No runs match.")); return; }

    const head = h("tr", {}, COLUMNS.map((c) => h("th", { scope: "col", class: c.align === "left" ? "left" : "", "aria-sort": state.sort === c.key ? (state.dir > 0 ? "ascending" : "descending") : "none" },
      h("button", { type: "button", class: "th-btn", onclick: () => { state.dir = state.sort === c.key ? -state.dir : (c.key === "name" ? 1 : -1); state.sort = c.key; draw(); } },
        c.label, state.sort === c.key ? h("span", { "aria-hidden": "true" }, state.dir > 0 ? " ↑" : " ↓") : null))));
    const body = rows.map((r) => {
      const href = `#/runs/${r.id}`;
      const cell = (content, cls = "") => h("td", { class: cls }, h("a", { href, class: "row-link", tabindex: "-1" }, content));
      return h("tr", { class: "run-row", onclick: () => (location.hash = href) },
        h("td", { class: "left" }, h("a", { href, class: "row-link" }, fmtDay(r.start_local, { month: "short", day: "numeric", year: "2-digit" }))),
        cell(r.name || "Run", "left name"),
        cell(`${miles(r.distance_m).toFixed(2)}`, "mono"), cell(dur(r.moving_s), "mono"),
        cell(pace(avgPace(r.moving_s, r.distance_m)), "mono pace-c"),
        cell(r.avg_hr ? Math.round(r.avg_hr) : "--", "mono hr-c"),
        cell(r.avg_cadence_spm ? Math.round(r.avg_cadence_spm) : "--", "mono"),
        cell(r.elevation_gain_m != null ? `${Math.round(r.elevation_gain_m * 3.281)} ft` : "--", "mono"));
    });
    tableHost.replaceChildren(h("table", { class: "runs-table" }, h("thead", {}, head), h("tbody", {}, body)));
  }
  draw();
}

function emptyState(ctx) {
  return h("div", { class: "page" }, h("div", { class: "empty-state" },
    h("p", { class: "eyebrow" }, "No runs yet"),
    h("h1", {}, "Let's get your runs in"),
    h("p", {}, "Run Lab pulls from Strava. Set up the connection once, then use Sync Strava in the top bar."),
    h("p", {}, "Setup steps are in ", h("code", {}, "CLAUDE.md"), " under “Strava sync”. Want to look around first? Start the server with ", h("code", {}, "--demo"), " to try it with generated data.")));
}
