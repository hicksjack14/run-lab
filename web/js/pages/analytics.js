// Analytics has three views: Story (the animated scroll), Explore (filterable timeline of every run), Places (where you run).
import { h } from "../lib/dom.js";
import * as story from "./analytics-story.js";
import * as explore from "./analytics-explore.js";
import * as places from "./analytics-places.js";

const TABS = [["story", "Story", "The season as an animated scroll"], ["explore", "Explore", "Every run, by effort and heart-rate zone"], ["places", "Places", "Where your runs take you"]];
const VIEWS = { story, explore, places };

export async function render(view, [tab = "story"], ctx) {
  const body = h("div", { class: "an-body" });
  const tabs = h("nav", { class: "an-tabs", "aria-label": "Analytics views" },
    TABS.map(([key, label, hint]) => h("a", { href: key === "story" ? "#/analytics" : `#/analytics/${key}`, title: hint, "aria-current": key === tab ? "page" : null }, label)));
  view.replaceChildren(h("div", { class: `an-root an-${tab}` }, tabs, body));
  return VIEWS[tab].render(body, ctx);
}
