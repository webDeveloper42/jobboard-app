"""Remote-job boards that cover many companies: Remotive, Remote OK, Arbeitnow and Jobicy. No key needed.
"""
import re
import urllib.parse

from ..rules import text
from . import http

def remotive(slug):
    url = "https://remotive.com/api/remote-jobs" + (f"?search={urllib.parse.quote(slug)}" if slug else "")
    out = []
    for j in http.get_json(url).get("jobs", []):
        out.append(http.make_job("remotive", slug, j.get("id"), title=j.get("title"), company=j.get("company_name"),
                        location=j.get("candidate_required_location") or "Remote", url=j.get("url"),
                        employment_type=(j.get("job_type") or "").replace("_", " "), department=j.get("category", ""),
                        description=text.html_to_text(j.get("description")), workplace="remote",
                        salary_text=j.get("salary") or "", tags=j.get("tags") or [], posted=http.parse_date(j.get("publication_date"))))
    return out


def remoteok(slug):
    url = "https://remoteok.com/api" + (f"?tag={urllib.parse.quote(slug)}" if slug else "")
    data = http.get_json(url)
    out = []
    for j in data if isinstance(data, list) else []:
        if not isinstance(j, dict) or not j.get("id") or not j.get("position"):
            continue  # the first item is a legal notice
        low, high = j.get("salary_min") or None, j.get("salary_max") or None
        out.append(http.make_job("remoteok", slug, j.get("id"), title=j.get("position"), company=j.get("company"),
                        location=j.get("location") or "Remote", url=j.get("url"), apply_url=j.get("apply_url"),
                        description=re.sub(r"\s*#[A-Za-z0-9+/=]{24,}\s*$", "", text.html_to_text(j.get("description"))), workplace="remote",
                        tags=j.get("tags") or [], posted=http.parse_date(j.get("epoch") or j.get("date")),
                        salary_guess=(low, high)))
    return out


def arbeitnow(slug):
    out = []
    for j in http.get_json("https://www.arbeitnow.com/api/job-board-api").get("data", []):
        if slug and slug.lower() not in (j.get("title", "") + " " + " ".join(j.get("tags") or [])).lower():
            continue
        out.append(http.make_job("arbeitnow", slug, j.get("slug"), title=j.get("title"), company=j.get("company_name"),
                        location=j.get("location", ""), url=j.get("url"), employment_type=", ".join(j.get("job_types") or [])[:80],
                        description=text.html_to_text(j.get("description")), workplace="remote" if j.get("remote") else "",
                        tags=j.get("tags") or [], posted=http.parse_date(j.get("created_at"))))
    return out



JOBICY = "https://jobicy.com/api/v2/remote-jobs"
_PER_YEAR = {"yearly": 1, "annual": 1, "monthly": 12, "weekly": 52, "hourly": 2080, "daily": 260}


def jobicy(slug):
    """Jobicy's remote jobs open to the US. The slug is an industry ('supporting' is customer and technical support).
    Jobicy asks to be credited and for Apply to go to the job's own link, so both are kept."""
    q = {"count": "100", "geo": "usa"}
    if slug:
        if not re.fullmatch(r"[a-z0-9-]{2,60}", slug):
            raise http.SourceError("use a Jobicy industry name, like supporting or technical-support")
        q["industry"] = slug
    try:
        data = http.get_json(JOBICY + "?" + urllib.parse.urlencode(q))
    except http.SourceError as e:
        if "400" in str(e):
            raise http.SourceError("Jobicy doesn't know that industry. Try supporting or technical-support") from None
        raise
    out = []
    for j in data.get("jobs") or []:
        geo = j.get("jobGeo") or ""
        regions = [g.strip().lower() for g in geo.split(",")]
        if geo and not any(g in ("usa", "us", "united states", "anywhere", "worldwide") for g in regions):
            continue
        low = high = None
        per = _PER_YEAR.get(str(j.get("salaryPeriod") or "yearly").lower())
        if per and (j.get("salaryCurrency") or "USD") == "USD":
            try:
                low = int(float(j.get("salaryMin") or j.get("annualSalaryMin") or 0) * per) or None
                high = int(float(j.get("salaryMax") or j.get("annualSalaryMax") or 0) * per) or low
            except (TypeError, ValueError):
                low = high = None
        out.append(http.make_job("jobicy", slug, j.get("id"), title=text.html_to_text(j.get("jobTitle")), company=j.get("companyName") or "",
                        location="Remote (USA)", url=j.get("url"), employment_type=", ".join(j.get("jobType") or [])[:80],
                        department="via Jobicy" + (f" · {', '.join(j.get('jobIndustry') or [])}" if j.get("jobIndustry") else ""),
                        description=text.html_to_text(j.get("jobDescription") or j.get("jobExcerpt")), workplace="remote",
                        salary_min=low, salary_max=high, posted=http.parse_date(j.get("pubDate"))))
    return out
