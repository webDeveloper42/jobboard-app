"""Job boards: one reader per kind of board, all returning the same job shape (see `http.make_job`).

To add a kind of board:
  1. write `read(slug)` (or `read(slug, key)` for boards needing your API key) in a new module here,
  2. add it to READERS and KINDS below (and to KEYED if it needs a key),
  3. add a test with the network stubbed (`mock.patch.object(boards.http, "get_json", ...)`).

Everything outside this package uses `boards.fetch(kind, slug, key)`.
"""
import re

from . import company_boards, fulltext, google_jobs, http, jooble_search, remote_boards, workday_sites  # noqa: F401 - the modules, for tests and tools
from .company_boards import ashby, greenhouse, lever
from .google_jobs import google, google_apply_link, google_lookup, google_query
from .http import SourceError
from .jooble_search import jooble, jooble_queries
from .remote_boards import arbeitnow, jobicy, remoteok, remotive
from .workday_sites import SITE_PATTERN, WORKDAY_NAMES, workday, workday_site

KINDS = {
    "greenhouse": "Greenhouse company board (slug as in boards.greenhouse.io/<slug>)",
    "lever": "Lever company board (slug as in jobs.lever.co/<slug>)",
    "ashby": "Ashby company board (slug as in jobs.ashbyhq.com/<slug>)",
    "remotive": "Remotive remote jobs (optional search term)",
    "remoteok": "Remote OK remote jobs (optional tag, like python)",
    "arbeitnow": "Arbeitnow jobs, mostly Europe",
    "google": "Google Jobs search (keywords @ place, like: help desk @ Washington, DC, or @ remote)",
    "workday": "Workday career site (site link | search terms, like: gdit.wd5.myworkdayjobs.com/External_Career_Site | help desk Washington OR IT intern)",
    "jobicy": "Jobicy remote jobs in the US (optional industry, like supporting or technical-support)",
    "jooble": "Jooble search (keywords @ place, like: help desk OR IT support @ Washington, DC, or @ remote)",
}

READERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby, "remotive": remotive, "remoteok": remoteok, "arbeitnow": arbeitnow, "google": google, "jooble": jooble, "jobicy": jobicy, "workday": workday}
KEYED = ("google", "jooble")  # boards that search with your own API key


_LABELS = {"google": "Google Jobs", "jooble": "Jooble", "jobicy": "Jobicy", "remotive": "Remotive", "remoteok": "Remote OK",
           "arbeitnow": "Arbeitnow", "greenhouse": "Company site", "lever": "Company site", "ashby": "Company site", "manual": "Added by you"}


def board_label(kind, slug=""):
    """What to call a board when showing where a job was found."""
    if kind == "workday":
        tenant = (slug or "").split(".", 1)[0]
        return f"{WORKDAY_NAMES.get(tenant, tenant.upper())} careers"
    return _LABELS.get(kind, kind.title())


def fetch(kind, slug, key=None):
    """One board's jobs. `key` is your API key for that kind of board (SerpApi for google, Jooble for jooble)."""
    if kind not in READERS:
        raise SourceError(f"unknown board type '{kind}'")
    if kind in KEYED:
        return READERS[kind](slug.strip(), key)
    return READERS[kind](slug.strip())


def slug_from(value):
    """Accept a pasted board URL as well as a bare slug: (kind or None, slug)."""
    v = (value or "").strip()
    m = SITE_PATTERN.search(v)
    if m:
        tenant, wd, site = m.groups()
        terms = v.partition("|")[2].strip()
        return "workday", f"{tenant}.{wd}.myworkdayjobs.com/{site}" + (f" | {terms}" if terms else "")
    for kind, pattern in (("greenhouse", r"greenhouse\.io/(?:embed/job_board\?for=)?([\w-]+)"), ("lever", r"lever\.co/([\w-]+)"),
                          ("ashby", r"ashbyhq\.com/([\w.-]+)")):
        m = re.search(pattern, v)
        if m:
            return kind, m.group(1)
    return None, v.strip("/ ").lower()


# Boards checked to answer on 2026-11-08, offered as one-click adds. Any company on these systems works.
SUGGESTED = [
    ("greenhouse", "airbnb", "Airbnb"), ("greenhouse", "anthropic", "Anthropic"), ("greenhouse", "affirm", "Affirm"), ("greenhouse", "asana", "Asana"),
    ("greenhouse", "cloudflare", "Cloudflare"), ("greenhouse", "coinbase", "Coinbase"), ("greenhouse", "databricks", "Databricks"),
    ("greenhouse", "datadog", "Datadog"), ("greenhouse", "discord", "Discord"), ("greenhouse", "dropbox", "Dropbox"), ("greenhouse", "duolingo", "Duolingo"),
    ("greenhouse", "figma", "Figma"), ("greenhouse", "gitlab", "GitLab"), ("greenhouse", "instacart", "Instacart"), ("greenhouse", "lyft", "Lyft"),
    ("greenhouse", "pinterest", "Pinterest"), ("greenhouse", "reddit", "Reddit"), ("greenhouse", "robinhood", "Robinhood"), ("greenhouse", "stripe", "Stripe"),
    ("greenhouse", "twilio", "Twilio"), ("lever", "palantir", "Palantir"), ("lever", "spotify", "Spotify"), ("ashby", "linear", "Linear"),
    ("ashby", "notion", "Notion"), ("ashby", "openai", "OpenAI"), ("ashby", "ramp", "Ramp"), ("ashby", "replit", "Replit"), ("ashby", "supabase", "Supabase"),
    ("ashby", "vercel", "Vercel"),
]
