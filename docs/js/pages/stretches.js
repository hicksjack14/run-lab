import { h, reducedMotion } from "../lib/dom.js";
import { ROUTINE, EXTRAS, SAFETY, routineSeconds } from "../lib/stretches-data.js";
import { mmss, makeTools } from "../lib/routine-tools.js";

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

// ------------------------------------------------------------------ page
export async function render(view) {
  const tools = makeTools();
  view.replaceChildren(h("div", { class: `page stretches${reducedMotion() ? " calm" : ""}` },
    h("header", { class: "page-head" }, h("div", {}, h("p", { class: "eyebrow" }, "Daily"), h("h1", {}, "Stretches"))), stretchPlayer(tools)));
  return () => { tools.stop(); tools.letSleep(); };
}
