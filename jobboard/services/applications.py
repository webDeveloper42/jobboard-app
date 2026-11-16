"""Your applications: saving, statuses, notes, hiding jobs, adding a job by hand, CSV export, and the row in your
Gridnook/Sheets job sheet.
"""
import json
import re

from .. import config
from .. import validation as validate
from ..errors import JobBoardError
from ..links import sheets
from ..rules import focus, match
from ..storage import db
from ..writing import resume
from .base import Service


class ApplicationService(Service):
    def add_job(self, d):
        """A job from anywhere else: paste the title, company, link and description."""
        title = validate.text(d.get("title"), 200, "the job title", required=True)
        company = validate.text(d.get("company"), 120, "the company", required=True)
        url = validate.text(d.get("url"), 1000, "the link")
        if url and not re.match(r"https?://", url):
            raise JobBoardError("The link should start with http:// or https://")
        raw = {"title": title, "company": company, "location": validate.text(d.get("location"), 160, "the location"), "url": url, "apply_url": url,
               "description": resume.tidy(validate.text(d.get("description"), config.MAX_TEXT, "the description")), "salary_text": validate.text(d.get("salary"), 120, "the pay"),
               "posted": db.today()}

        def go():
            src = self.con.execute("SELECT id FROM sources WHERE kind = 'manual'").fetchone()
            sid = src[0] if src else self.con.execute("INSERT INTO sources (kind, slug, name, enabled) VALUES ('manual', '', 'Added by you', 0)").lastrowid
            job = match.enrich(dict(raw))
            value, detail = match.score(job, db.profile(self.con))
            stamp = db.now()
            cur = self.con.execute("""INSERT INTO jobs (key, source_id, title, company, location, work_model, url, apply_url, description, salary_min, salary_max,
                                      salary_text, level, years_min, skills, sponsorship, posted, first_seen, last_seen, score, score_detail, scored_at)
                                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                   (f"manual::{stamp}:{title}:{company}", sid, job["title"], job["company"], job["location"], job["work_model"], job["url"],
                                    job["apply_url"], job["description"], job["salary_min"], job["salary_max"], job["salary_text"], job["level"],
                                    job["years_min"], json.dumps(job["skills"]), job["sponsorship"], job["posted"], stamp, stamp, value, json.dumps(detail), stamp))
            job_id = cur.lastrowid
            self.track(job_id, d.get("status") or "saved")
            self.con.commit()
            return {"id": job_id, "score": value}
        return self.run(go)

    def hide(self, job_id, flag):
        self.con.execute("UPDATE jobs SET hidden = ? WHERE id = ?", (flag, job_id))
        self.con.commit()
        return {"id": job_id, "hidden": flag}

    def track(self, job_id, status):
        if status not in db.STATUSES:
            raise JobBoardError("Pick a status")
        if not self.con.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone():
            raise JobBoardError("That job isn't here anymore")
        stamp = db.now()
        old = self.con.execute("SELECT status FROM applications WHERE job_id = ?", (job_id,)).fetchone()
        applied = stamp if status != "saved" else None
        if old is None:
            self.con.execute("INSERT INTO applications (job_id, status, saved_at, applied_at, updated) VALUES (?, ?, ?, ?, ?)",
                             (job_id, status, stamp, applied, stamp))
            db.log_event(self.con, job_id, status)
        elif old[0] != status:
            self.con.execute("UPDATE applications SET status = ?, updated = ?, applied_at = coalesce(applied_at, ?) WHERE job_id = ?",
                             (status, stamp, applied, job_id))
            db.log_event(self.con, job_id, status, f"from {old[0]}")
        out = {"id": job_id, "status": status}
        if (old is None or old[0] != status) and status in sheets.PROGRESS:
            out.update(self._to_sheet(job_id, status))
        return out

    def _to_sheet(self, job_id, status):
        """Write the application to its job sheet in the Sheets tab. A problem there never stops the tracker."""
        if self.app.sheets is None or db.setting(self.con, "sheets_sync", "on") == "off":
            return {}
        row = self.con.execute("SELECT j.*, s.kind FROM jobs j LEFT JOIN sources s ON s.id = j.source_id WHERE j.id = ?", (job_id,)).fetchone()
        try:
            done = sheets.record(dict(row), db.profile(self.con), status, row["kind"], self.app.sheets or None)
        except Exception as e:  # noqa: BLE001 - the sheet is a copy; the tracker is what counts
            db.log_event(self.con, job_id, "sheet", f"couldn't update the sheet: {e}")
            return {"sheet_error": f"Saved here, but the {sheets.book_for(focus.category(row['title']))} sheet wasn't updated: {e}"}
        if not done:
            return {}
        verb = {"added": "Added to", "updated": "Updated in", "unchanged": "Already in"}[done["action"]]
        db.log_event(self.con, job_id, "sheet", f"{verb} {done['book']} row {done['row']}")
        msg = f"{verb} your {done['book']} sheet (row {done['row']})" + (" — a new sheet laid out like your others" if done.get("created") else "")
        return {"sheet": msg}

    def save(self, d):
        job_id = validate.job_id(d.get("id"))

        def go():
            out = self.track(job_id, "saved") if not self.con.execute("SELECT 1 FROM applications WHERE job_id = ?", (job_id,)).fetchone() else {"id": job_id}
            self.con.commit()
            return out
        return self.run(go)

    def set_status(self, d):
        job_id, status = validate.job_id(d.get("id")), d.get("status")

        def go():
            out = self.track(job_id, status)
            self.con.commit()
            return out
        return self.run(go)

    def update(self, d):
        job_id = validate.job_id(d.get("id"))
        fields = {}
        if "next_step" in d:
            fields["next_step"] = validate.text(d["next_step"], 300, "the next step")
        if "next_date" in d:
            fields["next_date"] = validate.day(d["next_date"], "The date")
        if "notes" in d:
            fields["notes"] = validate.text(d["notes"], 20000, "notes")
        if "contact" in d:
            fields["contact"] = validate.text(d["contact"], 300, "a contact")
        if "salary_offer" in d:
            fields["salary_offer"] = validate.number(d["salary_offer"], "the offer", 0, 10_000_000)

        def go():
            if not self.con.execute("SELECT 1 FROM applications WHERE job_id = ?", (job_id,)).fetchone():
                self.track(job_id, d.get("status") or "saved")
            if fields:
                fields["updated"] = db.now()
                self.con.execute(f"UPDATE applications SET {', '.join(f'{k} = ?' for k in fields)} WHERE job_id = ?", list(fields.values()) + [job_id])
                if "next_step" in fields or "next_date" in fields:
                    db.log_event(self.con, job_id, "next step", " ".join(x for x in (fields.get("next_step"), fields.get("next_date")) if x))
            self.con.commit()
            return dict(self.con.execute("SELECT * FROM applications WHERE job_id = ?", (job_id,)).fetchone())
        return self.run(go)

    def untrack(self, d):
        job_id = validate.job_id(d.get("id"))

        def go():
            self.con.execute("DELETE FROM applications WHERE job_id = ?", (job_id,))
            db.log_event(self.con, job_id, "untracked")
            self.con.commit()
            return {"id": job_id}
        return self.run(go)

    def export_csv(self):
        import csv
        import io

        def go():
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["status", "title", "company", "location", "match", "salary_min", "salary_max", "saved", "applied", "next_step", "next_date", "url", "notes"])
            for r in self.con.execute("""SELECT a.status, j.title, j.company, j.location, j.score, j.salary_min, j.salary_max, a.saved_at, a.applied_at,
                                         a.next_step, a.next_date, coalesce(nullif(j.apply_url, ''), j.url), a.notes
                                         FROM applications a JOIN jobs j ON j.id = a.job_id ORDER BY a.updated DESC"""):
                w.writerow(list(r))
            return buf.getvalue().encode()
        return self.run(go)

    def set_hidden(self, d, hidden):
        """Hide a job from your matches (Not interested), or bring it back."""
        return self.run(self.hide, validate.job_id(d.get("id")), 1 if hidden else 0)
