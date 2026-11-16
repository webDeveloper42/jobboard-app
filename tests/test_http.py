"""The Jobs page's routes (shared with the dashboard) and the standalone `jobboard serve`. No network beyond localhost."""
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["OLLAMA_HOST"] = "http://127.0.0.1:9"

from jobboard import JobBoardApi  # noqa: E402
from jobboard.http_routes import JobsRoutes  # noqa: E402
from jobboard.server import serve_in_background  # noqa: E402


class Routes(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.api = JobBoardApi(os.path.join(self.dir.name, "jobboard.db"))
        self.addCleanup(self.api.close)
        self.routes = JobsRoutes(lambda: self.api)

    def test_page_and_its_files(self):
        page = self.routes.get("/jobs/")
        self.assertTrue(page.is_html)
        self.assertIn(b'src="/jobs/js/main.js"', page.body)
        self.assertEqual(self.routes.get("/jobs/js/main.js").content_type, "text/javascript; charset=utf-8")
        self.assertEqual(self.routes.get("/jobs/css/blocks/job-card.css").status, 200)
        for bad in ("/jobs/js/../../dev", "/jobs/js/../../jobboard/api.py", "/jobs/js/nope.js", "/jobs/css/x.py"):
            self.assertEqual(self.routes.get(bad).status, 404, bad)
        self.assertIsNone(self.routes.get("/budget/"))          # not ours: the host handles it

    def test_api_reads_writes_and_errors(self):
        self.assertIn("jobs", self.routes.get("/api/jobs/state", "view=recommended").body)
        ok = self.routes.post("/api/jobs/do", {"action": "resume_text", "text": "Jane Doe\nData Entry Clerk\nTyping, Excel, data entry.", "file": "r.txt"})
        self.assertEqual(ok.status, 200)
        self.assertIn("Data Entry", ok.body["skills"])
        self.assertEqual(self.routes.post("/api/jobs/do", {"action": "nope"}).status, 400)
        self.assertEqual(self.routes.get("/api/jobs/job", "id=999").status, 400)
        self.assertEqual(self.routes.get("/api/jobs/nothing").status, 404)
        csv = self.routes.get("/api/jobs/export")
        self.assertEqual((csv.status, csv.filename), (200, "applications.csv"))
        self.assertEqual(self.routes.post("/api/jobs/resume", {"file": "x"}).status, 400)   # no uploads set up here


class StandaloneServer(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        api = JobBoardApi(os.path.join(self.dir.name, "jobboard.db"))
        self.server, self.base = serve_in_background(0, api, Path(self.dir.name))
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), api.close()))

    def call(self, method, path, body=None, headers=None):
        data = body if isinstance(body, bytes) or body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def test_page_api_and_resume_upload(self):
        status, body, headers = self.call("GET", "/jobs/")
        self.assertEqual(status, 200)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(self.call("GET", "/design/icons.js")[0], 200)
        json_headers = {"Content-Type": "application/json"}
        self.assertEqual(self.call("POST", "/api/jobs/do", {"action": "rescore"}, json_headers)[0], 200)
        status, body, _ = self.call("POST", "/api/upload?path=resume.txt", b"Jane Doe\nIT Technician\n" + b"Supported Windows users, Active Directory accounts and troubleshooting for a help desk. " * 4,
                                    {"X-Capture-Upload": "1", "Content-Type": "application/octet-stream"})
        self.assertEqual(status, 200)
        status, body, _ = self.call("POST", "/api/jobs/resume", {"file": json.loads(body)["name"], "name": "resume.txt"}, json_headers)
        self.assertEqual(status, 200)
        self.assertIn("Active Directory", json.loads(body)["skills"])

    def test_other_sites_are_refused(self):
        json_headers = {"Content-Type": "application/json"}
        self.assertEqual(self.call("GET", "/jobs/", headers={"Host": "evil.example"})[0], 403)                  # DNS rebinding
        self.assertEqual(self.call("POST", "/api/jobs/do", {"action": "rescore"}, {**json_headers, "Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.call("POST", "/api/jobs/do", b"action=rescore", {"Content-Type": "application/x-www-form-urlencoded"})[0], 415)
        self.assertEqual(self.call("POST", "/api/upload?path=r.txt", b"x", {"Content-Type": "text/plain"})[0], 403)   # no upload header
        self.assertEqual(self.call("POST", "/api/upload?path=evil.sh", b"x", {"X-Capture-Upload": "1"})[0], 400)
        self.assertEqual(self.call("POST", "/api/jobs/resume", {"file": "../../etc/passwd"}, json_headers)[0], 400)


if __name__ == "__main__":
    unittest.main()
