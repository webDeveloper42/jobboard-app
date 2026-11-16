// Building the page. Text only ever goes in through text nodes or .value, never as HTML, because job posts come
// from the internet. Use h() for every element and bem() for every class name.

/**
 * Make an element. `attrs` keys: class, style (object), on<event> handlers, value/checked/disabled (set as
 * properties), anything else becomes an attribute. null/false attributes and children are skipped.
 *   h("button", { class: "button button--primary", onclick: save }, "Save")
 */
export function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value == null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (key === "value" || key === "disabled" || key === "checked") el[key] = value;
    else if (key === "style" && typeof value === "object") Object.assign(el.style, value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) el.append(kid);
  return el;
}

/**
 * A BEM class string. bem("job-card") -> "job-card"; bem("job-card", "title") -> "job-card__title";
 * bem("job-card", null, { active: true }) -> "job-card job-card--active". Extra plain classes go in `extra`.
 */
export function bem(block, element = null, modifiers = {}, extra = "") {
  const base = element ? `${block}__${element}` : block;
  const mods = Object.entries(modifiers || {}).filter(([, on]) => on).map(([name]) => `${base}--${name}`);
  return [base, ...mods, extra].filter(Boolean).join(" ");
}

/** An icon from the dashboard's shared icon set (/design/icons.js), hidden from screen readers. */
export function icon(name, size = 16) {
  const t = document.createElement("template");
  t.innerHTML = window.icon(name, size);
  const el = t.content.firstChild;
  if (el && el.setAttribute) el.setAttribute("aria-hidden", "true");
  return el;
}
