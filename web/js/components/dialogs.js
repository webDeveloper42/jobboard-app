// Pop-ups that more than one screen uses. Each takes the app and opens app.dialog.
import { STATUSES, STATUS_NAME } from "../core/constants.js";
import { h } from "../core/dom.js";
import { field } from "./widgets.js";

/** Tick the skills you have from a list; they're added to your profile and every job is re-scored. */
export function addSkillsDialog(app, missing) {
  const boxes = missing.map((s) => h("label", { class: "chip chip--checkable" }, h("input", { type: "checkbox", value: s }), s));
  app.dialog.open("Add skills you have", [h("p", { class: "u-muted" }, "Only add what you could talk about in an interview. Every job is re-scored after."), h("div", { class: "chip-list" }, boxes)],
    "Add", async () => {
      const picked = boxes.map((b) => b.querySelector("input")).filter((i) => i.checked).map((i) => i.value);
      if (!picked.length) return "";
      await app.api.act("profile", { skills: [...app.store.state.profile.skills, ...picked] });
      return `Added ${picked.join(", ")}`;
    });
}

/** A job you found somewhere else: paste its details and it's matched like the rest. */
export function addJobDialog(app) {
  const f = {
    title: h("input", { required: true }), company: h("input", { required: true }), url: h("input", { type: "url", placeholder: "https://…" }),
    location: h("input", { placeholder: "Remote, or a city" }), salary: h("input", { placeholder: "$18/hr or $40K" }),
    description: h("textarea", { rows: 7, placeholder: "Paste the job description so it can be matched and tailored" }),
    status: h("select", {}, STATUSES.slice(0, 3).map((s) => h("option", { value: s }, STATUS_NAME[s]))),
  };
  app.dialog.open("Add a job from anywhere", [h("div", { class: "form-grid" },
    field("Title", f.title), field("Company", f.company), field("Link", f.url), field("Location", f.location), field("Pay", f.salary), field("Status", f.status),
    field("Description", f.description, { wide: true }))], "Add", async () => {
    const out = await app.api.act("add_job", Object.fromEntries(Object.entries(f).map(([key, el]) => [key, el.value])));
    app.store.selectedId = out.id;
    return `Added with a ${out.score}% match`;
  });
}

/** A tailored resume or cover letter as a document in Docs, optionally on one of your templates' pages. */
export async function openInDocs(app, doc) {
  const open = async (template, win) => {
    const out = await app.api.act("doc_to_docs", { doc: doc.id, template: template || "" });
    if (win) win.location.href = out.url; else window.open(out.url, "_blank", "noopener");
    return `Opened “${out.title}” in Docs`;
  };
  let templates = [];
  try { templates = (await app.api.act("docs_templates")).templates || []; } catch (e) { /* no templates: just open it */ }
  if (!templates.length) {
    const win = window.open("about:blank", "_blank");
    try { app.toast.show(await open(null, win)); } catch (e) { if (win) win.close(); app.toast.error(e); }
    return;
  }
  const select = h("select", {}, h("option", { value: "" }, "A plain page"), templates.map((t) => h("option", { value: t.id }, `On my template: ${t.title}`)));
  app.dialog.open("Open in Docs", [h("p", { class: "u-muted" }, "The text becomes a document you can edit and download as Word or PDF. A template gives it that template's page layout: margins, header and footer."),
    field("Page", select)], "Open in Docs", () => {
    const win = window.open("about:blank", "_blank");
    return open(select.value, win).catch((e) => { if (win) win.close(); throw e; });
  });
}

/** Add a resume (r = null) or edit one: its name and the roles it's for. */
export function resumeDialog(app, r) {
  const name = h("input", { value: r ? r.name : "", placeholder: "Data entry, IT, Customer support…", required: true, maxlength: 60 });
  const boxes = app.store.state.focus.map((c) => h("label", { class: "chip chip--checkable" }, h("input", { type: "checkbox", value: c.id, checked: r ? r.roles.includes(c.id) : false }), c.name));
  const picked = () => boxes.map((b) => b.querySelector("input")).filter((i) => i.checked).map((i) => i.value);
  app.dialog.open(r ? "Edit resume" : "Add a resume", [
    field("Name", name),
    h("div", { class: "field" }, h("span", { class: "field__label" }, "Roles this resume is for"), h("div", { class: "chip-list" }, boxes)),
    h("p", { class: "u-muted u-small" }, r ? "While you search as this resume, the board shows only these roles. Tick none to show every role."
      : "You'll search as this resume right away, and the board switches to these roles. Then upload its file. Your other resumes keep their own file, skills and job titles.")],
  r ? "Save" : "Add", async () => {
    if (r) { await app.api.act("resume_update", { id: r.id, name: name.value, roles: picked() }); return "Saved"; }
    await app.api.act("resume_add", { name: name.value, roles: picked() });
    app.store.selectedId = null;
    app.store.job = null;
    return `Searching as your ${name.value.trim()} resume. Upload its file below.`;
  });
}

export function confirmDialog(app, title, text, okLabel, onOk) {
  app.dialog.open(title, [h("p", { class: "u-muted" }, text)], okLabel, onOk);
}
