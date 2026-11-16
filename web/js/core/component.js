// The base for every piece of the page. A component gets the app, reads what it needs from `this.store`, and returns
// elements from render(). It never changes the store itself; it calls App methods (like `this.app.pick(id)`).

export class Component {
  constructor(app) {
    this.app = app;
  }

  get store() { return this.app.store; }
  get api() { return this.app.api; }
  get state() { return this.app.store.state; }

  /** Is this action running? (The button shows "…" and is disabled.) */
  busy(key) { return Boolean(this.app.store.busy[key]); }

  render() {
    throw new Error(`${this.constructor.name} must implement render()`);
  }
}
