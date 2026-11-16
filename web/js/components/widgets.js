// Small pieces used all over the page. Each returns one element (or a list of them).
import { bem, h, icon } from "../core/dom.js";
import { scoreBand } from "../core/format.js";

/** The circular match score. `large` for the job detail. */
export function matchRing(value, large = false, label = "") {
  const v = value == null ? 0 : value;
  const band = scoreBand(v);
  return h("div", { class: bem("match-ring", null, { large, [band]: Boolean(band) }), style: { "--match-ring-value": v }, role: "img",
    "aria-label": `${v}% match${label ? `, ${label}` : ""}`, title: label || null },
  h("span", { class: "match-ring__value" }, value == null ? "–" : `${v}%`, large && label ? h("small", { class: "match-ring__label" }, label.replace(" match", "")) : null));
}

/** A small label. kind: pay, role, new, status, danger, warning (or none). */
export function tag(text, kind = "", title = "") {
  return h("span", { class: bem("tag", null, { [kind]: Boolean(kind) }), title: title || null }, text);
}

/** The warnings worth seeing before opening a job, read from its score flags. */
export function warningTags(job) {
  const flags = job.flags || (job.score_detail || {}).flags || [];
  const find = (re) => flags.find((f) => re.test(f));
  const out = [];
  if (flags.includes("Needs an active security clearance")) out.push(tag("Clearance required", "danger", "Asks for a Secret / Top Secret clearance you already hold"));
  const old = find(/^Posted \d+ days ago/);
  if (old) out.push(tag("Old post", "warning", old));
  const again = find(/^Posted again/);
  if (again) out.push(tag("Reposted", "warning", again));
  const site = find(/^Listed by a job site/);
  if (site) out.push(tag("Job site repost", "warning", `${site}. It may be a stale copy; look for the job on the employer's own site.`));
  const away = find(/^Remote, but listed in/);
  if (away) out.push(tag("Remote · check state", "", away));
  return out;
}

/** A centred message for "nothing here yet", with an optional icon and action button. */
export function emptyState({ iconName = null, title, text = "", action = null, extra = null }) {
  return h("div", { class: "empty-state" }, iconName ? icon(iconName, 28) : null, h("b", { class: "empty-state__title" }, title),
    text ? h("p", { class: "empty-state__text" }, text) : null, action, extra);
}

export const spinner = () => h("span", { class: "spinner", role: "status", "aria-label": "Working" });

/** A labelled progress bar (score parts, resume keywords, SerpApi usage). Red under 40%, amber under 65%. */
export function meter(percent, label) {
  const level = percent < 40 ? "low" : percent < 65 ? "mid" : "";
  return h("div", { class: "meter", role: "img", "aria-label": label },
    h("div", { class: bem("meter", "fill", { [level]: Boolean(level) }), style: { width: `${Math.max(0, Math.min(100, percent))}%` } }));
}

/** A standard button. kind: primary, ghost, danger (combine with spaces), small. */
export function button(label, onclick, { kind = "", iconName = null, disabled = false, title = null, ariaLabel = null, attrs = {} } = {}) {
  const mods = Object.fromEntries(kind.split(/\s+/).filter(Boolean).map((k) => [k, true]));
  return h("button", { class: bem("button", null, mods), onclick, disabled, title, "aria-label": ariaLabel, type: "button", ...attrs },
    iconName ? icon(iconName, mods.small ? 13 : 15) : null, label);
}

/** A card with a title row ("About the job", "Skills this job wants"…). `actions` go on the right of the title. */
export function panel(title, { iconName = null, note = null, actions = [], children = [] }) {
  return h("section", { class: "panel" },
    h("h3", { class: "panel__title" }, iconName ? icon(iconName, 15) : null, title, note ? h("span", { class: "panel__note" }, note) : null,
      actions.length ? h("span", { class: "panel__actions" }, actions) : null),
    children);
}

/** A labelled form control. `wide` spans both columns of a .form-grid. */
export function field(label, control, { wide = false, hint = null } = {}) {
  return h("label", { class: bem("field", null, { wide }) }, h("span", { class: "field__label" }, label), control, hint ? h("small", { class: "field__hint" }, hint) : null);
}

/** A chat transcript (Coach). */
export function chatLog(messages) {
  return h("div", { class: "chat", "aria-live": "polite" }, messages.map((m) => h("div", { class: bem("chat", "message", { [m.role]: true }) }, m.content)));
}
