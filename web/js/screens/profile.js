// Profile: your resumes, the primary resume's file, what you're looking for, skills, and contact details.
import { Component } from "../core/component.js";
import { bem, h } from "../core/dom.js";
import { confirmDialog, resumeDialog } from "../components/dialogs.js";
import { button, emptyState, field, panel, spinner, tag } from "../components/widgets.js";

const resumeSaved = (out) => `Resume saved. Found ${out.found_skills.length} skills${out.found_years != null ? ` and about ${out.found_years} years of experience` : ""}.`;

export class ProfileScreen extends Component {
  render() {
    if (!this.state) return emptyState({ title: "Loading…", extra: spinner() });
    const form = this.#form();
    const save = () => this.app.run("profile", () => this.api.act("profile", form.values()), "Saved. Every job was re-scored.");
    const saveButton = button(this.busy("profile") ? "Saving…" : "Save profile", save, { kind: "primary", disabled: this.busy("profile") });
    return [
      h("header", { class: "page-header" },
        h("div", { class: "page-header__titles" }, h("h1", { class: "page-header__title" }, "Profile"),
          h("p", { class: "page-header__subtitle" }, "Your resumes and what you're looking for. Matches are scored against these.")),
        h("div", { class: "page-header__actions" }, saveButton)),
      h("div", { class: "page" }, h("div", { class: "page__inner" },
        this.#resumes(), this.#resumeFile(), form.lookingFor, this.#hideRules(), form.skills, form.about,
        h("div", { class: bem("button-row", null, { end: true }) }, button(this.busy("profile") ? "Saving…" : "Save profile", save, { kind: "primary", disabled: this.busy("profile") }))))];
  }

  // ---- your resumes

  #resumes() {
    const app = this.app;
    return panel("Your resumes", {
      iconName: "file",
      actions: [button("Add a resume", () => resumeDialog(app, null), { kind: "small", iconName: "plus" })],
      children: [
        h("p", { class: "u-muted" }, "One resume per kind of job. The one you search as is used for matching, tailoring and cover letters, and the board shows its roles."),
        (this.state.resumes || []).map((r) => h("div", { class: bem("resume-row", null, { active: r.primary }) },
          h("div", { class: "resume-row__main" },
            h("div", { class: "resume-row__name" }, h("b", {}, r.name), r.primary ? tag("Searching as", "pay") : null),
            h("div", { class: "u-muted u-small" }, [`For ${this.store.roleNames(r.roles)}`, `${r.jobs} open jobs`, r.chars ? `${r.file || "Pasted"} · ${r.skills} skills` : "No resume file yet"].join(" · "))),
          !r.primary ? button("Search as this", () => app.useResume(r.id), { kind: "primary small", disabled: this.busy("resume") }) : null,
          button("Edit", () => resumeDialog(app, r), { kind: "ghost small" }),
          !r.primary ? button("Remove", () => confirmDialog(app, `Remove the ${r.name} resume?`, "Its text, skills and job titles are deleted. Jobs and applications stay.", "Remove",
            async () => { await this.api.act("resume_remove", { id: r.id }); return "Removed"; }), { kind: "ghost danger small" }) : null))] });
  }

  #resumeFile() {
    const p = this.state.profile;
    const primary = this.store.primaryResume;
    const area = h("textarea", { rows: 10, placeholder: "Paste your resume text here", hidden: true, "aria-label": "Resume text" });
    const useText = button("Use this text", () => this.app.run("resume", () => this.api.act("resume_text", { text: area.value, file: "Pasted" }), resumeSaved), { attrs: { hidden: true } });
    return panel(`Resume file${primary && this.state.resumes.length > 1 ? ` · ${primary.name}` : ""}`, {
      iconName: "file",
      note: p.resume_chars ? `${p.resume_file || "Pasted"} · ${p.resume_chars.toLocaleString()} characters` : null,
      children: [
        h("p", { class: "u-muted" }, "A PDF, Word (.docx) or text file, or pasted text. Skills, years and contact details are picked up; anything you've already set stays."),
        h("div", { class: "button-row" },
          button(this.busy("resume") ? [spinner(), "Reading…"] : p.resume_chars ? "Upload a new version" : "Upload resume", () => this.#pickFile(), { kind: "primary", iconName: this.busy("resume") ? null : "file", disabled: this.busy("resume") }),
          button("Paste text instead", () => { area.hidden = !area.hidden; useText.hidden = area.hidden; })),
        area, useText] });
  }

  #pickFile() {
    const picker = h("input", { type: "file", accept: ".pdf,.docx,.txt,.md", hidden: true });
    picker.onchange = () => {
      const file = picker.files[0];
      picker.remove();
      if (file) this.app.run("resume", () => this.api.uploadResume(file), resumeSaved);
    };
    document.body.append(picker);
    picker.click();
  }

  // ---- hide rules

  #hideRules() {
    const rules = this.state.hide_rules || { companies: [], words: [] };
    const group = (kind, label, items, placeholder) => {
      const input = h("input", { class: "u-grow", placeholder, "aria-label": label, onkeydown: (e) => { if (e.key === "Enter") { e.preventDefault(); add(); } } });
      const add = () => { const v = input.value.trim(); if (v) this.app.addHideRule(kind, v); };
      return h("div", { class: "hide-rules__group" },
        h("span", { class: "field__label" }, label),
        items.length ? h("div", { class: "chip-list" }, items.map((v) => h("span", { class: bem("chip", null, { active: true }) }, v,
          h("button", { class: "chip__remove", type: "button", "aria-label": `Stop hiding ${v}`, onclick: () => this.app.removeHideRule(kind, v) }, "×"))))
          : h("p", { class: "u-muted u-small" }, "None yet."),
        h("div", { class: "button-row" }, input, button("Add", add, { disabled: this.busy("rules") })));
    };
    const count = this.state.counts.by_rule;
    return panel("Hide rules", {
      iconName: "filter",
      note: count ? `${count} job${count === 1 ? "" : "s"} hidden right now` : null,
      children: [
        h("p", { class: "u-muted" }, "Jobs that match a rule never show in Matches or the morning email. Remove a rule to bring them back."),
        h("div", { class: "hide-rules" },
          group("company", "Never show jobs from", rules.companies, "A company, like Only Data Entry"),
          group("word", "Never show jobs that mention", rules.words, "A word or phrase, like night shift or CDL"))] });
  }

  // ---- the form (looking for, skills, about you)

  #form() {
    const p = this.state.profile;
    const input = (value, attrs = {}) => h("input", { value: value ?? "", ...attrs });
    const f = {
      target_titles: input(p.target_titles.join(", "), { placeholder: "IT Technician, Help Desk Technician" }),
      locations: input(p.locations.join(", "), { placeholder: "Washington, DC" }),
      home_address: input(p.home_address, { placeholder: "Street, city, ZIP (optional)", autocomplete: "street-address" }),
      min_salary: input(p.min_salary || "", { inputmode: "numeric", placeholder: "e.g. 40000 or 40k" }),
      years_exp: input(p.years_exp, { inputmode: "numeric" }),
      level: h("select", {}, h("option", { value: "" }, "Work it out from my years"), this.state.levels.map((l) => h("option", { value: l.id, selected: p.level === l.id }, l.name))),
      needs_sponsorship: h("input", { class: "checkbox__input", type: "checkbox", checked: p.needs_sponsorship }),
      name: input(p.name, { autocomplete: "name" }), headline: input(p.headline, { placeholder: "IT support technician, data entry clerk…" }),
      email: input(p.email, { type: "email", autocomplete: "email" }), phone: input(p.phone, { autocomplete: "tel" }),
      location: input(p.location, { placeholder: "Where you live" }), links: input(p.links, { placeholder: "LinkedIn, portfolio" }),
    };
    const models = new Set(p.work_models);
    const modelBoxes = [["remote", "Remote"], ["hybrid", "Hybrid"], ["onsite", "On-site"]].map(([m, label]) =>
      h("label", { class: "chip chip--checkable" }, h("input", { type: "checkbox", value: m, checked: models.has(m) }), label));
    const skills = new SkillsEditor(p.skills);
    const gaps = (this.state.insights.skill_gaps || []).filter((g) => !p.skills.some((s) => s.toLowerCase() === g.skill.toLowerCase()));
    return {
      values: () => ({
        ...Object.fromEntries(Object.entries(f).filter(([k]) => k !== "needs_sponsorship").map(([k, el]) => [k, el.value.trim ? el.value.trim() : el.value])),
        needs_sponsorship: f.needs_sponsorship.checked, skills: skills.values(),
        work_models: modelBoxes.map((b) => b.querySelector("input")).filter((i) => i.checked).map((i) => i.value),
      }),
      lookingFor: panel("What you're looking for", { iconName: "star", children: h("div", { class: "form-grid" },
        field("Job titles", f.target_titles, { wide: true }),
        h("div", { class: bem("field", null, { wide: true }) }, h("span", { class: "field__label" }, "Work type"), h("div", { class: "chip-list" }, modelBoxes)),
        field("Places for hybrid and on-site", f.locations),
        field("Home address, for commute directions", f.home_address, { hint: "Only used for Maps directions. Never on a resume or letter." }),
        field("Minimum yearly pay", f.min_salary), field("Years of experience", f.years_exp), field("Level", f.level),
        h("label", { class: "checkbox" }, f.needs_sponsorship, "I need visa sponsorship")) }),
      skills: panel("Skills", { iconName: "check", note: `${p.skills.length} skills`, children: [
        skills.render(), h("p", { class: "u-muted u-small" }, "Skills count most in your match score. Remove ones you wouldn't want to be asked about."),
        gaps.length ? [h("div", { class: "section-title" }, "Often asked for in your better matches"), h("div", { class: "chip-list" }, gaps.slice(0, 8).map((g) =>
          h("button", { class: "chip", type: "button", title: `Asked for by ${g.jobs} of your better matches. Add it if you have it.`, onclick: () => skills.add(g.skill) }, `+ ${g.skill} · ${g.jobs}`)))] : null] }),
      about: panel("About you", { iconName: "people", children: [h("p", { class: "u-muted" }, "Used in cover letters. Stays on this server."),
        h("div", { class: "form-grid" }, field("Name", f.name), field("Headline", f.headline), field("Email", f.email), field("Phone", f.phone), field("Lives in", f.location), field("Links", f.links))] }),
    };
  }
}

/** The skills box: type a skill and press Enter, × to remove, Backspace in an empty box removes the last one. */
class SkillsEditor {
  constructor(skills) {
    this.skills = [...skills];
    this.input = h("input", { class: "skills-editor__input", placeholder: "Add a skill and press Enter", "aria-label": "Add a skill", onkeydown: (e) => this.#onKey(e) });
    this.el = h("div", { class: "skills-editor" });
  }

  render() { this.#draw(false); return this.el; }

  add(skill) { if (skill && !this.skills.includes(skill)) this.skills.push(skill); this.#draw(); }

  values() { const pending = this.input.value.trim(); return pending ? [...this.skills, pending] : this.skills; }

  #onKey(e) {
    if ((e.key === "Enter" || e.key === ",") && e.target.value.trim()) {
      e.preventDefault();
      e.target.value.split(",").map((x) => x.trim()).filter(Boolean).forEach((x) => this.add(x));
      e.target.value = "";
    } else if (e.key === "Backspace" && !e.target.value && this.skills.length) {
      this.skills.pop();
      this.#draw();
    }
  }

  #draw(focus = true) {
    this.el.replaceChildren(...this.skills.map((s, i) => h("span", { class: bem("skill", null, { have: true }) }, s,
      h("button", { class: "skill__remove", type: "button", "aria-label": `Remove ${s}`, onclick: () => { this.skills.splice(i, 1); this.#draw(); } }, "×"))), this.input);
    if (focus) this.input.focus();
  }
}
