import { api, isStatic } from "../lib/api.js";
import { h, skeleton } from "../lib/dom.js";
import { miles, pace, avgPace, dur, fmtDay, fmtClock, parseLocal, KIND_LABEL } from "../lib/fmt.js";
import { routeGlyph } from "../lib/glyph.js";
import { findingBlock } from "../lib/findings.js";

export async function render(view, _params, ctx) {
  view.replaceChildren(h("div", { class: "page" }, skeleton(8)));
  const data = await api.get("/api/home");
  if (!data.recent.length) {
    view.replaceChildren(h("div", { class: "page" }, h("div", { class: "empty-state" },
      h("p", { class: "eyebrow" }, "Welcome"), h("h1", {}, "No runs yet"),
      h("p", {}, "Connect Strava once and hit Sync in the top bar to pull in your history. The setup steps are in ", h("code", {}, "CLAUDE.md"), "."),
      h("p", {}, "Or look around with generated data: start the server with ", h("code", {}, "--demo"), "."))));
    return;
  }
  const today = parseLocal(data.today);
  const page = h("div", { class: "page home" },
    h("header", { class: "page-head" }, h("div", {},
      h("p", { class: "eyebrow" }, today.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })),
      h("h1", {}, "Your training")), h("a", { class: "btn btn-quiet", href: "#/runs" }, "All runs")),
    h("div", { class: "home-grid" }, recentBlock(data), h("aside", { class: "home-side" }, weekBlock(data.week), goalBlock(data.plan, ctx), pacesBlock(data.fitness), coachBlock(data.coach))));
  view.replaceChildren(page);
}

function recentBlock(data) {
  return h("section", { class: "home-recent", "aria-labelledby": "recent-h" },
    h("h2", { id: "recent-h", class: "label" }, "Recent runs"),
    h("ol", { class: "run-rows" }, data.recent.map((r) => h("li", {}, h("a", { class: "run-row-card", href: `#/runs/${r.id}` },
      r.glyph ? routeGlyph(r.glyph, 76, 52) : h("span", { class: "glyph-empty", "aria-hidden": "true" }),
      h("span", { class: "rr-name" }, h("strong", {}, r.name || "Run"), h("span", { class: "muted" }, `${fmtDay(r.start_local, { weekday: "short", month: "short", day: "numeric" })} · ${fmtClock(r.start_local)}`)),
      h("span", { class: "rr-stat mono" }, miles(r.distance_m).toFixed(2), h("small", {}, "mi")),
      h("span", { class: "rr-stat mono pace-c" }, pace(avgPace(r.moving_s, r.distance_m)), h("small", {}, "/mi")),
      h("span", { class: "rr-stat mono hr-c" }, r.avg_hr ? Math.round(r.avg_hr) : "--", r.avg_hr ? h("small", {}, "bpm") : null))))));
}

function weekBlock(w) {
  const max = Math.max(w.miles, w.last_miles, 1);
  return h("section", { class: "side-block", "aria-label": "This week" },
    h("h2", { class: "label" }, "This week"),
    h("p", { class: "big mono" }, w.miles.toFixed(1), h("small", {}, "mi")),
    h("p", { class: "muted" }, `${w.runs} run${w.runs === 1 ? "" : "s"} so far`),
    h("div", { class: "week-bars", role: "img", "aria-label": `This week ${w.miles.toFixed(1)} miles, last week ${w.last_miles.toFixed(1)} miles` },
      h("div", { class: "wb" }, h("span", { class: "label" }, "This"), h("div", { class: "wb-track" }, h("div", { class: "wb-fill", style: { width: `${(w.miles / max) * 100}%` } })), h("span", { class: "mono" }, w.miles.toFixed(1))),
      h("div", { class: "wb" }, h("span", { class: "label" }, "Last"), h("div", { class: "wb-track" }, h("div", { class: "wb-fill dim", style: { width: `${(w.last_miles / max) * 100}%` } })), h("span", { class: "mono muted" }, w.last_miles.toFixed(1)))));
}

function goalBlock(planData, ctx) {
  if (!planData || !planData.plan) {
    return h("section", { class: "side-block", "aria-label": "Goal" }, h("h2", { class: "label" }, "Goal"),
      h("p", { class: "side-title" }, "No race on the calendar"),
      h("p", { class: "muted" }, "Pick a race and a date and Run Lab builds the plan, with the exact pace for every run."),
      h("a", { class: "btn btn-primary", href: "#/plan" }, "Set a goal"));
  }
  const { plan, stats, next } = planData;
  const days_to_race = Math.round((parseLocal(plan.race_date) - parseLocal(ctx.meta.today)) / 86400000);
  const finished = stats.done + stats.partial + stats.missed;
  return h("section", { class: "side-block", "aria-label": "Goal" }, h("h2", { class: "label" }, "Goal"),
    h("p", { class: "side-title" }, `${plan.goal} · ${fmtDay(plan.race_date, { month: "short", day: "numeric", year: "numeric" })}`),
    h("p", { class: "big mono" }, days_to_race > 0 ? days_to_race : 0, h("small", {}, days_to_race === 1 ? "day to go" : "days to go")),
    h("div", { class: "plan-progress", role: "img", "aria-label": `${stats.done} of ${stats.total} workouts done` },
      h("div", { class: "pp-done", style: { width: `${(stats.done / stats.total) * 100}%` } }),
      h("div", { class: "pp-partial", style: { width: `${(stats.partial / stats.total) * 100}%` } }),
      h("div", { class: "pp-missed", style: { width: `${(stats.missed / stats.total) * 100}%` } })),
    h("p", { class: "muted mono" }, `${stats.done} done · ${stats.missed} missed · ${stats.upcoming} to go`),
    next ? h("p", { class: "next-workout" }, h("span", { class: "label" }, "Next up"), h("strong", {}, `${fmtDay(next.date, { weekday: "short", month: "short", day: "numeric" })}: ${next.title}`),
      h("span", { class: "muted mono" }, next.kind === "race" ? `${pace(next.pace_lo)}/mi goal` : `${pace(next.pace_lo)} to ${pace(next.pace_hi)}/mi`)) : null,
    h("a", { class: "btn btn-quiet", href: "#/plan" }, "Open planner"));
}

function pacesBlock(f) {
  if (!f.paces) {
    return h("section", { class: "side-block", "aria-label": "Paces" }, h("h2", { class: "label" }, "Your paces"),
      h("p", { class: "muted" }, (f.needs && f.needs[0]) || "Not enough data to set paces yet."));
  }
  const row = (label, text, cls = "") => h("tr", {}, h("th", { scope: "row" }, label), h("td", { class: `mono ${cls}` }, text));
  return h("section", { class: "side-block", "aria-label": "Paces and predictions" }, h("h2", { class: "label" }, "Your paces (per mile)"),
    h("table", { class: "pace-table" }, h("tbody", {},
      row("Easy", f.paces.easy.text, "pace-c"), row("Marathon", f.paces.marathon.text), row("Tempo", f.paces.threshold.text), row("Intervals", f.paces.interval.text))),
    h("h2", { class: "label", style: { marginTop: "14px" } }, "Race predictions"),
    h("table", { class: "pace-table" }, h("tbody", {}, ["5K", "10K", "Half marathon", "Marathon"].filter((k) => f.prediction_text[k]).map((k) => row(k, f.prediction_text[k])))),
    h("p", { class: "hint" }, `Fitness score ${f.vdot.toFixed(1)}. `, f.vdot_is_estimate ? "An estimate from training runs, which reads low until you add a race result. " : "",
      f.vdot_is_estimate && !isStatic ? h("a", { class: "link", href: "#/plan" }, "Add one") : null));
}

function coachBlock(coach) {
  if (!coach) return h("div");
  return h("section", { class: "side-block coach", "aria-label": "Coach note" }, h("h2", { class: "label" }, "Coach's note"),
    findingBlock(coach, { compact: true }), h("a", { class: "link", href: "#/analytics" }, "See every finding →"));
}
