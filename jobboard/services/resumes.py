"""Several resumes, one primary.

The profile row always holds the primary resume's text, file name, skills, job titles and headline. The other
resumes wait in the `resumes` table. Making another one primary puts the profile's copy away and brings that one in,
so matching, tailoring and cover letters all use it, and the board shows the roles it is for (`role_sql`).
"""
import datetime as dt
import json
import re
from pathlib import Path

from .. import config
from .. import validation as validate
from ..errors import JobBoardError
from ..rules import focus, text
from ..storage import db
from ..writing import resume
from .base import Service


class ResumeService(Service):
    # The profile columns that belong to a resume (swapped in and out when the primary resume changes).
    RESUME_FIELDS = ("resume_text", "resume_file", "skills", "target_titles", "headline")

    def ensure_ready(self):
        """Once: the resume you already had becomes the first row, for every role. Returns the primary resume's id."""
        active = db.setting(self.con, "active_resume")
        if active and self.con.execute("SELECT 1 FROM resumes WHERE id = ?", (active,)).fetchone():
            return int(active)
        row = self.con.execute("SELECT id FROM resumes ORDER BY id LIMIT 1").fetchone()
        if row:
            rid = row[0]
        else:
            stamp = db.now()
            rid = self.con.execute("INSERT INTO resumes (name, roles, created, updated) VALUES ('My resume', '[]', ?, ?)", (stamp, stamp)).lastrowid
        db.set_setting(self.con, "active_resume", str(rid))
        self.stash(rid)
        self.con.commit()
        return rid

    def stash(self, rid):
        """Copy the profile's resume fields into a resume's row."""
        raw = self.con.execute(f"SELECT {', '.join(self.RESUME_FIELDS)} FROM profile WHERE id = 1").fetchone()
        self.con.execute(f"UPDATE resumes SET {', '.join(f'{k} = ?' for k in self.RESUME_FIELDS)}, updated = ? WHERE id = ?", list(raw) + [db.now(), rid])

    def active_roles(self):
        """The role ids the primary resume is for. Empty means every role."""
        rid = self.ensure_ready()
        roles = db.loads(self.con.execute("SELECT roles FROM resumes WHERE id = ?", (rid,)).fetchone()[0], [])
        return [r for r in roles if r in focus.CATEGORIES]

    def role_sql(self):
        """A WHERE clause that keeps the primary resume's roles (and jobs you added by hand, which have no role)."""
        roles = self.active_roles()
        if not roles or len(roles) == len(focus.CATEGORIES):
            return "1 = 1"
        return "job_role(title) IN ('', " + ", ".join(f"'{r}'" for r in roles) + ")"   # ids come from focus.CATEGORIES, never from a request

    def summaries(self, prof):
        active = self.ensure_ready()
        out = []
        for r in self.con.execute("SELECT * FROM resumes ORDER BY id"):
            mine = r["id"] == active
            src = prof if mine else {"resume_text": r["resume_text"], "resume_file": r["resume_file"], "skills": db.loads(r["skills"], []),
                                     "target_titles": db.loads(r["target_titles"], [])}
            roles = [x for x in db.loads(r["roles"], []) if x in focus.CATEGORIES]
            where = "1 = 1" if not roles else "job_role(title) IN (" + ", ".join(f"'{x}'" for x in roles) + ")"
            out.append({"id": r["id"], "name": r["name"], "roles": roles, "primary": mine, "file": src["resume_file"], "chars": len(src["resume_text"]),
                        "skills": len(src["skills"]), "titles": src["target_titles"],
                        "jobs": self.con.execute(f"SELECT count(*) FROM jobs WHERE active AND NOT hidden AND {where}").fetchone()[0]})
        return out

    @staticmethod
    def _roles_in(value):
        roles = [r for r in validate.str_list(value, 12, 40) if r in focus.CATEGORIES]
        return [r for r in focus.CATEGORIES if r in roles]

    def _row(self, rid):
        row = self.con.execute("SELECT * FROM resumes WHERE id = ?", (validate.number(rid, "resume", 1),)).fetchone()
        if not row:
            raise JobBoardError("That resume isn't here anymore")
        return row

    def _unique_name(self, name, but=None):
        if self.con.execute("SELECT 1 FROM resumes WHERE lower(name) = lower(?) AND id IS NOT ?", (name, but)).fetchone():
            raise JobBoardError(f"You already have a resume called {name}")

    def add(self, d):
        """A new, empty resume for some roles, made primary so the next upload or pasted text goes into it."""
        name = validate.text(d.get("name"), 60, "the resume's name", required=True)
        roles = self._roles_in(d.get("roles"))

        def go():
            self.ensure_ready()
            self._unique_name(name)
            if self.con.execute("SELECT count(*) FROM resumes").fetchone()[0] >= 12:
                raise JobBoardError("That's the most resumes you can keep. Remove one first")
            titles = [focus.CATEGORIES[r]["title"] for r in roles]
            stamp = db.now()
            rid = self.con.execute("INSERT INTO resumes (name, roles, target_titles, created, updated) VALUES (?, ?, ?, ?, ?)",
                                   (name, json.dumps(roles), json.dumps(titles), stamp, stamp)).lastrowid
            self.con.commit()
            return self.make_primary(rid)
        return self.run(go)

    def use(self, d):
        return self.run(lambda: self.make_primary(self._row(d.get("id"))["id"]))

    def make_primary(self, rid):
        """Make a resume the primary one: put the profile's copy away, bring this one in, and score every job against it."""
        active = self.ensure_ready()
        if rid != active:
            self.stash(active)
            row = self._row(rid)
            self.con.execute(f"UPDATE profile SET {', '.join(f'{k} = ?' for k in self.RESUME_FIELDS)}, updated = ? WHERE id = 1",
                             [row[k] for k in self.RESUME_FIELDS] + [db.now()])
            db.set_setting(self.con, "active_resume", str(rid))
            self.con.commit()
            self.app.catalog.rescore_all(open_only=True)
        row = self._row(rid)
        return {"primary": rid, "name": row["name"], "roles": [focus.CATEGORIES[r]["name"] for r in self.active_roles()]}

    def update(self, d):
        """Rename a resume, or change which roles it is for."""
        def go():
            self.ensure_ready()
            row = self._row(d.get("id"))
            fields = {}
            if "name" in d:
                fields["name"] = validate.text(d["name"], 60, "the resume's name", required=True)
                self._unique_name(fields["name"], row["id"])
            if "roles" in d:
                fields["roles"] = json.dumps(self._roles_in(d["roles"]))
            if fields:
                fields["updated"] = db.now()
                self.con.execute(f"UPDATE resumes SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?", list(fields.values()) + [row["id"]])
                self.con.commit()
            return {"updated": row["id"]}
        return self.run(go)

    def remove(self, d):
        def go():
            active = self.ensure_ready()
            row = self._row(d.get("id"))
            if row["id"] == active:
                raise JobBoardError("That's your primary resume. Make another one primary first")
            self.con.execute("DELETE FROM resumes WHERE id = ?", (row["id"],))
            self.con.commit()
            return {"removed": row["id"]}
        return self.run(go)

    def set_text(self, d):
        body = validate.text(d.get("text"), config.MAX_TEXT, "your resume text", required=True)
        return self.run(self._apply, resume.tidy(body), validate.text(d.get("file"), 300, "file name"), d.get("merge_skills", True))

    def set_file(self, d):
        path = d.get("path")
        if not isinstance(path, (str, Path)) or not str(path):
            raise JobBoardError("Pick a resume file")
        try:
            body = resume.read(path)
        except resume.ResumeError as e:
            raise JobBoardError(str(e)[0].upper() + str(e)[1:]) from None
        return self.run(self._apply, body, d.get("name") or Path(path).name, True)

    def _apply(self, body, filename, merge_skills):
        """Save the resume and learn what it can: skills, years, level, a headline. Your own edits win."""
        prof = db.profile(self.con)
        found = text.find_skills(body, prof["skills"])
        skills = list(dict.fromkeys(prof["skills"] + found)) if merge_skills else found
        years = text.resume_years(body, dt.date.today().year)
        fields = {"resume_text": body, "resume_file": filename or "", "skills": json.dumps(skills[:80]), "updated": db.now()}
        if prof["years_exp"] is None and years is not None:
            fields["years_exp"] = years
        if not prof["level"]:
            fields["level"] = text.level_of(body.split("\n", 2)[1] if body.count("\n") >= 1 else "", fields.get("years_exp", prof["years_exp"]))
        lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
        if not prof["name"] and lines and len(lines[0]) <= 60 and not re.search(r"[@\d]", lines[0]):
            fields["name"] = lines[0].title() if lines[0].isupper() else lines[0]
        if not prof["email"]:
            m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", body)
            if m:
                fields["email"] = m.group()
        if not prof["phone"]:
            m = re.search(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", body)
            if m:
                fields["phone"] = m.group()
        if not prof["headline"] and len(lines) > 1 and len(lines[1]) <= 90 and not re.search(r"[@|]|\d{3}", lines[1]):
            fields["headline"] = lines[1]
        self.con.execute(f"UPDATE profile SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = 1", list(fields.values()))
        self.con.commit()
        self.app.catalog.rescore_all()
        out = self.app.profiles.profile_out(db.profile(self.con))
        out["found_skills"] = found
        out["found_years"] = years
        return out
