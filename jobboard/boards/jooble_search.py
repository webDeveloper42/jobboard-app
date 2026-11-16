"""Jooble searches, with your own Jooble API key. Each OR term is one request; Jooble sends only a snippet per job.
"""
import hashlib
import os
import re
import urllib.parse

from ..rules import focus, text
from . import http

JOOBLE = "https://jooble.org/api/"
JOOBLE_PER_PAGE = 50   # one Jooble request per search term (terms are split on OR)
JOOBLE_RADIUS = "8"    # kilometres around the place; the board's own place rules still decide


def jooble_queries(slug):
    """'help desk OR IT support @ Washington, DC' to one Jooble request body per term. '@ remote' searches remote work in the US."""
    words, _, place = (slug or "").partition("@")
    words, place = words.strip(), place.strip()
    terms = [t.strip() for t in re.split(r"\s+OR\s+", words) if t.strip()]
    if not terms:
        raise http.SourceError("say what to search for, like: help desk technician @ Washington, DC")
    out = []
    for t in terms[:6]:
        if place.lower() in ("remote", "work from home", "anywhere", ""):
            out.append({"keywords": f"{t} remote" if place else t, "location": ""})
        else:
            out.append({"keywords": t, "location": place, "radius": JOOBLE_RADIUS})
    return out


def jooble(slug, key=None):
    key = key or os.environ.get("JOOBLE_KEY")
    if not key:
        raise http.SourceError("Jooble needs an API key. Add it under Job boards (jobboard jooble-key YOUR_KEY)")
    out, seen, failed = [], set(), None
    for body in jooble_queries(slug):
        try:
            data = http.post_json(JOOBLE + urllib.parse.quote(key, safe=""), dict(body, page="1", ResultOnPage=str(JOOBLE_PER_PAGE)))
        except http.SourceError as e:
            if any(c in str(e) for c in ("401", "403", "404")):
                raise http.SourceError("Jooble didn't accept the key. Check it under Job boards") from None
            if "429" in str(e):
                raise http.SourceError("Jooble says you've used up your requests for now") from None
            failed = e
            continue
        for j in (data or {}).get("jobs") or []:
            link = j.get("link") or ""
            via = j.get("source") or ""
            if not re.match(r"https?://", link) or focus.blocked(link) or "jobleads" in via.lower():
                continue
            ext_id = str(j.get("id") or hashlib.sha1(f"{j.get('title')}|{j.get('company')}|{j.get('location')}".encode()).hexdigest()[:20])
            if ext_id in seen:
                continue  # the same job found by two terms
            seen.add(ext_id)
            out.append(http.make_job("jooble", "", ext_id, title=text.html_to_text(j.get("title")), company=j.get("company") or "",
                            location=j.get("location") or "", url=link, apply_url=link,
                            employment_type=j.get("type") or "", description=text.html_to_text(j.get("snippet")),
                            salary_text=j.get("salary") or "", posted=http.parse_date(j.get("updated")),
                            department=f"via {via}" if via else ""))
    if failed and not out:
        raise failed
    return out
