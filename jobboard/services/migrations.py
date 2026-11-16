"""One-time changes to your saved data, run when the database opens.

Each step runs once: it checks a flag in the settings table, does its work, then sets the flag. To add a step,
add a block at the end of `upgrade` with a new flag name (like "something_v1") and say in a comment why and when.
"""
import json

from ..rules import focus, match, text
from ..storage import db
from .base import Service


class Migrations(Service):
    def upgrade(self):
        """Once per change in the rules: close scams already on the board, and rescore so resume keywords are
        read again (PDF text with words split apart used to hide them)."""
        if not db.setting(self.con, "jooble_v1"):
            # Jooble searches for the board's roles and places, added once. Switch off or remove any you don't want.
            self.con.executemany("INSERT OR IGNORE INTO sources (kind, slug, name, enabled) VALUES ('jooble', ?, ?, 1)", focus.JOOBLE_SEARCHES)
            db.set_setting(self.con, "jooble_v1", db.now())
            self.con.commit()
        if not db.setting(self.con, "workday_v1"):
            # Big DC employers' own career sites (GDIT, Leidos, CACI, Target), read straight from Workday.
            self.con.executemany("INSERT OR IGNORE INTO sources (kind, slug, name, enabled) VALUES ('workday', ?, ?, 1)", focus.WORKDAY_SEARCHES)
            db.set_setting(self.con, "workday_v1", db.now())
            self.con.commit()
        if not db.setting(self.con, "dedupe_v1"):
            self.app.catalog.fingerprint_all()
            db.set_setting(self.con, "dedupe_v1", db.now())
            self.con.commit()
            self.app.catalog.rescore_all()
        if not db.setting(self.con, "travel_v2"):
            # Travel times worked out again with the newer Metro estimate.
            for r in self.con.execute("SELECT id, location FROM jobs WHERE travel != '{}'").fetchall():
                self.con.execute("UPDATE jobs SET travel = ? WHERE id = ?", (json.dumps(self.app.catalog.travel_for(r["location"])), r["id"]))
            db.set_setting(self.con, "travel_v2", db.now())
            self.con.commit()
            self.app.catalog.rescore_all()
        if not db.setting(self.con, "dedupe_v2"):
            self.app.catalog.fingerprint_all()   # street address and city now count as the same place
            db.set_setting(self.con, "dedupe_v2", db.now())
            self.con.commit()
        if not db.setting(self.con, "titles_v2"):
            db.set_setting(self.con, "titles_v2", db.now())   # stocking titles ("Inbound (Stocking)") now match "Stocker"
            self.con.commit()
            self.app.catalog.rescore_all()
        if not db.setting(self.con, "jobicy_v1"):
            # Jobicy's support jobs (customer and technical support), remote in the US. Free and needs no key.
            self.con.execute("INSERT OR IGNORE INTO sources (kind, slug, name, enabled) VALUES ('jobicy', 'supporting', 'Jobicy · support · remote', 1)")
            db.set_setting(self.con, "jobicy_v1", db.now())
            self.con.commit()
        if not db.setting(self.con, "scam_v1"):
            self.app.catalog.close_off_focus()
            db.set_setting(self.con, "scam_v1", db.now())
            self.con.commit()
            self.app.catalog.rescore_all()
        if not db.setting(self.con, "quality_v1"):
            # 2026-11-13: entry-level titles read as entry level, data entry scam checks, remote jobs limited to other
            # states, and job-site reposts folded into the employer's own post.
            for r in self.con.execute("SELECT id, title, years_min FROM jobs").fetchall():
                self.con.execute("UPDATE jobs SET level = ? WHERE id = ?", (text.level_of(r["title"], r["years_min"]), r["id"]))
            self.app.catalog.close_off_focus()
            self.app.catalog.fold_aggregators()
            db.set_setting(self.con, "quality_v1", db.now())
            self.con.commit()
            self.app.catalog.rescore_all()
        if not db.setting(self.con, "skills_v2"):
            # 2026-11-13: clerical skills (data entry, typing, 10-key, records…) are recognised now. Read every resume
            # again and add any of them it mentions (nothing is removed), read every job's skills again, and rescore.
            prof = db.profile(self.con)
            found = text.find_skills(prof["resume_text"], prof["skills"]) if prof["resume_text"] else []
            new = [s for s in found if s.lower() not in {x.lower() for x in prof["skills"]}]
            if new:
                self.con.execute("UPDATE profile SET skills = ? WHERE id = 1", (json.dumps((prof["skills"] + new)[:80]),))
            for r in self.con.execute("SELECT id, resume_text, skills FROM resumes WHERE resume_text != ''").fetchall():
                have = db.loads(r["skills"], [])
                more = [s for s in text.find_skills(r["resume_text"], have) if s.lower() not in {x.lower() for x in have}]
                if more:
                    self.con.execute("UPDATE resumes SET skills = ? WHERE id = ?", (json.dumps((have + more)[:80]), r["id"]))
            for r in self.con.execute("SELECT id, title, description FROM jobs").fetchall():
                job = match.enrich_skills({"title": r["title"], "description": r["description"]})
                self.con.execute("UPDATE jobs SET skills = ?, years_min = ? WHERE id = ?", (json.dumps(job["skills"]), job["years_min"], r["id"]))
            self.app.resumes.stash(self.app.resumes.ensure_ready())   # keep the primary resume's row in step with the profile
            db.set_setting(self.con, "skills_v2", db.now())
            self.con.commit()
            self.app.catalog.rescore_all()
        if not db.setting(self.con, "roles_v2"):
            # 2026-11-13: stocking is no longer one of the board's roles, and data entry (remote or DC) is. The stocking
            # searches the board came with are taken off (ones you added yourself stay), the data entry ones added, and
            # open jobs that no longer fit are closed. Jobs you track are kept.
            self.con.executemany("DELETE FROM sources WHERE kind = ? AND slug = ?", focus.RETIRED_SEARCHES)
            for kind, searches in (("google", focus.GOOGLE_SEARCHES), ("jooble", focus.JOOBLE_SEARCHES)):
                self.con.executemany(f"INSERT OR IGNORE INTO sources (kind, slug, name, enabled) VALUES ('{kind}', ?, ?, 1)",
                                     [s for s in searches if "data entry" in s[0]])
            prof = db.profile(self.con)
            if "Stocker" in prof["target_titles"]:
                titles = [t for t in prof["target_titles"] if t != "Stocker"]
                self.con.execute("UPDATE profile SET target_titles = ? WHERE id = 1",
                                 (json.dumps(titles + [t for t in ("Data Entry Clerk",) if t not in titles]),))
            self.app.catalog.close_off_focus()
            db.set_setting(self.con, "roles_v2", db.now())
            self.con.commit()
            self.app.catalog.rescore_all()

    def focus_setup(self):
        """Once: add the Google Jobs searches, switch off the Europe board, aim the profile at these roles, and close
        jobs already saved that aren't one of them. Anything you change afterwards is left alone."""
        if db.setting(self.con, "focus_v1"):
            return
        self.con.executemany("INSERT OR IGNORE INTO sources (kind, slug, name, enabled) VALUES ('google', ?, ?, 1)", focus.GOOGLE_SEARCHES)
        self.con.execute("UPDATE sources SET enabled = 0 WHERE kind = 'arbeitnow'")
        prof = db.profile(self.con)
        if not prof["target_titles"]:
            self.con.execute("UPDATE profile SET target_titles = ? WHERE id = 1", (json.dumps(["IT Technician", "Help Desk Technician", "IT Intern", "Data Entry Clerk"]),))
        if not prof["locations"]:
            self.con.execute("UPDATE profile SET locations = ? WHERE id = 1", (json.dumps(["Washington, DC", "Remote"]),))
        self.app.catalog.close_off_focus()
        db.set_setting(self.con, "focus_v1", db.now())
        self.con.commit()
        self.app.catalog.rescore_all()
