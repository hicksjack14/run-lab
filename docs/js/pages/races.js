// Every race on the calendar, with the slice of the training plan that leads to it.
// Reads the same /api/plan data as the Planner: the plan's `chain` lists the races, workouts say which race they belong to.
import { api } from "../lib/api.js";
import { h, skeleton } from "../lib/dom.js";
import { pace, dur, fmtDay, fmtLongDay, parseLocal, avgPace, miles } from "../lib/fmt.js";
import { mileageChart, paceText, STATUS_MARK } from "../lib/plangrid.js";
import { logSection } from "./races-log.js";
import { goalsSection } from "./races-goals.js";

const MI = 1609.344;
const KEY_KINDS = new Set(["long", "tempo", "intervals", "race"]);

export async function render(view, _params, ctx) {
  view.replaceChildren(h("div", { class: "page" }, skeleton(8)));
  const [data, racesData] = await Promise.all([api.get("/api/plan"), api.get("/api/races")]);
  const root = h("div", { class: "page races" });
  view.replaceChildren(root);

  const today = ctx.meta.today;
  const chain = data.plan ? data.plan.chain : [];
  const nextIdx = chain.findIndex((c) => c.race_date >= today);

  // the log and the goal races redraw themselves after a race is added or removed
  const lower = h("div", { class: "races-lower" });
  const showLower = (rd) => lower.replaceChildren(logSection(rd, showLower), goalsSection(rd));
  showLower(racesData);

  root.append(
    h("header", { class: "page-head" },
      h("div", {}, h("p", { class: "eyebrow" }, "Races"), h("h1", {}, "Your races")),
      h("p", { class: "muted mono" }, chain.length ? `${chain.length} coming up · ${racesData.log.length} in the log` : `${racesData.log.length} in the log`)),
    h("section", { class: "races-section", "aria-labelledby": "coming-up-h" },
      h("div", { class: "section-head" }, h("h2", { id: "coming-up-h" }, "Coming up and in training")),
      chain.length ? h("div", { class: "races-upcoming" }, chain.map((c, i) => raceCard(c, data, today, i === nextIdx)))
        : h("div", { class: "empty-state compact" }, h("p", {}, "No race is on your calendar. Pick one in the Planner and it shows up here with its training plan."),
          h("a", { class: "btn btn-primary", href: "#/plan" }, "Open the planner"))),
    lower);
}

function daysBetween(a, b) {
  return Math.round((parseLocal(a) - parseLocal(b)) / 86400000);
}

function raceCard(c, data, today, isNext) {
  const days = daysBetween(c.race_date, today);
  const finished = days < 0;
  const companion = c.role === "companion";
  const workouts = data.workouts.filter((w) => w.plan_id === c.id);
  const weeks = data.plan.weeks.filter((w) => w.week >= c.week_from && w.week <= c.week_to);
  const raceDay = workouts.find((w) => w.kind === "race");
  const count = (st) => workouts.filter((w) => w.status === st).length;
  const done = count("done"), partial = count("partial"), missed = count("missed"), toGo = count("upcoming") + count("today");
  const total = workouts.length || 1;
  const plannedMi = workouts.reduce((a, w) => a + w.distance_mi, 0);
  const distMi = c.race_distance_m / MI;
  const goalPace = c.goal_time_s / distMi;

  const state = finished ? ["Finished", "st-done"] : isNext ? ["Up next", "st-today"] : ["Later", ""];
  const result = h("div", { class: "race-result", hidden: true });
  if (finished) showResult(result, raceDay);

  // the few sessions that matter: long runs, tempo, intervals, and the race. Past ones fall away once done.
  const key = workouts.filter((w) => KEY_KINDS.has(w.kind) && (finished ? w.kind === "race" : w.status === "upcoming" || w.status === "today")).slice(0, 6);

  return h("article", { class: `panel race${finished ? " is-finished" : ""}${isNext ? " is-next" : ""}`, "aria-label": c.goal },
    h("header", { class: "race-top" },
      h("div", { class: "race-date" }, h("span", { class: "label" }, fmtDay(c.race_date, { weekday: "short" })), h("strong", { class: "mono" }, fmtDay(c.race_date, { month: "short", day: "numeric" })), h("span", { class: "muted mono" }, parseLocal(c.race_date).getFullYear())),
      h("div", { class: "race-name" }, h("h2", {}, c.goal), h("span", { class: `status ${state[1]}` }, state[0])),
      finished ? null : h("div", { class: "countdown" }, h("span", { class: "big mono" }, days), h("span", { class: "label" }, days === 1 ? "day to go" : "days to go"))),

    h("div", { class: "race-cols" },
      h("section", { class: "race-facts", "aria-label": "Race" },
        h("dl", {},
          fact("Distance", `${distMi.toFixed(1)} mi`),
          companion
            ? fact("How you'll run it", `Easy, at ${pace(goalPace)}/mi`, "pace-c", "Beside someone: no goal time, no taper, no speed work.")
            : fact("Goal", `${dur(c.goal_time_s)} · ${pace(goalPace)}/mi`, "pace-c", c.projected_time_s ? `Fitness predicts ${dur(c.projected_time_s)}.` : null),
          companion ? fact("Expect to finish in", `about ${dur(c.goal_time_s)}`) : null),
        raceDay ? h("p", { class: "race-note" }, raceDay.description) : null,
        result),

      h("section", { class: "race-plan", "aria-label": "Training plan" },
        h("div", { class: "panel-head" }, h("h3", { class: "label" }, "The plan"),
          h("span", { class: "muted mono" }, `${weeks.length} weeks · ${c.days_per_week} runs a week · ${plannedMi.toFixed(0)} mi`)),
        mileageChart(weeks, workouts),
        h("div", { class: "plan-progress", role: "img", "aria-label": `${done} of ${workouts.length} workouts done` },
          h("div", { class: "pp-done", style: { width: `${(done / total) * 100}%` } }), h("div", { class: "pp-partial", style: { width: `${(partial / total) * 100}%` } }), h("div", { class: "pp-missed", style: { width: `${(missed / total) * 100}%` } })),
        h("p", { class: "muted mono" }, `${done} done · ${missed} missed · ${toGo} to go`),
        key.length ? h("div", { class: "key-block" }, h("h3", { class: "label" }, finished ? "Race day" : "Key sessions"),
          h("ul", { class: "key-sessions" }, key.map((w) => h("li", { class: `ks-${w.kind}` },
            h("span", { class: "ks-date mono" }, fmtDay(w.date, { weekday: "short", month: "short", day: "numeric" })),
            h("span", { class: "ks-title" }, w.title),
            h("span", { class: "ks-pace mono pace-c" }, paceText(w)),
            h("span", { class: "ks-mark mono", "aria-hidden": "true" }, STATUS_MARK[w.status]))))) : null,
        c.warnings && c.warnings.length ? h("ul", { class: "plan-warnings" }, c.warnings.map((w) => h("li", {}, w))) : null,
        h("a", { class: "btn btn-quiet", href: "#/plan" }, "Open in planner"))));
}

function fact(label, value, cls = "", note = null) {
  return h("div", { class: "race-fact" }, h("dt", { class: "label" }, label), h("dd", { class: `mono ${cls}` }, value), note ? h("p", { class: "muted" }, note) : null);
}

// What actually happened on race day: the run that was logged that day (if any).
async function showResult(box, raceDay) {
  if (!raceDay) return;
  box.hidden = false;
  if (!raceDay.run_id) { box.append(h("p", { class: "muted" }, "No run was recorded that day.")); return; }
  try {
    const r = await api.get(`/api/runs/${raceDay.run_id}`);
    const run = r.run || r;
    const p = avgPace(run.moving_s, run.distance_m);
    box.append(h("p", { class: "label" }, "Result"),
      h("p", { class: "mono big-result" }, dur(run.moving_s), h("small", {}, `${miles(run.distance_m).toFixed(1)} mi${p ? ` · ${pace(p)}/mi` : ""}`)),
      h("a", { class: "btn btn-quiet", href: `#/runs/${raceDay.run_id}` }, "View the run"));
  } catch {
    box.append(h("p", { class: "muted" }, `You ran ${raceDay.actual_mi.toFixed(1)} mi that day.`), h("a", { class: "btn btn-quiet", href: `#/runs/${raceDay.run_id}` }, "View the run"));
  }
}
