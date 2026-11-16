"""Which URL does what, for the Jobs page. One place, used by both the home dashboard and `jobboard serve`.

    GET  /jobs/                     the page (web/index.html)
    GET  /jobs/js/…, /jobs/css/…    the page's modules and stylesheets (only .js / .css files inside web/)
    GET  /api/jobs/state            everything the page shows (query string = filters)
    GET  /api/jobs/job?id=N         one job in full
    GET  /api/jobs/chat             the coach's chat about your whole search
    GET  /api/jobs/export           your applications as CSV (a download)
    POST /api/jobs/do               {"action": …, …} — any action in api.ACTIONS
    POST /api/jobs/resume           {"file": <uploaded name>, "name": <original name>} — read an uploaded resume

The web server around this (the dashboard, or server.py) checks the Host and Origin headers before calling it.
"""
import re
import traceback
from dataclasses import dataclass
from urllib.parse import parse_qs

from . import config
from .errors import JobBoardError

WEB_DIR = config.REPO_ROOT / "web"
ASSET = re.compile(r"^/jobs/((?:js|css|vendor)/[A-Za-z0-9_./-]+\.(?:js|css))$")
TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".html": "text/html; charset=utf-8"}


@dataclass
class Response:
    status: int
    body: object                      # bytes for files, or a dict / list sent as JSON
    content_type: str = "application/json"
    filename: str = None              # set for downloads

    @property
    def is_html(self):
        return self.content_type.startswith("text/html")


class JobsRoutes:
    def __init__(self, api_factory, web_dir=WEB_DIR, resolve_upload=None):
        """`api_factory()` returns the JobBoardApi to use (called on every request, so the host can swap it, as the
        dashboard's tests do). `resolve_upload(name)` turns an uploaded file's name into its full path, or raises."""
        self.api_factory = api_factory
        self.web_dir = web_dir
        self.resolve_upload = resolve_upload

    @staticmethod
    def handles(path):
        return path.startswith("/jobs/") or path.startswith("/api/jobs/")

    # ---- GET

    def get(self, path, query=""):
        """A Response for a GET, or None when the path isn't one of these routes."""
        if path == "/jobs/":
            return Response(200, (self.web_dir / "index.html").read_bytes(), TYPES[".html"])
        match = ASSET.match(path)
        if match:
            return self._asset(match.group(1))
        if path == "/api/jobs/export":
            return self._guard(lambda: Response(200, self.api_factory().export_csv(), "text/csv; charset=utf-8", "applications.csv"))
        args = {key: values[0] for key, values in parse_qs(query).items()}
        api = self.api_factory
        reads = {"/api/jobs/state": lambda: api().state(args), "/api/jobs/job": lambda: api().job(args.get("id", "")),
                 "/api/jobs/chat": lambda: api().chat_history(None)}
        if path in reads:
            return self._guard(lambda: Response(200, reads[path]()))
        if self.handles(path):
            return Response(404, {"error": "Not found"})
        return None

    def _asset(self, sub):
        root = self.web_dir.resolve()
        target = (self.web_dir / sub).resolve()
        if ".." in sub.split("/") or root not in target.parents or not target.is_file() or target.suffix not in TYPES:
            return Response(404, {"error": "Not found"})
        return Response(200, target.read_bytes(), TYPES[target.suffix])

    # ---- POST

    def post(self, path, data):
        """A Response for a POST with a JSON body (already parsed into `data`), or None for other paths."""
        data = data if isinstance(data, dict) else {}
        if path == "/api/jobs/do":
            return self._guard(lambda: Response(200, self.api_factory().do(data.get("action"), data)))
        if path == "/api/jobs/resume":
            if not self.resolve_upload:
                return Response(400, {"error": "Uploading isn't set up here"})
            return self._guard(lambda: Response(200, self.api_factory().do("resume_file", {"path": self.resolve_upload(data.get("file")), "name": data.get("name")})))
        if self.handles(path):
            return Response(404, {"error": "Not found"})
        return None

    # ---- errors

    @staticmethod
    def _guard(make):
        """Run a route: problems you can fix come back as 400 with their message; anything else as a plain 500."""
        try:
            return make()
        except JobBoardError as e:
            return Response(400, {"error": str(e)})
        except ValueError as e:   # the host's upload check (and other input problems) raise ValueError subclasses
            return Response(400, {"error": str(e) or "That didn't look right"})
        except Exception:  # noqa: BLE001 - a crash must not take the server down; the log has the details
            traceback.print_exc()
            return Response(500, {"error": "Something went wrong. Nothing else was changed. See the server log."})
