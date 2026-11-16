// One <dialog> for every pop-up: a title, any content, and OK / Cancel buttons.
import { h } from "./dom.js";

export class Dialog {
  /** `onDone(message)` runs after OK succeeds (App uses it to show the message and reload). */
  constructor(el, onDone, onError) {
    this.el = el;
    this.onDone = onDone;
    this.onError = onError;
  }

  get isOpen() { return this.el.open; }

  /**
   * Show a dialog. `onOk` may be async; whatever string it returns is shown as a toast. If it throws, the error is
   * shown and the dialog stays open. Pass cancelLabel = null for a dialog with only an OK button.
   */
  open(title, body, okLabel, onOk, cancelLabel = "Cancel") {
    const ok = h("button", { class: "button button--primary", type: "submit" }, okLabel);
    const form = h("form", { class: "dialog__form", method: "dialog" }, h("h2", { class: "dialog__title" }, title), body,
      h("div", { class: "dialog__actions" },
        cancelLabel ? h("button", { class: "button button--ghost", type: "button", onclick: () => this.el.close() }, cancelLabel) : null, ok));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      ok.disabled = true;
      try {
        const message = await onOk();
        this.el.close();
        await this.onDone(message);
      } catch (err) {
        this.onError(err);
        ok.disabled = false;
      }
    });
    this.el.replaceChildren(form);
    this.el.showModal();
  }
}
