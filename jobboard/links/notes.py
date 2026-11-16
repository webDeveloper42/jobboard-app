"""A note for each job, in the Notes tab: who you talked to, what they asked, what to ask them, the pay discussed.

The note is made through the Notes app's own storage code (~/notes-app/store.py) and tagged "job". It links back
to the job on the Jobs board, and the board remembers which note belongs to which job, so the button reopens it.
"""
import html
import importlib.util
import os
from pathlib import Path

_MODULE = None


class NotesLinkError(RuntimeError):
    pass


def _store(path=None):
    """The Notes app's store module (loaded under its own name, so it can't clash with other apps' modules)."""
    global _MODULE
    app = Path(os.environ.get("NOTES_APP_DIR") or Path.home() / "notes-app")
    if not (app / "store.py").exists():
        raise NotesLinkError("the Notes app isn't installed")
    if _MODULE is None:
        spec = importlib.util.spec_from_file_location("notes_app_store", app / "store.py")
        _MODULE = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_MODULE)
    if path:
        _MODULE.DB_PATH = str(path)
    elif os.environ.get("NOTES_DB"):
        _MODULE.DB_PATH = os.environ["NOTES_DB"]
    return _MODULE


def outline(job):
    e = lambda v: html.escape(str(v or ""))  # noqa: E731
    where = " · ".join(x for x in (e(job.get("location")), f'<a href="{e(job.get("url"))}">the posting</a>' if job.get("url") else "") if x)
    return (f'<p><b>Job:</b> <a href="/jobs/#job/{int(job["id"])}">{e(job.get("title"))} at {e(job.get("company"))}</a>{" · " + where if where else ""}</p>'
            "<h2>Interviewer</h2><p><br></p>"
            "<h2>Questions they asked</h2><ul><li><br></li></ul>"
            "<h2>Questions to ask them</h2><ul><li><br></li></ul>"
            "<h2>Salary discussed</h2><p><br></p>"
            "<h2>Notes</h2><p><br></p>")


def exists(note_id, path=None):
    store = _store(path)
    conn = store.connect()
    try:
        row = conn.execute("SELECT trashed_at FROM notes WHERE id = ?", (note_id,)).fetchone()
        return bool(row) and row["trashed_at"] is None
    finally:
        conn.close()


def make(job, path=None):
    """A new note for the job. Returns its id."""
    store = _store(path)
    store.init_db()
    conn = store.connect()
    try:
        with conn:
            settings = store.load_settings()
            row = conn.execute("SELECT id FROM notebooks WHERE id = ?", (settings.get("default_notebook"),)).fetchone() if settings.get("default_notebook") else None
            nb = row["id"] if row else conn.execute("SELECT id FROM notebooks ORDER BY created LIMIT 1").fetchone()["id"]
            title = f"Interview notes — {job.get('company') or ''} — {job.get('title') or ''}".strip(" —")[:300]
            return store.create_note(conn, {"notebook_id": nb, "title": title, "content": outline(job), "tags": ["job"]})
    finally:
        conn.close()
