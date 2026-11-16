"""`jobboard serve`: the Jobs page on its own, without the home dashboard. Listens on this computer only.

Open http://127.0.0.1:8820/jobs/ (or through an SSH tunnel). It serves the same page and API as the dashboard
(see http_routes.py). What it doesn't have: the dashboard's other tabs, so "Open in Docs" and "Notes" still write to
those apps but their links point at the dashboard.
"""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from . import config
from .api import JobBoardApi
from .http_routes import WEB_DIR, JobsRoutes, Response

LOOPBACK = {"localhost", "127.0.0.1", "::1", "[::1]"}
MAX_UPLOAD = 15 * 1024 * 1024
CSP = ("default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; "
       "base-uri 'none'; frame-ancestors 'none'; form-action 'none'")


class UploadRefused(ValueError):
    """An upload that isn't allowed. The message is shown to you."""


class Uploads:
    """Resume files sent from the page, kept in <data>/uploads."""

    def __init__(self, folder):
        self.folder = folder

    def save(self, stream, name, length):
        if length <= 0 or length > MAX_UPLOAD:
            raise UploadRefused("Resumes must be under 15 MB")
        safe = re.sub(r"[^A-Za-z0-9._ -]+", "_", (name or "").rsplit("/", 1)[-1]).strip(" .")[:120] or "resume"
        if not re.search(r"\.(pdf|docx|txt|md)$", safe, re.I):
            raise UploadRefused("Upload a .pdf, .docx, .txt or .md file")
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.folder / safe).write_bytes(stream.read(length))
        return {"name": safe}

    def resolve(self, name):
        path = (self.folder / str(name or "")).resolve()
        if path.parent != self.folder.resolve() or not path.is_file():
            raise UploadRefused("That file wasn't uploaded here")
        return str(path)


def make_handler(routes, uploads):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _send(self, response):
            body = response.body if isinstance(response.body, bytes) else json.dumps(response.body).encode()
            try:
                self.send_response(response.status)
                self.send_header("Content-Type", response.content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Content-Security-Policy", CSP)
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Cache-Control", "no-store")
                if response.filename:
                    self.send_header("Content-Disposition", f'attachment; filename="{response.filename}"')
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True

        def _host_ok(self):
            """Only this computer's own names, so a web page can't reach the server through DNS rebinding."""
            return (self.headers.get("Host") or "").lower().rsplit(":", 1)[0] in LOOPBACK

        def _same_origin(self):
            origin = self.headers.get("Origin")
            return not origin or urlsplit(origin).netloc.lower() == (self.headers.get("Host") or "").lower()

        def do_GET(self):
            if not self._host_ok():
                return self._send(Response(403, {"error": "Forbidden"}))
            parts = urlsplit(self.path)
            if parts.path in ("/", "/jobs"):
                self.send_response(302)
                self.send_header("Location", "/jobs/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            if parts.path == "/design/icons.js":   # the dashboard's shared icons; a copy lives in web/vendor
                return self._send(Response(200, (WEB_DIR / "vendor" / "icons.js").read_bytes(), "text/javascript; charset=utf-8"))
            return self._send(routes.get(parts.path, parts.query) or Response(404, {"error": "Not found"}))

        def do_POST(self):
            if not self._host_ok() or not self._same_origin():
                return self._send(Response(403, {"error": "Forbidden"}))
            path = urlsplit(self.path).path
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._send(Response(411, {"error": "Bad request"}))
            if path == "/api/upload":
                self.close_connection = True
                if self.headers.get("X-Capture-Upload") != "1":   # other sites can't set this header without a preflight
                    return self._send(Response(403, {"error": "Forbidden"}))
                name = dict(p.split("=", 1) for p in urlsplit(self.path).query.split("&") if "=" in p).get("path", "")
                try:
                    from urllib.parse import unquote  # noqa: PLC0415
                    return self._send(Response(200, uploads.save(self.rfile, unquote(name), length)))
                except UploadRefused as e:
                    return self._send(Response(400, {"error": str(e)}))
            if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
                return self._send(Response(415, {"error": "Send JSON"}))
            if length > MAX_UPLOAD:
                return self._send(Response(413, {"error": "Too large"}))
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._send(Response(400, {"error": "That wasn't JSON"}))
            return self._send(routes.post(path, data) or Response(404, {"error": "Not found"}))

    return Handler


def make_server(port=8820, api=None, data_dir=None):
    """A ready-to-run server on 127.0.0.1:port (port 0 picks a free one). Call serve_forever() on it."""
    api = api or JobBoardApi()
    uploads = Uploads((data_dir or config.DATA_DIR) / "uploads")
    routes = JobsRoutes(lambda: api, resolve_upload=uploads.resolve)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(routes, uploads))
    server.api = api
    return server


def serve(port=8820):
    server = make_server(port)
    print(f"Jobs page: http://127.0.0.1:{server.server_address[1]}/jobs/  (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.api.close()


def serve_in_background(port=0, api=None, data_dir=None):
    """For tests: start a server on a free port in a thread. Returns (server, base_url)."""
    server = make_server(port, api, data_dir)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"
