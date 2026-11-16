// This morning's run: the new jobs worth a look, best first. Shown on the day it ran, until you close it.
import { Component } from "../core/component.js";
import { h, icon } from "../core/dom.js";
import { plural } from "../core/format.js";

export class DailySummary extends Component {
  render() {
    const d = this.state.daily || {};
    const today = new Date().toLocaleDateString("en-CA");
    if (!d.day || d.day !== today || this.store.dailyClosedOn === today || this.store.filters.view === "hidden") return null;
    const jobs = d.jobs || [];
    const close = () => { this.store.dailyClosedOn = today; this.app.render(); };
    const notes = [`Checked ${d.boards} boards at ${String(d.at || "").slice(11, 16)}${d.emailed ? " and emailed you the list." : "."}`];
    if (d.full_posts && d.full_posts.read) notes.push(`Read ${plural(d.full_posts.read, "full post")}.`);
    if ((d.errors || []).length) notes.push(`${plural(d.errors.length, "board")} had a problem (see Job boards).`);
    return h("div", { class: "daily-summary", role: "note" },
      h("div", { class: "daily-summary__header" }, icon("today", 15),
        h("b", { class: "daily-summary__title" }, jobs.length ? `This morning: ${plural(jobs.length, "new match", "new matches")} at 65%+` : "This morning's check found nothing new at 65%+"),
        h("button", { class: "icon-button", type: "button", "aria-label": "Close this morning's summary", onclick: close }, icon("x", 14))),
      jobs.slice(0, 5).map((j) => h("button", { class: "daily-summary__job", type: "button", onclick: () => this.app.pick(j.id) },
        h("span", { class: "daily-summary__score" }, `${j.score}%`), h("span", { class: "u-ellipsis" }, `${j.title} · ${j.company}`))),
      h("div", { class: "daily-summary__footer" }, notes.join(" ")));
  }
}
