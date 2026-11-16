// The short message at the bottom of the screen ("Saved", "Couldn't reach the server…").

export class Toast {
  constructor(el) {
    this.el = el;
    this.timer = null;
  }

  show(text, isError = false) {
    this.el.textContent = text;
    this.el.className = isError ? "toast toast--error" : "toast";
    this.el.hidden = false;
    clearTimeout(this.timer);
    this.timer = setTimeout(() => { this.el.hidden = true; }, isError ? 6500 : 3500);
  }

  error(err) {
    this.show((err && err.message) || "Can't reach the server. Is the tunnel still open?", true);
  }
}
