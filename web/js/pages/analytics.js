import { h } from "../lib/dom.js";
export async function render(view) { view.replaceChildren(h("div", { class: "page" }, h("h1", {}, "Analytics"), h("p", { class: "muted" }, "Coming up next."))); }
