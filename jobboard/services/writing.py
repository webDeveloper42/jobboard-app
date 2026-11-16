"""AI writing and the other apps: tailored resumes, cover letters, Coach chat, and opening things in Docs and Notes.
"""
from .. import config
from .. import validation as validate
from ..errors import JobBoardError
from ..links import docs, notes
from ..storage import db
from ..writing import ai
from .base import Service


class WritingService(Service):
    def _context(self, job_id):
        def go():
            prof = db.profile(self.con)
            j = self.app.feed.job_detail(job_id) if job_id else None
            return prof, j, db.setting(self.con, "model")
        return self.run(go)

    def _save_doc(self, job_id, kind, body, model):
        def go():
            cur = self.con.execute("INSERT INTO documents (job_id, kind, body, model, created) VALUES (?, ?, ?, ?, ?)", (job_id, kind, body, model or "", db.now()))
            db.log_event(self.con, job_id, kind.replace("_", " "), model or "template")
            self.con.commit()
            return {"id": cur.lastrowid, "kind": kind, "body": body, "model": model or "", "created": db.now()}
        return self.run(go)

    def tailor(self, d):
        job_id = validate.job_id(d.get("id"))
        prof, j, wanted = self._context(job_id)
        if not prof["resume_text"]:
            raise JobBoardError("Add your resume first, in Profile")
        model = ai.pick(wanted) if d.get("ai", True) else None
        if model:
            try:
                body = ai.clean(ai.tailor(model, prof, j, j["score_detail"], j["coverage"]))
            except ai.AiError:
                model, body = None, ai.tailor_fallback(prof, j, j["score_detail"], j["coverage"])
        else:
            body = ai.tailor_fallback(prof, j, j["score_detail"], j["coverage"])
        return self._save_doc(job_id, "tailored_resume", body, model)

    def letter(self, d):
        job_id = validate.job_id(d.get("id"))
        prof, j, wanted = self._context(job_id)
        model = ai.pick(wanted) if d.get("ai", True) else None
        if model:
            try:
                body = ai.clean(ai.cover_letter(model, prof, j, j["score_detail"]))
            except ai.AiError:
                model, body = None, ai.letter_fallback(prof, j, j["score_detail"])
        else:
            body = ai.letter_fallback(prof, j, j["score_detail"])
        return self._save_doc(job_id, "cover_letter", body, model)

    def doc_save(self, d):
        doc_id = validate.number(d.get("doc"), "document", blank_ok=False)
        body = validate.text(d.get("body"), config.MAX_TEXT, "the text", required=True)

        def go():
            self.con.execute("UPDATE documents SET body = ? WHERE id = ?", (body, doc_id))
            self.con.commit()
            return {"id": doc_id}
        return self.run(go)

    def job_note(self, d):
        """The job's note in the Notes tab: the one made before, or a new one with an outline for interviews."""
        job_id = validate.job_id(d.get("id"))
        if self.app.notes is None:
            raise JobBoardError("The Notes tab isn't connected here")
        job = self.run(lambda: self.con.execute("SELECT id, title, company, location, url FROM jobs WHERE id = ?", (job_id,)).fetchone())
        if not job:
            raise JobBoardError("That job isn't here anymore")
        known = self.run(lambda: db.setting(self.con, f"job_note_{job_id}"))
        try:
            if known and notes.exists(int(known), self.app.notes or None):
                return {"id": int(known), "url": f"/notes/#note/{known}", "new": False}
            note_id = notes.make(dict(job), self.app.notes or None)
        except (notes.NotesLinkError, OSError, ValueError) as e:
            raise JobBoardError(f"Couldn't make the note: {e}") from None
        self.run(lambda: (db.set_setting(self.con, f"job_note_{job_id}", note_id), db.log_event(self.con, job_id, "note", "Notes"), self.con.commit()))
        return {"id": note_id, "url": f"/notes/#note/{note_id}", "new": True}

    def docs_templates(self, d=None):
        """Your Docs templates, for "Open in Docs with a template"."""
        if self.app.docs is None:
            return {"templates": []}
        try:
            return {"templates": docs.templates(self.app.docs or None)}
        except Exception:  # noqa: BLE001 - no Docs app just means no templates to offer
            return {"templates": []}

    def doc_to_docs(self, d):
        """A tailored resume or cover letter as a document in the Docs tab (optionally on one of your templates' pages)."""
        doc_id = validate.number(d.get("doc"), "document", blank_ok=False)
        template = validate.number(d.get("template"), "template") if d.get("template") not in (None, "") else None
        if self.app.docs is None:
            raise JobBoardError("The Docs tab isn't connected here")
        row = self.run(lambda: self.con.execute(
            "SELECT d.kind, d.body, j.title, j.company FROM documents d LEFT JOIN jobs j ON j.id = d.job_id WHERE d.id = ?", (doc_id,)).fetchone())
        if not row:
            raise JobBoardError("That document isn't here anymore")
        name = "Cover letter" if row["kind"] == "cover_letter" else "Resume"
        title = " — ".join(x for x in (name, row["company"], row["title"]) if x)[:150]
        try:
            new_id = docs.open_in_docs(title, row["body"], row["kind"], template, self.app.docs or None)
        except (docs.DocsLinkError, ValueError) as e:
            raise JobBoardError(f"Couldn't make the document: {e}") from None
        return {"id": new_id, "url": f"/docs/#doc/{new_id}", "title": title}

    def doc_delete(self, d):
        doc_id = validate.number(d.get("doc"), "document", blank_ok=False)
        return self.run(lambda: (self.con.execute("DELETE FROM documents WHERE id = ?", (doc_id,)), self.con.commit(), {"id": doc_id})[2])

    def ask(self, d):
        """The coach. With a job id it talks about that job; without one, about your search."""
        question = validate.text(d.get("q"), 2000, "a question", required=True)
        job_id = validate.job_id(d["id"]) if d.get("id") not in (None, "") else None
        prof, j, wanted = self._context(job_id)
        history = self.app.feed.chat_history(job_id)
        summary = self.run(self._search_summary, prof)
        model = ai.pick(wanted)
        if not model:
            raise JobBoardError("Coach needs Ollama, which isn't running. Start it with: ollama serve")
        try:
            answer = ai.clean(ai.ask(model, prof, j, history, question, summary))
        except ai.AiError as e:
            raise JobBoardError(f"Coach couldn't answer: {e}") from None

        def go():
            stamp = db.now()
            self.con.execute("INSERT INTO chat (job_id, role, content, at) VALUES (?, 'user', ?, ?)", (job_id, question, stamp))
            self.con.execute("INSERT INTO chat (job_id, role, content, at) VALUES (?, 'assistant', ?, ?)", (job_id, answer, stamp))
            self.con.commit()
            return {"answer": answer, "model": model}
        return self.run(go)

    def _search_summary(self, prof):
        """What Coach knows about the search: counts, the jobs being tracked and the best untracked matches."""
        stats = self.app.feed.insights(prof)
        lines = [f"{stats['applied']} applications sent, {stats['responses']} interviews or offers."]
        if stats["skill_gaps"]:
            lines.append("Skills their better matches ask for that they lack: " + ", ".join(g["skill"] for g in stats["skill_gaps"][:5]) + ".")
        tracked = self.con.execute("""SELECT a.status, j.title, j.company, j.score, a.next_step, a.next_date FROM applications a JOIN jobs j ON j.id = a.job_id
                                      WHERE a.status NOT IN ('rejected', 'withdrawn') ORDER BY a.updated DESC LIMIT 10""").fetchall()
        if tracked:
            lines.append("Tracked jobs:")
            lines += [f"- {r['title']} at {r['company']}: {r['status']}, {r['score']}% match" + (f", next: {r['next_step']} {r['next_date'] or ''}".rstrip() if r["next_step"] or r["next_date"] else "")
                      for r in tracked]
        best = self.con.execute("""SELECT title, company, score, work_model FROM jobs WHERE active AND NOT hidden AND id NOT IN (SELECT job_id FROM applications)
                                   ORDER BY score DESC LIMIT 5""").fetchall()
        if best:
            lines.append("Best matches not yet saved:")
            lines += [f"- {r['title']} at {r['company']} ({r['work_model']}): {r['score']}%" for r in best]
        return "\n".join(lines)

    def chat_clear(self, d):
        job_id = validate.job_id(d["id"]) if d.get("id") not in (None, "") else None
        return self.run(lambda: (self.con.execute("DELETE FROM chat WHERE job_id IS ?", (job_id,)), self.con.commit(), {"cleared": True})[2])
