// Guided calisthenics player: walks through one routine step by step, with the reps, form cues and an easier option for each move.
import { h } from "../lib/dom.js";
import { stepSecs, routineSecs } from "../lib/workouts-data.js";
import { store, mmss, todayKey } from "../lib/routine-tools.js";

const KEY_DONE = "runlab.routines.v1";   // { "2026-11-04": ["fedoseev", ...] }, per device

export function guidedPlayer(routine, tools) {
  const steps = routine.steps, estTotal = routineSecs(routine);
  const done = store.get(KEY_DONE, {});
  let i = 0, left = 0, elapsed = 0, state = "idle", last = 0;   // state: idle | running | paused | finished
  const target = (st) => (st.kind === "reps" ? `× ${st.reps}` : st.kind === "timed" ? st.target : "");
  const enter = (n) => { i = n; left = steps[i].kind === "reps" ? 0 : steps[i].secs; last = Date.now(); };
  enter(0);

  const el = {
    kind: h("span", { class: "label" }), pos: h("span", { class: "mono muted" }), name: h("h2", { class: "st-name" }), target: h("p", { class: "ci-rounds mono" }),
    count: h("p", { class: "st-count mono", "aria-hidden": "true" }), cue: h("p", { class: "st-why" }), easier: h("p", { class: "st-easier muted" }),
    bar: h("div", { class: "st-fill" }), allBar: h("div", { class: "st-fill all" }), elapsed: h("span", { class: "mono muted" }), next: h("p", { class: "muted st-next" }),
  };
  const live = h("p", { class: "visually-hidden", "aria-live": "polite" });
  const mainBtn = h("button", { class: "btn btn-primary btn-lg", type: "button", onclick: onMain }, "Start");
  const pauseBtn = h("button", { class: "btn btn-quiet", type: "button", onclick: onPause }, "Pause");
  const backBtn = h("button", { class: "btn btn-quiet", type: "button", onclick: () => go(i - 1) }, "Back");
  const soundBtn = h("button", { class: "btn btn-quiet", type: "button", "aria-pressed": "true", onclick: () => { soundBtn.setAttribute("aria-pressed", String(tools.toggleSound())); soundBtn.textContent = tools.soundOn ? "Sound on" : "Sound off"; } }, "Sound on");
  const rows = steps.map((st, n) => h("li", {}, h("button", { type: "button", class: "st-row", onclick: () => go(n) },
    h("span", { class: "st-row-name" }, st.name), h("span", { class: "mono muted" }, st.kind === "reps" ? `× ${st.reps}` : st.kind === "timed" ? mmss(st.secs) : mmss(st.secs)))));

  function paint() {
    if (state === "finished") {
      el.kind.textContent = "Finished"; el.pos.textContent = ""; el.name.textContent = "Nice work"; el.target.textContent = "";
      el.count.textContent = "Done"; el.cue.textContent = "Drink some water and walk around for a minute. Stretches tab next if your legs feel tight."; el.easier.textContent = ""; el.next.textContent = "";
      el.bar.style.width = "100%"; el.allBar.style.width = "100%"; el.elapsed.textContent = `${mmss(elapsed)} total`;
      mainBtn.textContent = "Do it again"; pauseBtn.hidden = true; backBtn.disabled = false; rows.forEach((r) => r.firstChild.removeAttribute("aria-current")); return;
    }
    const st = steps[i], nx = steps[i + 1];
    el.kind.textContent = st.kind === "reps" ? "Do the reps" : st.kind === "timed" ? "On the clock" : "Rest";
    el.pos.textContent = `Step ${i + 1} of ${steps.length}`;
    el.name.textContent = st.name; el.target.textContent = target(st);
    el.count.textContent = st.kind === "reps" ? "" : mmss(left);
    el.cue.textContent = st.cue; el.easier.textContent = st.easier ? `Easier: ${st.easier}` : "";
    el.next.textContent = nx ? `Next: ${nx.name}${nx.kind === "reps" ? ` × ${nx.reps}` : nx.kind === "timed" ? `, ${nx.target}` : ""}` : "Last one";
    el.bar.style.width = st.kind === "reps" ? "0%" : `${((st.secs - left) / st.secs) * 100}%`;
    el.allBar.style.width = `${Math.min(100, (elapsed / estTotal) * 100)}%`;
    el.elapsed.textContent = `${mmss(elapsed)} · about ${routine.minutes} min in all`;
    mainBtn.textContent = state === "idle" ? "Start" : st.kind === "reps" ? "Done, next" : st.kind === "rest" ? "Skip rest" : "Next";
    pauseBtn.hidden = state === "idle"; pauseBtn.textContent = state === "paused" ? "Resume" : "Pause";
    backBtn.disabled = i === 0;
    rows.forEach((r, n) => (n === i ? r.firstChild.setAttribute("aria-current", "step") : r.firstChild.removeAttribute("aria-current")));
  }
  function announce() { const st = steps[i]; live.textContent = `${st.name}${st.kind === "reps" ? `, ${st.reps} reps` : st.kind === "timed" ? `, ${st.target}` : `, ${st.secs} seconds`}`; }
  function go(n) {
    if (n < 0) n = 0;
    if (n >= steps.length) { finish(); return; }
    enter(n); if (state === "finished") state = "paused"; paint(); announce();
  }
  function finish() {
    state = "finished"; tools.stop(); tools.letSleep(); tools.chime(3);
    const k = todayKey(); done[k] = [...(done[k] || []), routine.id]; store.set(KEY_DONE, done); paintLog();
    paint();
  }
  function tick() {
    const now = Date.now(), dt = (now - last) / 1000; last = now; elapsed += dt;
    const st = steps[i];
    if (st.kind !== "reps") { left -= dt; if (left <= 0) { tools.chime(steps[i + 1] && steps[i + 1].kind === "rest" ? 1 : 2); go(i + 1); return; } }
    paint();
  }
  function run() { state = "running"; last = Date.now(); tools.every(200, tick); tools.keepAwake(); }
  function onMain() {
    tools.prime();
    if (state === "finished") { elapsed = 0; enter(0); run(); paint(); announce(); return; }
    if (state === "idle") { run(); paint(); announce(); return; }
    if (state === "paused") run();
    go(i + 1);
  }
  function onPause() { if (state === "running") { state = "paused"; tools.stop(); tools.letSleep(); } else if (state === "paused") run(); paint(); }

  const logEl = h("p", { class: "hint" });
  function paintLog() {
    const days = Array.from({ length: 7 }, (_, k) => { const d = new Date(); d.setDate(d.getDate() - k); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; });
    const week = days.reduce((t, k) => t + (done[k] || []).length, 0), today = (done[todayKey()] || []).length;
    logEl.textContent = `Finished ${today} today, ${week} in the last 7 days (saved on this device).`;
  }
  paintLog(); paint();

  return {
    stop() { state = state === "running" ? "paused" : state; tools.stop(); tools.letSleep(); },
    node: h("div", { class: "st-wrap" },
      h("section", { class: "panel st-card", "aria-label": routine.name },
        h("div", { class: "st-top" }, el.kind, el.pos),
        h("div", { class: "st-main" }, h("div", {}, el.name, el.target), el.count),
        h("div", { class: "st-bar" }, el.bar), el.cue, el.easier,
        h("div", { class: "st-controls" }, mainBtn, pauseBtn, backBtn, soundBtn),
        h("div", { class: "st-bar thin", role: "img", "aria-label": "Routine progress" }, el.allBar), h("div", { class: "st-foot" }, el.elapsed, el.next), live),
      h("section", { class: "st-side-col" }, h("h2", { class: "label" }, routine.name), h("p", { class: "muted" }, routine.blurb), h("p", { class: "hint" }, routine.note),
        h("h2", { class: "label", style: { marginTop: "18px" } }, "All steps"), h("ol", { class: "st-list" }, rows), logEl)),
  };
}
