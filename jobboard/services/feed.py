"""What the page reads: the job list with its filters, counts and insights, one job in full, and chat history.
"""
import datetime as dt
from collections import Counter

from .. import boards, config
from .. import validation as validate
from ..errors import JobBoardError
from ..rules import focus, match, text
from ..storage import db
from .base import Service


class FeedService(Service):
    def visible_sql(self):
        """A WHERE clause for the jobs you should see: the primary resume's roles, minus your hide rules.
        Runs on the database thread (it loads the hide rules the SQL function reads)."""
        self.app.settings.hide_rules()
        return f"{self.app.resumes.role_sql()} AND NOT hidden_by_rule(company, title, description)"

    def applied_companies(self):
        """Company keys you've applied to (any status past Saved), for the "applied here before" warning."""
        return {r[0] for r in self.con.execute("""SELECT DISTINCT company_key(j.company) FROM applications a JOIN jobs j ON j.id = a.job_id
                                                  WHERE a.status != 'saved'""")}

    def profile(self):
        return self.run(lambda: db.profile(self.con))

    def state(self, filters=None):
        return self.run(self._state, filters or {})

    def _state(self, f):
        con = self.con
        prof = db.profile(con)
        tracked = {r["job_id"]: r["status"] for r in con.execute("SELECT job_id, status FROM applications")}
        jobs, total = self._feed(f, tracked)
        board = {s: [] for s in db.STATUSES}
        for r in con.execute("""SELECT a.*, j.title, j.company, j.location, j.score, j.work_model, j.salary_min, j.salary_max, j.url, j.apply_url
                                FROM applications a JOIN jobs j ON j.id = a.job_id ORDER BY a.updated DESC"""):
            board.setdefault(r["status"], []).append(dict(r))
        srcs = [dict(r) for r in con.execute("""SELECT s.*, (SELECT count(*) FROM jobs j WHERE j.source_id = s.id AND j.active) jobs
                                                 FROM sources s ORDER BY s.kind IN ('remotive','remoteok','arbeitnow'), s.name""")]
        return {
            "profile": self.app.profiles.profile_out(prof),
            "resumes": self.app.resumes.summaries(prof),
            "jobs": jobs, "total": total,
            "board": board, "statuses": [{"id": s, "name": db.STATUS_NAMES[s]} for s in db.STATUSES],
            "sources": srcs, "kinds": boards.KINDS,
            "suggested": [{"kind": k, "slug": s, "name": n} for k, s, n in boards.SUGGESTED if (k, s) not in {(x["kind"], x["slug"]) for x in srcs}],
            "counts": {"active": con.execute(f"SELECT count(*) FROM jobs WHERE active AND NOT hidden AND {self.visible_sql()}").fetchone()[0],
                       "strong": con.execute(f"SELECT count(*) FROM jobs WHERE active AND NOT hidden AND score >= 80 AND {self.visible_sql()}").fetchone()[0],
                       "new": con.execute(f"SELECT count(*) FROM jobs WHERE active AND NOT hidden AND first_seen >= ? AND {self.visible_sql()}", ((dt.datetime.now() - dt.timedelta(days=1)).isoformat(),)).fetchone()[0],
                       "hidden": con.execute(f"SELECT count(*) FROM jobs WHERE hidden AND active AND {self.visible_sql()}").fetchone()[0],
                       "by_rule": con.execute(f"SELECT count(*) FROM jobs WHERE active AND NOT hidden AND {self.app.resumes.role_sql()} AND hidden_by_rule(company, title, description)").fetchone()[0]},
            "hide_rules": self.app.settings.hide_rules(),
            "insights": self.insights(prof),
            "last_refresh": db.setting(con, "last_refresh"),
            "daily": db.loads(db.setting(con, "daily_summary"), {}),
            "sheets_sync": db.setting(con, "sheets_sync", "on") != "off",
            "focus": focus.describe(), "google_key": bool(self.app.settings.google_key()),
            "jooble_key": bool(self.app.settings.jooble_key()),
            "levels": [{"id": k, "name": v} for k, v in text.LEVEL_NAMES.items()],
        }

    def _feed(self, f, tracked):
        where, args = ["active = 1", self.visible_sql()], []
        view = f.get("view") or "recommended"
        if view == "hidden":
            where.append("hidden = 1")
        else:
            where.append("hidden = 0")
        if view == "recommended" and str(f.get("show_tracked", "")) not in ("1", "true", "True"):
            where.append("id NOT IN (SELECT job_id FROM applications)")
        q = (f.get("q") or "").strip()
        if q:
            for word in q.split()[:6]:
                where.append("(title LIKE ? OR company LIKE ? OR location LIKE ? OR skills LIKE ?)")
                args += [f"%{word}%"] * 4
        if f.get("min_score") not in (None, "", "0"):
            where.append("coalesce(score, 0) >= ?")
            args.append(validate.number(f["min_score"], "minimum match", 0, 100))
        models = [m for m in str(f.get("work_model") or "").split(",") if m in db.WORK_MODELS]
        if models:
            where.append(f"work_model IN ({','.join('?' * len(models))})")
            args += models
        levels = [lv for lv in str(f.get("level") or "").split(",") if lv in text.LEVELS]
        if levels:
            where.append(f"level IN ({','.join('?' * len(levels))})")
            args += levels
        if f.get("days") not in (None, "", "0"):
            days = validate.number(f["days"], "days", 1, 3650)
            where.append("coalesce(posted, substr(first_seen, 1, 10)) >= ?")
            args.append((dt.date.today() - dt.timedelta(days=days)).isoformat())
        if str(f.get("salary")) in ("1", "true"):
            where.append("salary_max IS NOT NULL")
        if f.get("min_pay") not in (None, ""):
            where.append("coalesce(salary_max, salary_min) >= ?")
            args.append(validate.number(f["min_pay"], "minimum pay", 0))
        if str(f.get("no_clearance")) in ("1", "true"):
            # Leave out jobs that need a clearance you'd already have to hold. Ones you'd get on the job stay.
            where.append("coalesce(json_extract(score_detail, '$.clearance'), '') != 'active'")
        if f.get("max_commute") not in (None, "", "0"):
            # On-site and hybrid jobs farther than this by Metro/bus. Remote jobs, and ones with no address to measure, stay.
            where.append("(work_model = 'remote' OR json_extract(travel, '$.transit') IS NULL OR json_extract(travel, '$.transit') <= ?)")
            args.append(validate.number(f["max_commute"], "longest commute", 5, 300))
        if str(f.get("sponsor")) in ("1", "true"):
            where.append("sponsorship != 'no'")
        if f.get("source") not in (None, ""):
            where.append("source_id = ?")
            args.append(validate.number(f["source"], "board"))
        order = {"recent": "coalesce(posted, first_seen) DESC, score DESC", "salary": "coalesce(salary_max, salary_min, 0) DESC, score DESC",
                 "company": "company COLLATE NOCASE, score DESC"}.get(f.get("sort"), "coalesce(score, -1) DESC, coalesce(posted, first_seen) DESC")
        sql = " AND ".join(where)
        total = self.con.execute(f"SELECT count(*) FROM jobs WHERE {sql}", args).fetchone()[0]
        offset = validate.number(f.get("offset") or 0, "page", 0) or 0
        rows = self.con.execute(f"""SELECT id, title, company, location, work_model, employment_type, salary_min, salary_max, salary_text,
                                        level, years_min, skills, sponsorship, posted, first_seen, score, score_detail, url, apply_url, hidden,
                                        links, travel, reposts
                                    FROM jobs WHERE {sql} ORDER BY {order} LIMIT ? OFFSET ?""", args + [config.PAGE_SIZE, offset]).fetchall()
        out = []
        applied_to = self.applied_companies()
        for r in rows:
            j = db.job_row(r)
            d = j.pop("score_detail")
            j["label"] = d.get("label", "")
            j["matched"] = d.get("matched", [])[:5]
            j["missing"] = d.get("missing", [])[:3]
            j["flags"] = d.get("flags", [])
            j["skills"] = j["skills"][:6]
            j["status"] = tracked.get(j["id"])
            cat = focus.category(j["title"])
            j["role"] = focus.CATEGORIES[cat]["name"] if cat else ""
            j["applied_company"] = not j["status"] and focus.company_key(j["company"]) in applied_to
            out.append(j)
        return out, total

    def insights(self, prof):
        con = self.con
        counts = dict(con.execute("SELECT status, count(*) FROM applications GROUP BY status").fetchall())
        applied = sum(counts.get(s, 0) for s in ("applied", "interviewing", "offer", "rejected"))
        heard = sum(counts.get(s, 0) for s in ("interviewing", "offer"))
        week = (dt.datetime.now() - dt.timedelta(days=7)).isoformat()
        this_week = con.execute("SELECT count(*) FROM applications WHERE applied_at >= ?", (week,)).fetchone()[0]
        gaps = Counter()
        for (detail,) in con.execute(f"SELECT score_detail FROM jobs WHERE active AND NOT hidden AND score >= 55 AND {self.visible_sql()} ORDER BY score DESC LIMIT 80"):
            for s in db.loads(detail, {}).get("missing", []):
                gaps[s] += 1
        due = [dict(r) for r in con.execute("""SELECT a.job_id, a.next_step, a.next_date, j.title, j.company FROM applications a JOIN jobs j ON j.id = a.job_id
                                               WHERE a.next_date IS NOT NULL AND a.status NOT IN ('rejected','withdrawn') ORDER BY a.next_date LIMIT 8""")]
        return {"applied": applied, "this_week": this_week, "responses": heard,
                "response_rate": round(100 * heard / applied) if applied else None,
                "skill_gaps": [{"skill": s, "jobs": n} for s, n in gaps.most_common(8)], "due": due,
                "by_status": counts}

    def job(self, job_id):
        return self.run(self.job_detail, validate.job_id(job_id))

    def job_detail(self, job_id):
        row = self.con.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise JobBoardError("That job isn't here anymore")
        j = db.job_row(row)
        prof = db.profile(self.con)
        app = self.con.execute("SELECT * FROM applications WHERE job_id = ?", (job_id,)).fetchone()
        j["application"] = dict(app) if app else None
        j["events"] = [dict(r) for r in self.con.execute("SELECT at, kind, detail FROM app_events WHERE job_id = ? ORDER BY at DESC, id DESC", (job_id,))]
        j["documents"] = [dict(r) for r in self.con.execute("SELECT id, kind, body, model, created FROM documents WHERE job_id = ? ORDER BY created DESC, id DESC", (job_id,))]
        j["chat"] = [dict(r) for r in self.con.execute("SELECT role, content, at FROM chat WHERE job_id = ? ORDER BY id", (job_id,))]
        j["coverage"] = match.keyword_coverage(j, prof["resume_text"])
        j["level_name"] = text.LEVEL_NAMES.get(j["level"], j["level"])
        src = self.con.execute("SELECT kind, name FROM sources WHERE id = ?", (j["source_id"],)).fetchone() if j["source_id"] else None
        j["source"] = dict(src) if src else {"kind": "manual", "name": "Added by you"}
        # Your other applications at the same company, so you don't apply twice to one job posted under two titles.
        j["same_company"] = [dict(r) for r in self.con.execute(
            """SELECT a.job_id, j.title, a.status, coalesce(a.applied_at, a.saved_at) AS at FROM applications a JOIN jobs j ON j.id = a.job_id
               WHERE company_key(j.company) = company_key(?) AND a.job_id != ? ORDER BY at DESC""", (j["company"], job_id))]
        return j

    def chat_history(self, job_id=None):
        return self.run(lambda: [dict(r) for r in self.con.execute(
            "SELECT role, content, at FROM chat WHERE job_id IS ? ORDER BY id", (job_id,))])
