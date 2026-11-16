"""The jobs on your board: saving fetched jobs, merging copies of one job, closing ones that no longer fit,
and scoring every job against your profile.

Methods here run on the database thread (they're called from inside `self.run`).
"""
import datetime as dt
import json

from .. import boards, config
from ..rules import focus, match, travel
from ..storage import db
from .base import Service


class JobCatalog(Service):
    def fingerprint_all(self):
        """Give every saved job its fingerprint, and fold open copies of the same job into one, keeping its links.
        A copy you're tracking is the one kept."""
        tracked = {r[0] for r in self.con.execute("SELECT job_id FROM applications")}
        groups = {}
        for r in self.con.execute("SELECT j.*, s.kind, s.slug FROM jobs j LEFT JOIN sources s ON s.id = j.source_id ORDER BY j.id"):
            fp = focus.fingerprint(dict(r))
            links = db.loads(r["links"], []) or [{"via": boards.board_label(r["kind"] or "manual", r["slug"] or ""), "url": r["url"]}]
            self.con.execute("UPDATE jobs SET fingerprint = ?, links = ? WHERE id = ?", (fp, json.dumps(links), r["id"]))
            if r["active"]:
                bucket = groups.setdefault(focus.same_job_prefix(fp), [])
                home = next((g for g in bucket if focus.same_place(g[0], fp)), None)
                if home is None:
                    home = [fp, []]
                    bucket.append(home)
                # A copy with a street address is preferred, for travel times.
                home[1].append((r["id"] in tracked, "@" not in fp.rsplit("|", 1)[-1], -len(r["description"] or ""), r["id"], links))
        for copies in [c for bucket in groups.values() for _, c in bucket]:
            if len(copies) < 2:
                continue
            copies.sort(key=lambda c: (not c[0], c[1], c[2], c[3]))   # tracked first, then one with an address, then the fullest post
            keep, rest = copies[0], copies[1:]
            links = list(keep[4])
            for c in rest:
                links += [link for link in c[4] if link.get("url") not in {x.get("url") for x in links}]
                if not c[0]:
                    self.con.execute("UPDATE jobs SET active = 0 WHERE id = ?", (c[3],))
            self.con.execute("UPDATE jobs SET links = ? WHERE id = ?", (json.dumps(links[:12]), keep[3]))

    def close_off_focus(self):
        """Close every untracked job that isn't one of the board's roles in its places, links to jobleads.com or looks like a scam."""
        if not self.app.focus:
            return 0
        tracked = {r[0] for r in self.con.execute("SELECT job_id FROM applications")}
        off = [r["id"] for r in self.con.execute("""SELECT id, key, title, company, location, work_model, url, apply_url, description,
                                                           salary_min, salary_max FROM jobs WHERE active = 1""")
               if r["id"] not in tracked and focus.check(dict(r))[0] is None]
        self.con.executemany("UPDATE jobs SET active = 0 WHERE id = ?", [(i,) for i in off])
        return len(off)

    def fold_aggregators(self):
        """A job site's repost of a job the employer also lists here is folded into the employer's post: its link is kept
        there and the repost is closed. Ones you track stay. Returns how many were folded."""
        tracked = {r[0] for r in self.con.execute("SELECT job_id FROM applications")}
        rows = [r for r in self.con.execute("SELECT id, company, fingerprint, links, url FROM jobs WHERE active = 1 AND fingerprint != ''")]
        real = {}
        for r in rows:
            if not focus.aggregator(r["company"]):
                real.setdefault(r["fingerprint"].split("|", 1)[0], []).append(r)
        folded = 0
        for r in rows:
            if r["id"] in tracked or not focus.aggregator(r["company"]):
                continue
            home = next((x for x in real.get(r["fingerprint"].split("|", 1)[0], []) if focus.same_place(x["fingerprint"], r["fingerprint"])), None)
            if not home:
                continue
            links = db.loads(home["links"], []) or [{"via": "", "url": home["url"]}]
            for link in db.loads(r["links"], []) or [{"via": r["company"], "url": r["url"]}]:
                if link.get("url") and link["url"] not in {x.get("url") for x in links}:
                    links.append({"via": link.get("via") or r["company"], "url": link["url"]})
            self.con.execute("UPDATE jobs SET links = ? WHERE id = ?", (json.dumps(links[:12]), home["id"]))
            self.con.execute("UPDATE jobs SET active = 0 WHERE id = ?", (r["id"],))
            folded += 1
        return folded

    def travel_for(self, location):
        q = travel.address_query(location)
        if not q:
            return {}
        row = self.con.execute("SELECT lat, lon FROM geo WHERE query = ?", (q,)).fetchone()
        return travel.estimate((row[0], row[1])) if row and row[0] is not None else {}

    def record_source_result(self, sid, count, error):
        self.con.execute("UPDATE sources SET last_fetch = ?, last_count = coalesce(?, last_count), last_error = ? WHERE id = ?",
                         (db.now(), count, error, sid))
        self.con.commit()

    def store_jobs(self, src, found, started):
        prof = db.profile(self.con)
        added = updated = kept = scams = merged = 0
        via = boards.board_label(src["kind"], src["slug"])
        for raw in found:
            if not raw.get("title") or not raw.get("key"):
                continue
            job = match.enrich(dict(raw))
            if self.app.focus:
                cat, why = focus.check(job)
                if cat is None:
                    scams += why.startswith(focus.SCAM_REASON)
                    continue  # not one of the board's roles in its places, a jobleads.com link, or a scam
            kept += 1
            job["fingerprint"] = focus.fingerprint(job)
            job["travel"] = self.travel_for(job.get("location"))
            exists = self.con.execute("SELECT id, description, reposts FROM jobs WHERE key = ?", (job["key"],)).fetchone()
            if not exists and self.merge_twin(job, src, via, started):
                merged += 1
                continue
            if not exists:
                # The same job closed before and listed again is a repost.
                gone = self.con.execute("SELECT max(reposts) FROM jobs WHERE fingerprint = ? AND active = 0", (job["fingerprint"],)).fetchone()[0]
                job["reposts"] = (gone + 1) if gone is not None else 0
            else:
                job["reposts"] = exists["reposts"]
                if len(exists["description"] or "") > len(job.get("description") or ""):
                    job["description"] = exists["description"]   # never trade a full post for a snippet
                    match.enrich_skills(job)
            value, detail = match.score(job, prof)
            cols = {k: job.get(k) for k in ("title", "company", "location", "work_model", "employment_type", "department", "url", "apply_url",
                                             "description", "salary_min", "salary_max", "salary_text", "level", "years_min", "sponsorship", "posted")}
            for name in ("title", "company", "location", "employment_type", "department", "url", "apply_url", "salary_text", "level"):
                cols[name] = str(cols[name] or "")
            cols["work_model"] = cols["work_model"] or "unknown"
            cols["sponsorship"] = cols["sponsorship"] or "unknown"
            cols["description"] = (cols["description"] or "")[:config.MAX_TEXT]
            cols["skills"] = json.dumps(job["skills"])
            cols.update(score=value, score_detail=json.dumps(detail), scored_at=started, last_seen=started, active=1, source_id=src["id"],
                        fingerprint=job["fingerprint"], travel=json.dumps(job["travel"]), reposts=job["reposts"])
            if raw.get("full_text"):
                cols["full_text"] = 1
            if exists:
                self.con.execute(f"UPDATE jobs SET {', '.join(f'{k} = ?' for k in cols)} WHERE id = ?", list(cols.values()) + [exists["id"]])
                updated += 1
            else:
                cols.update(key=job["key"], first_seen=started, links=json.dumps([{"via": via, "url": job.get("url") or ""}]))
                self.con.execute(f"INSERT INTO jobs ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", list(cols.values()))
                added += 1
        # Jobs the board no longer lists are closed. Ones you track stay visible in your tracker.
        # A Google search shows a different slice each time, so its jobs close only after three weeks unseen.
        cutoff = (dt.datetime.now() - dt.timedelta(days=21)).isoformat() if src["kind"] in boards.KEYED else started
        self.con.execute("UPDATE jobs SET active = 0 WHERE source_id = ? AND last_seen < ?", (src["id"], cutoff))
        self.con.execute("UPDATE sources SET last_fetch = ?, last_count = ?, last_error = NULL WHERE id = ?", (db.now(), kept, src["id"]))
        self.con.commit()
        return added, updated, kept, scams, merged

    def merge_twin(self, job, src, via, started):
        """When another board already has this job open, add this board's link to it instead of a second copy.
        The fuller description and any pay it was missing are kept. Listed twice on the same board counts as a repost."""
        prefix = focus.same_job_prefix(job["fingerprint"])
        twin = next((r for r in self.con.execute("SELECT * FROM jobs WHERE substr(fingerprint, 1, ?) = ? AND active = 1 AND key != ? ORDER BY id",
                                                  (len(prefix), prefix, job["key"]))
                     if focus.same_place(r["fingerprint"], job["fingerprint"])), None)
        if not twin:
            return False
        links = db.loads(twin["links"], [])
        if not links:
            links = [{"via": "", "url": twin["url"]}]
        if not any(link.get("url") == job.get("url") for link in links):
            links.append({"via": via, "url": job.get("url") or ""})
        cols = {"links": json.dumps(links[:12]), "last_seen": started}
        if "@" in job["fingerprint"].rsplit("|", 1)[-1] and "@" not in twin["fingerprint"].rsplit("|", 1)[-1]:
            # This board gives the street address; keep it, for travel times.
            cols.update(location=job["location"], fingerprint=job["fingerprint"], travel=json.dumps(job.get("travel") or {}))
        if twin["source_id"] == src["id"]:
            cols["reposts"] = (twin["reposts"] or 0) + 1
        if len(job.get("description") or "") > len(twin["description"] or ""):
            cols["description"] = job["description"][:config.MAX_TEXT]
            cols["skills"] = json.dumps(job["skills"])
        if not twin["salary_min"] and job.get("salary_min"):
            cols.update(salary_min=job["salary_min"], salary_max=job.get("salary_max"), salary_text=str(job.get("salary_text") or ""))
        self.con.execute(f"UPDATE jobs SET {', '.join(f'{k} = ?' for k in cols)} WHERE id = ?", list(cols.values()) + [twin["id"]])
        if "description" in cols or "salary_min" in cols or "reposts" in cols:
            self.rescore_one(twin["id"])
        return True

    def rescore_one(self, job_id):
        row = self.con.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row:
            value, detail = match.score(db.job_row(row), db.profile(self.con))
            self.con.execute("UPDATE jobs SET score = ?, score_detail = ?, scored_at = ? WHERE id = ?", (value, json.dumps(detail), db.now(), job_id))

    def rescore(self):
        return self.run(self.rescore_all)

    def rescore_all(self, open_only=False):
        """Score every job against the profile. `open_only` skips closed jobs you aren't tracking (they're scored again if relisted)."""
        prof = db.profile(self.con)
        stamp = db.now()
        rows = self.con.execute("SELECT * FROM jobs" + (" WHERE active = 1 OR id IN (SELECT job_id FROM applications)" if open_only else "")).fetchall()
        for r in rows:
            j = db.job_row(r)
            value, detail = match.score(j, prof)
            self.con.execute("UPDATE jobs SET score = ?, score_detail = ?, scored_at = ? WHERE id = ?", (value, json.dumps(detail), stamp, j["id"]))
        self.con.commit()
        return {"rescored": len(rows)}
