// The sidebar (desktop) and the bottom tab bar (phones): the screens, and the resume you're searching as.
import { SCREENS, STATUSES } from "../core/constants.js";
import { Component } from "../core/component.js";
import { bem, h, icon } from "../core/dom.js";
import { cap, dayLabel } from "../core/format.js";

export class ResumeSwitcher extends Component {
  /** A select of your resumes (or the only one's name). `compact` is the phone version in the page header. */
  render({ compact = false } = {}) {
    const list = this.state.resumes || [];
    const primary = this.store.primaryResume;
    if (!primary) return null;
    const select = h("select", { class: "resume-switcher__select", id: compact ? "resume-switcher-compact" : "resume-switcher", disabled: this.busy("resume"),
      onchange: (e) => this.app.useResume(Number(e.target.value)) }, list.map((r) => h("option", { value: r.id, selected: r.primary }, r.name)));
    if (compact) return list.length > 1 ? h("label", { class: bem("resume-switcher", null, { compact: true }, "u-phone-only") }, h("span", { class: "u-sr-only" }, "Searching as"), select) : null;
    return h("div", { class: "resume-switcher" },
      h("label", { class: "resume-switcher__label", for: "resume-switcher" }, "Searching as"),
      list.length > 1 ? select : h("button", { class: "resume-switcher__single", type: "button", onclick: () => this.app.go("profile"), title: "Add another resume under Profile" }, `${primary.name} resume`),
      h("div", { class: "resume-switcher__roles" }, cap(this.store.roleNames(primary.roles))));
  }
}

export class Sidebar extends Component {
  constructor(app) {
    super(app);
    this.switcher = new ResumeSwitcher(app);
  }

  render() {
    if (!this.state) return h("aside", { class: "app__sidebar sidebar" });
    const s = this.state;
    const tracked = STATUSES.reduce((n, st) => n + (s.board[st] || []).length, 0);
    const counts = { jobs: s.counts.active, tracker: tracked, boards: s.sources.filter((b) => b.enabled).length };
    const ins = s.insights;
    return h("aside", { class: "app__sidebar sidebar", "aria-label": "Jobs" },
      h("div", { class: "sidebar__brand" }, h("div", { class: "sidebar__logo" }, icon("rocket", 15)), "Jobs"),
      this.switcher.render(),
      h("nav", { class: "sidebar__nav" }, SCREENS.map(([id, label, iconName]) => this.#navItem(id, label, iconName, counts[id]))),
      h("div", { class: "sidebar__footer" },
        h("div", { class: "sidebar__week" }, h("b", {}, String(ins.this_week)), " applied this week",
          ins.response_rate != null ? [" · ", h("b", {}, `${ins.response_rate}%`), " heard back"] : null),
        ins.due.length ? [h("div", { class: "sidebar__section-title" }, "Next steps"), ins.due.slice(0, 4).map((d) =>
          h("button", { class: "sidebar__due", type: "button", onclick: () => { this.store.screen = "tracker"; this.app.pick(d.job_id); } },
            h("b", {}, dayLabel(d.next_date)), `${d.next_step || "Next step"} · ${d.company}`))] : null,
        h("button", { class: "sidebar__shortcuts", type: "button", onclick: () => this.app.keyboard.showHelp() }, "Keyboard shortcuts ", h("kbd", {}, "?"))));
  }

  #navItem(id, label, iconName, count) {
    const active = this.store.screen === id;
    return h("button", { class: bem("nav-item", null, { active }), type: "button", "aria-current": active ? "page" : null, onclick: () => this.app.go(id) },
      icon(iconName), h("span", { class: "nav-item__label" }, label), count != null ? h("span", { class: "nav-item__count" }, String(count)) : null);
  }
}

export class BottomNav extends Component {
  render() {
    return h("nav", { class: "bottom-nav", "aria-label": "Screens" }, SCREENS.map(([id, label, iconName]) => {
      const active = this.store.screen === id;
      return h("button", { class: bem("bottom-nav", "item", { active }), type: "button", "aria-current": active ? "page" : null, onclick: () => this.app.go(id) },
        icon(iconName, 18), h("span", {}, label.replace("Job boards", "Boards")));
    }));
  }
}
