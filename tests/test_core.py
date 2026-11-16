"""Run: python3 -m unittest discover -s tests. No network and no Ollama: boards and the model are stubbed."""
import io
import os
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["OLLAMA_HOST"] = "http://127.0.0.1:9"  # nothing listens there, so AI falls back to templates

from jobboard import boards  # noqa: E402
from jobboard.rules import match, text  # noqa: E402
from jobboard.writing import ai, resume  # noqa: E402
from jobboard import JobBoardApi, JobBoardError  # noqa: E402

ai.HOST = "http://127.0.0.1:9"

RESUME = """JANE DOE
Backend Software Engineer
jane@example.com | (555) 123-4567

Software Engineer, Acme — 2021 – Present
• Built REST APIs in Python and FastAPI on AWS with PostgreSQL
• Docker, Kubernetes, CI/CD with GitHub Actions
Developer, Beta — 2019 – 2021
• SQL and Airflow pipelines
"""

POSTS = [
    {"key": "greenhouse:acme:1", "title": "Senior Backend Engineer", "company": "Acme", "location": "Remote (US)", "url": "https://x/1",
     "apply_url": "https://x/1/apply", "description": "We need 5+ years of experience with Python, PostgreSQL, AWS and Kubernetes. "
     "Salary range $150,000 - $180,000. We are unable to sponsor visas.", "posted": "2026-11-01"},
    {"key": "greenhouse:acme:2", "title": "Account Executive", "company": "Acme", "location": "New York, NY", "url": "https://x/2",
     "description": "Own a sales quota. Salesforce, negotiation, CRM. On-site in our NYC office.", "posted": "2026-11-02"},
    {"key": "greenhouse:acme:3", "title": "Software Engineer, Backend", "company": "Acme", "location": "Austin, TX (Hybrid)", "url": "https://x/3",
     "description": "Hybrid role. Python, FastAPI, Docker, SQL. 3+ years experience. $60/hr.", "posted": "2026-11-03"},
]


class Text(unittest.TestCase):
    def test_skills_are_found_with_aliases_and_context(self):
        found = text.find_skills("Experience with k8s, Postgres, ReactJS and Node.js. Languages: Python, Go, R.")
        for s in ("Kubernetes", "PostgreSQL", "React", "Node.js", "Python", "Go", "R"):
            self.assertIn(s, found)
        self.assertNotIn("Go", text.find_skills("Let's go to the office."))
        self.assertNotIn("Java", text.find_skills("Strong JavaScript skills"))

    def test_salary_forms(self):
        self.assertEqual(text.salary_from("Base pay $120K – $150K")[:2], (120000, 150000))
        self.assertEqual(text.salary_from("$55/hr")[:2], (114400, 114400))
        self.assertEqual(text.salary_from("$1,500 - $2,000 per month")[:2], (18000, 24000))
        self.assertEqual(text.salary_from("We raised $10M in our Series A")[:2], (None, None))

    def test_level_years_model_sponsorship(self):
        self.assertEqual(text.level_of("Sr. Data Engineer"), "senior")
        self.assertEqual(text.level_of("Account Manager"), "mid")
        self.assertEqual(text.level_of("Engineering Manager"), "manager")
        self.assertEqual(text.level_of("Software Engineering Intern"), "intern")
        self.assertEqual(text.years_required("At least 3+ years of professional experience"), 3)
        self.assertEqual(text.work_model("Remote - US"), "remote")
        self.assertEqual(text.work_model("Hybrid, 3 days in office"), "hybrid")
        self.assertEqual(text.sponsorship("We are unable to sponsor visas for this role"), "no")
        self.assertEqual(text.sponsorship("We will sponsor H-1B visas"), "yes")
        self.assertEqual(text.resume_years(RESUME, 2026), 7)

    def test_html_and_mojibake(self):
        self.assertEqual(text.html_to_text("&lt;p&gt;Hi &amp;amp; bye&lt;/p&gt;"), "Hi & bye")
        self.assertIn("• one", text.html_to_text("<ul><li>one</li><li>two</li></ul>"))
        self.assertEqual(text.fix_mojibake("Sothebyâ\u0080\u0099s"), "Sotheby’s")

    def test_title_similarity(self):
        self.assertGreater(text.title_similarity("Sr. Software Developer", "Software Engineer"), 0.9)
        self.assertEqual(text.title_similarity("Account Executive", "Software Engineer"), 0)


class Matching(unittest.TestCase):
    def profile(self, **over):
        p = {"skills": ["Python", "PostgreSQL", "AWS", "Docker", "FastAPI", "SQL"], "target_titles": ["Backend Engineer"], "headline": "",
             "level": "mid", "years_exp": 5, "work_models": ["remote", "hybrid"], "locations": ["Austin"], "min_salary": 120000,
             "needs_sponsorship": False, "resume_text": RESUME}
        p.update(over)
        return p

    def test_good_fit_beats_wrong_role(self):
        good = match.enrich(dict(POSTS[0]))
        bad = match.enrich(dict(POSTS[1]))
        g, gd = match.score(good, self.profile())
        b, _ = match.score(bad, self.profile())
        self.assertGreater(g, 70)
        self.assertLess(b, 40)
        self.assertIn("Python", gd["matched"])
        self.assertTrue(gd["why"])

    def test_deal_breakers_cap_the_score(self):
        job = match.enrich(dict(POSTS[0]))
        free, _ = match.score(job, self.profile())
        visa, vd = match.score(job, self.profile(needs_sponsorship=True))
        self.assertLess(visa, free)
        self.assertIn("Says it won't sponsor a visa", vd["flags"])
        onsite = match.enrich(dict(POSTS[2], description="On-site only. Python, FastAPI."))
        onsite["work_model"] = "onsite"
        self.assertLessEqual(match.score(onsite, self.profile())[0], 50)

    def test_coverage_reads_the_resume(self):
        job = match.enrich(dict(POSTS[0]))
        cov = match.keyword_coverage(job, RESUME)
        self.assertIn("Python", cov["present"])
        self.assertGreater(cov["percent"], 50)

    def test_coverage_reads_a_resume_with_words_split_apart(self):
        # What some PDF readers make of a resume: spaces in the middle of words.
        split = ("Car eer chang er mo ving fr om f our y ear s in high- volume r estaur ants in to IT , with hands- on e xperience. "
                 "Brings y ear s of cus tomer ser vice and clear c ommunic ation. Support: tr oubleshooting , Activ e Dir ect ory basics, "
                 "r emot e access, documen ting fix es. Systems: macOS, Windo ws, Linux, Bash. Tools: Git, Mong oDB , MySQL , "
                 "Micr osoft Ex cel, Google W ork space.")
        self.assertTrue(text.looks_split(split))
        self.assertFalse(text.looks_split(RESUME * 3))
        job = {"skills": ["Windows", "Active Directory", "Customer Service", "Excel", "MongoDB", "Google Workspace",
                          "Remote Access", "Documentation", "Communication", "Troubleshooting", "Kubernetes", "Hardware"]}
        cov = match.keyword_coverage(job, split)
        self.assertEqual(cov["absent"], ["Kubernetes", "Hardware"])
        # Normal text isn't read loosely, so "g it" doesn't turn into Git.
        self.assertFalse(text.mentions("Git", "a big it department"))
        self.assertTrue(text.mentions("Python Scripting", "Pyth on Scr ipting " + split))  # your own typed skills too


def make_docx(path, lines):
    body = "".join(f"<w:p><w:r><w:t>{ln}</w:t></w:r></w:p>" for ln in lines)
    xml = f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)


def make_pdf(path, lines, compress=True, per_letter=False):
    if per_letter:  # how Chrome (Skia) writes text: every letter placed with its own small move
        content = "BT /F1 11 Tf " + " ".join(f"1 0 0 -1 72 {40 + 14 * i} Tm " + " 5.5 0 Td ".join(f"({c}) Tj" for c in ln) for i, ln in enumerate(lines) if ln) + " ET"
    else:
        content = "BT /F1 11 Tf 72 720 Td " + " ".join(f"({ln}) Tj 0 -14 Td" for ln in lines) + " ET"
    data = zlib.compress(content.encode()) if compress else content.encode()
    filt = " /Filter /FlateDecode" if compress else ""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
            None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    for i, o in enumerate(objs, 1):
        out.write(f"{i} 0 obj\n".encode())
        if o is None:
            out.write(f"<< /Length {len(data)}{filt} >>\nstream\n".encode() + data + b"\nendstream\n")
        else:
            out.write(o.encode() + b"\n")
        out.write(b"endobj\n")
    out.write(b"trailer << /Root 1 0 R >>\n%%EOF")
    Path(path).write_bytes(out.getvalue())


class Resumes(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.lines = RESUME.replace("—", "-").replace("–", "-").replace("•", "-").splitlines() * 2

    def test_docx(self):
        p = os.path.join(self.dir.name, "r.docx")
        make_docx(p, self.lines)
        self.assertIn("FastAPI", resume.read(p))

    def test_pdf_plain_and_compressed(self):
        for compress in (False, True):
            p = os.path.join(self.dir.name, f"r{compress}.pdf")
            make_pdf(p, [ln.replace("(", "").replace(")", "") for ln in self.lines], compress)
            out = resume.read(p)
            self.assertIn("Kubernetes", out)
            self.assertIn("Backend Software Engineer", out)

    def test_pdf_with_every_letter_placed_separately(self):
        p = os.path.join(self.dir.name, "chrome.pdf")
        make_pdf(p, [ln.replace("(", "").replace(")", "") for ln in self.lines], True, per_letter=True)
        out = resume.read(p)
        self.assertIn("Backend Software Engineer", out)
        self.assertIn("Kubernetes", out)

    def test_it_support_resume(self):
        found = text.find_skills("Tier 1 help desk. Reset passwords, Active Directory, Windows and macOS, SSH, ticketing in ServiceNow. 11/2022 – 10/2025")
        for s in ("Technical Support", "User Management", "Active Directory", "Windows", "macOS", "SSH", "Ticketing Systems"):
            self.assertIn(s, found)
        self.assertEqual(text.resume_years("Kitchen, 11/2022 – 10/2025", 2026), 3)

    def test_unreadable_files_say_why(self):
        p = os.path.join(self.dir.name, "x.png")
        Path(p).write_bytes(b"\x89PNG")
        with self.assertRaises(resume.ResumeError):
            resume.read(p)


class Engine(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.api = JobBoardApi(os.path.join(self.dir.name, "jobboard.db"), focus=False)
        self.addCleanup(self.api.close)
        patch = mock.patch.object(boards, "fetch", side_effect=self.fake_fetch)
        patch.start()
        self.addCleanup(patch.stop)
        self.posts = [dict(p) for p in POSTS]

    def fake_fetch(self, kind, slug, key=None):
        if slug == "broken":
            raise boards.SourceError("the board answered 500")
        return [dict(p) for p in self.posts]

    def test_whole_flow(self):
        out = self.api.do("resume_text", {"text": RESUME})
        self.assertIn("Python", out["found_skills"])
        self.assertEqual(out["name"], "Jane Doe")
        self.assertEqual(out["email"], "jane@example.com")
        self.api.do("profile", {"target_titles": "Backend Engineer", "work_models": ["remote", "hybrid"], "locations": "Austin", "min_salary": "120k"})
        self.assertEqual(self.api.profile()["min_salary"], 120000)
        got = self.api.do("source_add", {"kind": "greenhouse", "slug": "https://boards.greenhouse.io/acme"})
        self.assertEqual(got["report"][0]["new"], 3)
        st = self.api.state({})
        titles = [j["title"] for j in st["jobs"]]
        self.assertEqual(titles[-1], "Account Executive")  # the wrong role ranks last
        top = st["jobs"][0]
        self.api.do("save", {"id": top["id"]})
        self.assertNotIn(top["id"], [j["id"] for j in self.api.state({})["jobs"]])  # tracked jobs leave Recommended
        self.api.do("status", {"id": top["id"], "status": "applied"})
        self.api.do("track", {"id": top["id"], "next_step": "Follow up", "next_date": "2026-11-20"})
        st = self.api.state({})
        self.assertEqual(st["board"]["applied"][0]["next_step"], "Follow up")
        self.assertEqual(st["insights"]["applied"], 1)
        job = self.api.job(top["id"])
        self.assertEqual([e["kind"] for e in job["events"]][-2:], ["applied", "saved"])
        # Without Ollama, tailoring and letters still give a starting point.
        letter = self.api.do("letter", {"id": top["id"]})
        self.assertIn("Acme", letter["body"])
        self.assertEqual(letter["model"], "")
        tailored = self.api.do("tailor", {"id": top["id"]})
        self.assertIn("KEYWORDS", tailored["body"])
        with self.assertRaises(JobBoardError):
            self.api.do("ask", {"q": "hi"})
        self.assertIn("Follow up", self.api.export_csv().decode())

    def test_refetch_updates_and_closes(self):
        self.api.do("source_add", {"kind": "lever", "slug": "acme"})
        first = self.api.state({})["total"]
        self.posts = self.posts[:2]
        self.posts[0]["title"] = "Senior Backend Engineer II"
        out = self.api.refresh({})
        self.assertEqual(out["new"], 0)
        st = self.api.state({})
        self.assertEqual(st["total"], first - 1)
        self.assertIn("Senior Backend Engineer II", [j["title"] for j in st["jobs"]])

    def test_filters(self):
        self.api.do("profile", {"skills": "Python", "target_titles": "Backend Engineer"})
        self.api.do("source_add", {"kind": "ashby", "slug": "acme"})
        self.assertEqual({j["work_model"] for j in self.api.state({"work_model": "remote"})["jobs"]}, {"remote"})
        self.assertTrue(all(j["salary_max"] for j in self.api.state({"salary": "1"})["jobs"]))
        self.assertEqual(len(self.api.state({"q": "Account"})["jobs"]), 1)
        hid = self.api.state({"q": "Account"})["jobs"][0]["id"]
        self.api.do("hide", {"id": hid})
        self.assertEqual(len(self.api.state({"q": "Account"})["jobs"]), 0)
        self.assertEqual(len(self.api.state({"view": "hidden"})["jobs"]), 1)

    def test_bad_input_is_explained(self):
        for action, data in (("status", {"id": 999, "status": "applied"}), ("status", {"id": "x", "status": "applied"}),
                             ("source_add", {"kind": "greenhouse", "slug": "bad slug!"}), ("profile", {"years_exp": "lots"}),
                             ("add_job", {"title": "", "company": "x"}), ("add_job", {"title": "x", "company": "y", "url": "javascript:alert(1)"}),
                             ("nope", {})):
            with self.assertRaises(JobBoardError, msg=action):
                self.api.do(action, data)

    def test_a_failing_board_doesnt_stop_others(self):
        self.api.do("source_add", {"kind": "greenhouse", "slug": "broken", "fetch": False})
        self.api.do("source_add", {"kind": "greenhouse", "slug": "fine", "fetch": False})
        out = self.api.refresh({})
        errors = [r for r in out["report"] if r.get("error")]
        self.assertEqual(len(errors), 1)
        self.assertEqual(out["new"], 3)

    def test_manual_job(self):
        out = self.api.do("add_job", {"title": "Data Analyst", "company": "Local Co", "url": "https://example.com/j", "description": "SQL, Excel, Tableau. Remote."})
        self.assertEqual(self.api.state({})["board"]["saved"][0]["job_id"], out["id"])



class Paths(unittest.TestCase):
    def test_your_data_lives_in_the_repo_data_folder(self):
        """Moving storage/db.py once pointed the app at a new, empty database. This keeps it pointed at <repo>/data."""
        from jobboard.storage import db
        with mock.patch.dict(os.environ, {"JOBBOARD_DATA_DIR": ""}):
            self.assertEqual(db.default_path(), Path(__file__).resolve().parent.parent / "data" / "jobboard.db")


if __name__ == "__main__":
    unittest.main()
