"""The board's focus: IT technician and IT internship (remote or DC), data entry (remote or DC), never jobleads.com. No network."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["OLLAMA_HOST"] = "http://127.0.0.1:9"

from jobboard import boards  # noqa: E402
from jobboard.rules import focus, match, text  # noqa: E402
from jobboard import JobBoardApi, JobBoardError  # noqa: E402


def job(title, location, work_model="onsite", url="https://example.com/a"):
    return {"title": title, "location": location, "work_model": work_model, "url": url, "apply_url": url}


class Quality(unittest.TestCase):
    def test_data_entry_scams(self):
        base = "Enter customer records into our system and check them for accuracy. Monday to Friday, 9 to 5. We use Excel and Salesforce. "
        real = {"title": "Data Entry Clerk", "company": "Maxion Corp", "location": "Remote", "work_model": "remote", "url": "https://m.example/1",
                "description": base * 3, "salary_min": 37000, "salary_max": 42000}
        self.assertEqual(focus.check(real)[0], "data_entry")
        for extra, why in (("To apply, text your name to (202) 555-0143.", "text a phone number"),
                           ("You can work from your phone. ", "work from your phone")):
            cat, reason = focus.check(dict(real, description=real["description"] + extra, company="Only Data Entry"))
            self.assertIsNone(cat, extra)
            self.assertIn(why, reason)
        self.assertIsNone(focus.check(dict(real, salary_min=70000, salary_max=90000, company="Typing Jobs Online"))[0])   # pay far too high
        # The same phone number in an IT post isn't a data-entry check.
        it = dict(real, title="Help Desk Technician", description=base * 3 + "Questions? Call (202) 555-0143.")
        self.assertEqual(focus.check(it)[0], "it_tech")

    def test_remote_jobs_limited_to_other_states(self):
        post = lambda d: {"title": "Help Desk Technician", "company": "A", "location": "Anywhere", "work_model": "remote",  # noqa: E731
                          "url": "https://a.example/1", "description": "Support users with Windows and tickets. " * 6 + d}
        for d in ("Must reside in the state of Pennsylvania.", "Candidates must live in one of the following states: TX, FL, GA.",
                  "Must reside within a reasonable commuting distance of Long Beach, CA."):
            cat, why = focus.check(post(d))
            self.assertIsNone(cat, d)
            self.assertTrue(why.startswith("remote only for people in"), why)
        for d in ("Open to candidates based in the United States.", "Must reside in Maryland, Virginia or DC.", "Must live in the DMV area.",
                  "Candidates must be located in Washington, DC or nearby.", ""):
            self.assertEqual(focus.check(post(d))[0], "it_tech", d)
        # A DC job that is also remote-friendly stays: you can take it in person.
        self.assertEqual(focus.check(dict(post("Must reside in Pennsylvania."), location="Washington, DC · Remote"))[0], "it_tech")

    def test_aggregators_and_levels(self):
        for c in ("Remote Career", "remote quest jobs", "AllJobs", "Job.com", "Toward Jobs", "The Joblink", "Feedinkoo: Remote Jobs", "LinkedIn"):
            self.assertTrue(focus.aggregator(c), c)
        for c in ("GDIT", "Maxion Corp", "Leidos", "Jobot", "Addison Group", "System One"):
            self.assertFalse(focus.aggregator(c), c)
        for title, want in (("Data Entry Clerk", "entry"), ("Help Desk Technician", "entry"), ("IT Support Specialist", "entry"),
                            ("Tier 1 Service Desk Analyst", "entry"), ("Help Desk Technician II", "mid"), ("Tier 2 Desktop Support", "mid"),
                            ("Senior Help Desk Technician", "senior"), ("Systems Administrator", "mid")):
            self.assertEqual(text.level_of(title), want, title)
        self.assertEqual(text.level_of("Help Desk Technician", 4), "mid")      # the post asks for years: it says so


class Rules(unittest.TestCase):
    def test_roles(self):
        for title, want in (("IT Technician", "it_tech"), ("Help Desk Technician I", "it_tech"), ("Desktop Support Specialist", "it_tech"),
                            ("IT Support Specialist", "it_tech"), ("Service Desk Analyst", "it_tech"), ("Computer Technician", "it_tech"),
                            ("IT Intern", "it_intern"), ("Information Technology Internship - Summer 2027", "it_intern"), ("Help Desk Intern", "it_intern"),
                            ("Data Entry Clerk", "data_entry"), ("Remote Data Entry Specialist", "data_entry"), ("Data-Entry Operator", "data_entry"), ("Typist", "data_entry"),
                            ("Overnight Stocker", None), ("Stock Associate", None), ("Data Analyst", None), ("Data Entry Manager", None),
                            ("Senior Software Engineer", None), ("IT Manager", None), ("Pharmacy Technician", None), ("HVAC Technician", None),
                            ("Marketing Intern", None), ("Stock Trader", None), ("Network Engineer", None), ("Account Executive", None)):
            self.assertEqual(focus.category(title), want, title)

    def test_places(self):
        ok = [job("IT Technician", "Washington, DC"), job("IT Technician", "Anywhere", "remote"), job("Help Desk Technician", "Washington, D.C. 20001"),
              job("IT Intern", "Remote (US)", "remote"), job("IT Intern", "Washington, District of Columbia"),
              job("Data Entry Clerk", "Washington, DC"), job("Data Entry Clerk", "Anywhere", "remote"), job("Data Entry Specialist", "Remote (US)", "remote")]
        bad = [job("IT Technician", "Arlington, VA"), job("IT Technician", "Seattle, WA"), job("IT Technician", "Washington"),
               job("IT Technician", "Remote - Europe", "remote"), job("Data Entry Clerk", "Suitland, MD"), job("Data Entry Clerk", "Bethesda, MD"), job("Stocker", "Washington, DC"),
               job("IT Intern", "New York, NY")]
        for j in ok:
            self.assertIsNotNone(focus.check(j)[0], j)
        for j in bad:
            self.assertIsNone(focus.check(j)[0], j)

    def test_jobleads_is_left_out(self):
        for url in ("https://www.jobleads.com/us/job/123", "https://jobleads.com/x", "https://us.jobleads.com/y"):
            self.assertEqual(focus.check(job("IT Technician", "Washington, DC", url=url)), (None, "jobleads.com link"))
        self.assertFalse(focus.blocked("https://notjobleads.com/x"))
        self.assertFalse(focus.blocked("https://www.indeed.com/viewjob?from=jobleads.com"))


def serp_page(results, token=None):
    return {"jobs_results": results, **({"serpapi_pagination": {"next_page_token": token}} if token else {})}


GOOGLE = [
    {"title": "IT Help Desk Technician", "company_name": "City Agency", "location": "Washington, DC", "via": "LinkedIn", "job_id": "a1",
     "description": "Support users.", "detected_extensions": {"posted_at": "2 days ago", "schedule_type": "Full-time", "salary": "$25–$30 an hour"},
     "apply_options": [{"title": "JobLeads", "link": "https://www.jobleads.com/j/1"}, {"title": "LinkedIn", "link": "https://www.linkedin.com/jobs/view/1"}]},
    {"title": "IT Support Technician", "company_name": "Only Leads", "location": "Washington, DC", "job_id": "a2",
     "apply_options": [{"title": "JobLeads", "link": "https://jobleads.com/j/2"}]},
    {"title": "IT Technician", "company_name": "Nearby", "location": "Arlington, VA", "job_id": "a3",
     "apply_options": [{"title": "Company", "link": "https://nearby.example/jobs/3"}]},
]


REAL_DESC = ("We're hiring an IT Support Technician to handle tickets, image laptops and support Microsoft 365 users in our "
             "Washington, DC office. 1+ years of help desk experience. Apply through our careers site. ")
WARNING = ("Acme will only contact you from @acme.com addresses, never from Gmail or Yahoo or via WhatsApp, Telegram, etc. "
           "We will never ask you to pay a fee, deposit a check or buy equipment.")


def post(desc, company="Acme Corp", title="IT Support Technician", **kw):
    return dict(job(title, "Washington, DC"), company=company, description=desc, **kw)


class Scams(unittest.TestCase):
    def test_scams_are_left_out(self):
        fakes = [
            REAL_DESC + "Interviews will be conducted via Telegram. Add our hiring manager on Telegram: @acme_hr",
            REAL_DESC + "Text us on WhatsApp +1 202 555 0100 to schedule your screening.",
            REAL_DESC + "We will send you a check to purchase your laptop and software from our approved vendor.",
            REAL_DESC + "A one-time training fee of $85 is required before you start.",
            REAL_DESC + "Send your SSN and bank account details with your resume for direct deposit setup.",
            "Remote help desk work. Receive and reship packages from home. Earn $500 per day!!",
            REAL_DESC + "Email your resume to acme.hiring.dept@gmail.com. No interview required.",
        ]
        for d in fakes:
            cat, why = focus.check(post(d))
            self.assertIsNone(cat, d)
            self.assertTrue(why.startswith(focus.SCAM_REASON), why)

    def test_real_posts_stay(self):
        self.assertEqual(focus.check(post(REAL_DESC))[0], "it_tech")
        self.assertEqual(focus.check(post(REAL_DESC + WARNING))[0], "it_tech")  # a warning about scams isn't one
        self.assertEqual(focus.check(post(REAL_DESC + "Our product integrates with WhatsApp and Telegram.", salary_min=52000, salary_max=68000))[0], "it_tech")
        stock = post("Keying invoices and updating customer records at our office in Washington, DC. Competitive weekly pay. 18+.",
                     title="Data Entry Clerk: Part-Time with Weekly Pay")
        self.assertEqual(focus.check(stock)[0], "data_entry")

    def test_weak_hints_add_up(self):
        self.assertEqual(focus.check(post(REAL_DESC, company=""))[0], "it_tech")  # one hint alone isn't enough
        self.assertIsNone(focus.check(post(REAL_DESC + "Urgently hiring, start today!", company="Confidential", salary_max=180000))[0])


JOOBLE_REPLY = {"totalCount": 3, "jobs": [
    {"id": 111, "title": "<b>Help Desk</b> Technician", "company": "Acme IT", "location": "Washington, DC", "snippet": "&nbsp;...support <b>Windows</b> users...",
     "salary": "$22 - $26 per hour", "type": "Full-time", "link": "https://jooble.org/desc/111", "source": "acme.com", "updated": "2026-11-10T00:00:00.0000000"},
    {"id": 222, "title": "IT Support Technician", "company": "B", "location": "Washington, DC", "snippet": "tickets", "link": "https://jooble.org/desc/222",
     "source": "jobleads.com", "updated": "2026-11-10T00:00:00"},
    {"id": 333, "title": "Data Entry Clerk", "company": "C", "location": "Washington, DC", "snippet": "key records", "link": "https://jooble.org/desc/333",
     "source": "c.com", "updated": "2026-11-09T00:00:00"}]}


class Jooble(unittest.TestCase):
    def test_queries_split_terms_and_places(self):
        q = boards.jooble_queries("help desk OR IT support @ Washington, DC")
        self.assertEqual([b["keywords"] for b in q], ["help desk", "IT support"])
        self.assertEqual(q[0]["location"], "Washington, DC")
        self.assertEqual(boards.jooble_queries("IT intern @ remote"), [{"keywords": "IT intern remote", "location": ""}])
        with self.assertRaises(boards.SourceError):
            boards.jooble_queries("@ remote")

    def test_reads_results_skips_jobleads_and_duplicates(self):
        calls = []
        with mock.patch.object(boards.http, "post_json", side_effect=lambda url, body: calls.append((url, body)) or JOOBLE_REPLY):
            jobs = boards.jooble("help desk OR IT support @ Washington, DC", "k" * 32)
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0][0].endswith("/" + "k" * 32))
        self.assertEqual([j["title"] for j in jobs], ["Help Desk Technician", "Data Entry Clerk"])  # jobleads left out, no repeats
        self.assertEqual(jobs[0]["posted"], "2026-11-10")
        self.assertEqual(jobs[0]["key"], "jooble::111")
        self.assertIn("Windows", jobs[0]["description"])

    def test_bad_key_and_no_key(self):
        with self.assertRaises(boards.SourceError):
            boards.jooble("help desk @ Washington, DC", "")
        with mock.patch.object(boards.http, "post_json", side_effect=boards.SourceError("the board answered 403")):
            with self.assertRaisesRegex(boards.SourceError, "didn't accept the key"):
                boards.jooble("help desk @ Washington, DC", "k" * 32)

    def test_short_snippets_arent_a_scam_sign(self):
        j = dict(job("IT Support Technician", "Washington, DC"), company="", description="Support users.", key="jooble::1")
        self.assertEqual(focus.check(j)[0], "it_tech")


JOBICY_REPLY = {"jobs": [
    {"id": 1, "url": "https://jobicy.com/jobs/1-it-associate", "jobTitle": "IT Associate", "companyName": "Softgic", "jobIndustry": ["Technical Support"],
     "jobType": ["Full-Time"], "jobGeo": "LATAM, USA", "jobDescription": "<p>Support users on <b>Windows</b>.</p>", "pubDate": "2026-11-12T16:52:40+00:00",
     "salaryMin": "18", "salaryMax": "22", "salaryCurrency": "USD", "salaryPeriod": "hourly"},
    {"id": 2, "url": "https://jobicy.com/jobs/2", "jobTitle": "Help Desk Technician", "companyName": "E", "jobGeo": "EMEA", "jobDescription": "x"}]}


class Jobicy(unittest.TestCase):
    def test_reads_us_remote_jobs(self):
        with mock.patch.object(boards.http, "get_json", return_value=JOBICY_REPLY) as got:
            jobs = boards.fetch("jobicy", "supporting")
        self.assertIn("industry=supporting", got.call_args[0][0])
        self.assertIn("geo=usa", got.call_args[0][0])
        self.assertEqual([j["title"] for j in jobs], ["IT Associate"])  # the Europe-only job is left out
        j = jobs[0]
        self.assertEqual((j["salary_min"], j["salary_max"]), (18 * 2080, 22 * 2080))
        self.assertEqual(j["location"], "Remote (USA)")
        self.assertEqual(j["apply_url"], "https://jobicy.com/jobs/1-it-associate")
        self.assertTrue(j["department"].startswith("via Jobicy"))
        self.assertEqual(focus.check(match.enrich(dict(j)))[0], "it_tech")

    def test_bad_industry(self):
        with self.assertRaises(boards.SourceError):
            boards.jobicy("not an industry!")


class Google(unittest.TestCase):
    def test_query(self):
        self.assertEqual(boards.google_query("stocker @ Suitland, MD")["q"], "stocker Suitland, MD")
        remote = boards.google_query("help desk @ remote")
        self.assertEqual((remote["ltype"], remote["location"]), ("1", "United States"))
        with self.assertRaises(boards.SourceError):
            boards.google_query(" @ remote")

    def test_reads_results_and_skips_jobleads(self):
        calls = []

        def fake(url):
            calls.append(url)
            return serp_page(GOOGLE, "next") if len(calls) == 1 else serp_page([])
        with mock.patch.object(boards.http, "get_json", side_effect=fake):
            out = boards.google("IT technician @ Washington, DC", "k" * 40)
        self.assertEqual(len(calls), 2)  # followed the next page
        self.assertNotIn("Only Leads", [j["company"] for j in out])
        first = out[0]
        self.assertEqual(first["apply_url"], "https://www.linkedin.com/jobs/view/1")
        self.assertEqual(first["salary_text"], "$25–$30 an hour")
        self.assertTrue(first["key"].startswith("google::"))

    def test_needs_a_key(self):
        with mock.patch.dict(os.environ, {"SERPAPI_KEY": ""}), self.assertRaises(boards.SourceError):
            boards.google("help desk @ remote", None)


class Board(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.api = JobBoardApi(os.path.join(self.dir.name, "jobboard.db"))
        self.addCleanup(self.api.close)
        env = mock.patch.dict(os.environ, {"SERPAPI_KEY": ""})
        env.start()
        self.addCleanup(env.stop)

    def test_setup_adds_google_searches(self):
        st = self.api.state({})
        google = [s for s in st["sources"] if s["kind"] == "google"]
        self.assertEqual(len(google), 6)
        self.assertFalse(st["google_key"])
        self.assertFalse([s for s in st["sources"] if s["kind"] == "arbeitnow"][0]["enabled"])
        self.assertIn("Data Entry Clerk", st["profile"]["target_titles"])

    def test_refresh_keeps_only_the_focus(self):
        posts = [{"key": "remotive::1", "title": "IT Support Technician", "company": "A", "location": "USA", "workplace": "remote", "url": "https://a/1"},
                 {"key": "remotive::2", "title": "Senior Backend Engineer", "company": "B", "location": "Remote", "workplace": "remote", "url": "https://b/2"},
                 {"key": "remotive::3", "title": "Overnight Stocker", "company": "C", "location": "Remote", "workplace": "remote", "url": "https://c/3"},
                 {"key": "remotive::4", "title": "Help Desk Technician", "company": "D", "location": "Remote", "workplace": "remote", "url": "https://jobleads.com/4"}]
        with mock.patch.object(boards, "fetch", return_value=posts):
            out = self.api.refresh({})
        self.assertTrue(any("SerpApi key" in (r.get("error") or "") for r in out["report"]))  # Google searches wait for the key
        st = self.api.state({})
        self.assertEqual([j["title"] for j in st["jobs"]], ["IT Support Technician"])
        self.assertEqual(st["jobs"][0]["role"], "IT technician")

    def test_scams_never_reach_the_board(self):
        posts = [{"key": "remotive::s1", "title": "IT Support Technician", "company": "A", "location": "USA", "workplace": "remote",
                  "url": "https://a/s1", "description": REAL_DESC},
                 {"key": "remotive::s2", "title": "Help Desk Technician", "company": "B", "location": "USA", "workplace": "remote",
                  "url": "https://b/s2", "description": REAL_DESC + "Interviews are held over Telegram, contact @hr_desk."}]
        with mock.patch.object(boards, "fetch", return_value=posts):
            out = self.api.refresh({})
        counted = [r["scams"] for r in out["report"] if "scams" in r]
        self.assertTrue(counted and all(n == 1 for n in counted), out["report"])  # every board ran the same two posts
        self.assertEqual([j["title"] for j in self.api.state({})["jobs"]], ["IT Support Technician"])

    def test_scams_already_saved_are_closed(self):
        path = os.path.join(self.dir.name, "jobboard.db")
        self.api.state({})
        self.api.run_in_db(lambda: (self.api.con.execute(
            "INSERT INTO jobs (key, title, company, location, work_model, description, first_seen, last_seen) VALUES (?,?,?,?,?,?,?,?)",
            ("x:1", "IT Technician", "C", "Washington, DC", "onsite", REAL_DESC + "Text us on WhatsApp to get hired.", "2026-11-01", "2026-11-01")),
            self.api.con.execute("DELETE FROM settings WHERE key = 'scam_v1'"), self.api.con.commit()))
        again = JobBoardApi(path)  # opening the board again runs the one-time cleanup
        self.addCleanup(again.close)
        self.assertEqual(again.state({})["jobs"], [])

    def test_jooble_key_and_searches(self):
        st = self.api.state({})
        self.assertEqual(len([s for s in st["sources"] if s["kind"] == "jooble"]), 6)
        self.assertEqual([s["slug"] for s in st["sources"] if s["kind"] == "jobicy"], ["supporting"])
        self.assertFalse(st["jooble_key"])
        with self.assertRaises(JobBoardError):
            self.api.do("jooble_key", {"key": "bad key!"})
        self.assertTrue(self.api.do("jooble_key", {"key": "0a1b2c3d-4e5f-6789-abcd-ef0123456789"})["jooble_key"])
        self.assertNotIn("0a1b2c3d-4e5f", json.dumps(self.api.state({})))  # never sent to the page
        seen = {}
        with mock.patch.object(boards, "fetch", side_effect=lambda k, s, key=None: (seen.setdefault(k, key), [])[1]):
            self.api.refresh({})
        self.assertEqual(seen["jooble"], "0a1b2c3d-4e5f-6789-abcd-ef0123456789")
        self.assertIsNone(seen.get("remotive"))
        self.assertFalse(self.api.do("jooble_key", {"key": ""})["jooble_key"])

    def test_google_key(self):
        with self.assertRaises(JobBoardError):
            self.api.do("google_key", {"key": "not a key!"})
        self.assertTrue(self.api.do("google_key", {"key": "a" * 64})["google_key"])
        self.assertNotIn("a" * 64, json.dumps(self.api.state({})))  # never sent to the page
        seen = []
        with mock.patch.object(boards, "fetch", side_effect=lambda k, s, key=None: seen.append(key) or []):
            self.api.refresh({})
        self.assertIn("a" * 64, seen)
        self.assertFalse(self.api.do("google_key", {"key": ""})["google_key"])

    def test_add_google_search(self):
        out = self.api.do("source_add", {"kind": "google", "slug": "Computer Technician @ Washington, DC", "fetch": False})
        src = [s for s in self.api.state({})["sources"] if s["id"] == out["id"]][0]
        self.assertEqual(src["slug"], "Computer Technician @ Washington, DC")
        with self.assertRaises(JobBoardError):
            self.api.do("source_add", {"kind": "google", "slug": "@ remote"})


if __name__ == "__main__":
    unittest.main()
