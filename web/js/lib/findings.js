import { h } from "./dom.js";

export const FINDING_KINDS = {
  good: { label: "Going well", mark: "+" },
  improve: { label: "Fix next", mark: "!" },
  works: { label: "Works for you", mark: "✓" },
  doesnt: { label: "Doesn't work", mark: "×" },
};

const CONF_BARS = { high: 3, medium: 2, low: 1 };

export function confidenceMeter(conf, n) {
  const filled = CONF_BARS[conf] || 1;
  return h("span", { class: "conf", title: `${conf} confidence, ${n} runs` },
    h("span", { class: "conf-bars", "aria-hidden": "true" }, [1, 2, 3].map((i) => h("i", { class: i <= filled ? "on" : "" }))),
    h("span", { class: "conf-text" }, `${conf} confidence · ${n} runs`));
}

/** One finding as a block of text with a kind marker, headline, plain-language body, and confidence. */
export function findingBlock(f, { compact = false, runLinks = true } = {}) {
  const kind = FINDING_KINDS[f.kind] || FINDING_KINDS.good;
  const block = h("article", { class: `finding k-${f.kind}${compact ? " compact" : ""}` },
    h("div", { class: "finding-top" }, h("span", { class: "k-mark", "aria-hidden": "true" }, kind.mark), h("span", { class: "k-label" }, kind.label),
      f.stat ? h("span", { class: "k-stat mono" }, f.stat.value) : null),
    h("h3", {}, f.title), h("p", { class: "finding-body" }, f.body), confidenceMeter(f.confidence, f.n));
  if (runLinks && !compact && f.runs && f.runs.length) {
    block.append(h("p", { class: "finding-runs" }, h("span", { class: "label" }, "Runs behind this"),
      f.runs.slice(0, 6).map((id) => h("a", { href: `#/runs/${id}`, class: "run-pill mono" }, `#${String(id).slice(-4)}`))));
  }
  return block;
}
