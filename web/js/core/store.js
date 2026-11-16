// Everything the page knows, in one place. Screens read from the store; only App changes it.
import { DEFAULT_FILTERS } from "./constants.js";

const KEYS = { screen: "jobs-screen", filters: "jobs-filters", dailyClosed: "jobs-daily-closed" };
const SCREENS = ["jobs", "tracker", "profile", "boards", "coach"];

/** Browser storage that never throws (private windows and blocked storage just forget). */
const saved = {
  get(key, fallback = null) { try { return localStorage.getItem(key) ?? fallback; } catch (e) { return fallback; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* fine */ } },
};

export class Store {
  constructor() {
    this.state = null;          // the server's state: jobs, counts, profile, resumes, sources…
    this.job = null;            // the open job, in full
    this.selectedId = null;     // its id
    this.screen = "jobs";
    this.filters = { ...DEFAULT_FILTERS };
    this.busy = {};             // action name -> true while it runs (buttons show a spinner and disable)
    this.ui = { tab: "overview", filtersOpen: false, showFull: false, editing: new Set() };
    this.chat = [];             // the coach's chat about your whole search
    this.serp = null;           // SerpApi usage, once checked
    this.#restore();
  }

  #restore() {
    const screen = saved.get(KEYS.screen, "jobs");
    this.screen = SCREENS.includes(screen) ? screen : "jobs";
    try { Object.assign(this.filters, JSON.parse(saved.get(KEYS.filters, "{}")), { q: "" }); } catch (e) { /* defaults */ }
  }

  remember() {
    saved.set(KEYS.screen, this.screen);
    saved.set(KEYS.filters, JSON.stringify({ ...this.filters, q: "" }));
  }

  get dailyClosedOn() { return saved.get(KEYS.dailyClosed, ""); }
  set dailyClosedOn(day) { saved.set(KEYS.dailyClosed, day); }

  // ---- handy reads

  get primaryResume() { return (this.state?.resumes || []).find((r) => r.primary) || null; }

  /** "IT technician, IT internship" for a list of role ids; "every role" when none. */
  roleNames(ids) {
    if (!ids || !ids.length) return "every role";
    return this.state.focus.filter((c) => ids.includes(c.id)).map((c) => c.name).join(", ");
  }

  levelName(id) { return (this.state?.levels.find((l) => l.id === id) || {}).name || id; }

  /** True when the "New today" view is on (it's the days=1 filter). */
  get isNewView() { return this.filters.days === "1"; }

  /** Filters from the Filters panel that are switched on (shown as chips). */
  activeFilterKeys(labels) {
    return Object.keys(labels).filter((key) => this.filters[key] !== "" && this.filters[key] != null && !(key === "days" && this.isNewView && this.filters.view === "recommended"));
  }

  /** The id `step` places away from the open job in the list (the first job when none is open). */
  neighbourId(step) {
    const ids = (this.state?.jobs || []).map((j) => j.id);
    if (!ids.length) return null;
    const i = ids.indexOf(this.selectedId);
    return i < 0 ? ids[0] : ids[Math.max(0, Math.min(ids.length - 1, i + step))];
  }
}
