import { api, isStatic } from "./lib/api.js";
import { $, $$, h, toast } from "./lib/dom.js";
import { mountBackdrop } from "./lib/backdrop.js";
import * as home from "./pages/home.js";
import * as runs from "./pages/runs.js";
import * as run from "./pages/run.js";
import * as planner from "./pages/planner.js";
import * as calculator from "./pages/calculator.js";
import * as analytics from "./pages/analytics.js";

const ROUTES = [
  { re: /^#?\/?$/, page: home, nav: "home", title: "Home" },
  { re: /^#\/runs$/, page: runs, nav: "runs", title: "Runs" },
  { re: /^#\/runs\/([^/]+)$/, page: run, nav: "runs", title: "Run" },
  { re: /^#\/plan$/, page: planner, nav: "plan", title: "Planner" },
  { re: /^#\/calc$/, page: calculator, nav: "calc", title: "Calculator" },
  { re: /^#\/analytics(?:\/(story|explore|places))?$/, page: analytics, nav: "analytics", title: "Analytics" },
];

export const ctx = { meta: null, refresh: () => navigate() };
let cleanup = null;
let renderId = 0;

async function navigate() {
  const id = ++renderId;
  const view = $("#view");
  if (cleanup) { try { cleanup(); } catch (e) { console.error(e); } cleanup = null; }
  view.replaceChildren();
  const hash = location.hash || "#/";
  const route = ROUTES.find((r) => r.re.test(hash)) || ROUTES[0];
  const params = (hash.match(route.re) || []).slice(1).map((p) => (p == null ? p : decodeURIComponent(p)));
  $$(".nav a").forEach((a) => (a.dataset.route === route.nav ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  document.title = `${route.title} · Run Lab`;
  window.scrollTo(0, 0);
  try {
    const result = await route.page.render(view, params, ctx);
    if (id !== renderId) { if (typeof result === "function") result(); return; }  // navigated away mid-load
    cleanup = typeof result === "function" ? result : null;
  } catch (err) {
    console.error(err);
    if (id === renderId) {
      view.replaceChildren(h("div", { class: "page" }, h("div", { class: "empty-state" },
        h("h1", {}, "Something went wrong"), h("p", {}, err.message || String(err)),
        h("button", { class: "btn btn-quiet", type: "button", onclick: () => navigate() }, "Try again"))));
    }
  }
}

async function pollSync(btn) {
  for (;;) {
    await new Promise((r) => setTimeout(r, 2000));
    const st = await api.get("/api/sync");
    if (st.running) continue;
    btn.disabled = false;
    btn.textContent = "Sync Strava";
    if (st.error) toast(`Sync stopped: ${st.error}`, 8000);
    else if (st.rate_limited) toast(`Imported ${st.imported.length} runs. Strava's rate limit hit; run Sync again in about 15 minutes to continue.`, 9000);
    else toast(st.imported.length ? `Imported ${st.imported.length} new run${st.imported.length === 1 ? "" : "s"}.` : "Already up to date.");
    ctx.meta = await api.get("/api/meta");
    navigate();
    return;
  }
}

function setupSync() {
  const btn = $("#sync-btn");
  btn.hidden = ctx.meta.demo || isStatic;
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.textContent = "Syncing…";
    try {
      await api.post("/api/sync");
      pollSync(btn);
    } catch (err) {
      btn.disabled = false;
      btn.textContent = "Sync Strava";
      toast(err.message, 9000);
    }
  });
}

async function boot() {
  mountBackdrop();
  ctx.meta = await api.get("/api/meta");
  if (isStatic) {
    // the snapshot was frozen when exported, but "today" should be today so countdowns and the plan grid stay right
    const d = new Date();
    ctx.meta.today = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const when = new Date(ctx.meta.exported_at);
    const chip = $("#snap-chip");
    chip.hidden = false;
    chip.textContent = `Snapshot · ${when.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
    chip.title = `Read-only copy, last updated ${when.toLocaleString()}`;
  }
  $("#demo-chip").hidden = !ctx.meta.demo;
  setupSync();
  window.addEventListener("hashchange", navigate);
  navigate();
}
boot().catch((err) => {
  console.error(err);
  $("#view").replaceChildren(h("div", { class: "page" }, h("div", { class: "empty-state" },
    h("h1", {}, "Can't reach the Run Lab server"), h("p", {}, err.message))));
});
