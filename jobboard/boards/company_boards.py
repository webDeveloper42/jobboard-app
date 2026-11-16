"""Company boards: Greenhouse, Lever and Ashby. Public APIs, no key; the slug is the company's board name.
"""
import re
import urllib.parse

from ..rules import text
from . import http

def greenhouse(slug):
    data = http.get_json(f"https://boards-api.greenhouse.io/v1/boards/{urllib.parse.quote(slug)}/jobs?content=true")
    out = []
    for j in data.get("jobs", []):
        company = j.get("company_name") or slug.title()
        dept = ", ".join(d.get("name", "") for d in j.get("departments") or [] if d.get("name"))
        dept = re.sub(r"^\d+\s+", "", dept)
        out.append(http.make_job("greenhouse", slug, j.get("id"), title=j.get("title"), company=company,
                        location=(j.get("location") or {}).get("name", ""), url=j.get("absolute_url"),
                        department=dept, description=text.html_to_text(j.get("content")),
                        posted=http.parse_date(j.get("first_published") or j.get("updated_at"))))
    return out


def lever(slug):
    data = http.get_json(f"https://api.lever.co/v0/postings/{urllib.parse.quote(slug)}?mode=json")
    if not isinstance(data, list):
        raise http.SourceError("that board wasn't found. Check the company's slug")
    out = []
    for j in data:
        cats = j.get("categories") or {}
        parts = [j.get("openingPlain") or "", j.get("descriptionBodyPlain") or j.get("descriptionPlain") or ""]
        for block in j.get("lists") or []:
            parts.append(block.get("text", "") + "\n" + text.html_to_text(block.get("content", "")))
        parts.append(j.get("additionalPlain") or "")
        salary = j.get("salaryRange") or {}
        out.append(http.make_job("lever", slug, j.get("id"), title=j.get("text"), company=slug.replace("-", " ").title(),
                        location=cats.get("location", ""), url=j.get("hostedUrl"), apply_url=j.get("applyUrl"),
                        employment_type=cats.get("commitment", ""), department=cats.get("team", ""),
                        description="\n\n".join(p.strip() for p in parts if p and p.strip()),
                        workplace=j.get("workplaceType", ""), posted=http.parse_date(j.get("createdAt")),
                        salary_min=salary.get("min"), salary_max=salary.get("max")))
    return out


def ashby(slug):
    data = http.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{urllib.parse.quote(slug)}?includeCompensation=true")
    out = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        comp = (j.get("compensation") or {}).get("scrapeableCompensationSalarySummary") or (j.get("compensation") or {}).get("compensationTierSummary") or ""
        where = [j.get("location") or ""] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
        out.append(http.make_job("ashby", slug, j.get("id"), title=j.get("title"), company=slug.replace("-", " ").title(),
                        location=" · ".join(w for w in where if w)[:200], url=j.get("jobUrl"), apply_url=j.get("applyUrl"),
                        employment_type=j.get("employmentType", ""), department=j.get("department") or j.get("team") or "",
                        description=j.get("descriptionPlain") or text.html_to_text(j.get("descriptionHtml")),
                        workplace=("remote" if j.get("isRemote") and (j.get("workplaceType") or "").lower() == "remote" else j.get("workplaceType") or ""),
                        salary_text=comp, posted=http.parse_date(j.get("publishedAt"))))
    return out
