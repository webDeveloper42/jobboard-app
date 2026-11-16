"""Local SQLite storage: your profile, job boards, jobs with their match scores, applications, documents and chat.

Dates are ISO strings: 'YYYY-MM-DD' for days and 'YYYY-MM-DDTHH:MM:SS' for moments, so other apps
(and the data hub) can read them without knowing anything about this one.
"""
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from .. import config

STATUSES = ["saved", "applied", "interviewing", "offer", "rejected", "withdrawn"]
STATUS_NAMES = {"saved": "Saved", "applied": "Applied", "interviewing": "Interviewing", "offer": "Offer", "rejected": "Rejected", "withdrawn": "Withdrawn"}
WORK_MODELS = ["remote", "hybrid", "onsite"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '', headline TEXT NOT NULL DEFAULT '', links TEXT NOT NULL DEFAULT '',
    resume_text TEXT NOT NULL DEFAULT '', resume_file TEXT NOT NULL DEFAULT '',
    target_titles TEXT NOT NULL DEFAULT '[]',      -- JSON list of job titles you want
    skills TEXT NOT NULL DEFAULT '[]',             -- JSON list
    years_exp INTEGER,                              -- years of experience
    level TEXT NOT NULL DEFAULT '',                -- intern, entry, mid, senior, lead, manager, director, executive
    work_models TEXT NOT NULL DEFAULT '["remote","hybrid","onsite"]',
    locations TEXT NOT NULL DEFAULT '[]',          -- cities or regions you'd work in
    min_salary INTEGER,                             -- yearly dollars
    needs_sponsorship INTEGER NOT NULL DEFAULT 0,
    updated TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,                             -- greenhouse, lever, ashby, remotive, remoteok, arbeitnow, manual
    slug TEXT NOT NULL DEFAULT '',                  -- the company's board name, or a search term
    name TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    last_fetch TEXT, last_count INTEGER, last_error TEXT,
    UNIQUE (kind, slug)
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,                       -- kind:slug:board id, so a refetch updates instead of duplicating
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    title TEXT NOT NULL, company TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '',
    work_model TEXT NOT NULL DEFAULT 'unknown', employment_type TEXT NOT NULL DEFAULT '', department TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '', apply_url TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    salary_min INTEGER, salary_max INTEGER, salary_text TEXT NOT NULL DEFAULT '',
    level TEXT NOT NULL DEFAULT '', years_min INTEGER,
    skills TEXT NOT NULL DEFAULT '[]',
    sponsorship TEXT NOT NULL DEFAULT 'unknown',    -- yes, no, unknown
    posted TEXT, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,              -- 0 once the board stops listing it
    hidden INTEGER NOT NULL DEFAULT 0,              -- you marked it not interested
    score INTEGER, score_detail TEXT NOT NULL DEFAULT '{}', scored_at TEXT
);
CREATE INDEX IF NOT EXISTS jobs_score ON jobs(active, hidden, score DESC);
CREATE INDEX IF NOT EXISTS jobs_posted ON jobs(posted);
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'saved',
    saved_at TEXT NOT NULL, applied_at TEXT, updated TEXT NOT NULL,
    next_step TEXT NOT NULL DEFAULT '', next_date TEXT,   -- what to do next, and by when (YYYY-MM-DD)
    notes TEXT NOT NULL DEFAULT '', contact TEXT NOT NULL DEFAULT '', salary_offer INTEGER
);
CREATE TABLE IF NOT EXISTS app_events (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    at TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS app_events_job ON app_events(job_id);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,                             -- tailored_resume, cover_letter
    body TEXT NOT NULL, model TEXT NOT NULL DEFAULT '', created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat (
    id INTEGER PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    role TEXT NOT NULL, content TEXT NOT NULL, at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS resumes (                 -- one row per resume; the primary one's fields are also what the profile holds
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    roles TEXT NOT NULL DEFAULT '[]',               -- JSON list of the board's role ids this resume is for; empty means every role
    resume_text TEXT NOT NULL DEFAULT '', resume_file TEXT NOT NULL DEFAULT '',
    skills TEXT NOT NULL DEFAULT '[]', target_titles TEXT NOT NULL DEFAULT '[]', headline TEXT NOT NULL DEFAULT '',
    created TEXT NOT NULL DEFAULT '', updated TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS geo (                     -- places looked up on OpenStreetMap, so each is asked once
    query TEXT PRIMARY KEY, lat REAL, lon REAL, at TEXT NOT NULL
);
"""

# Columns added after the first release. connect() adds any that an older database is missing.
ADDED_COLUMNS = [
    ("jobs", "fingerprint", "TEXT NOT NULL DEFAULT ''"),   # same title + company + place, for merging one job seen on two boards
    ("jobs", "links", "TEXT NOT NULL DEFAULT '[]'"),       # [{"via": "Jooble", "url": ...}] the other boards that list it
    ("jobs", "reposts", "INTEGER NOT NULL DEFAULT 0"),     # times it came back after closing, or was listed again as new
    ("jobs", "travel", "TEXT NOT NULL DEFAULT '{}'"),      # {"km", "transit", "drive"} from Suitland, when the post gives an address
    ("jobs", "full_text", "INTEGER NOT NULL DEFAULT 0"),
    ("profile", "home_address", "TEXT NOT NULL DEFAULT ''"),  # only for commute directions; never on resumes or letters   # 1 once the full post was fetched (or tried) for a board that sends snippets
]

DEFAULT_SOURCES = [
    ("remotive", "", "Remotive (remote jobs)", 1),
    ("remoteok", "", "Remote OK (remote jobs)", 1),
    ("arbeitnow", "", "Arbeitnow (Europe)", 0),
]


def now():
    return datetime.now().replace(microsecond=0).isoformat()


def today():
    return datetime.now().date().isoformat()


def default_path():
    return Path(os.environ.get(config.ENV_DATA_DIR) or config.DATA_DIR) / "jobboard.db"


def connect(path=None):
    path = Path(path or default_path())
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fresh = not path.exists()
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    from ..rules import focus  # noqa: PLC0415
    con.create_function("job_role", 1, lambda title: focus.category(title) or "", deterministic=True)   # for WHERE job_role(title) IN (...)
    con.create_function("company_key", 1, focus.company_key, deterministic=True)                     # "Target Corp" -> "target"
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.executescript(SCHEMA)
    for table, column, decl in ADDED_COLUMNS:
        if column not in {r[1] for r in con.execute(f"PRAGMA table_info({table})")}:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    con.execute("CREATE INDEX IF NOT EXISTS jobs_fingerprint ON jobs(fingerprint)")
    con.execute("INSERT OR IGNORE INTO profile (id, updated) VALUES (1, ?)", (now(),))
    if fresh:
        con.executemany("INSERT OR IGNORE INTO sources (kind, slug, name, enabled) VALUES (?, ?, ?, ?)", DEFAULT_SOURCES)
        os.chmod(path, 0o600)
    con.commit()
    return con


def loads(value, default):
    try:
        out = json.loads(value) if value else default
    except ValueError:
        return default
    return out if isinstance(out, type(default)) else default


def profile(con):
    row = dict(con.execute("SELECT * FROM profile WHERE id = 1").fetchone())
    for key, default in (("target_titles", []), ("skills", []), ("work_models", []), ("locations", [])):
        row[key] = loads(row[key], default)
    row["needs_sponsorship"] = bool(row["needs_sponsorship"])
    return row


def job_row(row):
    job = dict(row)
    job["skills"] = loads(job.get("skills"), [])
    job["score_detail"] = loads(job.get("score_detail"), {})
    if "links" in job:
        job["links"] = loads(job.get("links"), [])
    if "travel" in job:
        job["travel"] = loads(job.get("travel"), {})
    return job


def setting(con, key, default=None):
    row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(con, key, value):
    con.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))


def log_event(con, job_id, kind, detail=""):
    con.execute("INSERT INTO app_events (job_id, at, kind, detail) VALUES (?, ?, ?, ?)", (job_id, now(), kind, detail))
