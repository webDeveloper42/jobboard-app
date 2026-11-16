// App: owns the store, the API client and the screens, and is the only thing that changes the store.
// Flow: something happens (click, key) -> an App method -> the store changes -> render() redraws the page.
import { ApiClient } from "./api.js";
import { DEFAULT_FILTERS } from "./constants.js";
import { Dialog } from "./dialog.js";
import { h } from "./dom.js";
import { Store } from "./store.js";
import { Toast } from "./toast.js";
import { KeyboardShortcuts } from "./keyboard.js";
import { BottomNav, Sidebar } from "../components/sidebar.js";
import { JobDetail } from "../components/job-detail.js";
import { ApplicationsScreen } from "../screens/applications.js";
import { BoardsScreen } from "../screens/boards.js";
import { MatchesScreen } from "../screens/matches.js";
import { CoachScreen } from "../screens/coach.js";
import { ProfileScreen } from "../screens/profile.js";

// Elements whose scroll position survives a redraw.
const SCROLLERS = [".split-view__list", ".split-view__detail", ".drawer", ".page", ".coach"];

export class App {
  constructor({ root, toastEl, dialogEl }) {
    this.root = root;
    this.store = new Store();
    this.api = new ApiClient();
    this.toast = new Toast(toastEl);
    this.dialog = new Dialog(dialogEl, (message) => { if (message) this.toast.show(message); return this.refreshAll(); }, (e) => this.toast.error(e));
    this.sidebar = new Sidebar(this);
    this.bottomNav = new BottomNav(this);
    this.jobDetail = new JobDetail(this);
    this.screens = { jobs: new MatchesScreen(this), tracker: new ApplicationsScreen(this), profile: new ProfileScreen(this), boards: new BoardsScreen(this), coach: new CoachScreen(this) };
    this.keyboard = new KeyboardShortcuts(this);
  }

  async start() {
    this.keyboard.listen();
    window.addEventListener("hashchange", () => this.openFromHash());
    await this.refreshAll();
    if (this.store.screen === "coach") await this.loadChat();
    await this.openFromHash();
  }

  // ---- drawing

  render() {
    const keep = SCROLLERS.map((sel) => [sel, document.querySelector(sel)?.scrollTop]);
    const focused = document.activeElement?.id;
    const caret = focused ? document.activeElement.selectionStart : null;
    const screen = this.screens[this.store.screen];
    this.root.replaceChildren(this.sidebar.render(), h("main", { class: "app__main", id: "main" }, screen.render()), this.bottomNav.render());
    for (const [sel, top] of keep) { const el = document.querySelector(sel); if (el && top != null) el.scrollTop = top; }
    if (focused) {
      const el = document.getElementById(focused);
      if (el) { el.focus(); try { if (caret != null) el.setSelectionRange(caret, caret); } catch (e) { /* not a text box */ } }
    }
  }

  // ---- loading

  async refreshAll(keepJob = true) {
    try {
      this.store.state = await this.api.state(this.store.filters);
      if (keepJob && this.store.selectedId) {
        try { this.store.job = await this.api.job(this.store.selectedId); } catch (e) { this.store.selectedId = null; this.store.job = null; }
      }
      this.render();
    } catch (e) { this.toast.error(e); }
  }

  async loadChat() {
    try { this.store.chat = await this.api.chat(); this.render(); } catch (e) { this.toast.error(e); }
  }

  /** Open a job. `keepTab` keeps the detail on the same tab (used when moving with j/k). */
  async pick(id, keepTab = false) {
    try {
      if (!keepTab) this.store.ui.tab = "overview";
      this.store.selectedId = id;
      this.store.job = await this.api.job(id);
      this.store.ui.showFull = false;
      this.render();
      const detail = document.querySelector(".split-view__detail, .drawer");
      if (detail) detail.scrollTop = 0;
      document.querySelector(`.job-card[data-id="${id}"]`)?.scrollIntoView({ block: "nearest" });
    } catch (e) { this.toast.error(e); }
  }

  closeJob() {
    this.store.selectedId = null;
    this.store.job = null;
    this.render();
  }

  /** #job/12 in the address opens that job (from its note in Notes, or a bookmark). */
  async openFromHash() {
    const m = /^#job\/(\d+)$/.exec(location.hash);
    if (!m) return;
    this.store.screen = "jobs";
    await this.pick(Number(m[1]));
  }

  go(screen) {
    this.store.screen = screen;
    this.store.remember();
    if (screen !== "jobs" && screen !== "tracker") { this.store.selectedId = null; this.store.job = null; }
    this.render();
    if (screen === "coach") this.loadChat();
  }

  // ---- actions

  /**
   * Run an action that changes something: marks `key` busy (its button shows progress), runs `fn`, shows `done`
   * (a string, or a function of the result) as a toast, shows any error, then reloads. Returns fn's result.
   */
  async run(key, fn, done) {
    if (this.store.busy[key]) return undefined;
    this.store.busy[key] = true;
    this.render();
    try {
      const out = await fn();
      if (done) this.toast.show(typeof done === "function" ? done(out) : done);
      return out;
    } catch (e) {
      this.toast.error(e);
      return undefined;
    } finally {
      this.store.busy[key] = false;
      await this.refreshAll();
    }
  }

  /** "Marked applied. Added to your IT sheet (row 4)" — the status message plus what happened in your job sheet. */
  withSheet(message) {
    return (out) => [message, out && (out.sheet || out.sheet_error)].filter(Boolean).join(". ");
  }

  setFilter(key, value) { this.setFilters({ [key]: value }); }

  setFilters(changes) {
    Object.assign(this.store.filters, changes);
    this.store.remember();
    this.refreshAll(false);
  }

  clearSearch() { this.setFilters({ ...DEFAULT_FILTERS, sort: this.store.filters.sort }); }

  toggleWorkModel(model) {
    const set = new Set(this.store.filters.work_model ? this.store.filters.work_model.split(",") : []);
    if (set.has(model)) set.delete(model); else set.add(model);
    this.setFilter("work_model", [...set].join(","));
  }

  refreshBoards() {
    return this.run("refresh", () => this.api.act("refresh"), (out) => {
      const bad = out.report.filter((r) => r.error);
      const scams = out.report.reduce((n, r) => n + (r.scams || 0), 0);
      return `${out.new} new job${out.new === 1 ? "" : "s"}` + (scams ? `, ${scams} scam post${scams === 1 ? "" : "s"} blocked` : "")
        + (bad.length ? `. ${bad.map((b) => `${b.source}: ${b.error}`).join("; ")}` : "");
    });
  }

  saveJob(job) { return this.run("status", () => this.api.act("save", { id: job.id }), "Saved to Applications"); }

  markApplied(job) { return this.run("status", () => this.api.act("status", { id: job.id, status: "applied" }), this.withSheet("Marked applied")); }

  setStatus(job, status, label) { return this.run("status", () => this.api.act("status", { id: job.id, status }), this.withSheet(`Moved to ${label}`)); }

  /** Not interested (or bring it back). Hiding moves on to the next job in the list. */
  async toggleHidden(job) {
    const next = this.store.neighbourId(1) === job.id ? this.store.neighbourId(-1) : this.store.neighbourId(1);
    await this.run("hide", () => this.api.act(job.hidden ? "unhide" : "hide", { id: job.id }), job.hidden ? "Back in your matches" : "Hidden. Find it under Not interested");
    if (!job.hidden && this.store.screen === "jobs" && next && next !== job.id && this.store.state.jobs.some((j) => j.id === next)) this.pick(next);
  }

  /** A hide rule: never show jobs from a company ("company") or that mention a word or phrase ("word"). */
  addHideRule(kind, value) {
    if (kind === "company") { this.store.selectedId = null; this.store.job = null; }
    return this.run("rules", () => this.api.act("hide_rule_add", { kind, value }), kind === "company" ? `Hiding jobs from ${value}. Undo it under Profile → Hide rules.` : `Hiding jobs that mention “${value}”.`);
  }

  removeHideRule(kind, value) {
    return this.run("rules", () => this.api.act("hide_rule_remove", { kind, value }), "Rule removed");
  }

  /** Make another resume the one you search as. */
  useResume(id) {
    const resume = this.store.state.resumes.find((r) => r.id === id);
    if (!resume || resume.primary) return undefined;
    this.store.selectedId = null;
    this.store.job = null;
    return this.run("resume", () => this.api.act("resume_use", { id }), `Searching as your ${resume.name} resume: ${this.store.roleNames(resume.roles)}.`);
  }

  /** Open the apply page, then ask whether you applied. */
  openApply(job) {
    const link = job.apply_url || job.url;
    if (!link) return;
    window.open(link, "_blank", "noopener");
    setTimeout(() => this.askApplied(job), 400);
  }

  askApplied(job) {
    if (job.application && job.application.status !== "saved") return;
    this.dialog.open("Did you apply?", [h("p", { class: "u-muted" }, `Mark ${job.title} at ${job.company} as applied so it moves along in your tracker.`)],
      "Yes, I applied", () => this.api.act("status", { id: job.id, status: "applied" }).then(this.withSheet("Marked applied")), "Not yet");
  }

  /** The job's note in Notes (made with an outline the first time), opened in a new tab. */
  async openJobNote(job) {
    const win = window.open("about:blank", "_blank");
    try {
      const out = await this.api.act("job_note", { id: job.id });
      if (win) win.location.href = out.url; else window.open(out.url, "_blank");
      this.toast.show(out.new ? "Made a note for this job in Notes" : "Opened this job's note");
    } catch (e) { if (win) win.close(); this.toast.error(e); }
  }

  copyText(value, done) {
    const fallback = () => {
      const t = h("textarea", { class: "u-offscreen" });
      t.value = value;
      document.body.append(t);
      t.select();
      const ok = document.execCommand("copy");
      t.remove();
      return ok;
    };
    const say = (ok) => (ok ? this.toast.show(done) : this.toast.show("Copy didn't work here. Select the text instead.", true));
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(value).then(() => say(true), () => say(fallback()));
    else say(fallback());
  }

  /** Read the whole post for a job that only has a snippet, and show it in place. */
  async getFullPost(job) {
    if (this.store.busy.full) return;
    this.store.busy.full = true;
    this.render();
    try {
      const out = await this.api.act("full_post", { id: job.id });
      if (out.found) {
        this.store.job = await this.api.job(job.id);
        this.store.ui.showFull = true;
        this.toast.show(`Got the full description from ${out.via}`);
      } else this.toast.show(out.why, true);
    } catch (e) { this.toast.error(e); } finally { this.store.busy.full = false; this.render(); }
  }

  /** SerpApi searches used this month (checking is free). */
  async loadSerpUsage(fresh = false) {
    if (this.store.busy.serp) return;
    this.store.busy.serp = true;
    try { this.store.serp = await this.api.act("serpapi_usage", { fresh }); } catch (e) { this.store.serp = { error: e.message }; }
    finally { this.store.busy.serp = false; this.render(); }
  }
}
