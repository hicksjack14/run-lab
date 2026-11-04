import { h, reducedMotion } from "../lib/dom.js";
import { CIRCUIT, circuitRepsPerRound, ROUTINES } from "../lib/workouts-data.js";
import { guidedPlayer } from "./workouts-guided.js";
import { store, mmss, todayKey, makeTools } from "../lib/routine-tools.js";

const KEY_PICK = "runlab.workouts.pick.v1";

const KEY_CIRCUIT = "runlab.circuit.v1";

// ------------------------------------------------------------------ the 20-minute circuit
function circuitPlayer(tools) {
  const total = CIRCUIT.minutes * 60, perRound = circuitRepsPerRound();
  const log = store.get(KEY_CIRCUIT, {});
  let left = total, running = false, last = 0, finished = false, rounds = log[todayKey()] || 0;

  const count = h("p", { class: "st-count mono", "aria-hidden": "true" }), roundsEl = h("p", { class: "ci-rounds mono" }), repsEl = h("p", { class: "muted" });
  const bar = h("div", { class: "st-fill all" }), hist = h("div", { class: "ci-hist" });
  const startBtn = h("button", { class: "btn btn-primary btn-lg", type: "button", onclick: () => (running ? pause() : start()) }, "Start the clock");
  const roundBtn = h("button", { class: "btn btn-primary btn-lg ci-round", type: "button", onclick: () => setRounds(rounds + 1) }, "Round done");
  const undoBtn = h("button", { class: "btn btn-quiet", type: "button", onclick: () => setRounds(Math.max(0, rounds - 1)) }, "−1 round");
  const resetBtn = h("button", { class: "btn btn-quiet", type: "button", onclick: reset }, "Reset clock");

  function setRounds(n) { rounds = n; log[todayKey()] = n; store.set(KEY_CIRCUIT, log); paint(); }
  function paintHist() {
    const days = Array.from({ length: 7 }, (_, k) => { const d = new Date(); d.setDate(d.getDate() - (6 - k)); const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; return { key, n: log[key] || 0, label: d.toLocaleDateString(undefined, { weekday: "narrow" }) }; });
    const max = Math.max(1, ...days.map((d) => d.n));
    hist.replaceChildren(...days.map((d) => h("div", { class: "ci-day", title: `${d.key}: ${d.n} rounds` },
      h("span", { class: "mono ci-n" }, d.n || "·"), h("div", { class: "ci-col" }, h("div", { style: { height: `${(d.n / max) * 100}%` } })), h("span", { class: "label" }, d.label))));
  }
  function paint() {
    count.textContent = finished ? "Time" : mmss(left);
    roundsEl.textContent = `${rounds} round${rounds === 1 ? "" : "s"} today`;
    repsEl.textContent = rounds ? `${rounds * perRound} reps: ${CIRCUIT.exercises.map((e) => `${rounds * e.reps} ${e.name.toLowerCase()}`).join(", ")}` : "Nothing logged yet today.";
    bar.style.width = `${((total - left) / total) * 100}%`;
    startBtn.textContent = running ? "Pause" : finished ? "Go again" : left < total ? "Resume" : "Start the clock";
    paintHist();
  }
  function tick() {
    const now = Date.now(); left -= (now - last) / 1000; last = now;
    if (left <= 0) { left = 0; finished = true; running = false; tools.stop(); tools.letSleep(); tools.chime(3); }
    paint();
  }
  function start() { tools.prime(); if (finished) { finished = false; left = total; } running = true; last = Date.now(); tools.every(200, tick); tools.keepAwake(); paint(); }
  function pause() { running = false; tools.stop(); tools.letSleep(); paint(); }
  function reset() { running = false; finished = false; left = total; tools.stop(); tools.letSleep(); paint(); }
  paint();

  return h("div", { class: "st-wrap" },
    h("section", { class: "panel st-card", "aria-label": "Daily circuit" },
      h("div", { class: "st-top" }, h("span", { class: "label" }, `${CIRCUIT.minutes} minutes, as many rounds as you can`), h("span", { class: "mono muted" }, `${perRound} reps a round`)),
      h("div", { class: "st-main" }, h("div", {}, h("h2", { class: "st-name" }, "Daily circuit"), roundsEl, repsEl), count),
      h("div", { class: "st-bar" }, bar),
      h("div", { class: "st-controls" }, startBtn, roundBtn, undoBtn, resetBtn),
      h("p", { class: "hint" }, CIRCUIT.note)),
    h("section", { class: "st-side-col" }, h("h2", { class: "label" }, "Every round"),
      h("ol", { class: "ci-list" }, CIRCUIT.exercises.map((e) => h("li", {}, h("div", { class: "ci-ex" }, h("strong", {}, e.name), h("span", { class: "mono ci-reps" }, `× ${e.reps}`)), h("p", { class: "st-why" }, e.cue), h("p", { class: "muted st-easier" }, `Easier: ${e.scale}`)))),
      h("h2", { class: "label", style: { marginTop: "22px" } }, "Last 7 days (saved on this device)"), hist));
}

// ------------------------------------------------------------------ page: pick a routine, then run it
export async function render(view) {
  const tools = makeTools();
  const choices = [...ROUTINES.map((r) => ({ id: r.id, label: r.name, sub: `${r.minutes} min` })), { id: "circuit", label: "Open clock", sub: "20 min, any order" }];
  let pick = store.get(KEY_PICK, ROUTINES[0].id);
  if (!choices.some((c) => c.id === pick)) pick = choices[0].id;
  const stage = h("div", {});
  let current = null;
  const picker = h("div", { class: "wk-picker", role: "group", "aria-label": "Choose a routine" });
  function show(id) {
    if (current) current.stop();
    tools.stop(); tools.letSleep(); pick = id; store.set(KEY_PICK, id);
    picker.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.id === id)));
    if (id === "circuit") { current = { stop() {} }; stage.replaceChildren(circuitPlayer(tools)); return; }
    current = guidedPlayer(ROUTINES.find((r) => r.id === id), tools); stage.replaceChildren(current.node);
  }
  picker.append(...choices.map((c) => h("button", { type: "button", class: "chip-btn", "data-id": c.id, "aria-pressed": "false", onclick: () => show(c.id) }, `${c.label} · ${c.sub}`)));
  view.replaceChildren(h("div", { class: `page stretches${reducedMotion() ? " calm" : ""}` },
    h("header", { class: "page-head" }, h("div", {}, h("p", { class: "eyebrow" }, "Daily"), h("h1", {}, "Workouts"))), picker, stage));
  show(pick);
  return () => { if (current) current.stop(); tools.stop(); tools.letSleep(); };
}
