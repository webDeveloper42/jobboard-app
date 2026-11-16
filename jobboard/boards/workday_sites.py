"""Workday career sites (GDIT, Leidos, CACI…): the same JSON API every Workday site uses.

A slug is "site link | search terms". Only jobs whose title and place already fit are read in full.
"""
import re
from datetime import datetime, timedelta
import urllib.parse

from ..rules import focus, text
from . import http


WORKDAY_PAGES = 3        # 20 jobs a page, per search term
WORKDAY_DETAILS = 40     # full posts read per board per refresh (only for jobs whose title and place already fit)
WORKDAY_DEFAULT_TERMS = "help desk Washington OR IT technician Washington OR desktop support Washington OR IT intern OR data entry Washington"
WORKDAY_NAMES = {"gdit": "GDIT", "leidos": "Leidos", "bah": "Booz Allen Hamilton", "caci": "CACI", "target": "Target", "lowes": "Lowe's",
                 "homedepot": "The Home Depot", "cvshealth": "CVS Health", "accenture": "Accenture"}
SITE_PATTERN = re.compile(r"(?:https?://)?([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_-]+)")


def workday_site(slug):
    """'gdit.wd5.myworkdayjobs.com/External_Career_Site | help desk OR IT intern' to (host, tenant, site, [terms])."""
    site_part, _, terms = (slug or "").partition("|")
    m = SITE_PATTERN.search(site_part.strip())
    if not m:
        raise http.SourceError("paste the Workday jobs page link, like gdit.wd5.myworkdayjobs.com/External_Career_Site")
    tenant, wd, site = m.groups()
    words = [t.strip() for t in re.split(r"\s+OR\s+", terms.strip() or WORKDAY_DEFAULT_TERMS) if t.strip()]
    return f"{tenant}.{wd}.myworkdayjobs.com", tenant, site, words[:8]


def place_from(value):
    """Workday writes 'USA DC Washington' or 'USA DC Home Office (DCHOME)'; the board reads 'Washington, DC' and 'Remote (USA)'."""
    v = re.sub(r"\s+", " ", value or "").strip()
    if re.search(r"\b(home office|remote|telework|virtual)\b", v, re.I):
        return "Remote (USA)"
    m = re.match(r"^(?:USA|US|United States)[,\s-]+([A-Z]{2})[,\s-]+(.+?)(?:\s+-\s+.*|\s*\(.*\))?$", v)
    if m:
        return f"{m.group(2).strip()}, {m.group(1)}"
    return v


def posted_from(value):
    v = re.sub(r"(?i)^posted\s+", "", value or "").strip().lower()
    if v.startswith("today"):
        return datetime.now().date().isoformat()
    if v.startswith("yesterday"):
        return (datetime.now().date() - timedelta(days=1)).isoformat()
    return http.days_ago(v)


def workday(slug):
    host, tenant, site, terms = workday_site(slug)
    base = f"https://{host}/wday/cxs/{tenant}/{site}"
    company = WORKDAY_NAMES.get(tenant, tenant.upper() if len(tenant) <= 5 else tenant.title())
    seen, picks, failed = set(), [], None
    for term in terms:
        for page in range(WORKDAY_PAGES):
            try:
                data = http.post_json(base + "/jobs", {"appliedFacets": {}, "limit": 20, "offset": page * 20, "searchText": term})
            except http.SourceError as e:
                if any(c in str(e) for c in ("401", "404", "422")):
                    raise http.SourceError("that Workday site didn't answer. Check the jobs page link") from None
                failed = e
                break
            posts = data.get("jobPostings") or []
            for j in posts:
                path = j.get("externalPath") or ""
                if not path or path in seen:
                    continue
                seen.add(path)
                # Only jobs whose title is one of the board's roles are read in full, so a refresh stays quick and polite.
                if focus.category(j.get("title")) is None:
                    continue
                where = place_from(j.get("locationsText"))
                many = bool(re.match(r"^\d+ locations?$", where, re.I))
                if not many and where and not focus.places({"location": where}):
                    continue
                picks.append((path, j, where))
            if len(posts) < 20 or (page + 1) * 20 >= (data.get("total") or 0):
                break
    out = []
    for path, j, where in picks[:WORKDAY_DETAILS]:
        try:
            info = (http.get_json(base + path) or {}).get("jobPostingInfo") or {}
        except http.SourceError:
            info = {}
        places = [where] if where and not re.match(r"^\d+ locations?$", where, re.I) else []
        for loc in [info.get("location")] + list(info.get("additionalLocations") or []):
            p = place_from(loc)
            if p and p not in places:
                places.append(p)
        if info.get("remoteType") and re.search(r"remote", str(info["remoteType"]), re.I) and "Remote (USA)" not in places:
            places.append("Remote (USA)")
        url = info.get("externalUrl") or f"https://{host}/{site}{path}"
        out.append(http.make_job("workday", tenant, info.get("jobReqId") or path.rsplit("_", 1)[-1], title=info.get("title") or j.get("title"),
                        company=company, location=" · ".join(places)[:200], url=url,
                        employment_type=info.get("timeType") or "", department=f"via {company} careers (Workday)",
                        description=text.html_to_text(info.get("jobDescription")),
                        posted=http.parse_date(info.get("startDate")) or posted_from(j.get("postedOn"))))
    if failed and not out and not picks:
        raise failed
    return out
