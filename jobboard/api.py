"""JobBoardApi: the one object the web page and the terminal talk to.

It owns the database and the services (see services/__init__.py for the list) and maps each page action to the
service method that does it. To add an action:
  1. write the method on the right service (take a dict `d`, check inputs with `validation`, use `self.run` for the
     database),
  2. add one line to ACTIONS below,
  3. call it from the page with `api.act("your_action", {...})` and add a test.
"""
from .errors import JobBoardError
from .services import (ApplicationService, BoardService, FeedService, JobCatalog, Migrations, ProfileService, ResumeService,
                       SettingsService, WritingService)
from .storage import db
from .storage.database import Database

# action name (what the page sends) -> (service, method). Every method takes the request's data dict.
ACTIONS = {
    "profile": ("profiles", "save"),
    "resume_text": ("resumes", "set_text"), "resume_file": ("resumes", "set_file"),
    "resume_add": ("resumes", "add"), "resume_use": ("resumes", "use"), "resume_update": ("resumes", "update"), "resume_remove": ("resumes", "remove"),
    "source_add": ("boards", "add"), "source_toggle": ("boards", "toggle"), "source_remove": ("boards", "remove"),
    "refresh": ("boards", "refresh"), "full_post": ("boards", "full_post"),
    "google_key": ("settings", "set_google_key"), "jooble_key": ("settings", "set_jooble_key"),
    "sheets_sync": ("settings", "set_sheets_sync"), "serpapi_usage": ("settings", "serpapi_usage"),
    "hide_rule_add": ("settings", "add_hide_rule"), "hide_rule_remove": ("settings", "remove_hide_rule"),
    "save": ("applications", "save"), "status": ("applications", "set_status"), "track": ("applications", "update"),
    "untrack": ("applications", "untrack"), "add_job": ("applications", "add_job"),
    "tailor": ("writing", "tailor"), "letter": ("writing", "letter"), "ask": ("writing", "ask"), "chat_clear": ("writing", "chat_clear"),
    "doc_save": ("writing", "doc_save"), "doc_delete": ("writing", "doc_delete"), "doc_to_docs": ("writing", "doc_to_docs"),
    "docs_templates": ("writing", "docs_templates"), "job_note": ("writing", "job_note"),
}


class JobBoardApi:
    def __init__(self, path=None, focus=True, sheets=None, docs=None, notes=None):
        """`path` is the database file (your real one when left out). `focus=False` turns off the role and place rules
        (only the general engine tests do that). `sheets`, `docs`, `notes` point at those apps' databases; with a
        custom `path` they default to None, so a test can never write to your real Sheets, Docs or Notes."""
        self.path = str(path or db.default_path())
        self.focus = focus
        self.sheets = sheets if sheets is not None else (None if path else "")
        self.docs = docs if docs is not None else (None if path else "")
        self.notes = notes if notes is not None else (None if path else "")
        self.db = Database(self.path, on_open=self._on_open)
        self.profiles = ProfileService(self)
        self.resumes = ResumeService(self)
        self.settings = SettingsService(self)
        self.catalog = JobCatalog(self)
        self.boards = BoardService(self)
        self.feed = FeedService(self)
        self.applications = ApplicationService(self)
        self.writing = WritingService(self)
        self.migrations = Migrations(self)

    def _on_open(self, database):
        # hidden_by_rule(company, title, description) in SQL: 1 when a job breaks one of your hide rules.
        database.con.create_function("hidden_by_rule", 3, self.settings.rule_hit)
        if self.focus:
            self.migrations.focus_setup()
            self.migrations.upgrade()

    # ---- actions from the page

    def do(self, action, data):
        """Run a page action by name (see ACTIONS) and return its result. Unknown actions raise JobBoardError."""
        data = data or {}
        if action == "hide":
            return self.applications.set_hidden(data, True)
        if action == "unhide":
            return self.applications.set_hidden(data, False)
        if action == "rescore":
            return self.catalog.rescore()
        if action not in ACTIONS:
            raise JobBoardError("Unknown action")
        service, method = ACTIONS[action]
        return getattr(getattr(self, service), method)(data)

    # ---- reading

    def profile(self):
        return self.feed.profile()

    def state(self, filters=None):
        return self.feed.state(filters)

    def job(self, job_id):
        return self.feed.job(job_id)

    def chat_history(self, job_id=None):
        return self.feed.chat_history(job_id)

    def export_csv(self):
        return self.applications.export_csv()

    # ---- used by the morning run and the terminal

    def refresh(self, d=None):
        return self.boards.refresh(d)

    def full_post(self, d):
        return self.boards.full_post(d)

    def role_sql(self):
        return self.resumes.role_sql()

    def visible_sql(self):
        """WHERE clause for jobs you should see: the primary resume's roles, minus your hide rules."""
        return self.feed.visible_sql()

    def run_in_db(self, fn, *args):
        """Run `fn` on the database thread (see storage/database.py)."""
        return self.db.run(fn, *args)

    @property
    def con(self):
        return self.db.con

    def close(self):
        self.db.close()
