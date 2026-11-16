// Applications: your tracked jobs by stage (drag a card to move it), with the open job in a drawer.
import { STATUSES, STATUS_NAME } from "../core/constants.js";
import { Component } from "../core/component.js";
import { bem, h, icon } from "../core/dom.js";
import { dayLabel } from "../core/format.js";
import { addJobDialog } from "../components/dialogs.js";
import { button, emptyState, spinner } from "../components/widgets.js";

export class ApplicationsScreen extends Component {
  constructor(app) {
    super(app);
    this.dragging = null;
  }

  render() {
    if (!this.state) return emptyState({ title: "Loading…", extra: spinner() });
    const s = this.state;
    const ins = s.insights;
    const empty = !STATUSES.some((st) => (s.board[st] || []).length);
    return [
      h("header", { class: "page-header" },
        h("div", { class: "page-header__titles" }, h("h1", { class: "page-header__title" }, "Applications"),
          h("p", { class: "page-header__subtitle" }, "Drag a card to move it to another stage. Changes go to your job sheets too.")),
        h("div", { class: "page-header__actions" },
          h("a", { class: "button button--ghost", href: this.api.exportUrl(), download: "applications.csv" }, icon("download", 15), h("span", { class: "u-hide-phone" }, "Export CSV")),
          button(h("span", { class: "u-hide-phone" }, "Add job"), () => addJobDialog(this.app), { kind: "ghost", iconName: "plus", ariaLabel: "Add a job" }))),
      h("div", { class: "split-view" },
        h("div", { class: "tracker" },
          h("div", { class: "stat-row" },
            this.#stat(ins.applied, "applied"), this.#stat(ins.this_week, "this week"), this.#stat(ins.responses, "interviews or offers"),
            this.#stat(ins.response_rate == null ? "–" : `${ins.response_rate}%`, "heard back")),
          empty ? emptyState({ title: "Nothing tracked yet", text: "Save a job from Matches, or press I applied on one.", action: button("See your matches", () => this.app.go("jobs"), { kind: "primary" }) })
            : h("div", { class: "kanban" }, STATUSES.map((st) => this.#column(st, s.board[st] || [])))),
        this.store.job ? h("aside", { class: "drawer", "aria-label": "Job details" },
          h("div", { class: "drawer__close" }, button("Close", () => this.app.closeJob(), { kind: "ghost small", iconName: "x" })), this.app.jobDetail.render(this.store.job)) : null)];
  }

  #stat(value, label) {
    return h("div", { class: "stat" }, h("b", { class: "stat__value" }, String(value)), h("span", { class: "stat__label" }, label));
  }

  #column(status, items) {
    const drop = (e) => {
      e.preventDefault();
      e.currentTarget.classList.remove("kanban__column--drop");
      if (this.dragging && this.dragging.status !== status) this.app.run("status", () => this.api.act("status", { id: this.dragging.job_id, status }), this.app.withSheet(`Moved to ${STATUS_NAME[status]}`));
      this.dragging = null;
    };
    return h("div", { class: "kanban__column", ondragover: (e) => { e.preventDefault(); e.currentTarget.classList.add("kanban__column--drop"); },
      ondragleave: (e) => e.currentTarget.classList.remove("kanban__column--drop"), ondrop: drop },
    h("header", { class: "kanban__header" }, h("span", { class: bem("kanban", "dot", { [status]: true }) }), STATUS_NAME[status], h("span", { class: "kanban__count" }, String(items.length))),
    h("div", { class: "kanban__items" }, items.length ? items.map((it) => this.#card(it)) : h("div", { class: "kanban__empty" }, "Drag a card here")));
  }

  #card(it) {
    return h("button", { class: bem("tracker-card", null, { active: this.store.selectedId === it.job_id }), type: "button", draggable: "true",
      ondragstart: () => { this.dragging = it; }, onclick: () => this.app.pick(it.job_id) },
    h("div", { class: "tracker-card__head" }, h("div", { class: "tracker-card__title" }, it.title), it.score != null ? h("span", { class: "u-muted u-small" }, `${it.score}%`) : null),
    h("div", { class: "tracker-card__company" }, it.company),
    it.next_step || it.next_date ? h("div", { class: "tracker-card__next" }, [it.next_date ? dayLabel(it.next_date) : "", it.next_step].filter(Boolean).join(" · ")) : null);
  }
}
