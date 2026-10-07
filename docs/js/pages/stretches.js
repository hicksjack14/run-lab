import { h, reducedMotion } from "../lib/dom.js";
import { ROUTINE, EXTRAS, CIRCUIT, SAFETY, routineSeconds, circuitRepsPerRound } from "../lib/stretches-data.js";

const KEY_MODE = "runlab.stretches.mode", KEY_CIRCUIT = "runlab.circuit.v1";
const store = {
  get(k, fallback) { try { const v = localStorage.getItem(k); return v == null ? fallback : JSON.parse(v); } catch { return fallback; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private window or blocked storage: the page still works */ } },
};
const mmss = (s) => { s = Math.max(0, Math.ceil(s)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
const todayKey = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };

// ------------------------------------------------------------------ shared: chime + screen wake lock + a drift-free ticker
function makeTools() {
  let audio = null, wake = null, soundOn = true, timer = null;
  return {
    get soundOn() { return soundOn; },
    toggleSound() { soundOn = !soundOn; return soundOn; },
    prime() { try { audio = audio || new (window.AudioContext || window.webkitAudioContext)(); audio.resume(); } catch { audio = null; } },
    chime(times = 1) {
      if (!soundOn || !audio) return;
      for (let n = 0; n < times; n++) {
        const t = audio.currentTime + n * 0.22, o = audio.createOscillator(), g = audio.createGain();
        o.frequency.value = 880; g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.18, t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.18);
        o.connect(g).connect(audio.destination); o.start(t); o.stop(t + 0.2);
      }
    },
    async keepAwake() { try { wake = await navigator.wakeLock.request("screen"); } catch { wake = null; } },
    letSleep() { try { wake && wake.release(); } catch { /* already released */ } wake = null; },
    every(ms, fn) { clearInterval(timer); timer = setInterval(fn, ms); },
    stop() { clearInterval(timer); timer = null; },
  };
}

// ------------------------------------------------------------------ the 15-minute stretch player
function stretchPlayer(tools) {
  const segs = [];
  ROUTINE.forEach((step, si) => (step.sides ? step.sides : [[null, step.secs]]).forEach(([side, secs]) => segs.push({ step, si, side, secs })));
  const total = segs.reduce((t, s) => t + s.secs, 0);
  let i = 0, left = segs[0].secs, running = false, last = 0, done = false;

  const el = {
    count: h("p", { class: "st-count mono", "aria-hidden": "true" }), name: h("h2", { class: "st-name" }), side: h("span", { class: "st-side" }), area: h("span", { class: "label" }),
    cues: h("ul", { class: "st-cues" }), why: h("p", { class: "st-why" }), easier: h("p", { class: "st-easier muted" }), next: h("p", { class: "muted st-next" }),
    segBar: h("div", { class: "st-fill" }), allBar: h("div", { class: "st-fill all" }), pos: h("span", { class: "mono muted" }), elapsed: h("span", { class: "mono muted" }),
  };
  const live = h("p", { class: "visually-hidden", "aria-live": "polite" });
  const startBtn = h("button", { class: "btn btn-primary btn-lg", type: "button", onclick: () => (running ? pause() : start()) }, "Start");
  const backBtn = h("button", { class: "btn btn-quiet", type: "button", onclick: () => go(i - 1) }, "Back");
  const skipBtn = h("button", { class: "btn btn-quiet", type: "button", onclick: () => go(i + 1) }, "Skip");
  const soundBtn = h("button", { class: "btn btn-quiet", type: "button", "aria-pressed": "true", onclick: () => { soundBtn.setAttribute("aria-pressed", String(tools.toggleSound())); soundBtn.textContent = tools.soundOn ? "Sound on" : "Sound off"; } }, "Sound on");

  function elapsedSecs() { return segs.slice(0, i).reduce((t, s) => t + s.secs, 0) + (done ? 0 : segs[i].secs - left); }
  function paint() {
    if (done) {
      el.count.textContent = "Done"; el.name.textContent = "Nice work"; el.side.textContent = ""; el.area.textContent = "Finished";
      el.cues.replaceChildren(h("li", {}, "Drink some water. Walk around for a minute before you sit down."));
      el.why.textContent = ""; el.easier.textContent = ""; el.next.textContent = "";
      el.segBar.style.width = "100%"; el.allBar.style.width = "100%"; el.pos.textContent = `${ROUTINE.length} of ${ROUTINE.length}`; el.elapsed.textContent = mmss(total);
      startBtn.textContent = "Do it again"; backBtn.disabled = false; skipBtn.disabled = true; return;
    }
    const sg = segs[i], nx = segs[i + 1];
    el.count.textContent = mmss(left);
    el.name.textContent = sg.step.name; el.area.textContent = sg.step.area;
    el.side.textContent = sg.side ? `${sg.side} side` : "Both sides together";
    el.side.dataset.side = sg.side || "both";
    el.cues.replaceChildren(...sg.step.cues.map((c) => h("li", {}, c)));
    el.why.textContent = sg.step.why; el.easier.textContent = `Easier: ${sg.step.easier}`;
    el.next.textContent = nx ? `Next: ${nx.step.name}${nx.side ? `, ${nx.side} side` : ""}` : "Last one";
    el.segBar.style.width = `${((sg.secs - left) / sg.secs) * 100}%`;
    el.allBar.style.width = `${(elapsedSecs() / total) * 100}%`;
    el.pos.textContent = `Move ${sg.si + 1} of ${ROUTINE.length}`; el.elapsed.textContent = `${mmss(elapsedSecs())} of ${mmss(total)}`;
    startBtn.textContent = running ? "Pause" : elapsedSecs() > 0 ? "Resume" : "Start";
    backBtn.disabled = i === 0; skipBtn.disabled = false;
  }
  function go(n) {
    if (n < 0) n = 0;
    if (n >= segs.length) { finish(); return; }
    done = false; i = n; left = segs[i].secs; last = Date.now(); paint();
    live.textContent = `${segs[i].step.name}${segs[i].side ? `, ${segs[i].side} side` : ""}, ${segs[i].secs} seconds`;
  }
  function finish() { done = true; running = false; tools.stop(); tools.letSleep(); tools.chime(3); paint(); }
  function tick() {
    const now = Date.now(); left -= (now - last) / 1000; last = now;
    if (left <= 0) { tools.chime(segs[i + 1] && segs[i + 1].step !== segs[i].step ? 2 : 1); go(i + 1); } else paint();
  }
  function start() {
    tools.prime();
    if (done) { done = false; i = 0; left = segs[0].secs; }
    running = true; last = Date.now(); tools.every(200, tick); tools.keepAwake(); paint();
  }
  function pause() { running = false; tools.stop(); tools.letSleep(); paint(); }

  const list = h("ol", { class: "st-list" }, ROUTINE.map((step, si) => {
    const secs = step.sides ? step.sides.map(([, n]) => n) : [step.secs];
    const detail = step.sides ? step.sides.map(([s, n]) => `${s} ${n}s`).join(" · ") : `${step.secs}s`;
    return h("li", {}, h("button", { type: "button", class: "st-row", onclick: () => { const at = segs.findIndex((s) => s.si === si); const wasRunning = running; go(at); if (!wasRunning) paint(); } },
      h("span", { class: "st-row-name" }, step.name, h("small", { class: "muted" }, step.area)), h("span", { class: "mono muted" }, detail),
      h("span", { class: "visually-hidden" }, `${secs.reduce((a, b) => a + b, 0)} seconds in all`)));
  }));
  paint();
  return h("div", { class: "st-wrap" },
    h("section", { class: "panel st-card", "aria-label": "Stretch player" },
      h("div", { class: "st-top" }, el.area, el.pos),
      h("div", { class: "st-main" }, h("div", {}, el.name, el.side), el.count),
      h("div", { class: "st-bar" }, el.segBar), el.cues, el.why, el.easier,
      h("div", { class: "st-controls" }, startBtn, backBtn, skipBtn, soundBtn),
      h("div", { class: "st-bar thin", role: "img", "aria-label": "Routine progress" }, el.allBar), h("div", { class: "st-foot" }, el.elapsed, el.next), live),
    h("section", { class: "st-side-col" }, h("h2", { class: "label" }, `The routine · ${mmss(total)}`), list,
      h("h2", { class: "label", style: { marginTop: "22px" } }, "Extras, not timed"),
      h("ul", { class: "st-extras" }, EXTRAS.map((x) => h("li", {}, h("strong", {}, x.name), h("span", { class: "muted" }, x.detail)))),
      h("div", { class: "st-safety" }, SAFETY.map((t) => h("p", { class: "hint" }, t)))));
}

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

// ------------------------------------------------------------------ page
export async function render(view) {
  const tools = makeTools();
  let mode = store.get(KEY_MODE, "stretch");
  const body = h("div", {});
  const modeBtns = [["stretch", `Stretch · ${Math.round(routineSeconds() / 60)} min`], ["circuit", `Circuit · ${CIRCUIT.minutes} min`]].map(([k, label]) =>
    h("button", { type: "button", "aria-pressed": String(k === mode), onclick: () => setMode(k) }, label));
  function setMode(k) {
    tools.stop(); tools.letSleep(); mode = k; store.set(KEY_MODE, k);
    modeBtns.forEach((b, n) => b.setAttribute("aria-pressed", String(n === (k === "stretch" ? 0 : 1))));
    body.replaceChildren(k === "stretch" ? stretchPlayer(tools) : circuitPlayer(tools));
  }
  view.replaceChildren(h("div", { class: `page stretches${reducedMotion() ? " calm" : ""}` },
    h("header", { class: "page-head" }, h("div", {}, h("p", { class: "eyebrow" }, "Daily"), h("h1", {}, "Stretches and circuit")), h("div", { class: "seg", role: "group", "aria-label": "Routine" }, modeBtns)), body));
  setMode(mode);
  return () => { tools.stop(); tools.letSleep(); };
}
