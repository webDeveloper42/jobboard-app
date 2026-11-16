// The open job: a pinned header (facts and main actions) and tabs. Each tab's content is a panel class in
// job-panels.js; add a tab by adding a panel there and a line to TABS below.
import { HOME_FALLBACK, STATUSES, STATUS_NAME } from "../core/constants.js";
import { Component } from "../core/component.js";
import { bem, h, icon } from "../core/dom.js";
import { ago, pay, place } from "../core/format.js";
import { ApplyKitPanel, AskPanel, MatchPanel, OverviewPanel, TrackingPanel } from "./job-panels.js";
import { button, matchRing, tag, warningTags } from "./widgets.js";

export class JobDetail extends Component {
  constructor(app) {
    super(app);
    this.panels = { overview: new OverviewPanel(app), match: new MatchPanel(app), kit: new ApplyKitPanel(app), ask: new AskPanel(app), track: new TrackingPanel(app) };
  }

  /** The tabs this job has: [id, label]. Tracking only appears once you've saved or applied. */
  tabs(job) {
    const tabs = [["overview", "Overview"], ["match", `Match ${job.score ?? 0}%`], ["kit", `Apply kit${job.documents.length ? ` (${job.documents.length})` : ""}`], ["ask", "Ask Coach"]];
    if (job.application) tabs.push(["track", "Tracking"]);
    return tabs;
  }

  render(job) {
    const ui = this.store.ui;
    const tabs = this.tabs(job);
    if (!tabs.some(([id]) => id === ui.tab)) ui.tab = "overview";
    return h("article", { class: "job-detail" },
      h("div", { class: "job-detail__header" },
        button("All jobs", () => this.app.closeJob(), { kind: "ghost small", iconName: "left", attrs: { class: "button button--ghost button--small job-detail__back" } }),
        h("div", { class: "job-detail__headline" },
          h("div", { class: "job-detail__main" },
            h("h2", { class: "job-detail__title" }, job.title),
            h("div", { class: "job-detail__company" }, [job.company, place(job)].filter(Boolean).join(" · ")),
            this.#facts(job),
            h("div", { class: "job-detail__tags" }, warningTags(job), !job.active ? tag("No longer listed", "danger") : null,
              job.sponsorship !== "unknown" && this.state.profile.needs_sponsorship ? tag(job.sponsorship === "no" ? "No visa sponsorship" : "Sponsors visas", job.sponsorship === "no" ? "danger" : "pay") : null)),
          h("button", { class: "job-detail__score", type: "button", title: "See why it matches", onclick: () => { ui.tab = "match"; this.app.render(); } },
            matchRing(job.score, true, (job.score_detail || {}).label))),
        this.#actions(job),
        h("div", { class: "tabs", role: "tablist", "aria-label": "About this job" }, tabs.map(([id, label]) =>
          h("button", { class: bem("tabs", "tab", { active: ui.tab === id }), type: "button", role: "tab", id: `tab-${id}`, "aria-selected": String(ui.tab === id), "aria-controls": "job-tab-panel",
            onclick: () => { ui.tab = id; this.app.render(); } }, label)))),
      h("div", { class: "job-detail__panel", id: "job-tab-panel", role: "tabpanel", "aria-labelledby": `tab-${ui.tab}` }, this.panels[ui.tab].render(job)));
  }

  #facts(job) {
    const trip = job.travel && job.travel.transit ? `~${job.travel.transit} min by Metro/bus from home` : "";
    const items = [
      pay(job) ? h("span", { class: bem("facts", "item", { pay: true }) }, pay(job)) : null,
      trip ? h("span", { class: "facts__item", title: `About ${job.travel.drive} min driving. Estimated from the distance (${job.travel.km} km), not live directions.` }, trip) : null,
      job.level_name ? h("span", { class: "facts__item" }, job.level_name) : null,
      job.employment_type ? h("span", { class: "facts__item" }, job.employment_type) : null,
      job.years_min ? h("span", { class: "facts__item" }, `${job.years_min}+ years`) : null,
      h("span", { class: "facts__item" }, `Posted ${ago(job.posted || job.first_seen).toLowerCase()}`),
      h("span", { class: "facts__item" }, `via ${job.source.name}`)];
    return h("div", { class: bem("facts", null, { large: true }) }, items);
  }

  #actions(job) {
    const app = this.app;
    const ap = job.application;
    const link = job.apply_url || job.url;
    const status = h("label", { class: "job-detail__status" }, h("span", { class: "u-sr-only" }, "Application status"),
      h("select", { onchange: (e) => app.setStatus(job, e.target.value, STATUS_NAME[e.target.value]) },
        STATUSES.map((s) => h("option", { value: s, selected: ap && ap.status === s }, STATUS_NAME[s]))));
    return h("div", { class: "job-detail__actions" },
      link ? h("a", { class: "button button--primary", href: link, target: "_blank", rel: "noopener noreferrer", onclick: () => setTimeout(() => app.askApplied(job), 400) }, "Apply", icon("share", 14)) : null,
      !ap || ap.status === "saved" ? button("I applied", () => app.markApplied(job), { iconName: "check", disabled: this.busy("status") }) : status,
      !ap ? button("Save", () => app.saveJob(job), { iconName: "flag", disabled: this.busy("status") }) : null,
      button(job.hidden ? "Show again" : "Not interested", () => app.toggleHidden(job), { kind: "ghost", disabled: this.busy("hide") }),
      this.#moreMenu(job, link));
  }

  /** Less-used actions, tucked into a "More" menu (a <details>, so it works without extra code and with the keyboard). */
  #moreMenu(job, link) {
    const app = this.app;
    const item = (label, attrs) => h(attrs.href ? "a" : "button", { class: bem("menu", "item", { danger: Boolean(attrs.danger) }), role: "menuitem", type: attrs.href ? null : "button", ...attrs, danger: null }, label);
    const maps = mapsUrl(job, this.state.profile);
    return h("details", { class: "menu" },
      h("summary", { class: "button button--ghost menu__toggle", "aria-label": "More actions" }, icon("dots", 16), h("span", { class: "u-hide-phone" }, "More")),
      h("div", { class: "menu__popup", role: "menu", onclick: (e) => { const d = e.target.closest("details"); if (d) d.open = false; } },
        item("Notes for this job", { onclick: () => app.openJobNote(job), title: "A note in Notes: interviewer, questions they asked, questions to ask, pay discussed" }),
        maps ? item("Commute in Google Maps ↗", { href: maps, target: "_blank", rel: "noopener noreferrer" }) : null,
        link ? item("Original post ↗", { href: job.url || link, target: "_blank", rel: "noopener noreferrer" }) : null,
        link ? item("Copy the job link", { onclick: () => app.copyText(link, "Link copied") }) : null,
        job.company ? item(`Never show jobs from ${job.company}`, { onclick: () => app.addHideRule("company", job.company) }) : null,
        job.application ? item("Remove from Applications", { danger: true, onclick: () => app.run("status", () => app.api.act("untrack", { id: job.id }), "Removed from Applications") }) : null));
  }
}

/** Google Maps directions from home to the job, by transit. Only for jobs you'd travel to. */
export function mapsUrl(job, profile, fallback = HOME_FALLBACK) {
  if (job.work_model === "remote" || !job.location) return null;
  const parts = job.location.split(/\s+·\s+/).filter((p) => p && !/\bremote\b/i.test(p));
  if (!parts.length) return null;
  const best = parts.find((p) => /^\d+\s/.test(p)) || parts.find((p) => /washington|\bdc\b|suitland/i.test(p)) || parts[0];
  const isAddress = /^\d+\s/.test(best);
  // A street address finds the building; a city alone needs the company name to find the place.
  const dest = (isAddress ? best.replace(/,?\s*(ste|suite|unit|#)\.?\s*[\w-]+(?=,|\s|$)/i, ",") : `${job.company}, ${best}`).replace(/,\s*,/g, ",").replace(/,(?=\S)/g, ", ");
  const origin = (profile.home_address || "").trim() || (profile.location || "").trim() || fallback;
  return `https://www.google.com/maps/dir/?api=1&travelmode=transit&origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(dest)}`;
}
