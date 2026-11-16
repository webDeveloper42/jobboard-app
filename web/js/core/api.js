// Talking to the job board engine through the dashboard. Every call returns parsed JSON or throws an Error whose
// message is meant to be shown to you.

export class ApiClient {
  constructor(base = "/api/jobs") {
    this.base = base;
  }

  async #parse(response) {
    let body = {};
    try { body = await response.json(); } catch (e) { /* not JSON */ }
    if (!response.ok) throw new Error(body.error || "Something went wrong");
    return body;
  }

  /** Everything the page shows: jobs (with these filters), counts, profile, resumes, boards… */
  state(filters) {
    const query = new URLSearchParams(Object.entries(filters).filter(([, v]) => v !== "" && v != null)).toString();
    return fetch(`${this.base}/state?${query}`).then((r) => this.#parse(r));
  }

  /** One job in full: description, match detail, application, documents, chat. */
  job(id) {
    return fetch(`${this.base}/job?id=${encodeURIComponent(id)}`).then((r) => this.#parse(r));
  }

  /** The coach's chat about your whole search. */
  chat() {
    return fetch(`${this.base}/chat`).then((r) => this.#parse(r));
  }

  /** Run an engine action by name (see ACTIONS in jobboard/api.py). */
  act(action, data = {}) {
    return fetch(`${this.base}/do`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, ...data }) })
      .then((r) => this.#parse(r));
  }

  /** Upload a resume file: it goes through the dashboard's upload (a copy lands in ~/incoming), then is read. */
  async uploadResume(file) {
    const sent = await fetch(`/api/upload?path=${encodeURIComponent(file.name)}`,
      { method: "POST", headers: { "Content-Type": "application/octet-stream", "X-Capture-Upload": "1" }, body: file }).then((r) => this.#parse(r));
    return fetch(`${this.base}/resume`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ file: sent.name, name: file.name }) })
      .then((r) => this.#parse(r));
  }

  exportUrl() {
    return `${this.base}/export`;
  }
}
