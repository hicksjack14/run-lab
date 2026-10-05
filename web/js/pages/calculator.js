// Race-time calculator: your pace (or target time) + your stops = a finish time, next to estimates from your own running.
import { api } from "../lib/api.js";
import { h, skeleton } from "../lib/dom.js";
import { pace as fmtPace, dur, parseDuration } from "../lib/fmt.js";

const DISTANCES = { "5K": 3.10686, "10K": 6.21371, "Half marathon": 13.1094, "Marathon": 26.2188, Custom: null };
const QUICK_STOPS = [["Water", 1, 0.5], ["Gel", 1, 0.5], ["Bathroom", 1, 2]];

function interp(curve, miles, field) {
  const d = Math.min(30, Math.max(1, miles));
  const i = Math.min(curve.length - 2, Math.max(0, Math.floor((d - 1) * 2)));
  const [a, b] = [curve[i], curve[i + 1]];
  if (a[field] == null || b[field] == null) return null;
  return a[field] + (b[field] - a[field]) * ((d - a.mi) / (b.mi - a.mi));
}
const confidenceOf = (curve, miles) => curve[Math.min(curve.length - 1, Math.max(0, Math.ceil((Math.min(30, Math.max(1, miles)) - 1) * 2)))].confidence;

export async function render(view, ctx) {
  view.replaceChildren(h("div", { class: "page" }, skeleton(8)));
  const model = await api.get("/api/calc");
  const hasUsual = !!model.usual;
  const st = { dist: "Half marathon", miles: DISTANCES["Half marathon"], mode: "pace", pace: null, time: null,
    routine: true, every: model.defaults.stop_every_mi, stopMin: model.defaults.stop_min, extras: [] };
  const usualPace = () => (hasUsual ? interp(model.curve, st.miles, "usual") : null);
  st.pace = Math.round(model.defaults.pace_s || usualPace() || 600);

  // ---------- inputs ----------
  const out = h("div", { class: "calc-out", "aria-live": "polite" });
  const err = h("p", { class: "error-text", role: "alert" });
  const distBtns = Object.keys(DISTANCES).map((k) => h("button", { type: "button", dataset: { k }, "aria-pressed": String(k === st.dist),
    onclick: () => { st.dist = k; if (DISTANCES[k]) { st.miles = DISTANCES[k]; customIn.value = st.miles.toFixed(2); } customWrap.hidden = k !== "Custom"; sync(); } }, k));
  const customIn = h("input", { class: "input mono", type: "number", step: "0.1", min: "1", max: "30", id: "c-miles", value: st.miles.toFixed(2), "aria-label": "Distance in miles",
    oninput: (e) => { const v = parseFloat(e.target.value); if (v >= 1 && v <= 30) { st.miles = v; paint(); } } });
  const customWrap = h("div", { class: "field", hidden: true }, h("label", { class: "label", for: "c-miles" }, "Miles (1 to 30)"), customIn);

  const paceIn = h("input", { class: "input mono", type: "text", id: "c-pace", inputmode: "numeric", autocomplete: "off", value: fmtPace(st.pace), placeholder: "9:45",
    oninput: (e) => { const v = parseDuration(e.target.value); st.pace = v && v > 180 && v < 1800 ? v : null; paint(); } });
  const timeIn = h("input", { class: "input mono", type: "text", id: "c-time", inputmode: "numeric", autocomplete: "off", placeholder: "2:10:00",
    oninput: (e) => { st.time = parseDuration(e.target.value); paint(); } });
  const paceField = h("div", { class: "field" }, h("label", { class: "label", for: "c-pace" }, "Pace per mile (while moving)"), paceIn);
  const timeField = h("div", { class: "field", hidden: true }, h("label", { class: "label", for: "c-time" }, "Target moving time (without stops)"), timeIn);
  function setMode(k) {
    st.mode = k;
    paceField.hidden = k !== "pace";
    timeField.hidden = k !== "time";
    modeBtns.forEach((b, i) => b.setAttribute("aria-pressed", String(i === (k === "pace" ? 0 : 1))));
    paint();
  }
  const modeBtns = [["pace", "I know my pace"], ["time", "I know my time"]].map(([k, label]) => h("button", { type: "button", "aria-pressed": String(k === st.mode), onclick: () => setMode(k) }, label));

  const routineOn = h("input", { type: "checkbox", id: "c-routine", checked: true, onchange: (e) => { st.routine = e.target.checked; paint(); } });
  const everyIn = h("input", { class: "input mono small", type: "number", step: "0.5", min: "0.5", id: "c-every", value: st.every, "aria-label": "Miles between stops", oninput: (e) => { st.every = parseFloat(e.target.value) || 0; paint(); } });
  const stopIn = h("input", { class: "input mono small", type: "number", step: "0.25", min: "0", id: "c-stop", value: st.stopMin, "aria-label": "Minutes per stop", oninput: (e) => { st.stopMin = parseFloat(e.target.value) || 0; paint(); } });
  const extrasHost = h("div", { class: "extras" });
  const addExtra = (label, count, min) => { st.extras.push({ label, count, min }); drawExtras(); paint(); };
  function drawExtras() {
    extrasHost.replaceChildren(...st.extras.map((x, i) => h("div", { class: "extra-row" },
      h("input", { class: "input", type: "text", value: x.label, "aria-label": "Stop name", oninput: (e) => (x.label = e.target.value) }),
      h("input", { class: "input mono small", type: "number", min: "0", step: "1", value: x.count, "aria-label": `${x.label} count`, oninput: (e) => { x.count = parseFloat(e.target.value) || 0; paint(); } }), h("span", { class: "muted" }, "×"),
      h("input", { class: "input mono small", type: "number", min: "0", step: "0.25", value: x.min, "aria-label": `${x.label} minutes each`, oninput: (e) => { x.min = parseFloat(e.target.value) || 0; paint(); } }), h("span", { class: "muted" }, "min"),
      h("button", { type: "button", class: "btn btn-quiet icon-btn", "aria-label": `Remove ${x.label}`, onclick: () => { st.extras.splice(i, 1); drawExtras(); paint(); } }, "×"))));
  }
  const observed = model.stops && model.stops.observed_min_per_mile;

  const form = h("section", { class: "calc-form", "aria-label": "Your plan" },
    h("div", { class: "field" }, h("span", { class: "label" }, "Race distance"), h("div", { class: "seg wrap", role: "group", "aria-label": "Race distance" }, distBtns)), customWrap,
    h("div", { class: "field" }, h("span", { class: "label" }, "How you'll run it"), h("div", { class: "seg", role: "group", "aria-label": "Pace or time" }, modeBtns)), paceField, timeField,
    h("div", { class: "field" }, h("span", { class: "label" }, "Your stops"),
      h("label", { class: "check", for: "c-routine" }, routineOn, "Stop every", everyIn, "miles for", stopIn, "min"),
      observed ? h("p", { class: "hint" }, `In your recent runs you stopped about ${observed.toFixed(1)} min per mile (${model.stops.n} runs). Your usual routine is pre-filled.`) : null),
    h("div", { class: "field" }, h("span", { class: "label" }, "Extra stops (gels, bathroom, shoelace)"), extrasHost,
      h("div", { class: "quick-row" }, QUICK_STOPS.map(([label, count, min]) => h("button", { type: "button", class: "chip-btn", onclick: () => addExtra(label, count, min) }, `+ ${label}`)))),
    err);

  const page = h("div", { class: "page calc" },
    h("header", { class: "page-head" }, h("div", {}, h("p", { class: "eyebrow" }, "Race-time calculator"), h("h1", {}, "What time will I run?")),
      h("p", { class: "muted pl-lede" }, "Your pace plus your stops gives a finish time. Next to it: what your own recent running and your fitness say.")),
    h("div", { class: "calc-grid" }, form, out));
  view.replaceChildren(page);
  drawExtras();

  // ---------- maths ----------
  function stopsFor(miles) {
    const routine = st.routine && st.every > 0 ? Math.max(0, Math.ceil(miles / st.every) - 1) : 0;
    const extra = st.extras.reduce((t, x) => t + x.count, 0);
    return { routine, count: routine + extra, seconds: routine * st.stopMin * 60 + st.extras.reduce((t, x) => t + x.count * x.min * 60, 0) };
  }
  const row = (label, value, cls = "") => h("div", { class: "kv" }, h("dt", {}, label), h("dd", { class: `mono ${cls}` }, value));

  function paint() {
    const miles = st.miles, stops = stopsFor(miles);
    const moving = st.mode === "pace" ? (st.pace ? st.pace * miles : null) : st.time;
    err.textContent = moving ? "" : st.mode === "pace" ? "Enter a pace like 9:45." : "Enter a time like 2:10:00.";
    const blocks = [];
    if (moving) {
      const finish = moving + stops.seconds, usedPace = moving / miles;
      blocks.push(h("section", { class: "result-main" }, h("p", { class: "label" }, "Your finish time"), h("p", { class: "big-time mono" }, dur(finish)),
        h("dl", { class: "kvs" }, row("Moving time", dur(moving)), row("Stopped", `${dur(stops.seconds)} (${stops.count} stop${stops.count === 1 ? "" : "s"})`),
          row("Pace while moving", `${fmtPace(usedPace)}/mi`, "pace-c"), row("Average pace with stops", `${fmtPace(finish / miles)}/mi`))));
      if (model.hr_at_pace && model.max_hr) {
        const hr = model.hr_at_pace.c + model.hr_at_pace.k * usedPace, pct = (hr / model.max_hr) * 100;
        const inRange = usedPace >= model.hr_at_pace.pace_lo - 30 && usedPace <= model.hr_at_pace.pace_hi + 30;
        const verdict = pct < 75 ? "easy: you could hold this a long time" : pct < 85 ? "comfortably hard: sustainable for most of an hour or more" : pct < 92 ? "hard: tough to hold past about an hour" : "near your limit: you won't hold this for long";
        blocks.push(h("section", { class: "result-sec" }, h("p", { class: "label" }, "Heart rate at that pace"),
          h("p", { class: "mono hr-c result-num" }, `about ${Math.round(hr)} bpm`, h("small", {}, ` ${Math.round(pct)}% of your max`)), h("p", { class: "muted" }, `${verdict[0].toUpperCase()}${verdict.slice(1)}.`),
          h("p", { class: "hint" }, inRange ? `From ${model.hr_at_pace.n} of your recent runs.` : "That pace is outside what your recent runs cover, so treat this as a rough guess.")));
      }
    }
    // estimates from his own data
    const estimates = [];
    if (hasUsual) {
      const p = usualPace(), band = interp(model.curve, miles, "band"), conf = confidenceOf(model.curve, miles);
      const lo = (p - band) * miles + stops.seconds, mid = p * miles + stops.seconds, hi = (p + band) * miles + stops.seconds;
      const confText = { solid: "Solid: you've run about this far recently.", stretch: `A stretch: your longest run is ${model.longest_mi.toFixed(1)} mi, so this goes beyond your evidence.`, guess: `A guess: your longest run is ${model.longest_mi.toFixed(1)} mi, far short of this distance.` }[conf];
      estimates.push(h("section", { class: "result-sec" }, h("p", { class: "label" }, "Based on how you run now"),
        h("p", { class: "mono result-num" }, dur(mid), h("small", {}, ` range ${dur(lo)} to ${dur(hi)}`)),
        h("p", { class: "muted" }, `Your usual effort over ${miles.toFixed(1)} miles is about ${fmtPace(p)}/mi, plus your stops. Your pace slows about ${Math.round(model.usual.seconds_slower_per_doubling)} sec/mi every time the distance doubles.`),
        h("p", { class: `conf-note c-${conf}` }, confText),
        moving ? h("p", { class: "muted" }, deltaText(moving + stops.seconds, mid)) : null,
        h("button", { type: "button", class: "btn btn-quiet", onclick: () => { st.pace = Math.round(p); paceIn.value = fmtPace(st.pace); setMode("pace"); } }, "Use this pace")));
    } else {
      estimates.push(h("section", { class: "result-sec" }, h("p", { class: "label" }, "Based on how you run now"),
        h("p", { class: "muted" }, `Needs at least 8 runs of 1+ mile in the last ${4} months of different lengths. You have ${model.recent_runs} so far. Sync more runs and this fills in.`)));
    }
    const race = interp(model.curve, miles, "race_s");
    if (race) {
      estimates.push(h("section", { class: "result-sec" }, h("p", { class: "label" }, "If you raced it (fitness estimate)"),
        h("p", { class: "mono result-num" }, dur(race + stops.seconds), h("small", {}, ` ${dur(race)} moving`)),
        h("p", { class: "muted" }, `Your fitness score of ${model.vdot.toFixed(1)} is worth ${fmtPace(race / miles)}/mi flat out for ${miles.toFixed(1)} miles. Racing with fewer stops would be faster still.`),
        model.vdot_is_estimate ? h("p", { class: "hint" }, "Your fitness score is an estimate from training runs, so this reads on the cautious side. Adding a race result in the Planner sharpens it.") : null));
    }
    out.replaceChildren(...blocks, ...estimates);
  }
  const deltaText = (planned, estimate) => {
    const diff = planned - estimate, m = Math.round(Math.abs(diff) / 60);
    return Math.abs(diff) < 60 ? "Your plan matches that estimate." : `Your plan is about ${m} min ${diff < 0 ? "faster" : "slower"} than that estimate.`;
  };
  function sync() { paint(); }
  paint();
}
