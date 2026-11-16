"""Google Jobs, through SerpApi (Google blocks scripts). Each results page costs one SerpApi search.
"""
import hashlib
import os
import re
import urllib.parse
from datetime import datetime, timedelta

from ..rules import focus
from . import http

SERPAPI = "https://serpapi.com/search.json"
GOOGLE_PAGES = 2       # 10 jobs a page; each page is one SerpApi search


def google_query(slug):
    """'keywords @ place' to SerpApi Google Jobs parameters. A place of 'remote' asks for work-from-home jobs in the US."""
    words, _, place = (slug or "").partition("@")
    words, place = words.strip(), place.strip()
    if not words:
        raise http.SourceError("say what to search for, like: help desk technician @ Washington, DC")
    params = {"engine": "google_jobs", "hl": "en", "gl": "us"}
    if place.lower() in ("remote", "work from home", "anywhere"):
        params.update(q=f"{words} remote", ltype="1", location="United States")
    else:
        params["q"] = f"{words} {place}".strip()
    return params




def google_apply_link(j):
    """The first apply link that isn't on a left-out site (jobleads.com). None when every link is."""
    for opt in j.get("apply_options") or []:
        link = (opt or {}).get("link") or ""
        if re.match(r"https?://", link) and not focus.blocked(link):
            return link
    return None


def google(slug, key=None):
    key = key or os.environ.get("SERPAPI_KEY")
    if not key:
        raise http.SourceError("Google Jobs needs a SerpApi key. Add it under Job boards (free at serpapi.com)")
    params, out, token = google_query(slug), [], None
    for _ in range(GOOGLE_PAGES):
        q = dict(params, api_key=key, **({"next_page_token": token} if token else {}))
        try:
            data = http.get_json(SERPAPI + "?" + urllib.parse.urlencode(q))
        except http.SourceError as e:
            if "401" in str(e) or "403" in str(e):
                raise http.SourceError("SerpApi didn't accept the key. Check it under Job boards") from None
            if "429" in str(e):
                raise http.SourceError("SerpApi says you're out of searches for now") from None
            if out:
                break
            raise
        if data.get("error"):
            if "hasn't returned any results" in data["error"] or "no results" in data["error"].lower():
                break
            raise http.SourceError(f"SerpApi: {data['error']}")
        for j in data.get("jobs_results") or []:
            link = google_apply_link(j)
            if not link:
                continue  # only on jobleads.com, or no link at all
            ext = j.get("detected_extensions") or {}
            ext_id = hashlib.sha1((j.get("job_id") or f"{j.get('title')}|{j.get('company_name')}|{j.get('location')}").encode()).hexdigest()[:20]
            out.append(http.make_job("google", "", ext_id, title=j.get("title"), company=j.get("company_name"),
                            location=j.get("location") or "", url=link, apply_url=link,
                            employment_type=ext.get("schedule_type", ""), description=j.get("description") or "",
                            workplace="remote" if ext.get("work_from_home") else "",
                            salary_text=ext.get("salary", ""), posted=http.days_ago(ext.get("posted_at")),
                            department=f"via {j['via'].removeprefix('via ')}" if j.get("via") else ""))
        token = (data.get("serpapi_pagination") or {}).get("next_page_token")
        if not token:
            break
    return out


def google_lookup(title, company, location, key):
    """One Google Jobs search (one SerpApi search) for a single job, to read its whole post: [(title, company, description, link)]."""
    if not key:
        raise http.SourceError("Google Jobs needs a SerpApi key. Add it under Job boards (free at serpapi.com)")
    place = "remote" if re.search(r"\bremote\b", location or "", re.I) else re.sub(r"^\d+[^,]*,\s*", "", location or "").split(" · ")[0]
    params = dict(google_query(f"{title} {company} @ {place}"), api_key=key)
    try:
        data = http.get_json(SERPAPI + "?" + urllib.parse.urlencode(params))
    except http.SourceError as e:
        if "401" in str(e) or "403" in str(e):
            raise http.SourceError("SerpApi didn't accept the key. Check it under Job boards") from None
        if "429" in str(e):
            raise http.SourceError("SerpApi says you're out of searches for now") from None
        raise
    return [(j.get("title") or "", j.get("company_name") or "", j.get("description") or "", google_apply_link(j) or "")
            for j in data.get("jobs_results") or []]
