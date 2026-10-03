// Training-plan pieces shared by the Planner and Home pages: weekly mileage chart, the week-by-week grid, one workout's detail.
import { h, s } from "./dom.js";
import { pace, fmtDay, fmtLongDay, addDays, KIND_LABEL } from "./fmt.js";

export const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
export const STATUS_MARK = { done: "✓", partial: "~", missed: "×", today: "•", upcoming: "" };
export const STATUS_TEXT = { done: "Done", partial: "Partly done", missed: "Missed", today: "Today", upcoming: "Upcoming" };

export function paceText(w) {
  return w.kind === "race" ? `${pace(w.pace_lo)}/mi` : `${pace(w.pace_lo)} to ${pace(w.pace_hi)} /mi`;
}

// ---------------------------------------------------------------- weekly mileage chart
export function mileageChart(weeks, workouts) {
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

// ---------------------------------------------------------------- week-by-week grid
// onSelect(workout, button) fires on click. Returns the grid, the button for the next workout (to preselect), and a legend.
export function weekGrid(plan, workouts, { today, nextDate, onSelect }) {
  const byDate = new Map(workouts.map((w) => [w.date, w]));
  let preselect = null;
  const grid = h("div", { class: "week-grid", role: "table", "aria-label": "Training plan by week" },
    h("div", { class: "wg-head", role: "row" }, h("span", { role: "columnheader" }, "Week"), DOW.map((d) => h("span", { role: "columnheader" }, d)), h("span", { role: "columnheader", class: "wg-miles" }, "Miles")),
    plan.weeks.map((wk) => {
      const row = h("div", { class: `wg-row${wk.recovery ? " recovery" : ""}`, role: "row" },
        h("div", { class: "wg-label", role: "rowheader" }, h("strong", {}, `Wk ${wk.week}`), h("span", { class: "muted" }, `${fmtDay(wk.start)} · ${wk.recovery ? "recovery" : wk.phase}`)));
      for (let i = 0; i < 7; i++) {
        const date = addDays(wk.start, i), w = byDate.get(date);
        const isToday = date === today;
        if (!w) { row.append(h("div", { class: `wg-cell empty${isToday ? " today" : ""}`, role: "cell" }, h("span", { class: "rest", "aria-label": "Rest" }, "·"))); continue; }
        const btn = h("button", { type: "button", class: `wg-workout kd-${w.kind} st-${w.status}`, "aria-label": `${fmtDay(date, { weekday: "long", month: "short", day: "numeric" })}: ${w.title}. ${STATUS_TEXT[w.status]}`,
          onclick: () => onSelect(w, btn) },
          h("span", { class: "wgw-top" }, h("span", { class: "wgw-dist mono" }, w.distance_mi.toFixed(1)), h("span", { class: "wgw-mark", "aria-hidden": "true" }, STATUS_MARK[w.status])),
          h("span", { class: "wgw-kind" }, w.kind === "race" ? "RACE" : KIND_LABEL[w.kind] || w.kind));
        row.append(h("div", { class: `wg-cell${isToday ? " today" : ""}`, role: "cell" }, btn));
        if (nextDate && w.date === nextDate) preselect = [w, btn];
      }
      row.append(h("div", { class: "wg-cell wg-miles mono", role: "cell" }, wk.planned_mi.toFixed(1)));
      return row;
    }));
  const legend = h("ul", { class: "legend" }, ["easy", "long", "tempo", "intervals", "race"].map((k) => h("li", {}, h("span", { class: `kind-dot kd-${k}` }), KIND_LABEL[k])),
    h("li", {}, h("span", { class: "mono" }, "✓"), "done"), h("li", {}, h("span", { class: "mono" }, "~"), "partly"), h("li", {}, h("span", { class: "mono" }, "×"), "missed"));
  return { grid, preselect, legend };
}

// ---------------------------------------------------------------- one workout's details (children for a .workout-detail section)
export function workoutDetail(w, fit) {
  const done = w.status === "done" || w.status === "partial";
  const zoneFor = () => {
    if (!fit || !fit.hr_zones || !w.hr_zone) return null;
    const [a, b] = w.hr_zone, za = fit.hr_zones[a - 1], zb = fit.hr_zones[b - 1];
    return a === b ? `Zone ${a} (${za.lo}-${za.hi} bpm)` : `Zones ${a}-${b} (${za.lo}-${zb.hi} bpm)`;
  };
  const zone = zoneFor();
  return [
    h("div", { class: "wd-top" }, h("span", { class: `kind-dot kd-${w.kind}`, "aria-hidden": "true" }), h("h2", {}, w.title),
      h("span", { class: `status st-${w.status}` }, STATUS_TEXT[w.status])),
    h("p", { class: "muted" }, `${fmtLongDay(w.date)} · week ${w.week}, ${w.phase}`),
    h("p", {}, w.description),
    h("dl", { class: "wd-stats" },
      h("div", {}, h("dt", {}, "Distance"), h("dd", { class: "mono" }, `${w.distance_mi.toFixed(1)} mi`)),
      h("div", {}, h("dt", {}, "Target pace"), h("dd", { class: "mono pace-c" }, paceText(w))),
      h("div", {}, h("dt", {}, "About"), h("dd", { class: "mono" }, `${w.duration_min} min`)),
      zone ? h("div", {}, h("dt", {}, "Heart rate"), h("dd", { class: "mono hr-c" }, zone)) : null,
      done ? h("div", {}, h("dt", {}, "You ran"), h("dd", { class: "mono" }, `${w.actual_mi.toFixed(1)} mi`)) : null),
    w.run_id && done ? h("a", { class: "btn btn-quiet", href: `#/runs/${w.run_id}` }, "View that run") : null].filter(Boolean);
}
