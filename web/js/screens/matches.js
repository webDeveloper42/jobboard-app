// Matches: the toolbar, the job list and the open job side by side.
import { FILTER_LABELS } from "../core/constants.js";
import { Component } from "../core/component.js";
import { bem, h, icon } from "../core/dom.js";
import { ago } from "../core/format.js";
import { DailySummary } from "../components/daily-summary.js";
import { addJobDialog } from "../components/dialogs.js";
import { JobCard } from "../components/job-card.js";
import { ResumeSwitcher } from "../components/sidebar.js";
import { button, emptyState, field, spinner } from "../components/widgets.js";

export class MatchesScreen extends Component {
  constructor(app) {
    super(app);
    this.card = new JobCard(app);
    this.daily = new DailySummary(app);
    this.switcher = new ResumeSwitcher(app);
    this.searchTimer = null;
  }

  render() {
    if (!this.state) return emptyState({ title: "Loading your matches…", extra: spinner() });
    return [this.#header(), this.#toolbar(), this.store.ui.filtersOpen ? this.#filterPanel() : null, this.#activeFilters(),
      h("div", { class: "split-view" },
        h("div", { class: "split-view__list", role: "list", "aria-label": "Jobs" }, this.#list()),
        h("section", { class: bem("split-view", "detail", { empty: !this.store.job }), "aria-label": "Job details" },
          this.store.job ? this.app.jobDetail.render(this.store.job)
            : emptyState({ iconName: "star", title: "Pick a job", text: "Its full post, how well it matches, and your apply kit show up here.",
              extra: h("p", { class: "u-muted u-small" }, "Tip: press ", h("kbd", {}, "j"), " and ", h("kbd", {}, "k"), " to move through the list.") })))];
  }

  // ---- parts

  #title() {
    const f = this.store.filters;
    return f.view === "hidden" ? "Not interested" : this.store.isNewView ? "New today" : "Matches";
  }

  #header() {
    const s = this.state;
    const primary = this.store.primaryResume;
    const roles = primary && primary.roles.length && primary.roles.length < s.focus.length ? this.store.roleNames(primary.roles).toLowerCase() + " " : "";
    return h("header", { class: "page-header" },
      h("div", { class: "page-header__titles" }, h("h1", { class: "page-header__title" }, this.#title()),
        h("p", { class: "page-header__subtitle" }, `${s.total.toLocaleString()} ${roles}job${s.total === 1 ? "" : "s"}${primary ? ` for your ${primary.name} resume` : ""}`)),
      h("div", { class: "page-header__actions" },
        this.switcher.render({ compact: true }),
        s.last_refresh ? h("span", { class: "page-header__updated u-hide-phone", title: s.last_refresh.replace("T", " ").slice(0, 16) }, `Updated ${ago(s.last_refresh).toLowerCase()}`) : null,
        button(this.busy("refresh") ? [spinner(), h("span", { class: "u-hide-phone" }, "Fetching…")] : h("span", { class: "u-hide-phone" }, "Refresh"), () => this.app.refreshBoards(), {
          iconName: this.busy("refresh") ? null : "retry", disabled: this.busy("refresh"), title: "Fetch new jobs from every board that's switched on", ariaLabel: "Refresh" }),
        button(h("span", { class: "u-hide-phone" }, "Add job"), () => addJobDialog(this.app), { kind: "ghost", iconName: "plus", title: "Add a job you found somewhere else", ariaLabel: "Add a job" })));
  }

  #toolbar() {
    const f = this.store.filters;
    const models = new Set(f.work_model ? f.work_model.split(",") : []);
    const activeCount = this.store.activeFilterKeys(FILTER_LABELS).length;
    const search = h("label", { class: "search-field" }, icon("search", 15), h("span", { class: "u-sr-only" }, "Search jobs"),
      h("input", { class: "search-field__input", id: "search", type: "search", placeholder: "Search title, company, skill or place", value: f.q, autocomplete: "off",
        oninput: (e) => { f.q = e.target.value; clearTimeout(this.searchTimer); this.searchTimer = setTimeout(() => this.app.refreshAll(false), 250); } }),
      h("kbd", { class: "search-field__key u-hide-phone" }, "/"));
    const workType = h("div", { class: bem("segmented", null, { small: true }), role: "group", "aria-label": "Work type" },
      [["remote", "Remote"], ["hybrid", "Hybrid"], ["onsite", "On-site"]].map(([m, label]) =>
        h("button", { class: bem("segmented", "option", { active: models.has(m) }), type: "button", "aria-pressed": String(models.has(m)), onclick: () => this.app.toggleWorkModel(m) }, label)));
    const sort = h("label", { class: "toolbar__sort" }, h("span", { class: "u-sr-only" }, "Sort"),
      h("select", { onchange: (e) => this.app.setFilter("sort", e.target.value) }, [["score", "Best match"], ["recent", "Newest"], ["salary", "Highest pay"], ["company", "Company A–Z"]].map(([v, l]) =>
        h("option", { value: v, selected: (f.sort || "score") === v }, l))));
    const filters = h("button", { class: bem("button", null, { active: this.store.ui.filtersOpen || activeCount > 0 }), type: "button", "aria-expanded": String(this.store.ui.filtersOpen), "aria-controls": "filter-panel",
      onclick: () => { this.store.ui.filtersOpen = !this.store.ui.filtersOpen; this.app.render(); } },
    icon("filter", 15), "Filters", activeCount ? h("span", { class: "count-pill" }, String(activeCount)) : null);
    return h("div", { class: "toolbar" }, search, h("div", { class: "toolbar__row" }, this.#viewTabs(), workType, sort, filters));
  }

  #viewTabs() {
    const f = this.store.filters;
    const counts = this.state.counts;
    const current = f.view === "hidden" ? "hidden" : this.store.isNewView ? "new" : "all";
    const views = { all: { view: "recommended", days: "" }, new: { view: "recommended", days: "1" }, hidden: { view: "hidden", days: "" } };
    const pill = (id) => (id === "new" && counts.new ? h("span", { class: "count-pill" }, String(counts.new))
      : id === "hidden" && counts.hidden ? h("span", { class: bem("count-pill", null, { muted: true }) }, String(counts.hidden)) : null);
    return h("div", { class: "segmented", role: "tablist", "aria-label": "Which jobs" }, [["all", "All"], ["new", "New today"], ["hidden", "Not interested"]].map(([id, label]) =>
      h("button", { class: bem("segmented", "option", { active: current === id }), type: "button", role: "tab", "aria-selected": String(current === id), onclick: () => this.app.setFilters(views[id]) }, label, pill(id))));
  }

  #filterPanel() {
    const f = this.store.filters;
    const select = (key, label, options, hint = null) => field(label,
      h("select", { onchange: (e) => this.app.setFilter(key, e.target.value) }, options.map(([v, l]) => h("option", { value: v, selected: String(f[key] || "") === v }, l))), { hint });
    const checkbox = (key, label, title = null) => h("label", { class: "checkbox", title },
      h("input", { class: "checkbox__input", type: "checkbox", checked: Boolean(f[key]), onchange: (e) => this.app.setFilter(key, e.target.checked ? "1" : "") }), label);
    return h("div", { class: "filter-panel", id: "filter-panel" },
      select("min_score", "Match", [["", "Any match"], ["50", "50% or better"], ["65", "65% or better"], ["80", "80% or better"]]),
      !this.store.isNewView ? select("days", "Posted", [["", "Any time"], ["1", "Past 24 hours"], ["3", "Past 3 days"], ["7", "Past week"], ["30", "Past month"]]) : null,
      select("max_commute", "Commute by Metro/bus", [["", "Any commute"], ["30", "30 min or less"], ["45", "45 min or less"], ["60", "60 min or less"], ["75", "75 min or less"]], "Remote jobs and ones without an address stay."),
      h("div", { class: "filter-panel__checks" },
        checkbox("salary", "Shows pay"),
        checkbox("no_clearance", "No clearance needed", "Hide jobs that need a Secret / Top Secret clearance you'd already have to hold"),
        this.state.profile.needs_sponsorship ? checkbox("sponsor", "Visa friendly") : null));
  }

  #activeFilters() {
    const keys = this.store.activeFilterKeys(FILTER_LABELS);
    if (!keys.length) return null;
    const f = this.store.filters;
    return h("div", { class: "active-filters" },
      keys.map((key) => h("button", { class: bem("chip", null, { active: true }), type: "button", onclick: () => this.app.setFilter(key, ""), "aria-label": `Remove filter: ${FILTER_LABELS[key](f[key])}` },
        FILTER_LABELS[key](f[key]), icon("x", 12))),
      h("button", { class: "link-button", type: "button", onclick: () => this.app.setFilters(Object.fromEntries(Object.keys(FILTER_LABELS).map((k) => [k, ""]))) }, "Clear all"));
  }

  #list() {
    const s = this.state;
    const f = this.store.filters;
    if (!s.profile.ready) {
      return emptyState({ title: "Start with your resume", text: "Matches are scored against your skills, job titles and preferences.",
        action: button("Set up your profile", () => this.app.go("profile"), { kind: "primary" }) });
    }
    if (!s.jobs.length) {
      if (!s.last_refresh) return emptyState({ title: "No jobs yet", text: "Fetch jobs from your boards to see your matches.", action: button("Fetch jobs", () => this.app.refreshBoards(), { kind: "primary" }) });
      if (f.view === "hidden") return emptyState({ title: "Nothing hidden", text: "Jobs you mark Not interested land here." });
      const narrowed = this.store.activeFilterKeys(FILTER_LABELS).length || f.q || f.work_model;
      return emptyState({ title: "No jobs match", text: "Try a broader search or fewer filters.",
        action: narrowed ? button("Clear search and filters", () => this.app.clearSearch()) : button("Add job boards", () => this.app.go("boards")) });
    }
    const byRule = s.counts.by_rule ? h("p", { class: "u-muted u-small u-center" }, `${s.counts.by_rule} more hidden by your hide rules. `,
      h("button", { class: "link-button", type: "button", onclick: () => this.app.go("profile") }, "See rules")) : null;
    return [this.daily.render(), s.jobs.map((job) => this.card.render(job)), byRule,
      s.total > s.jobs.length ? h("p", { class: "u-muted u-small u-center" }, `Showing the top ${s.jobs.length} of ${s.total}. Search or filter to narrow it down.`) : null];
  }
}
