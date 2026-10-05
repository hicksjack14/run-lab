// The race log: every race he has run (some come from the training plan by themselves, the rest he adds), plus personal bests.
import { api, isStatic } from "../lib/api.js";
import { h, toast } from "../lib/dom.js";
import { pace, dur, fmtDay, parseDuration, isoDate } from "../lib/fmt.js";

const MI = 1609.344;
export const DISTANCES = [["5K", 5000], ["10K", 10000], ["10 miles", 16093.44], ["Half marathon", 21097.5], ["Marathon", 42195]];
const PB_DISTANCES = [["5K", 5000], ["10K", 10000], ["Half marathon", 21097.5], ["Marathon", 42195]];

export function distLabel(m) {
  const hit = DISTANCES.find(([, d]) => Math.abs(m - d) / d <= 0.02);
  return hit ? hit[0] : `${(m / MI).toFixed(1)} mi`;
}

function personalBests(log) {
  return PB_DISTANCES.map(([label, d]) => {
    const rows = log.filter((e) => e.time_s && Math.abs(e.distance_m - d) / d <= 0.02);
    const best = rows.sort((a, b) => a.time_s - b.time_s)[0];
    return best ? { label, best } : null;
  }).filter(Boolean);
}

export function logSection(data, onData) {
  const log = data.log;
  const goalName = (key) => (data.goals.find((g) => g.key === key) || {}).short;
  const pbs = personalBests(log);
  const totalMi = log.reduce((a, e) => a + e.distance_m / MI, 0);

  const list = log.length
    ? h("ul", { class: "race-log" }, log.map((e) => h("li", { class: `rl-row${e.source === "plan" ? " from-plan" : ""}` },
      h("span", { class: "rl-date mono" }, fmtDay(e.race_date, { month: "short", day: "numeric", year: "numeric" })),
      h("span", { class: "rl-name" }, e.run_id ? h("a", { href: `#/runs/${e.run_id}` }, e.name) : e.name,
        h("span", { class: "rl-tags" },
          e.source === "plan" ? h("span", { class: "tag", title: "Added automatically from your training plan. The time is your watch's moving time." }, "From plan") : null,
          e.nyrr ? h("span", { class: "tag" }, "NYRR") : null,
          e.event ? h("span", { class: "tag tag-goal" }, `Counts: ${goalName(e.event) || e.event}`) : null)),
      h("span", { class: "rl-dist mono" }, distLabel(e.distance_m)),
      h("span", { class: "rl-time mono" }, e.time_s ? dur(e.time_s) : "no time"),
      h("span", { class: "rl-pace mono pace-c" }, e.time_s ? `${pace(e.time_s / (e.distance_m / MI))}/mi` : ""),
      isStatic || e.source === "plan" ? h("span") : h("button", { type: "button", class: "btn btn-quiet btn-small", "aria-label": `Remove ${e.name} from the log`,
        onclick: async () => { if (confirm(`Remove "${e.name}" from your race log?`)) { onData(await api.del(`/api/races/${e.id}`)); toast("Removed."); } } }, "Remove"))))
    : h("p", { class: "muted" }, "No races logged yet. Races from your training plan show up here on their own once you have run them. Add any you have already run below.");

  return h("section", { class: "races-section", "aria-labelledby": "race-log-h" },
    h("div", { class: "section-head" }, h("h2", { id: "race-log-h" }, "Race log"),
      log.length ? h("p", { class: "muted mono" }, `${log.length} race${log.length === 1 ? "" : "s"} · ${totalMi.toFixed(0)} mi raced`) : null),
    pbs.length ? h("dl", { class: "pb-row" }, pbs.map(({ label, best }) => h("div", {}, h("dt", { class: "label" }, `${label} best`), h("dd", { class: "mono" }, dur(best.time_s)), h("dd", { class: "muted" }, `${best.name}, ${fmtDay(best.race_date, { month: "short", year: "numeric" })}`)))) : null,
    list,
    isStatic ? null : addForm(data, onData));
}

function addForm(data, onData) {
  const today = data.today;
  const name = h("input", { class: "input", id: "rl-name", type: "text", maxlength: "80", placeholder: "e.g. Brooklyn Half", required: true });
  const date = h("input", { class: "input", id: "rl-date", type: "date", max: today, value: today, required: true });
  const distSel = h("select", { class: "input", id: "rl-dist", "aria-label": "Distance" }, [...DISTANCES.map(([l, d], i) => h("option", { value: d, selected: l === "Half marathon" ? true : null }, l)), h("option", { value: "other" }, "Other distance")]);
  const other = h("input", { class: "input mono", id: "rl-miles", type: "number", step: "0.01", min: "0.5", max: "120", placeholder: "miles", hidden: true, "aria-label": "Distance in miles" });
  const time = h("input", { class: "input mono", id: "rl-time", type: "text", inputmode: "numeric", autocomplete: "off", placeholder: "1:52:30 (optional)" });
  const event = h("select", { class: "input", id: "rl-event", "aria-label": "Counts toward" }, [h("option", { value: "" }, "None"), ...data.goals.map((g) => h("option", { value: g.key }, `It was the ${g.short}`))]);
  const nyrr = h("input", { type: "checkbox", id: "rl-nyrr" });
  const notes = h("input", { class: "input", id: "rl-notes", type: "text", maxlength: "300", placeholder: "Optional note" });
  const error = h("p", { class: "error-text", role: "alert" });
  const submit = h("button", { class: "btn btn-primary", type: "submit" }, "Add to log");
  distSel.addEventListener("change", () => { other.hidden = distSel.value !== "other"; });

  const form = h("form", { class: "goal-form", novalidate: true, onsubmit: async (e) => {
    e.preventDefault(); error.textContent = "";
    const distance_m = distSel.value === "other" ? Number(other.value) * MI : Number(distSel.value);
    const t = time.value.trim() ? parseDuration(time.value) : null;
    if (!name.value.trim()) { error.textContent = "Give the race a name."; return; }
    if (!(distance_m > 0)) { error.textContent = "Enter the distance in miles."; return; }
    if (time.value.trim() && !t) { error.textContent = "Finish time should look like 1:52:30 or 24:10."; return; }
    submit.disabled = true;
    try {
      onData(await api.post("/api/races", { name: name.value.trim(), race_date: date.value, distance_m, time_s: t, event: event.value || null, nyrr: nyrr.checked, notes: notes.value.trim() || null }));
      toast("Added to your race log.");
    } catch (err) { error.textContent = err.message; submit.disabled = false; }
  } },
    h("div", { class: "form-row" }, field("Race", "rl-name", name), field("Date", "rl-date", date)),
    h("div", { class: "form-row" }, h("div", { class: "field" }, h("label", { class: "label", for: "rl-dist" }, "Distance"), distSel, other), field("Official finish time", "rl-time", time)),
    h("div", { class: "form-row" }, field("Counts toward", "rl-event", event), field("Note", "rl-notes", notes)),
    h("label", { class: "check", for: "rl-nyrr" }, nyrr, h("span", {}, "An NYRR race (counts toward the NYC Half 4-of-6 and the Marathon 9+1)")),
    error, h("div", { class: "form-actions" }, submit));
  return h("details", { class: "add-race" }, h("summary", {}, "Add a race you've run"), form);
}

const field = (label, id, input) => h("div", { class: "field" }, h("label", { class: "label", for: id }, label), input);

export { isoDate };
