// Keyboard shortcuts on the Matches screen. The list in SHORTCUTS is also what the "?" dialog shows.
import { h } from "./dom.js";

export const SHORTCUTS = [
  ["j or ↓", "Next job"], ["k or ↑", "Previous job"], ["s", "Save the job"], ["x", "Not interested (moves to the next job)"],
  ["a", "Open the apply page"], ["/", "Search"], ["Esc", "Close filters, a menu or the job"], ["?", "This list"],
];

export class KeyboardShortcuts {
  constructor(app) {
    this.app = app;
  }

  listen() {
    document.addEventListener("keydown", (e) => this.#onKey(e));
    // An open "More" menu closes on a click outside it.
    document.addEventListener("click", (e) => {
      document.querySelectorAll("details.menu[open]").forEach((menu) => { if (!menu.contains(e.target)) menu.open = false; });
    });
  }

  showHelp() {
    const rows = SHORTCUTS.map(([key, what]) => h("tr", { class: "shortcut-list__row" }, h("td", { class: "shortcut-list__key" }, h("kbd", {}, key)), h("td", {}, what)));
    this.app.dialog.open("Keyboard shortcuts", [h("table", { class: "shortcut-list" }, rows)], "Done", () => "", null);
  }

  #onKey(e) {
    const { app } = this;
    const store = app.store;
    if (e.key === "Escape") document.querySelectorAll("details.menu[open]").forEach((menu) => { menu.open = false; });
    if (app.dialog.isOpen || e.metaKey || e.ctrlKey || e.altKey) return;
    const t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) {
      if (e.key === "Escape" && t.id === "search") t.blur();
      return;
    }
    if (e.key === "?") { e.preventDefault(); this.showHelp(); return; }
    if (store.screen !== "jobs") return;
    const job = store.job;
    switch (e.key) {
      case "/": e.preventDefault(); document.getElementById("search")?.focus(); break;
      case "j": case "ArrowDown": this.#move(e, 1); break;
      case "k": case "ArrowUp": this.#move(e, -1); break;
      case "Escape":
        if (store.ui.filtersOpen) { store.ui.filtersOpen = false; app.render(); } else if (job) app.closeJob();
        break;
      case "s": if (job && !job.application) app.saveJob(job); break;
      case "x": if (job) app.toggleHidden(job); break;
      case "a": if (job) app.openApply(job); break;
      default: break;
    }
  }

  #move(e, step) {
    const id = this.app.store.neighbourId(step);
    if (id) { e.preventDefault(); this.app.pick(id, true); }
  }
}
