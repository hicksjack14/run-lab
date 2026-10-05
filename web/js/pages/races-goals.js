// Goal races (NYC Half, NYC Marathon, Boston): what it takes to get in, and which parts are done.
import { h } from "../lib/dom.js";
import { dur, fmtDay, pace } from "../lib/fmt.js";

const STATUS = {
  completed: ["Completed", "st-done"],
  qualified: ["Time standard met", "st-partial"],
  not_yet: ["Not yet", ""],
};

export function goalsSection(data) {
  const estimate = data.fitness_is_estimate;
  return h("section", { class: "races-section", "aria-labelledby": "goal-races-h" },
    h("div", { class: "section-head" }, h("h2", { id: "goal-races-h" }, "Goal races"),
      h("p", { class: "muted mono" }, `${data.division.label} standards`)),
    h("p", { class: "muted goal-intro" },
      `Requirements last checked ${fmtDay(data.verified, { month: "long", day: "numeric", year: "numeric" })}. They change every year, so confirm on each race's own site before you plan around a date. `
      + "Boston's came straight from the B.A.A.; the NYC ones come from NYRR pages as quoted by search results, because NYRR blocks automated reading."),
    h("div", { class: "goal-list" }, data.goals.map((g) => goalCard(g, estimate))));
}

function goalCard(g, estimate) {
  const p = g.progress;
  const [label, cls] = STATUS[p.status];
  const std = g.standard;
  return h("article", { class: `panel goal${p.status === "completed" ? " is-done" : ""}`, "aria-label": g.name },
    h("header", { class: "goal-top" },
      h("div", {}, h("h3", {}, g.name), h("p", { class: "muted" }, `${g.city} · ${g.when}`)),
      h("span", { class: `status ${cls}` }, label)),

    h("div", { class: "goal-std" },
      h("div", {}, h("span", { class: "label" }, "Time standard"), h("strong", { class: "mono big-std" }, std.text), h("span", { class: "muted" }, `${std.distance_label}${std.alt ? `, or ${std.alt.text} for the ${std.alt.distance_label}` : ""}`)),
      p.predicted ? h("div", {}, h("span", { class: "label" }, "Your fitness today"),
        h("strong", { class: "mono big-std pace-c" }, p.predicted.predicted_text), h("span", { class: "muted" },
          (p.predicted.gap_s > 0 ? `${p.predicted.distance_label} prediction: ${p.predicted.gap_text} to cut, about ${pace(p.predicted.pace_needed_s)}/mi needed` : `${p.predicted.distance_label} prediction already beats the standard`)
          + (estimate ? ". An estimate from training runs, so it reads low until you add a race result in the Planner." : ""))) : null,
      p.closest ? h("div", {}, h("span", { class: "label" }, "Fastest logged in the window"),
        h("strong", { class: "mono big-std" }, p.closest.text), h("span", { class: "muted" }, `${p.closest.name || "Race"}, ${p.closest.gap_s <= 0 ? "meets the standard" : `${dur(p.closest.gap_s)} over`}`)) : null),

    p.completed.length ? h("div", { class: "goal-done" }, h("span", { class: "label" }, "You have run it"),
      h("ul", {}, p.completed.map((e) => h("li", {}, `${fmtDay(e.race_date, { month: "long", day: "numeric", year: "numeric" })}${e.time_s ? ` in ${dur(e.time_s)}` : ""}`)))) : null,

    h("div", { class: "goal-routes" }, h("span", { class: "label" }, "Ways in"),
      h("ol", {}, g.routes.map((r) => routeItem(r, p)))),

    h("p", { class: "goal-window mono" }, p.window_closed ? "Qualifying window for the next race: closed." : (p.days_left ? `Qualifying window ends in ${p.days_left} day${p.days_left === 1 ? "" : "s"}.` : "")),
    g.notes ? h("p", { class: "muted" }, g.notes) : null,
    h("p", { class: "goal-sources muted" }, "Sources: ", ...g.sources.flatMap((s, i) => [i ? ", " : "", h("a", { href: s.url, target: "_blank", rel: "noopener noreferrer" }, s.label)])));
}

function routeItem(r, p) {
  const counter = p.counters.find((c) => c.title === r.title);
  const isTime = r.title === "Run a qualifying time";
  const done = isTime ? !!p.qualified_with : counter ? counter.have >= counter.need : null;
  return h("li", { class: `route${done === true ? " is-done" : ""}` },
    h("div", { class: "route-head" }, h("strong", {}, r.title),
      done === null ? null : h("span", { class: `route-mark mono ${done ? "ok" : ""}`, "aria-label": done ? "Done" : "Not done yet" }, done ? "✓ done" : "not yet")),
    h("p", {}, r.detail),
    counter ? h("div", { class: "counter" }, h("div", { class: "bar", role: "progressbar", "aria-valuemin": 0, "aria-valuemax": counter.need, "aria-valuenow": counter.have, "aria-label": `${r.title} progress` },
      h("div", { style: { width: `${Math.min(100, (counter.have / counter.need) * 100)}%` } })),
      h("span", { class: "muted mono" }, `${counter.have} of ${counter.need} NYRR races logged in ${counter.year}${counter.title.startsWith("9+1") ? " (plus one volunteer shift)" : ""}`)) : null,
    isTime && p.qualified_with ? h("p", { class: "mono ok-note" }, `Met with ${dur(p.qualified_with.entry.time_s)} on ${fmtDay(p.qualified_with.entry.race_date, { month: "short", day: "numeric", year: "numeric" })}.`) : null);
}
