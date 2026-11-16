// One job in the Matches list.
import { STATUS_NAME } from "../core/constants.js";
import { Component } from "../core/component.js";
import { bem, h } from "../core/dom.js";
import { ago, pay, place } from "../core/format.js";
import { matchRing, tag, warningTags } from "./widgets.js";

const DAY_MS = 864e5;

export class JobCard extends Component {
  render(job) {
    const active = this.store.selectedId === job.id;
    const isNew = job.first_seen && Date.now() - new Date(job.first_seen) < DAY_MS;
    const trip = job.travel && job.travel.transit ? `~${job.travel.transit} min by Metro/bus` : "";
    const primary = this.store.primaryResume;
    const showRole = job.role && !(primary && primary.roles.length === 1);   // with one role, every card would say the same
    return h("button", { class: bem("job-card", null, { active }), type: "button", role: "listitem", "data-id": job.id, "aria-current": active ? "true" : null, onclick: () => this.app.pick(job.id) },
      h("div", { class: "job-card__body" },
        h("div", { class: "job-card__title" }, job.title),
        h("div", { class: "job-card__company" }, [job.company, place(job)].filter(Boolean).join(" · ")),
        h("div", { class: "facts" },
          pay(job) ? h("span", { class: bem("facts", "item", { pay: true }) }, pay(job)) : null,
          trip ? h("span", { class: "facts__item", title: `About ${job.travel.drive} min driving. Estimated from the distance.` }, trip) : null,
          h("span", { class: "facts__item" }, ago(job.posted || job.first_seen))),
        h("div", { class: "job-card__tags" },
          job.status ? tag(STATUS_NAME[job.status], "status") : null,
          isNew ? tag("New", "new") : null,
          job.applied_company ? tag("Applied here before", "warning", `You have an application at ${job.company} already`) : null,
          showRole ? tag(job.role, "role") : null,
          warningTags(job),
          job.sponsorship === "no" && this.state.profile.needs_sponsorship ? tag("No sponsorship", "danger") : null)),
      matchRing(job.score, false, job.label));
  }
}
