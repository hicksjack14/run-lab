import { api } from "../lib/api.js";
import { h, s, skeleton, toast } from "../lib/dom.js";
import { pace, dur, fmtDay, fmtLongDay, addDays, parseLocal, parseDuration, KIND_LABEL } from "../lib/fmt.js";

const GOALS = ["5K", "10K", "Half marathon", "Marathon"];
const MIN_WEEKS = { "5K": 6, "10K": 8, "Half marathon": 10, "Marathon": 14 };
const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const STATUS_MARK = { done: "✓", partial: "~", missed: "×", today: "•", upcoming: "" };
const STATUS_TEXT = { done: "Done", partial: "Partly done", missed: "Missed", today: "Today", upcoming: "Upcoming" };

export async function render(view, _params, ctx) {
  view.replaceChildren(h("div", { class: "page" }, skeleton(8)));
  const [planData, fit] = await Promise.all([api.get("/api/plan"), api.get("/api/fitness")]);
  const root = h("div", { class: "page planner" });
  view.replaceChildren(root);

  const show = (data, forceForm = false) => {
    root.replaceChildren();
    if (!data.plan || forceForm) root.append(goalForm(data, fit, ctx, (d) => show(d), () => show(data)));
    else root.append(...planView(data, fit, ctx, () => show(data, true), (d) => show(d)));
  };
  show(planData);
}

// =============================================================== form
function goalForm(current, fit, ctx, onCreated, onCancel) {
  const st = { goal: "Half marathon", days: 4, longDow: 6 };
  const today = ctx.meta.today;
  const saturdayOffset = (6 - parseLocal(today).getDay() + 7) % 7;   // days until the next Saturday
  const dateInput = h("input", { class: "input", type: "date", id: "race-date", min: addDays(today, 14), value: addDays(today, 7 * 14 + saturdayOffset), required: true });
  const timeInput = h("input", { class: "input mono", type: "text", id: "goal-time", inputmode: "numeric", autocomplete: "off" });
  const preview = h("p", { class: "hint", "aria-live": "polite" });
  const error = h("p", { class: "error-text", role: "alert" });
  const submit = h("button", { class: "btn btn-primary btn-lg", type: "submit" }, "Build my plan");

  const segment = (items, key, label) => {
    const wrap = h("div", { class: "seg", role: "group", "aria-label": label },
      items.map(([val, text]) => h("button", { type: "button", "aria-pressed": String(st[key] === val), dataset: { val },
        onclick: () => { st[key] = val; [...wrap.children].forEach((b) => b.setAttribute("aria-pressed", String(String(st[key]) === b.dataset.val))); refresh(); } }, text)));
    return wrap;
  };

  function refresh() {
    const pred = fit.prediction_text && fit.prediction_text[st.goal];
    timeInput.placeholder = pred ? `e.g. ${pred}` : "h:mm:ss (optional)";
    const days = Math.round((parseLocal(dateInput.value) - parseLocal(today)) / 86400000);
    const weeks = Math.ceil(days / 7);
    const need = MIN_WEEKS[st.goal];
    preview.textContent = (isNaN(weeks) ? "" : `${weeks} weeks to race day. ${weeks < need ? `That is short for a ${st.goal}; ${need}+ is recommended, so the build gets compressed.` : "Plenty of time for a proper build."}`)
      + (pred ? ` Your current fitness predicts ${pred}.` : "");
  }
  dateInput.addEventListener("input", refresh);

  const form = h("form", { class: "goal-form", novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    error.textContent = "";
    const gt = timeInput.value.trim() ? parseDuration(timeInput.value) : null;
    if (timeInput.value.trim() && !gt) { error.textContent = "Goal time should look like 1:55:00 or 25:30."; return; }
    submit.disabled = true; submit.textContent = "Building…";
    try {
      const data = await api.post("/api/plan", { goal: st.goal, race_date: dateInput.value, goal_time_s: gt, days_per_week: st.days, long_run_dow: st.longDow });
      toast("Plan built.");
      onCreated(data);
    } catch (err) {
      error.textContent = err.data && err.data.needs ? `${err.message} ${err.data.needs.join(" ")}` : err.message;
      submit.disabled = false; submit.textContent = "Build my plan";
    }
  } },
    h("div", { class: "field" }, h("span", { class: "label" }, "Goal race"), segment(GOALS.map((g) => [g, g]), "goal", "Goal race")),
    h("div", { class: "form-row" },
      h("div", { class: "field" }, h("label", { class: "label", for: "race-date" }, "Race date"), dateInput),
      h("div", { class: "field" }, h("label", { class: "label", for: "goal-time" }, "Goal finish time (optional)"), timeInput)),
    h("div", { class: "form-row" },
      h("div", { class: "field" }, h("span", { class: "label" }, "Runs per week"), segment([3, 4, 5, 6].map((d) => [d, String(d)]), "days", "Runs per week")),
      h("div", { class: "field" }, h("span", { class: "label" }, "Long run day"), segment([[5, "Saturday"], [6, "Sunday"]], "longDow", "Long run day"))),
    preview, error,
    h("div", { class: "form-actions" }, submit, current.plan ? h("button", { class: "btn btn-quiet", type: "button", onclick: onCancel }, "Keep current plan") : null));
  refresh();

  return h("div", {},
    h("header", { class: "page-head" }, h("div", {}, h("p", { class: "eyebrow" }, current.plan ? "Replace your plan" : "Set a goal"), h("h1", {}, current.plan ? "New plan" : "What are you training for?"))),
    h("div", { class: "planner-form-grid" }, form, numbersPanel(fit)));
}

// =============================================================== numbers (fitness + overrides)
const RACE_DISTANCES = { "1 mile": 1609.344, "5K": 5000, "10K": 10000, "Half marathon": 21097.5 };

function sourceNote(fit) {
  const b = fit.vdot_basis;
  if (fit.vdot_source === "override") return "Set by you.";
  if (fit.vdot_source === "race") return `From your ${b.label} result of ${dur(b.seconds)}.`;
  if (b && b.type === "EverydayPace") return `Estimated from your everyday pace (${pace(b.pace)}/mi across ${b.runs} recent runs), treated as comfortable running.`;
  if (b && b.type === "WholeRun") return `Estimated from a whole run on ${fmtDay(b.date, { month: "short", day: "numeric" })}.`;
  return b ? `From your ${b.type.replace("Fastest", "")} effort on ${fmtDay(b.date, { month: "short", day: "numeric" })}.` : "";
}

function numbersPanel(fit) {
  const body = h("section", { class: "panel numbers" }, h("div", { class: "panel-head" }, h("h2", {}, "Your numbers")));
  if (!fit.vdot) {
    body.append(h("p", { class: "muted" }, fit.needs[0] || "Not enough data yet."),
      h("p", { class: "hint" }, "Add a recent race result below, or set a fitness score by hand, to get paces."));
  } else {
    body.append(h("p", { class: "big mono" }, fit.vdot.toFixed(1), h("small", {}, "fitness score")),
      h("p", { class: "hint" }, sourceNote(fit)),
      fit.vdot_is_estimate ? h("p", { class: "estimate-note" }, "This is an estimate from training runs, and those usually read low. A recent race or hard effort makes your paces much sharper: add one below.") : null,
      h("table", { class: "pace-table" }, h("tbody", {},
        ...[["Easy", fit.paces.easy.text, "pace-c"], ["Marathon", fit.paces.marathon.text], ["Tempo", fit.paces.threshold.text], ["Intervals", fit.paces.interval.text]]
          .map(([k, v, c]) => h("tr", {}, h("th", { scope: "row" }, `${k} (/mi)`), h("td", { class: `mono ${c || ""}` }, v))))));
  }
  if (fit.max_hr) body.append(h("p", { class: "muted" }, `Max heart rate ${fit.max_hr} bpm${fit.max_hr_source === "override" ? " (set by you)" : " (from your runs)"}.`));

  const saved = fit.settings.race_result;
  const distSel = h("select", { class: "input", id: "rr-dist", "aria-label": "Race distance" }, Object.keys(RACE_DISTANCES).map((k) => h("option", { value: k, selected: k === "5K" ? true : null }, k)));
  const timeIn = h("input", { class: "input mono", type: "text", id: "rr-time", inputmode: "numeric", autocomplete: "off", placeholder: "e.g. 27:30", "aria-label": "Race time" });
  const rrErr = h("p", { class: "error-text", role: "alert" });
  const saveRace = async (e) => {
    e.preventDefault(); rrErr.textContent = "";
    const secs = parseDuration(timeIn.value);
    if (!secs) { rrErr.textContent = "Enter the time like 27:30 or 1:55:00."; return; }
    try {
      await api.post("/api/settings", { race_result: { distance_m: RACE_DISTANCES[distSel.value], seconds: secs, label: distSel.value } });
      toast("Race result saved. Paces updated.");
      location.reload();
    } catch (ex) { rrErr.textContent = ex.message; }
  };
  body.append(h("details", { class: "overrides", open: fit.vdot_is_estimate || !fit.vdot ? true : null }, h("summary", {}, saved ? "Race result (saved)" : "Add a race result"),
    h("form", { onsubmit: saveRace },
      h("p", { class: "hint" }, "A recent race, time trial, or all-out effort (within the last few months) is the best way to set your paces."),
      h("div", { class: "form-row" }, h("div", { class: "field" }, h("label", { class: "label", for: "rr-dist" }, "Distance"), distSel), h("div", { class: "field" }, h("label", { class: "label", for: "rr-time" }, "Time"), timeIn)),
      rrErr, h("div", { class: "form-actions" }, h("button", { class: "btn btn-quiet", type: "submit" }, "Use this result"),
        saved ? h("button", { class: "btn btn-quiet", type: "button", onclick: async () => { await api.post("/api/settings", { race_result: null }); location.reload(); } }, "Remove it") : null))));

  const vdot = h("input", { class: "input mono", type: "number", step: "0.1", min: "15", max: "85", id: "ov-vdot", value: fit.settings.vdot_override || "", placeholder: "auto" });
  const maxhr = h("input", { class: "input mono", type: "number", step: "1", min: "100", max: "240", id: "ov-maxhr", value: fit.settings.max_hr || "", placeholder: "auto" });
  const err = h("p", { class: "error-text", role: "alert" });
  const save = async (e) => {
    e.preventDefault(); err.textContent = "";
    try {
      await api.post("/api/settings", { vdot_override: vdot.value ? Number(vdot.value) : null, max_hr: maxhr.value ? Number(maxhr.value) : null });
      toast("Saved.");
      location.reload();
    } catch (ex) { err.textContent = ex.message; }
  };
  body.append(h("details", { class: "overrides" }, h("summary", {}, "Adjust by hand"),
    h("form", { onsubmit: save },
      h("div", { class: "field" }, h("label", { class: "label", for: "ov-vdot" }, "Fitness score (empty = auto)"), vdot),
      h("div", { class: "field" }, h("label", { class: "label", for: "ov-maxhr" }, "Max heart rate (empty = auto)"), maxhr),
      err, h("button", { class: "btn btn-quiet", type: "submit" }, "Save"))));
  return body;
}

// =============================================================== plan view
function planView(data, fit, ctx, onNewPlan, onChange) {
  const { plan, workouts, stats, next, days_to_race } = data;
  const byDate = new Map(workouts.map((w) => [w.date, w]));
  const detail = h("section", { class: "workout-detail", "aria-live": "polite" }, h("p", { class: "muted" }, "Select a workout to see its pace, heart-rate target, and details."));
  let selectedBtn = null;

  const goalPace = plan.goal_time_s / (plan.race_distance_m / 1609.344);
  const head = h("header", { class: "plan-head" },
    h("div", {}, h("p", { class: "eyebrow" }, "Current goal"), h("h1", {}, `${plan.goal}, ${fmtDay(plan.race_date, { month: "long", day: "numeric", year: "numeric" })}`),
      h("p", { class: "muted mono" }, `Goal ${dur(plan.goal_time_s)} · ${pace(goalPace)}/mi · fitness predicts ${dur(plan.projected_time_s)}`)),
    h("div", { class: "countdown" }, h("span", { class: "big mono" }, Math.max(0, days_to_race)), h("span", { class: "label" }, days_to_race === 1 ? "day to go" : "days to go")));

  const calPanel = calendarPanel();
  const actions = h("div", { class: "plan-actions" },
    h("button", { class: "btn btn-primary", type: "button", onclick: () => { calPanel.open = true; calPanel.scrollIntoView({ behavior: "smooth", block: "nearest" }); } }, "Add to Google Calendar"),
    h("button", { class: "btn btn-quiet", type: "button", onclick: onNewPlan }, "New plan"),
    h("button", { class: "btn btn-quiet", type: "button", onclick: async () => {
      if (!confirm("Remove this plan? Your runs stay untouched.")) return;
      await api.del("/api/plan"); onChange({ plan: null });
    } }, "Remove plan"));

  const warnings = plan.warnings.length ? h("ul", { class: "plan-warnings" }, plan.warnings.map((w) => h("li", {}, w))) : null;
  const nextBanner = next ? h("section", { class: "next-banner" }, h("span", { class: "label" }, next.status === "today" ? "Today" : "Next up"),
    h("strong", {}, `${fmtDay(next.date, { weekday: "long", month: "short", day: "numeric" })}: ${next.title}`),
    h("span", { class: "muted mono" }, next.kind === "race" ? `${pace(next.pace_lo)}/mi` : `${pace(next.pace_lo)} to ${pace(next.pace_hi)} /mi`)) : null;

  const zoneFor = (w) => {
    if (!fit.hr_zones || !w.hr_zone) return null;
    const [a, b] = w.hr_zone, za = fit.hr_zones[a - 1], zb = fit.hr_zones[b - 1];
    return a === b ? `Zone ${a} (${za.lo}-${za.hi} bpm)` : `Zones ${a}-${b} (${za.lo}-${zb.hi} bpm)`;
  };
  function select(w, btn) {
    if (selectedBtn) selectedBtn.removeAttribute("aria-current");
    btn.setAttribute("aria-current", "true"); selectedBtn = btn;
    const done = w.status === "done" || w.status === "partial";
    detail.replaceChildren(...[
      h("div", { class: "wd-top" }, h("span", { class: `kind-dot kd-${w.kind}`, "aria-hidden": "true" }), h("h2", {}, w.title),
        h("span", { class: `status st-${w.status}` }, STATUS_TEXT[w.status])),
      h("p", { class: "muted" }, `${fmtLongDay(w.date)} · week ${w.week}, ${w.phase}`),
      h("p", {}, w.description),
      h("dl", { class: "wd-stats" },
        h("div", {}, h("dt", {}, "Distance"), h("dd", { class: "mono" }, `${w.distance_mi.toFixed(1)} mi`)),
        h("div", {}, h("dt", {}, "Target pace"), h("dd", { class: "mono pace-c" }, w.kind === "race" ? `${pace(w.pace_lo)}/mi` : `${pace(w.pace_lo)} to ${pace(w.pace_hi)} /mi`)),
        h("div", {}, h("dt", {}, "About"), h("dd", { class: "mono" }, `${w.duration_min} min`)),
        zoneFor(w) ? h("div", {}, h("dt", {}, "Heart rate"), h("dd", { class: "mono hr-c" }, zoneFor(w))) : null,
        done ? h("div", {}, h("dt", {}, "You ran"), h("dd", { class: "mono" }, `${w.actual_mi.toFixed(1)} mi`)) : null),
      w.run_id && done ? h("a", { class: "btn btn-quiet", href: `#/runs/${w.run_id}` }, "View that run") : null].filter(Boolean));
  }

  const mileage = mileageChart(plan.weeks, workouts);
  let preselect = null;
  const grid = h("div", { class: "week-grid", role: "table", "aria-label": "Training plan by week" },
    h("div", { class: "wg-head", role: "row" }, h("span", { role: "columnheader" }, "Week"), DOW.map((d) => h("span", { role: "columnheader" }, d)), h("span", { role: "columnheader", class: "wg-miles" }, "Miles")),
    plan.weeks.map((wk) => {
      const row = h("div", { class: `wg-row${wk.recovery ? " recovery" : ""}`, role: "row" },
        h("div", { class: "wg-label", role: "rowheader" }, h("strong", {}, `Wk ${wk.week}`), h("span", { class: "muted" }, `${fmtDay(wk.start)} · ${wk.recovery ? "recovery" : wk.phase}`)));
      for (let i = 0; i < 7; i++) {
        const date = addDays(wk.start, i), w = byDate.get(date);
        const isToday = date === ctx.meta.today;
        if (!w) { row.append(h("div", { class: `wg-cell empty${isToday ? " today" : ""}`, role: "cell" }, h("span", { class: "rest", "aria-label": "Rest" }, "·"))); continue; }
        const btn = h("button", { type: "button", class: `wg-workout kd-${w.kind} st-${w.status}`, "aria-label": `${fmtDay(date, { weekday: "long", month: "short", day: "numeric" })}: ${w.title}. ${STATUS_TEXT[w.status]}`,
          onclick: () => select(w, btn) },
          h("span", { class: "wgw-top" }, h("span", { class: "wgw-dist mono" }, w.distance_mi.toFixed(1)), h("span", { class: "wgw-mark", "aria-hidden": "true" }, STATUS_MARK[w.status])),
          h("span", { class: "wgw-kind" }, w.kind === "race" ? "RACE" : KIND_LABEL[w.kind] || w.kind));
        row.append(h("div", { class: `wg-cell${isToday ? " today" : ""}`, role: "cell" }, btn));
        if (next && w.date === next.date) preselect = [w, btn];
      }
      row.append(h("div", { class: "wg-cell wg-miles mono", role: "cell" }, wk.planned_mi.toFixed(1)));
      return row;
    }));
  if (preselect) select(...preselect);

  const legend = h("ul", { class: "legend" }, ["easy", "long", "tempo", "intervals", "race"].map((k) => h("li", {}, h("span", { class: `kind-dot kd-${k}` }), KIND_LABEL[k])),
    h("li", {}, h("span", { class: "mono" }, "✓"), "done"), h("li", {}, h("span", { class: "mono" }, "~"), "partly"), h("li", {}, h("span", { class: "mono" }, "×"), "missed"));
  const summary = h("p", { class: "muted mono" }, `${stats.done} done · ${stats.partial} partial · ${stats.missed} missed · ${stats.upcoming} to go` +
    (stats.planned_mi_to_date ? ` · ${stats.actual_mi_to_date.toFixed(0)} of ${stats.planned_mi_to_date.toFixed(0)} planned miles so far` : ""));

  return [head, warnings, h("div", { class: "plan-toolbar" }, actions, summary), calPanel, nextBanner,
    h("div", { class: "plan-main" }, h("div", { class: "plan-left" }, mileage, grid, legend), h("aside", { class: "plan-right" }, detail, numbersPanel(fit)))].filter(Boolean);
}

// =============================================================== calendar export
function calendarPanel() {
  const time = h("input", { class: "input mono", type: "time", id: "ics-time", value: "17:00", style: { maxWidth: "140px" } });
  const link = h("a", { class: "btn btn-primary", href: "/api/plan.ics?time=17:00", download: "" }, "Download calendar file (.ics)");
  time.addEventListener("input", () => link.setAttribute("href", `/api/plan.ics?time=${encodeURIComponent(time.value || "17:00")}`));
  return h("details", { class: "panel cal-panel" },
    h("summary", {}, h("strong", {}, "Add this plan to Google Calendar"), h("span", { class: "muted" }, " · one file, every workout")),
    h("div", { class: "cal-body" },
      h("div", { class: "cal-controls" }, h("div", { class: "field" }, h("label", { class: "label", for: "ics-time" }, "Usual run time"), time), link),
      h("ol", { class: "cal-steps" },
        h("li", {}, "Download the file above."),
        h("li", {}, "Open ", h("a", { href: "https://calendar.google.com/calendar/u/0/r/settings/export", target: "_blank", rel: "noopener" }, "Google Calendar's Import & export page"), "."),
        h("li", {}, "Choose the file and pick a calendar. Make a new calendar called “Run Lab” first, so you can delete the whole plan in one click later."),
        h("li", {}, "Click Import. Each run appears with its distance, pace, and heart-rate target, plus a reminder an hour before.")),
      h("p", { class: "hint" }, "Building a new plan later? Delete the old Run Lab calendar before importing the new one so you don't get both.")));
}

// =============================================================== weekly mileage chart
function mileageChart(weeks, workouts) {
  const W = 760, H = 130, pad = { l: 34, r: 8, t: 10, b: 22 };
  const actualByWeek = new Map(weeks.map((w) => [w.week, 0]));
  for (const w of workouts) if (w.actual_mi) actualByWeek.set(w.week, (actualByWeek.get(w.week) || 0) + w.actual_mi);
  const max = Math.max(...weeks.map((w) => Math.max(w.planned_mi, actualByWeek.get(w.week) || 0)), 10);
  const bw = (W - pad.l - pad.r) / weeks.length;
  const y = (v) => pad.t + (1 - v / max) * (H - pad.t - pad.b);
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, class: "mileage-chart", role: "img", "aria-label": "Planned and actual weekly mileage" });
  for (const v of [0, Math.round(max / 2), Math.round(max)]) {
    svg.append(s("line", { x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v), stroke: "var(--line-soft)" }), s("text", { x: pad.l - 6, y: y(v) + 4, "text-anchor": "end" }, String(v)));
  }
  weeks.forEach((w, i) => {
    const x = pad.l + i * bw + bw * 0.12, width = bw * 0.76, act = actualByWeek.get(w.week) || 0;
    svg.append(s("rect", { x, y: y(w.planned_mi), width, height: y(0) - y(w.planned_mi), rx: 2, fill: "none", stroke: "var(--faint)", "stroke-dasharray": w.recovery ? "3 2" : "0" }),
      act ? s("rect", { x, y: y(act), width, height: y(0) - y(act), rx: 2, fill: "var(--pace)", opacity: 0.9 }) : null);
    if (weeks.length <= 24 || i % 2 === 0) svg.append(s("text", { x: x + width / 2, y: H - 6, "text-anchor": "middle" }, String(w.week)));
  });
  return h("figure", { class: "mileage" }, h("figcaption", { class: "label" }, "Weekly miles: planned (outline) vs. run (filled)"), svg);
}
