"""Tailored resumes and cover letters, opened as real documents in the Docs tab.

The text becomes a document through the Docs app's own storage code (~/docs-app/docs/store.py), so it's cleaned and
saved by the same rules as anything typed there. With one of your Docs templates, the new document takes that
template's page setup (margins, page size, header and footer) and the text goes in as the body.
"""
import html
import json
import os
import re
import sys
from pathlib import Path


class DocsLinkError(RuntimeError):
    pass


def _store():
    app = Path(os.environ.get("DOCS_APP_DIR") or Path.home() / "docs-app")
    if not (app / "docs" / "store.py").exists():
        raise DocsLinkError("the Docs app isn't installed")
    if str(app) not in sys.path:
        sys.path.insert(0, str(app))
    from docs import store  # noqa: PLC0415
    return store


_BULLET = re.compile(r"^\s*(?:[-*•▪◦]|\d+[.)])\s+")


def _heading(line):
    """'Skills:' or 'EXPERIENCE' on a line of its own."""
    return (len(line) <= 40 and line.endswith(":")) or (2 < len(line) <= 40 and line.isupper() and any(c.isalpha() for c in line))


def to_html(text, kind=""):
    """Plain text to a document: a short first line of a resume is its title, short lines ending in ':' or written in
    capitals are headings, '- ' lines are bullet lists, and blank lines separate paragraphs."""
    blocks = re.split(r"\n\s*\n", (text or "").strip().replace("\r\n", "\n"))
    out, first = [], True
    for block in blocks:
        lines = [ln.rstrip() for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if first and kind == "tailored_resume" and len(line) <= 60 and not _BULLET.match(line):
                out.append(f'<h1 class="title">{html.escape(line)}</h1>')
            elif _BULLET.match(line):
                items = []
                while i < len(lines) and _BULLET.match(lines[i]):
                    items.append(f"<li>{html.escape(_BULLET.sub('', lines[i]).strip())}</li>")
                    i += 1
                out.append("<ul>" + "".join(items) + "</ul>")
                first = False
                continue
            elif _heading(line):
                out.append(f"<h2>{html.escape(line.rstrip(':'))}</h2>")
            else:
                # the rest of this block is one paragraph, keeping its line breaks
                rest = []
                while i < len(lines) and not _BULLET.match(lines[i]) and not (rest and _heading(lines[i].strip())):
                    rest.append(html.escape(lines[i].strip()))
                    i += 1
                out.append("<p>" + "<br>".join(rest) + "</p>")
                first = False
                continue
            first = False
            i += 1
    return "".join(out) or "<p><br></p>"


def templates(path=None):
    """Your Docs templates: [{id, title}]."""
    store = _store()
    conn = store.connect(path)
    try:
        return [{"id": t["id"], "title": t["title"]} for t in store.listing(conn, templates=True)]
    finally:
        conn.close()


def open_in_docs(title, body, kind="", template_id=None, path=None):
    """Makes the document and returns its id."""
    store = _store()
    conn = store.connect(path)
    try:
        page = None
        if template_id:
            t = store.row(conn, int(template_id))
            if not t["is_template"]:
                raise DocsLinkError("that isn't a Docs template")
            page = json.loads(t["page"] or "{}")
        return store.add(conn, title, to_html(body, kind), page)
    finally:
        conn.close()
