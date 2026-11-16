// Job boards: the boards you pull from, your search-service keys (Google Jobs via SerpApi, Jooble), adding a
// company's own careers site, and the Sheets switch.
import { Component } from "../core/component.js";
import { bem, h } from "../core/dom.js";
import { ago } from "../core/format.js";
import { confirmDialog } from "../components/dialogs.js";
import { button, emptyState, meter, panel, spinner, tag } from "../components/widgets.js";

const added = (out) => { const r = (out.report || [])[0]; return r && r.error ? `Added, but ${r.error}` : `Added${r ? `: ${r.found} jobs` : ""}`; };

export class BoardsScreen extends Component {
  render() {
    if (!this.state) return emptyState({ title: "Loading…", extra: spinner() });
    const boards = this.state.sources.filter((s) => s.kind !== "manual");
    return [
      h("header", { class: "page-header" },
        h("div", { class: "page-header__titles" }, h("h1", { class: "page-header__title" }, "Job boards"),
          h("p", { class: "page-header__subtitle" }, `${boards.filter((s) => s.enabled).length} of ${boards.length} switched on. Every board keeps only your roles and places.`)),
        h("div", { class: "page-header__actions" },
          button(this.busy("refresh") ? [spinner(), "Fetching…"] : "Refresh all", () => this.app.refreshBoards(), { kind: "primary", iconName: this.busy("refresh") ? null : "retry", disabled: this.busy("refresh") }))),
      h("div", { class: "page" }, h("div", { class: "page__inner" },
        panel("Your boards", { children: boards.map((s) => this.#boardRow(s)) }),
        this.#keyBox(GOOGLE), this.#keyBox(JOOBLE), this.#addCompany(), this.#sheetsSwitch(),
        h("p", { class: "u-muted u-small" }, "Boards are read straight from their public APIs, with no account, and nothing about you is sent. Google Jobs searches go through SerpApi and Jooble searches through Jooble, each with your own key.")))];
  }

  #boardRow(s) {
    const app = this.app;
    return h("div", { class: "source-row" },
      switchButton(s.enabled, `Fetch from ${s.name}`, () => app.run(`src${s.id}`, () => this.api.act("source_toggle", { id: s.id, enabled: !s.enabled }))),
      h("div", { class: "source-row__main" }, h("b", { class: "source-row__name" }, s.name),
        h("small", { class: "source-row__meta" }, `${s.jobs} open jobs` + (s.last_fetch ? ` · checked ${ago(s.last_fetch).toLowerCase()}` : " · not fetched yet")),
        s.last_error ? h("small", { class: bem("source-row", "meta", { error: true }) }, s.last_error) : null),
      button(this.busy(`one${s.id}`) ? "…" : "Fetch", () => app.run(`one${s.id}`, () => this.api.act("refresh", { source: s.id }), (o) => o.report[0].error || `${o.report[0].found} jobs, ${o.report[0].new} new`), { kind: "ghost small", disabled: this.busy(`one${s.id}`) }),
      button("Remove", () => confirmDialog(app, `Remove ${s.name}?`, "Its jobs leave your matches. Jobs you're tracking stay.", "Remove", () => this.api.act("source_remove", { id: s.id }).then(() => "Removed")),
        { kind: "ghost danger small", ariaLabel: `Remove ${s.name}` }));
  }

  /** A search service that needs your own API key: its key, usage, and a box to add searches. */
  #keyBox(cfg) {
    const app = this.app;
    const saved = Boolean(this.state[cfg.flag]);
    const key = h("input", { class: "u-grow", type: "password", autocomplete: "off", "aria-label": `${cfg.name} key`, placeholder: saved ? "Key saved. Paste a new one to replace it" : cfg.placeholder });
    const search = h("input", { class: "u-grow", placeholder: cfg.example, "aria-label": `New ${cfg.name} search` });
    const saveKey = () => app.run(cfg.busy, () => this.api.act(cfg.action, { key: key.value.trim() }), (r) => (r[cfg.flag] ? `Key saved. Press Refresh all to search ${cfg.name}` : "Key removed"));
    const addSearch = () => app.run(`${cfg.busy}-add`, () => this.api.act("source_add", { kind: cfg.kind, slug: search.value }), added);
    return panel(cfg.name, {
      iconName: "search",
      note: saved ? tag("Key saved", "pay") : tag("Needs a key", "warning"),
      children: [
        saved && cfg.usage ? this.#serpUsage() : null,
        h("p", { class: "u-muted" }, saved ? cfg.savedText : cfg.needText()),
        h("div", { class: "button-row" }, key, button(this.busy(cfg.busy) ? "Saving…" : "Save key", saveKey, { kind: "primary", disabled: this.busy(cfg.busy) }),
          saved ? button("Remove key", () => { key.value = ""; saveKey(); }, { kind: "ghost danger", disabled: this.busy(cfg.busy) }) : null),
        h("div", { class: "button-row" }, search, button(this.busy(`${cfg.busy}-add`) ? "Adding…" : "Add search", addSearch, { disabled: this.busy(`${cfg.busy}-add`) }))] });
  }

  /** SerpApi searches used and left this month (from SerpApi's own account page; checking is free). */
  #serpUsage() {
    const u = this.store.serp;
    if (!u && !this.busy("serp")) setTimeout(() => this.app.loadSerpUsage(false), 0);
    const pct = u && u.per_month ? Math.min(100, Math.round((100 * (u.used || 0)) / u.per_month)) : null;
    const text = !u ? "checking…" : u.error ? u.error
      : `${u.used ?? "?"} used this month${u.per_month ? ` of ${u.per_month}` : ""}${u.left != null ? ` · ${u.left} left` : ""}${u.plan ? ` · ${u.plan}` : ""}`;
    return h("div", { class: "usage" },
      h("div", { class: "usage__header" }, h("b", {}, "SerpApi searches"), h("span", { class: "u-muted u-small" }, text), h("span", { class: "u-spacer" }),
        button("Check again", () => this.app.loadSerpUsage(true), { kind: "ghost small", disabled: this.busy("serp") })),
      pct != null ? meter(100 - pct, `${100 - pct}% of this month's searches left`) : null);
  }

  #addCompany() {
    const app = this.app;
    const s = this.state;
    const kind = h("select", { "aria-label": "Board type" }, Object.entries(s.kinds).filter(([id]) => id !== "google" && id !== "jooble").map(([id, about]) => h("option", { value: id }, about.split(" (")[0])));
    const slug = h("input", { class: "u-grow", placeholder: "Company board name (stripe) or its jobs page link", "aria-label": "Company board" });
    return panel("Add a company", {
      iconName: "plus",
      children: [
        h("p", { class: "u-muted" }, "Paste a company's jobs page link (Greenhouse, Lever, Ashby or Workday) and the type is worked out for you. For Workday you can add search terms after a |, like: … | help desk Washington OR IT intern."),
        h("div", { class: "button-row" }, kind, slug, button(this.busy("source") ? "Adding…" : "Add", () => app.run("source", () => this.api.act("source_add", { kind: kind.value, slug: slug.value }), added), { kind: "primary", disabled: this.busy("source") })),
        s.suggested.length ? [h("div", { class: "section-title" }, "Popular"), h("div", { class: "chip-list" }, s.suggested.map((g) =>
          h("button", { class: "chip", type: "button", disabled: this.busy("source"), title: `${g.kind} · ${g.slug}`,
            onclick: () => app.run("source", () => this.api.act("source_add", g), (o) => `${g.name}: ${(o.report || [{}])[0].found ?? 0} jobs`) }, `+ ${g.name}`)))] : null] });
  }

  #sheetsSwitch() {
    const on = this.state.sheets_sync;
    return panel("Job sheets", {
      iconName: "grid",
      children: h("div", { class: "source-row" },
        switchButton(on, "Write applications to the Sheets tab", () => this.app.run("sheets", () => this.api.act("sheets_sync", { on: !on }), (o) => (o.sheets_sync ? "Applications will be written to your sheets" : "Sheets syncing is off"))),
        h("div", { class: "source-row__main" }, h("b", { class: "source-row__name" }, "Write applications to the Sheets tab"),
          h("small", { class: "source-row__meta" }, "When you apply or a job changes stage, its row in your IT or Data Entry workbook is added or updated (Company, Position, Platform, Offer, Ask, Progress, Where, Type). Undo any change from that sheet's version history."))) });
  }
}

/** An on/off switch (role="switch", so screen readers announce it as one). */
function switchButton(on, label, onclick) {
  return h("button", { class: bem("switch", null, { on }), type: "button", role: "switch", "aria-checked": String(Boolean(on)), "aria-label": label, onclick });
}

// The two search services, described once.
const GOOGLE = {
  name: "Google Jobs", kind: "google", action: "google_key", flag: "google_key", busy: "google-key", usage: true,
  placeholder: "Paste your SerpApi key", example: "Keywords @ place, like: computer technician @ Washington, DC (or @ remote)",
  savedText: "Each Google search uses up to 2 SerpApi searches per refresh. Get the full description uses 1 when the employer's page can't be read, and the morning run uses up to 5 for the best new matches.",
  needText: () => ["Google doesn't let scripts search it directly, so searches go through SerpApi. Get a free key at ", h("a", { href: "https://serpapi.com/users/sign_up", target: "_blank", rel: "noopener" }, "serpapi.com"), " and paste it here. It stays on this server."],
};
const JOOBLE = {
  name: "Jooble", kind: "jooble", action: "jooble_key", flag: "jooble_key", busy: "jooble-key", usage: false,
  placeholder: "Paste your Jooble API key", example: "Keywords @ place, like: help desk OR IT support @ Washington, DC (or @ remote)",
  savedText: "Each word or phrase between OR is one Jooble request per refresh. The same role, place and scam rules apply.",
  needText: () => ["Jooble searches need your API key (request one at ", h("a", { href: "https://jooble.org/api/about", target: "_blank", rel: "noopener" }, "jooble.org/api/about"), "). It stays on this server."],
};
