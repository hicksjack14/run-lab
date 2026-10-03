import { api, isStatic } from "../lib/api.js";
import { h, skeleton, toast } from "../lib/dom.js";
import { pace, dur, fmtDay, addDays, parseLocal, parseDuration } from "../lib/fmt.js";
import { mileageChart, weekGrid, workoutDetail, paceText } from "../lib/plangrid.js";

const GOALS = ["5K", "10K", "Half marathon", "Marathon"];
const MIN_WEEKS = { "5K": 6, "10K": 8, "Half marathon": 10, "Marathon": 14 };

export async function render(view, _params, ctx) {
  view.replaceChildren(h("div", { class: "page" }, skeleton(8)));
  const [planData, fit] = await Promise.all([api.get("/api/plan"), api.get("/api/fitness")]);
  const root = h("div", { class: "page planner" });
  view.replaceChildren(root);

  const show = (data, forceForm = false) => {
    root.replaceChildren();
    if (isStatic && !data.plan) root.append(h("div", { class: "empty-state" }, h("p", { class: "eyebrow" }, "Planner"), h("h1", {}, "No plan in this snapshot"),
      h("p", {}, "Plans are built in Run Lab on your computer. Build one there, then update the snapshot and it shows up here.")));
    else if (!data.plan || forceForm) root.append(goalForm(data, fit, ctx, (d) => show(d), () => show(data)));
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

  if (isStatic) return body;      // the read-only copy can't change settings
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
  const { plan, workouts, stats, next } = data;
  const daysToRace = Math.round((parseLocal(plan.race_date) - parseLocal(ctx.meta.today)) / 86400000);   // from today's date, so it stays right between snapshots
  const detail = h("section", { class: "workout-detail", "aria-live": "polite" }, h("p", { class: "muted" }, "Select a workout to see its pace, heart-rate target, and details."));
  let selectedBtn = null;

  const goalPace = plan.goal_time_s / (plan.race_distance_m / 1609.344);
  const head = h("header", { class: "plan-head" },
    h("div", {}, h("p", { class: "eyebrow" }, "Current goal"), h("h1", {}, `${plan.goal}, ${fmtDay(plan.race_date, { month: "long", day: "numeric", year: "numeric" })}`),
      h("p", { class: "muted mono" }, `Goal ${dur(plan.goal_time_s)} · ${pace(goalPace)}/mi · fitness predicts ${dur(plan.projected_time_s)}`)),
    h("div", { class: "countdown" }, h("span", { class: "big mono" }, Math.max(0, daysToRace)), h("span", { class: "label" }, daysToRace === 1 ? "day to go" : "days to go")));

  const calPanel = calendarPanel();
  const actions = h("div", { class: "plan-actions" },
    h("button", { class: "btn btn-primary", type: "button", onclick: () => { calPanel.open = true; calPanel.scrollIntoView({ behavior: "smooth", block: "nearest" }); } }, "Add to Google Calendar"),
    isStatic ? null : h("button", { class: "btn btn-quiet", type: "button", onclick: onNewPlan }, "New plan"),
    isStatic ? null : h("button", { class: "btn btn-quiet", type: "button", onclick: async () => {
      if (!confirm("Remove this plan? Your runs stay untouched.")) return;
      await api.del("/api/plan"); onChange({ plan: null });
    } }, "Remove plan"));

  const warnings = plan.warnings.length ? h("ul", { class: "plan-warnings" }, plan.warnings.map((w) => h("li", {}, w))) : null;
  const nextBanner = next ? h("section", { class: "next-banner" }, h("span", { class: "label" }, next.status === "today" ? "Today" : "Next up"),
    h("strong", {}, `${fmtDay(next.date, { weekday: "long", month: "short", day: "numeric" })}: ${next.title}`),
    h("span", { class: "muted mono" }, paceText(next))) : null;

  function select(w, btn) {
    if (selectedBtn) selectedBtn.removeAttribute("aria-current");
    btn.setAttribute("aria-current", "true"); selectedBtn = btn;
    detail.replaceChildren(...workoutDetail(w, fit));
  }

  const mileage = mileageChart(plan.weeks, workouts);
  const { grid, preselect, legend } = weekGrid(plan, workouts, { today: ctx.meta.today, nextDate: next && next.date, onSelect: select });
  if (preselect) select(...preselect);

  const summary = h("p", { class: "muted mono" }, `${stats.done} done · ${stats.partial} partial · ${stats.missed} missed · ${stats.upcoming} to go` +
    (stats.planned_mi_to_date ? ` · ${stats.actual_mi_to_date.toFixed(0)} of ${stats.planned_mi_to_date.toFixed(0)} planned miles so far` : ""));

  return [head, warnings, h("div", { class: "plan-toolbar" }, actions, summary), calPanel, nextBanner,
    h("div", { class: "plan-main" }, h("div", { class: "plan-left" }, mileage, grid, legend), h("aside", { class: "plan-right" }, detail, numbersPanel(fit)))].filter(Boolean);
}

// =============================================================== calendar export
function calendarPanel() {
  const time = h("input", { class: "input mono", type: "time", id: "ics-time", value: "17:00", style: { maxWidth: "140px" } });
  const link = h("a", { class: "btn btn-primary", href: isStatic ? "data/plan.ics" : "/api/plan.ics?time=17:00", download: "" }, "Download calendar file (.ics)");
  time.addEventListener("input", () => link.setAttribute("href", `/api/plan.ics?time=${encodeURIComponent(time.value || "17:00")}`));
  return h("details", { class: "panel cal-panel" },
    h("summary", {}, h("strong", {}, "Add this plan to Google Calendar"), h("span", { class: "muted" }, " · one file, every workout")),
    h("div", { class: "cal-body" },
      h("div", { class: "cal-controls" }, isStatic ? null : h("div", { class: "field" }, h("label", { class: "label", for: "ics-time" }, "Usual run time"), time), link),
      h("ol", { class: "cal-steps" },
        h("li", {}, "Download the file above."),
        h("li", {}, "Open ", h("a", { href: "https://calendar.google.com/calendar/u/0/r/settings/export", target: "_blank", rel: "noopener" }, "Google Calendar's Import & export page"), "."),
        h("li", {}, "Choose the file and pick a calendar. Make a new calendar called “Run Lab” first, so you can delete the whole plan in one click later."),
        h("li", {}, "Click Import. Each run appears with its distance, pace, and heart-rate target, plus a reminder an hour before.")),
      h("p", { class: "hint" }, "Building a new plan later? Delete the old Run Lab calendar before importing the new one so you don't get both.")));
}
