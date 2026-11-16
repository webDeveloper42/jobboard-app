"""Job boards: adding, switching and removing them, refreshing (fetch, then save through the catalog), and reading a
job's full post when a board only sent a snippet.
"""
import datetime as dt
import json
import re
import sqlite3
import urllib.parse

from .. import boards, config
from .. import validation as validate
from ..boards import fulltext
from ..errors import JobBoardError
from ..rules import focus, match, text, travel
from ..storage import db
from ..writing import resume
from .base import Service


class BoardService(Service):
    def add(self, d):
        kind = validate.text(d.get("kind"), 20, "a board type", required=True)
        if kind in boards.KEYED:
            guessed, slug = None, re.sub(r"\s+", " ", validate.text(d.get("slug"), 200, "what to search for", required=True))
            if not slug.partition("@")[0].strip():
                raise JobBoardError("Say what to search for, like: help desk technician @ Washington, DC")
        else:
            guessed, slug = boards.slug_from(validate.text(d.get("slug"), 200, "the company's board name"))
        kind = guessed or kind
        if kind not in boards.KINDS:
            raise JobBoardError("Pick a board type")
        if kind in ("greenhouse", "lever", "ashby") and not re.fullmatch(r"[\w.-]{1,80}", slug or ""):
            raise JobBoardError("Enter the company's board name, like stripe, or paste its jobs page link")
        if kind == "workday":
            try:
                boards.workday_site(slug)
            except boards.SourceError as e:
                raise JobBoardError(str(e)[0].upper() + str(e)[1:]) from None
        name = validate.text(d.get("name"), 80, "a name") or (f"{kind.title()} · {slug}"[:80] if kind in boards.KEYED else boards.board_label(kind, slug) if kind == "workday" else slug.replace("-", " ").title() if slug else boards.KINDS[kind].split(" (")[0])

        def go():
            try:
                cur = self.con.execute("INSERT INTO sources (kind, slug, name) VALUES (?, ?, ?)", (kind, slug, name))
            except sqlite3.IntegrityError:
                raise JobBoardError("That board is already on your list") from None
            self.con.commit()
            return cur.lastrowid
        source_id = self.run(go)
        result = {"id": source_id}
        if d.get("fetch", True):
            result.update(self.refresh({"source": source_id}))
        return result

    def toggle(self, d):
        sid = validate.number(d.get("id"), "board", blank_ok=False)
        on = 1 if d.get("enabled") in (True, 1, "1", "true") else 0

        def go():
            self.con.execute("UPDATE sources SET enabled = ? WHERE id = ?", (on, sid))
            self.con.commit()
            return {"id": sid, "enabled": on}
        return self.run(go)

    def remove(self, d):
        sid = validate.number(d.get("id"), "board", blank_ok=False)

        def go():
            # Jobs you're tracking stay; the rest of that board's jobs go with it.
            self.con.execute("DELETE FROM jobs WHERE source_id = ? AND id NOT IN (SELECT job_id FROM applications)", (sid,))
            self.con.execute("DELETE FROM sources WHERE id = ?", (sid,))
            self.con.commit()
            return {"removed": sid}
        return self.run(go)

    def refresh(self, d=None):
        """Fetch every enabled board (or one), save what changed, and score it. Boards that fail don't stop the others."""
        d = d or {}
        one = validate.number(d.get("source"), "board") if d.get("source") not in (None, "") else None
        wanted = self.run(lambda: [dict(r) for r in self.con.execute(
            "SELECT * FROM sources WHERE " + ("id = ?" if one else "enabled = 1 AND kind != 'manual'"), (one,) if one else ())])
        report = []
        keys = self.run(lambda: {"google": self.app.settings.google_key(), "jooble": self.app.settings.jooble_key()})
        if not keys["google"] and any(s["kind"] == "google" for s in wanted):
            report.append({"source": "Google Jobs", "error": "add your SerpApi key under Job boards to search Google Jobs"})
            wanted = [s for s in wanted if s["kind"] != "google"]
        if not keys["jooble"] and any(s["kind"] == "jooble" for s in wanted):
            report.append({"source": "Jooble", "error": "add your Jooble API key under Job boards (or: jobboard jooble-key YOUR_KEY)"})
            wanted = [s for s in wanted if s["kind"] != "jooble"]
        for src in wanted:
            started = dt.datetime.now().isoformat(timespec="microseconds")  # fine-grained, so a quick second refresh still closes old jobs
            try:
                found = boards.fetch(src["kind"], src["slug"], keys.get(src["kind"]))
            except boards.SourceError as e:
                self.run(self.app.catalog.record_source_result, src["id"], None, str(e))
                report.append({"source": src["name"], "error": str(e)})
                continue
            self._prepare(src, found)
            added, updated, kept, scams, merged = self.run(self.app.catalog.store_jobs, src, found, started)
            report.append({"source": src["name"], "found": kept, "new": added, "updated": updated, "left_out": len(found) - kept,
                           "scams": scams, "merged": merged})
        self.run(lambda: (self.app.catalog.close_off_focus(), self.app.catalog.fold_aggregators(), db.set_setting(self.con, "last_refresh", db.now()), self.con.commit()))
        return {"report": report, "new": sum(r.get("new", 0) for r in report)}

    def _prepare(self, src, found):
        """Network work done before saving, outside the database thread: the whole post for boards that send only a
        snippet, and the map position of addresses not looked up before (for travel times)."""
        likely = [j for j in found if j.get("title") and focus.category(j.get("title"))] if self.app.focus else []
        if src["kind"] == "jooble":
            done = self.run(lambda: {r[0] for r in self.con.execute("SELECT key FROM jobs WHERE full_text = 1")})
            for j in [j for j in likely if j.get("key") not in done][:fulltext.PER_REFRESH]:
                full = fulltext.fetch(j.get("url"))
                if len(full) > len(j.get("description") or ""):
                    j["description"] = full
                j["full_text"] = 1
        wanted = {q for q in (travel.address_query(j.get("location")) for j in likely) if q}
        if wanted:
            known = self.run(lambda: {r[0] for r in self.con.execute(
                f"SELECT query FROM geo WHERE query IN ({','.join('?' * len(wanted))})", list(wanted))})
            new = travel.lookup_all(sorted(wanted - known))
            if new:
                stamp = db.now()
                self.run(lambda: (self.con.executemany("INSERT OR REPLACE INTO geo (query, lat, lon, at) VALUES (?, ?, ?, ?)",
                                                        [(q, (p or (None, None))[0], (p or (None, None))[1], stamp) for q, p in new.items()]),
                                   self.con.commit()))

    def full_post(self, d):
        """The whole description for one job that only has a snippet (Jooble sends a few lines). The job's own links are
        read first; when none can be (Jooble's pages block scripts), the same job is looked up on Google Jobs, which
        costs one SerpApi search. Returns {'found', 'via', 'chars'} or {'found': False, 'why'}."""
        job_id = validate.job_id(d.get("id"))
        use_google = d.get("google", True) not in (False, 0, "0", "false")
        j = self.run(self.app.feed.job_detail, job_id)
        have = len(j.get("description") or "")
        best, via, extra = "", "", None
        urls = list(dict.fromkeys(u for u in [j.get("apply_url"), j.get("url")] + [x.get("url") for x in j.get("links") or []] if u))
        for url in urls:
            if (urllib.parse.urlsplit(url).hostname or "").lower().endswith("jooble.org"):
                continue
            got = fulltext.fetch(url)
            if len(got) > len(best):
                best, via = got, "the employer's page"
        why = "Its page can't be read from here. Use Original post to read it there."
        if len(best) < have + 200 and use_google:
            key = self.run(self.app.settings.google_key)
            if not key:
                why = "Its page can't be read from here, and looking it up on Google Jobs needs your SerpApi key (Job boards)."
            else:
                try:
                    hits = boards.google_lookup(j["title"], j["company"], j.get("location") or "", key)
                except boards.SourceError as e:
                    raise JobBoardError(str(e)) from None
                same = [h for h in hits if focus.company_key(h[1]) == focus.company_key(j["company"])
                        and text.title_similarity(h[0], j["title"]) >= 0.8 and text.title_similarity(j["title"], h[0]) >= 0.8]
                if same:
                    hit = max(same, key=lambda h: len(h[2]))
                    if len(hit[2]) > len(best):
                        best, via, extra = resume.tidy(hit[2]), "Google Jobs", hit[3]
                else:
                    why = "Google Jobs doesn't list this job (same title and company), so only the snippet is known. Use Original post to read it there."
        if len(best) < have + 200:
            self.run(lambda: (self.con.execute("UPDATE jobs SET full_text = 1 WHERE id = ?", (job_id,)), self.con.commit()))   # tried
            return {"found": False, "why": why}

        def go():
            row = self.con.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                raise JobBoardError("That job isn't here anymore")
            job = db.job_row(row)
            job["description"] = best[:config.MAX_TEXT]
            match.enrich_skills(job)
            links = list(job.get("links") or [])
            if extra and not focus.blocked(extra) and extra not in {x.get("url") for x in links}:
                links.append({"via": "Google Jobs", "url": extra})
            value, detail = match.score(job, db.profile(self.con))
            self.con.execute("""UPDATE jobs SET description = ?, skills = ?, years_min = ?, links = ?, full_text = 1, score = ?, score_detail = ?,
                                scored_at = ? WHERE id = ?""", (job["description"], json.dumps(job["skills"]), job["years_min"], json.dumps(links[:12]),
                                                              value, json.dumps(detail), db.now(), job_id))
            self.con.commit()
            return {"found": True, "via": via, "chars": len(job["description"])}
        return self.run(go)
