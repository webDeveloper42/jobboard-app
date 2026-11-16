// The tabs inside an open job. Each panel is a class with render(job).
import { SCORE_PARTS, SCORE_WEIGHTS, SNIPPET_LENGTH, STATUS_NAME } from "../core/constants.js";
import { Component } from "../core/component.js";
import { bem, h, icon } from "../core/dom.js";
import { cap, dayLabel } from "../core/format.js";
import { addSkillsDialog, openInDocs } from "./dialogs.js";
import { button, chatLog, field, meter, panel, spinner } from "./widgets.js";

/** The post itself (first, because reading it is the point), the skills it asks for, and the history. */
export class OverviewPanel extends Component {
  render(job) {
    const app = this.app;
    const link = job.apply_url || job.url;
    const isSnippet = (job.description || "").length < SNIPPET_LENGTH;
    const showFull = this.store.ui.showFull || isSnippet;
    const others = (job.links || []).filter((l) => l.url && l.url !== link);
    return [
      this.#alreadyApplied(job),
      panel("About the job", {
        actions: [
          job.description ? button("Copy", () => app.copyText(job.description, "Description copied"), { kind: "ghost small" }) : null,
          link ? h("a", { class: "button button--ghost button--small", href: job.url || link, target: "_blank", rel: "noopener noreferrer" }, "Original post", icon("share", 12)) : null],
        children: [
          isSnippet ? h("div", { class: "callout" },
            h("div", { class: "callout__text" }, h("b", {}, "Only part of the post came through."), " This board sent a few lines; get the rest from the employer's page."),
            button(this.busy("full") ? [spinner(), "Getting it…"] : "Get the full description", () => app.getFullPost(job), {
              kind: "small", disabled: this.busy("full"), title: "Reads the whole post from the employer's page. If that page can't be read, the job is looked up on Google Jobs, which uses one SerpApi search." })) : null,
          h("div", { class: bem("description", null, { collapsed: !showFull }) }, job.description || "No description was given."),
          (job.description || "").length > 1200 ? button(this.store.ui.showFull ? "Show less" : "Show the whole post", () => { this.store.ui.showFull = !this.store.ui.showFull; app.render(); }, { kind: "ghost small", attrs: { class: "button button--ghost button--small description__toggle" } }) : null,
          others.length ? h("p", { class: "u-muted u-small" }, "Also listed on ", others.map((l, i) => [i ? ", " : "", h("a", { href: l.url, target: "_blank", rel: "noopener noreferrer" }, l.via || "another board")])) : null] }),
      new SkillsPanel(app).render(job),
      historyPanel(job)];
  }

  /** "You've applied to this company before", so one job posted under two titles doesn't get two applications. */
  #alreadyApplied(job) {
    const others = job.same_company || [];
    if (!others.length) return null;
    return h("div", { class: bem("callout", null, { info: true }), role: "note" },
      h("div", { class: "callout__text" }, h("b", {}, `You already have ${others.length === 1 ? "an application" : `${others.length} applications`} at ${job.company}.`),
        " Check it isn't the same job under another title:",
        h("ul", { class: "callout__list" }, others.map((o) => h("li", {},
          h("button", { class: "link-button", type: "button", onclick: () => this.app.pick(o.job_id) }, o.title),
          ` · ${STATUS_NAME[o.status] || o.status}${o.at ? `, ${dayLabel(o.at.slice(0, 10))}` : ""}`)))));
  }
}

/** Every skill found in the post, ticked when it's on your profile. */
export class SkillsPanel extends Component {
  render(job) {
    const all = job.skills || [];
    const d = job.score_detail || {};
    const mine = new Set([...(this.state.profile.skills || []), ...(d.matched || [])].map((x) => String(x).toLowerCase()));
    const have = all.filter((x) => mine.has(x.toLowerCase()));
    const need = all.filter((x) => !mine.has(x.toLowerCase()));
    return panel("Skills this job wants", {
      note: all.length ? `${have.length} of ${all.length} are yours` : null,
      actions: all.length ? [button("Copy", () => this.app.copyText(all.join(", "), "Skills copied"), { kind: "ghost small" })] : [],
      children: all.length ? h("div", { class: "skill-list" },
        have.map((x) => h("span", { class: bem("skill", null, { have: true }), title: "On your profile" }, icon("check", 11), x)),
        need.map((x) => h("span", { class: bem("skill", null, { missing: true }), title: "Not on your profile" }, x)),
        need.length ? button("I have some of these", () => addSkillsDialog(this.app, need), { kind: "ghost small" }) : null)
        : h("p", { class: "u-muted" }, (job.description || "").length < SNIPPET_LENGTH ? "None found in the few lines this board sent. Get the full description above to see them." : "No specific skills were found in this post.") });
  }
}

/** How the score is made up, the reasons, and how many of the job's skills your resume mentions word for word. */
export class MatchPanel extends Component {
  render(job) {
    const d = job.score_detail || {};
    const parts = d.parts || {};
    const cov = job.coverage;
    return panel("Why this match", {
      note: d.label || null,
      children: [
        h("div", { class: "score-bars" }, Object.keys(SCORE_WEIGHTS).map((key) => {
          const v = parts[key] ?? 0;
          return h("div", { class: "score-bars__row", title: `${SCORE_PARTS[key]} counts for ${SCORE_WEIGHTS[key]} of 100 points` },
            h("span", { class: "score-bars__label" }, SCORE_PARTS[key]), meter(v, `${SCORE_PARTS[key]} ${v}%`), h("b", { class: "score-bars__value" }, `${v}%`));
        })),
        d.why && d.why.length ? h("ul", { class: "reasons" }, d.why.map((w) => h("li", { class: "reasons__item" }, w))) : null,
        this.state.profile.resume_chars ? h("div", { class: "keyword-coverage", title: "How many of the job's skills appear word for word in your resume. Applicant tracking systems look for these." },
          h("span", {}, `Resume keywords ${cov.percent}%`), meter(cov.percent, `Resume keywords ${cov.percent}%`),
          cov.absent.length ? h("span", { class: "u-muted" }, `missing ${cov.absent.slice(0, 5).join(", ")}`) : null) : null,
        (d.missing || []).length ? h("div", { class: "button-row" }, button("I have some of the missing skills", () => addSkillsDialog(this.app, d.missing), { kind: "ghost small" })) : null] });
  }
}

/** A tailored resume and a cover letter, written on this server by the local model. */
export class ApplyKitPanel extends Component {
  render(job) {
    const app = this.app;
    const working = this.busy(`tailor${job.id}`) || this.busy(`letter${job.id}`);
    return panel("Apply kit", {
      iconName: "bolt",
      actions: [
        button("Tailor my resume", () => app.run(`tailor${job.id}`, () => app.api.act("tailor", { id: job.id }), "Tailored resume ready"), { kind: "small", disabled: working }),
        button("Write a cover letter", () => app.run(`letter${job.id}`, () => app.api.act("letter", { id: job.id }), "Cover letter ready"), { kind: "small", disabled: working })],
      children: [
        working ? h("div", { class: "working" }, spinner(), "Writing with your local model. This takes about a minute.") : null,
        !job.documents.length && !working ? h("p", { class: "u-muted" }, this.state.profile.resume_chars
          ? "A resume tailored to this post and a cover letter, written from your resume on this server. Nothing is sent anywhere."
          : "Add your resume in Profile first for the best results.") : null,
        job.documents.map((doc) => this.#document(doc))] });
  }

  #document(doc) {
    const app = this.app;
    const editing = this.store.ui.editing;
    const name = doc.kind === "cover_letter" ? "Cover letter" : "Tailored resume";
    const isEditing = editing.has(doc.id);
    const area = isEditing ? h("textarea", { class: "document__editor", value: doc.body, id: `doc${doc.id}`, "aria-label": name }) : null;
    return h("div", { class: "document" },
      h("header", { class: "document__header" }, h("b", {}, name), h("span", { class: "u-muted" }, `${doc.created.replace("T", " ").slice(0, 16)} · ${doc.model || "template"}`),
        h("span", { class: "u-spacer" }),
        button("Copy", () => app.copyText(isEditing ? area.value : doc.body, "Copied"), { kind: "ghost small" }),
        isEditing ? button("Save", () => { editing.delete(doc.id); app.run("doc", () => app.api.act("doc_save", { doc: doc.id, body: area.value }), "Saved"); }, { kind: "small" })
          : button("Edit", () => { editing.add(doc.id); app.render(); }, { kind: "ghost small" }),
        button("Open in Docs", () => openInDocs(app, doc), { kind: "ghost small", title: "Open it as a document in the Docs tab, to polish it and download it as Word or PDF" }),
        button("Delete", () => app.run("doc", () => app.api.act("doc_delete", { doc: doc.id }), "Deleted"), { kind: "ghost danger small" })),
      isEditing ? area : h("pre", { class: "document__body" }, doc.body));
  }
}

/** The coach, about this one job. */
export class AskPanel extends Component {
  render(job) {
    const app = this.app;
    const key = `ask${job.id}`;
    const input = h("input", { class: "ask-box__input", id: `ask${job.id}`, placeholder: "Ask about this job", "aria-label": "Ask Coach about this job", onkeydown: (e) => { if (e.key === "Enter") send(); } });
    const send = () => {
      const q = input.value.trim();
      if (!q) return;
      input.value = "";
      this.store.job.chat.push({ role: "user", content: q });
      app.run(key, () => app.api.act("ask", { id: job.id, q }));
    };
    const suggestions = ["How do I stand out for this role?", "Likely interview questions?", "What should I ask them?", "Is the pay fair?"];
    return panel("Ask Coach about this job", {
      iconName: "bolt",
      actions: job.chat.length ? [button("Clear", () => app.run("chat", () => app.api.act("chat_clear", { id: job.id })), { kind: "ghost small" })] : [],
      children: [
        chatLog(job.chat),
        this.busy(key) ? h("div", { class: "working" }, spinner(), "Coach is thinking…") : null,
        !job.chat.length ? h("div", { class: "chip-list" }, suggestions.map((s) => h("button", { class: "chip", type: "button", onclick: () => { input.value = s; send(); } }, s))) : null,
        h("div", { class: "ask-box" }, input, button("Ask", send, { kind: "primary", disabled: this.busy(key) }))] });
  }
}

/** Your application: next step, contact, offer and notes, plus the history. */
export class TrackingPanel extends Component {
  render(job) {
    const app = this.app;
    const ap = job.application;
    const f = {
      next_step: h("input", { value: ap.next_step, placeholder: "Phone screen, send a thank-you note…" }),
      next_date: h("input", { type: "date", value: ap.next_date || "" }),
      contact: h("input", { value: ap.contact, placeholder: "Recruiter or referral" }),
      salary_offer: h("input", { value: ap.salary_offer || "", inputmode: "numeric", placeholder: "Yearly, if offered" }),
      notes: h("textarea", { value: ap.notes, rows: 4, placeholder: "Interview notes, questions they asked, what to mention next time" }),
    };
    const save = () => app.run("track", () => app.api.act("track", { id: job.id, ...Object.fromEntries(Object.entries(f).map(([k, el]) => [k, el.value])) }), "Saved");
    return [
      panel(`Application · ${STATUS_NAME[ap.status]}`, {
        iconName: "board",
        note: ap.applied_at ? `Applied ${dayLabel(ap.applied_at.slice(0, 10))}` : `Saved ${dayLabel(ap.saved_at.slice(0, 10))}`,
        children: [
          h("div", { class: "form-grid" },
            field("Next step", f.next_step), field("Date", f.next_date), field("Contact", f.contact), field("Offer", f.salary_offer), field("Notes", f.notes, { wide: true })),
          h("div", { class: "button-row" }, button("Save", save, { kind: "primary", disabled: this.busy("track") }))] }),
      historyPanel(job)];
  }
}

// ---- shared bits



function historyPanel(job) {
  if (!job.events.length) return null;
  return panel("History", {
    children: h("ul", { class: "history" }, job.events.map((e) =>
      h("li", { class: "history__item" }, h("time", { class: "history__time" }, e.at.replace("T", " ").slice(0, 16)), cap(e.kind), e.detail ? ` · ${e.detail}` : ""))) });
}
