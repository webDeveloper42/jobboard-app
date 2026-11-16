"""Workday boards, merging one job seen on two boards, reposts and old posts, clearances, travel times, full posts
for snippet boards, the job sheets in the Sheets tab, and the morning run. No network: every request is stubbed."""
import datetime as dt
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["OLLAMA_HOST"] = "http://127.0.0.1:9"

from jobboard import boards, morning  # noqa: E402
from jobboard.boards import fulltext  # noqa: E402
from jobboard.links import sheets as sheets_link  # noqa: E402
from jobboard.rules import focus, match, text, travel  # noqa: E402
from jobboard import JobBoardApi  # noqa: E402

GEO = mock.patch.object(travel, "geocode", return_value=None)   # never ask OpenStreetMap from a test
GEO.start()
FULL = mock.patch.object(fulltext, "fetch", return_value="")
FULL.start()
LOOKUP = mock.patch.object(boards, "google_lookup", return_value=[])   # never spend a real SerpApi search from a test
LOOKUP.start()

def _app_installed(env, folder, marker):
    """Some tests write through your other dashboard apps' own code. On a machine without them (like GitHub's test
    runner) those tests are skipped instead of failing."""
    return (Path(os.environ.get(env) or Path.home() / folder) / marker).exists()


NEEDS_SHEETS = unittest.skipUnless(_app_installed("SHEETS_APP_DIR", "sheets-app", "sheets/store.py"), "the Sheets app isn't installed here")
NEEDS_DOCS = unittest.skipUnless(_app_installed("DOCS_APP_DIR", "docs-app", "docs/store.py"), "the Docs app isn't installed here")
NEEDS_NOTES = unittest.skipUnless(_app_installed("NOTES_APP_DIR", "notes-app", "store.py"), "the Notes app isn't installed here")


DESC = "Help desk support for Windows and Microsoft 365 users, tickets and troubleshooting. 1+ years of experience."


def wd_reply(url, body):
    if body["offset"]:
        return {"total": 3, "jobPostings": []}
    return {"total": 3, "jobPostings": [
        {"title": "Helpdesk Support Technician", "externalPath": "/job/USA-DC-Washington/Helpdesk-Support-Technician_RQ1", "locationsText": "USA DC Washington",
         "postedOn": "Posted 2 Days Ago"},
        {"title": "Program Analyst", "externalPath": "/job/x_RQ2", "locationsText": "USA DC Washington", "postedOn": "Posted Today"},
        {"title": "Help Desk Technician", "externalPath": "/job/y_RQ3", "locationsText": "USA FL Tampa", "postedOn": "Posted Today"}]}


def wd_detail(url):
    return {"jobPostingInfo": {"title": "Helpdesk Support Technician", "jobReqId": "RQ1", "location": "USA DC Washington", "timeType": "Full time",
                               "startDate": "2026-11-10", "externalUrl": "https://gdit.wd5.myworkdayjobs.com/External_Career_Site/job/RQ1",
                               "jobDescription": "<p>" + DESC + "</p><p>Clearance Level Must Currently Possess:</p><p>None</p>"}}


class Workday(unittest.TestCase):
    def test_reads_only_jobs_that_fit_and_their_full_posts(self):
        with mock.patch.object(boards.http, "post_json", side_effect=wd_reply) as search, mock.patch.object(boards.http, "get_json", side_effect=wd_detail) as detail:
            jobs = boards.fetch("workday", "gdit.wd5.myworkdayjobs.com/External_Career_Site | help desk Washington")
        self.assertIn("/wday/cxs/gdit/External_Career_Site/jobs", search.call_args[0][0])
        self.assertEqual(detail.call_count, 1)   # the analyst job and the Tampa job are never read in full
        j = jobs[0]
        self.assertEqual((j["title"], j["company"], j["location"], j["posted"]), ("Helpdesk Support Technician", "GDIT", "Washington, DC", "2026-11-10"))
        self.assertEqual(j["key"], "workday:gdit:RQ1")
        self.assertIn("Windows", j["description"])
        self.assertEqual(focus.check(match.enrich(dict(j)))[0], "it_tech")

    def test_places_and_links(self):
        self.assertEqual(boards.workday_sites.place_from("USA DC Home Office (DCHOME)"), "Remote (USA)")
        self.assertEqual(boards.workday_sites.place_from("USA VA Falls Church"), "Falls Church, VA")
        self.assertEqual(boards.slug_from("https://gdit.wd5.myworkdayjobs.com/en-US/External_Career_Site")[0], "workday")
        with self.assertRaises(boards.SourceError):
            boards.workday_site("not a link")


class Clearance(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(text.clearance("Clearance Level Must Currently Possess:\nTop Secret/SCI\n"), "active")
        self.assertEqual(text.clearance("Clearance Level Must Currently Possess:\nNone\nClearance Level Must Be Able to Obtain:\nNone"), None)
        self.assertEqual(text.clearance("Security Clearance: Active TS/SCI Required"), "active")
        self.assertEqual(text.clearance("", "Help Desk Technician - TS/SCI with Polygraph"), "active")
        self.assertEqual(text.clearance("US citizens with the ability to obtain and maintain a Secret security clearance."), "obtain")
        self.assertEqual(text.clearance("Ability to obtain a Secret clearance (or possess an active clearance)."), "obtain")
        self.assertIsNone(text.clearance(DESC))

    def test_active_clearance_caps_the_score(self):
        prof = {"skills": ["Technical Support", "Windows", "Troubleshooting", "Microsoft 365", "Ticketing Systems"], "target_titles": ["Help Desk Technician"],
                "headline": "", "level": "", "years_exp": 1, "work_models": [], "locations": ["Washington, DC"], "min_salary": None, "needs_sponsorship": False}
        base = match.enrich({"title": "Help Desk Technician", "location": "Washington, DC", "description": DESC})
        cleared = match.enrich({"title": "Help Desk Technician", "location": "Washington, DC", "description": DESC + "\nActive Top Secret clearance required."})
        self.assertLessEqual(match.score(cleared, prof)[0], 55)
        self.assertIn("Needs an active security clearance", match.score(cleared, prof)[1]["flags"])
        self.assertGreater(match.score(base, prof)[0], match.score(cleared, prof)[0])


class Travel(unittest.TestCase):
    def test_address_and_estimate(self):
        self.assertEqual(travel.address_query("3100 14th St NW,Ste 201 Washington,DC 20010-2444"), "3100 14th St NW, Washington, DC 20010")
        self.assertIsNone(travel.address_query("Washington, DC"))
        near = travel.estimate((38.8452, -76.9300))     # Suitland
        far = travel.estimate((38.9296, -77.0325))      # Columbia Heights
        self.assertLess(near["transit"], far["transit"])
        self.assertGreater(far["transit"], far["drive"])


class FullText(unittest.TestCase):
    def test_reads_jobposting_data(self):
        page = ('<html><script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting","title":"IT Tech",'
                '"description":"&lt;p&gt;' + DESC * 3 + '&lt;/p&gt;"}</script></html>')
        self.assertIn("Microsoft 365", fulltext.from_html(page))
        self.assertEqual(fulltext.from_html("<html>no data</html>"), "")


def board_post(key, title="Help Desk Technician", company="Acme IT", location="Washington, DC", **kw):
    return {"key": key, "title": title, "company": company, "location": location, "url": f"https://x/{key}", "description": DESC, **kw}


class Board(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.sheets = os.path.join(self.dir.name, "sheets.db")
        self.api = JobBoardApi(os.path.join(self.dir.name, "jobboard.db"), sheets=self.sheets)
        self.addCleanup(self.api.close)
        env = mock.patch.dict(os.environ, {"SERPAPI_KEY": "", "JOOBLE_KEY": ""})
        env.start()
        self.addCleanup(env.stop)
        self.api.state({})
        self.ids = {k: self.api.do("source_add", {"kind": "remotive", "slug": k, "fetch": False})["id"] for k in ("one", "two")}

    def fetch(self, board, posts):
        with mock.patch.object(boards, "fetch", return_value=posts):
            return self.api.refresh({"source": self.ids[board]})["report"][0]

    def test_one_job_on_two_boards_shows_once(self):
        self.fetch("one", [board_post("remotive:one:1")])
        rep = self.fetch("two", [board_post("remotive:two:9", title="Help Desk Technician (Remote)", company="Acme IT, Inc.",
                                            description=DESC + " Extra detail. " * 20, salary_text="$22 - $26 per hour")])
        self.assertEqual((rep["new"], rep["merged"]), (0, 1))
        jobs = self.api.state({})["jobs"]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(len(jobs[0]["links"]), 2)
        full = self.api.job(jobs[0]["id"])
        self.assertIn("Extra detail", full["description"])   # the fuller post is kept
        self.assertTrue(full["salary_min"])                   # and the pay it was missing

    def test_a_street_address_and_its_city_are_one_place(self):
        self.fetch("one", [board_post("remotive:one:1", title="Data Entry Clerk (R2259)", company="Target", location="Washington, DC")])
        rep = self.fetch("two", [board_post("remotive:two:1", title="Data Entry Clerk (R2259)", company="Target",
                                            location="3100 14th St NW, Washington, DC 20010")])
        self.assertEqual(rep["merged"], 1)
        jobs = self.api.state({})["jobs"]
        self.assertEqual(len(jobs), 1)
        self.assertTrue(jobs[0]["location"].startswith("3100 14th St NW"))   # the address is kept
        self.assertFalse(focus.same_place("a|b|3100 14th@dc", "a|b|remote"))
        self.assertFalse(focus.same_place("a|b|3100 14th@dc", "a|b|4500 wisconsin@dc"))   # two stores stay two jobs

    def test_listed_twice_on_the_same_board_is_a_repost(self):
        self.fetch("one", [board_post("remotive:one:1"), board_post("remotive:one:2"), board_post("remotive:one:3")])
        jobs = self.api.state({})["jobs"]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["reposts"], 2)
        self.assertTrue(any(f.startswith("Posted again 2 times") for f in self.api.job(jobs[0]["id"])["score_detail"]["flags"]))

    def test_get_the_full_description(self):
        long = "Full post. " + DESC * 8
        self.fetch("one", [board_post("remotive:one:1", description="Help desk support for Windows users...")])
        jid = self.api.state({})["jobs"][0]["id"]
        # The employer's page can be read: no Google search is spent.
        with mock.patch.object(fulltext, "fetch", return_value=long), mock.patch.object(boards, "google_lookup") as look:
            out = self.api.do("full_post", {"id": jid})
        self.assertEqual((out["found"], out["via"]), (True, "the employer's page"))
        look.assert_not_called()
        self.assertEqual(self.api.job(jid)["description"], long)
        # A later refresh with the snippet doesn't put the snippet back.
        self.fetch("one", [board_post("remotive:one:1", description="Help desk support for Windows users...")])
        self.assertEqual(self.api.job(jid)["description"], long)

    def test_full_description_from_google_when_the_page_is_blocked(self):
        self.fetch("one", [board_post("remotive:one:1", description="Help desk support for Windows users...")])
        job = self.api.state({})["jobs"][0]
        out = self.api.do("full_post", {"id": job["id"]})          # no key yet
        self.assertFalse(out["found"])
        self.assertIn("SerpApi key", out["why"])
        self.api.do("google_key", {"key": "k" * 40})
        hits = [("Marketing Manager", job["company"], "x" * 3000, "https://other/1"),
                (job["title"], job["company"], "Whole post. " + DESC * 8, "https://employer.example/apply/1"),
                (job["title"], "Someone Else Inc", "y" * 4000, "https://other/2")]
        with mock.patch.object(boards, "google_lookup", return_value=hits) as look:
            out = self.api.do("full_post", {"id": job["id"]})
        self.assertEqual(look.call_count, 1)
        self.assertEqual((out["found"], out["via"]), (True, "Google Jobs"))
        full = self.api.job(job["id"])
        self.assertTrue(full["description"].startswith("Whole post."))   # the same title and company only
        self.assertIn("https://employer.example/apply/1", [x["url"] for x in full["links"]])
        with mock.patch.object(boards, "google_lookup", return_value=hits[:1]):
            out = self.api.do("full_post", {"id": job["id"]})
        self.assertFalse(out["found"])

    def test_resumes_switch_the_board_to_their_roles(self):
        self.api.do("resume_text", {"text": "Jane Doe\nIT Technician\nWindows, Active Directory, ticketing systems, troubleshooting.", "file": "it.pdf"})
        self.fetch("one", [board_post("remotive:one:1", title="Help Desk Technician"),
                           board_post("remotive:one:2", title="Data Entry Clerk", company="B", description="Typing and data entry in Excel. Attention to detail.")])
        titles = lambda: sorted(j["title"] for j in self.api.state({})["jobs"])  # noqa: E731
        first = self.api.state({})["resumes"]
        self.assertEqual([(r["name"], r["primary"], r["roles"], r["file"]) for r in first], [("My resume", True, [], "it.pdf")])
        self.assertEqual(titles(), ["Data Entry Clerk", "Help Desk Technician"])          # one resume for every role: nothing hidden
        self.api.do("resume_update", {"id": first[0]["id"], "name": "IT", "roles": ["it_tech", "it_intern", "nonsense"]})
        self.assertEqual(titles(), ["Help Desk Technician"])
        it_score = self.api.state({})["jobs"][0]["score"]
        # A second resume: it becomes primary, starts empty with the role's title, and the board shows its role.
        out = self.api.do("resume_add", {"name": "Data entry", "roles": ["data_entry"]})
        self.assertEqual(out["roles"], ["Data entry"])
        st = self.api.state({})
        self.assertEqual(titles(), ["Data Entry Clerk"])
        self.assertEqual(st["counts"]["active"], 1)
        self.assertEqual((st["profile"]["resume_chars"], st["profile"]["target_titles"], st["profile"]["skills"]), (0, ["Data Entry Clerk"], []))
        self.api.do("resume_text", {"text": "Jane Doe\nData Entry Clerk\nFast typing, Excel, data entry, attention to detail.", "file": "de.pdf"})
        rs = {r["name"]: r for r in self.api.state({})["resumes"]}
        self.assertEqual((rs["Data entry"]["primary"], rs["Data entry"]["file"], rs["IT"]["primary"], rs["IT"]["file"]), (True, "de.pdf", False, "it.pdf"))
        self.assertEqual((rs["IT"]["jobs"], rs["Data entry"]["jobs"]), (1, 1))
        with self.assertRaises(Exception):
            self.api.do("resume_remove", {"id": rs["Data entry"]["id"]})                  # the primary one can't be removed
        with self.assertRaises(Exception):
            self.api.do("resume_add", {"name": "it", "roles": []})                        # names are unique
        # Back to the IT resume: its own text, skills and jobs return, scored the same as before.
        self.api.do("resume_use", {"id": rs["IT"]["id"]})
        st = self.api.state({})
        self.assertEqual(titles(), ["Help Desk Technician"])
        self.assertEqual(st["jobs"][0]["score"], it_score)
        self.assertEqual(st["profile"]["resume_file"], "it.pdf")
        self.assertIn("Active Directory", st["profile"]["skills"])
        self.api.do("resume_remove", {"id": rs["Data entry"]["id"]})
        self.assertEqual(len(self.api.state({})["resumes"]), 1)

    def test_morning_run_reads_full_posts_for_the_best_snippets(self):
        self.api.do("resume_text", {"text": "Jane Doe\nHelp Desk Technician\nWindows, Active Directory, ticketing systems, troubleshooting.", "file": "r.pdf"})
        self.api.do("google_key", {"key": "a" * 64})
        posts = [board_post(f"remotive:one:{i}", title="Help Desk Technician", company=f"Co{i}", description="Help desk support for Windows users...")
                 for i in range(8)]
        self.fetch("one", posts)
        long = "Whole post. " + DESC * 20
        with mock.patch.object(morning, "AUTO_GOOGLE", 2), mock.patch.object(fulltext, "fetch", return_value=""), \
                mock.patch.object(boards, "google_lookup", side_effect=lambda t, c, loc, key: [(t, c, long, "")]) as look:
            got = morning.fill_snippets(self.api, "2000-01-01")
            again = morning.fill_snippets(self.api, "2000-01-01")
        self.assertEqual(look.call_count, 2)                 # capped
        self.assertEqual((got["read"], got["google"], got["tried"]), (2, 2, 8))
        self.assertEqual(again["tried"], 0)                  # every job is tried once
        self.assertEqual(sum(len(self.api.job(j["id"])["description"]) > 1500 for j in self.api.state({})["jobs"]), 2)

    def test_job_site_reposts_fold_into_the_employers_post(self):
        self.fetch("one", [board_post("remotive:one:1", title="Data Entry Clerk", company="Maxion Corp", location="Remote", workplace="remote",
                                      description="Enter records in Excel. " * 20)])
        self.fetch("two", [board_post("remotive:two:1", title="Data Entry Clerk", company="Remote Career", location="Remote", workplace="remote",
                                      description="Enter records in Excel. " * 20),
                           board_post("remotive:two:2", title="Help Desk Technician", company="AllJobs", location="Remote", workplace="remote")])
        jobs = {j["company"]: j for j in self.api.state({})["jobs"]}
        self.assertEqual(sorted(jobs), ["AllJobs", "Maxion Corp"])                 # the Remote Career copy was folded in
        self.assertEqual(len(self.api.job(jobs["Maxion Corp"]["id"])["links"]), 2)
        self.assertTrue(any(f.startswith("Listed by a job site") for f in jobs["AllJobs"]["flags"]))  # no employer post to fold into

    def test_clearance_and_commute_filters(self):
        far = (38.9845, -77.0269)   # upper Georgia Ave, about an hour by Metro/bus
        with mock.patch.object(travel, "geocode", return_value=far):
            self.fetch("one", [board_post("remotive:one:1", title="IT Technician", description=DESC + "\nActive Top Secret clearance required."),
                               board_post("remotive:one:2", title="Data Entry Clerk", company="Target", location="7828 Georgia Ave NW, Washington, DC 20012"),
                               board_post("remotive:one:3", title="Help Desk Technician", company="B", location="Remote", workplace="remote")])
        titles = lambda f: sorted(j["title"] for j in self.api.state(f)["jobs"])  # noqa: E731
        self.assertEqual(titles({"no_clearance": "1"}), ["Data Entry Clerk", "Help Desk Technician"])
        self.assertEqual(titles({"max_commute": "45"}), ["Help Desk Technician", "IT Technician"])   # no address: kept; remote: kept
        self.assertEqual(titles({"max_commute": "90"}), ["Data Entry Clerk", "Help Desk Technician", "IT Technician"])

    def test_old_posts_are_flagged(self):
        old = (dt.date.today() - dt.timedelta(days=45)).isoformat()
        self.fetch("one", [board_post("remotive:one:1", posted=old)])
        flags = self.api.job(self.api.state({})["jobs"][0]["id"])["score_detail"]["flags"]
        self.assertTrue(any(f.startswith("Posted 45 days ago") for f in flags))

    def test_travel_time_for_an_address(self):
        with mock.patch.object(travel, "geocode", return_value=(38.9296, -77.0325)) as geo:
            self.fetch("one", [board_post("remotive:one:1", title="Data Entry Clerk", company="Target", location="3100 14th St NW, Washington, DC 20010")])
            self.fetch("one", [board_post("remotive:one:1", title="Data Entry Clerk", company="Target", location="3100 14th St NW, Washington, DC 20010")])
        self.assertEqual(geo.call_count, 1)   # each address is looked up once
        j = self.api.state({})["jobs"][0]
        self.assertGreater(j["travel"]["transit"], 0)

    def sheet(self, name):
        con = sqlite3.connect(self.sheets)
        row = con.execute("SELECT doc FROM books WHERE name = ?", (name,)).fetchone()
        con.close()
        return json.loads(row[0])["sheets"][0] if row else None

    @NEEDS_SHEETS
    def test_applying_writes_the_job_sheet(self):
        # Your IT workbook, laid out like the real one.
        store = sheets_link._store()
        con = store.connect(self.sheets)
        cells = {f"{c}1": {"v": hname} for c, hname in zip("ABCDEFGH", sheets_link.HEADERS)}
        cells.update({"A2": {"v": "DagTech"}, "B2": {"v": "IT Support Engineer"}, "F2": {"v": "Emailed"}})
        sheet = dict(store.blank_sheet("Book(IT)"), cells=cells, colW={"0": 210, "1": 242})
        store.add_book(con, "IT", {"sheets": [sheet], "active": 0})
        con.close()
        self.fetch("one", [board_post("remotive:one:1", salary_text="$20 - $24 an hour"),
                           board_post("remotive:one:2", title="Data Entry Clerk", company="Target", location="Washington, DC")])
        jobs = {j["title"]: j["id"] for j in self.api.state({})["jobs"]}
        out = self.api.do("status", {"id": jobs["Help Desk Technician"], "status": "applied"})
        self.assertIn("IT sheet (row 3)", out["sheet"])
        it = self.sheet("IT")["cells"]
        self.assertEqual([it[f"{c}3"]["v"] for c in "ABCDEFGH"], ["Acme IT", "Help Desk Technician", "Remotive", "20-24", "24/hr", "Applied", "Washington DC", "N/A"])
        self.assertEqual(it["A2"]["v"], "DagTech")   # your rows stay as they are
        # Data Entry has no workbook yet: one is made with the same layout.
        out = self.api.do("status", {"id": jobs["Data Entry Clerk"], "status": "applied"})
        self.assertIn("new sheet", out["sheet"])
        st = self.sheet("Data Entry")
        self.assertEqual(st["name"], "Book(Data Entry)")
        self.assertEqual(st["colW"], {"0": 210, "1": 242})
        self.assertEqual([st["cells"][f"{c}1"]["v"] for c in "ABCDEFGH"], sheets_link.HEADERS)
        self.assertEqual(st["cells"]["A2"]["v"], "Target")
        # Moving on in the tracker changes only Progress.
        self.api.do("status", {"id": jobs["Help Desk Technician"], "status": "interviewing"})
        self.assertEqual(self.sheet("IT")["cells"]["F3"]["v"], "Interviewing")
        self.assertNotIn("A4", self.sheet("IT")["cells"])
        # It can be switched off.
        self.api.do("sheets_sync", {"on": False})
        self.assertNotIn("sheet", self.api.do("status", {"id": jobs["Help Desk Technician"], "status": "offer"}))

    @NEEDS_SHEETS
    def test_sheets_with_column_names(self):
        # Your sheets now keep the headers as column names, not in row 1; data starts at row 1. Columns are found by name.
        store = sheets_link._store()
        con = store.connect(self.sheets)
        names = {"0": "Company", "1": "Position", "2": "Platform", "3": "Offer", "4": "Ask", "5": "Status", "6": "Where", "7": "Type"}
        names["5"], names["8"] = "Notes", "Progress"   # Progress moved to column I, and column F renamed
        sheet = dict(store.blank_sheet("Book(IT)"), names=names, cells={"A1": {"v": "DagTech"}, "B1": {"v": "IT Support Engineer"}})
        store.add_book(con, "IT", {"sheets": [sheet], "active": 0})
        con.close()
        self.fetch("one", [board_post("remotive:one:1"), board_post("remotive:one:2", title="Data Entry Clerk", company="Target")])
        jobs = {j["title"]: j["id"] for j in self.api.state({})["jobs"]}
        out = self.api.do("status", {"id": jobs["Help Desk Technician"], "status": "applied"})
        self.assertIn("row 2", out["sheet"])
        it = self.sheet("IT")["cells"]
        self.assertEqual((it["A2"]["v"], it["I2"]["v"]), ("Acme IT", "Applied"))
        self.assertNotIn("F2", it)
        self.assertNotIn("A3", it)
        self.api.do("status", {"id": jobs["Data Entry Clerk"], "status": "applied"})
        st = self.sheet("Data Entry")
        self.assertEqual(st["names"], names)            # a new workbook copies the column names
        self.assertEqual(st["cells"]["A1"]["v"], "Target")   # and its data starts at row 1

    @NEEDS_DOCS
    def test_open_in_docs(self):
        docs_db = os.path.join(self.dir.name, "docs.db")
        api = JobBoardApi(os.path.join(self.dir.name, "jobboard.db"), docs=docs_db)
        self.addCleanup(api.close)
        self.fetch("one", [board_post("remotive:one:1")])
        job_id = self.api.state({})["jobs"][0]["id"]
        doc_id = api.run_in_db(lambda: (api.con.execute("INSERT INTO documents (job_id, kind, body, created) VALUES (?, 'cover_letter', ?, ?)",
                                                   (job_id, "Dear hiring manager,\n\nI am applying.\n\nSkills:\n- Windows\n- Linux", "2026-11-12")).lastrowid,
                                   api.con.commit())[0])
        from jobboard.links import docs as docs_link
        store = docs_link._store()
        con = store.connect(docs_db)
        tid = store.add(con, "Letterhead", "<p>x</p>", {"margins": 0.5, "header": "<p>Jane Doe</p>"}, template=True)
        con.close()
        self.assertEqual([t["title"] for t in api.do("docs_templates", {})["templates"]], ["Letterhead"])
        out = api.do("doc_to_docs", {"doc": doc_id, "template": tid})
        self.assertEqual(out["url"], f"/docs/#doc/{out['id']}")
        self.assertTrue(out["title"].startswith("Cover letter — Acme IT"))
        con = store.connect(docs_db)
        row = store.row(con, out["id"])
        con.close()
        self.assertIn("<h2>Skills</h2><ul><li>Windows</li><li>Linux</li></ul>", row["html"])
        self.assertIn("Jane Doe", json.loads(row["page"])["header"])   # the template's page layout
        self.assertFalse(row["is_template"])
        self.assertIsNone(self.api.docs)   # a test's board never writes to your Docs

    @NEEDS_NOTES
    def test_a_note_for_each_job(self):
        notes_db = os.path.join(self.dir.name, "notes", "n.db")
        api = JobBoardApi(os.path.join(self.dir.name, "jobboard.db"), notes=notes_db)
        self.addCleanup(api.close)
        self.fetch("one", [board_post("remotive:one:1")])
        job_id = self.api.state({})["jobs"][0]["id"]
        first = api.do("job_note", {"id": job_id})
        self.assertTrue(first["new"])
        self.assertEqual(first["url"], f"/notes/#note/{first['id']}")
        again = api.do("job_note", {"id": job_id})
        self.assertEqual((again["id"], again["new"]), (first["id"], False))   # the same note opens again
        con = sqlite3.connect(notes_db)
        title, content = con.execute("SELECT title, content FROM notes WHERE id = ?", (first["id"],)).fetchone()
        con.close()
        self.assertEqual(title, "Interview notes — Acme IT — Help Desk Technician")
        self.assertIn(f'href="/jobs/#job/{job_id}"', content)
        self.assertIn("Questions to ask them", content)
        self.assertIsNone(self.api.notes)

    def test_tests_never_touch_your_sheets(self):
        api = JobBoardApi(os.path.join(self.dir.name, "other.db"))
        self.addCleanup(api.close)
        self.assertIsNone(api.sheets)

    def test_morning_run(self):
        self.api.do("google_key", {"key": "a" * 64})
        kinds = []
        real = self.api.refresh

        def refresh(d):
            src = self.api.run_in_db(lambda: self.api.con.execute("SELECT kind FROM sources WHERE id = ?", (d["source"],)).fetchone()[0])
            kinds.append(src)
            with mock.patch.object(boards, "fetch", return_value=[board_post("remotive:one:1")] if src == "remotive" else []):
                return real(d)
        tuesday = dt.date(2026, 11, 17)
        with mock.patch.object(self.api, "refresh", side_effect=refresh), mock.patch.object(morning, "mail_config", return_value=None):
            out = morning.run(self.api, auto=True, today=tuesday)
            again = morning.run(self.api, auto=True, today=tuesday)
        self.assertNotIn("google", kinds)          # keyed searches wait for Monday
        self.assertIn("remotive", kinds)
        self.assertEqual(again, {"skipped": "already ran today"})
        self.assertEqual([j["title"] for j in out["jobs"]], ["Help Desk Technician"] if out["jobs"] else [])
        self.assertEqual(self.api.state({})["daily"]["day"], "2026-11-17")
        self.assertIn("full_posts", out)
        subject, body, plain = morning.render([{"score": 80, "title": "IT Tech", "company": "A", "location": "Washington, DC", "url": "https://x",
                                               "flags": ["Old post"], "travel": {"transit": 40}, "pay": "$20–$24/hr"}], tuesday)
        self.assertIn("1 new job match", subject)
        self.assertIn("40 min by Metro/bus", plain)


if __name__ == "__main__":
    unittest.main()
