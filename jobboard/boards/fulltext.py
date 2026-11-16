"""The whole job post, for boards that only send a snippet (Jooble).

The job's link is followed to the employer's page, and the post is read from the JobPosting data that most job
systems put in the page for search engines (Workday, Greenhouse, Lever, iCIMS, SmartRecruiters…). Pages that hide
behind a bot check (Jooble's own pages do) are skipped, and each job is only tried once.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from ..rules import text

AGENT = "Mozilla/5.0 (compatible; jobboard-local/1.0; personal job search)"
PER_REFRESH = 15
MAX_BYTES = 1_500_000
_LD = re.compile(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", re.S | re.I)


def _postings(node):
    if isinstance(node, list):
        for n in node:
            yield from _postings(n)
    elif isinstance(node, dict):
        kind = node.get("@type")
        if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
            yield node
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in node:
                yield from _postings(node[key])


def from_html(page):
    """The JobPosting description in a page, as plain text, or ''."""
    for block in _LD.findall(page or ""):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        for post in _postings(data):
            desc = text.html_to_text(post.get("description") or "")
            if len(desc) > 200:
                return desc
    return ""


def fetch(url):
    """The full post behind a link, or '' when it can't be read."""
    if not re.match(r"https?://", url or ""):
        return ""
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "text/html,application/xhtml+xml"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            host = (urllib.parse.urlsplit(r.geturl()).hostname or "").lower()
            if host.endswith("jooble.org"):
                return ""   # Jooble's pages sit behind a bot check
            page = r.read(MAX_BYTES).decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
        return ""
    return from_html(page)
