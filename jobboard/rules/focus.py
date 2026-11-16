"""What the board is for: only these roles, only in these places. Everything else is left out.

* IT technician (help desk, desktop / IT support): remote, or in Washington, DC
* IT internship: remote, or in Washington, DC
* Data entry (data entry clerk / operator / specialist, typist): remote, or in Washington, DC

Any job whose link goes to jobleads.com is left out too, whatever the role, and so is any post that looks like
a scam (see scam.py).
Every board is filtered the same way, so the feed only ever shows these.
"""
import re
import urllib.parse

from ..config import HOME_STATES  # states you can work from: change it in config.py
from . import scam

CATEGORIES = {
    "it_intern": {"name": "IT internship", "title": "IT Intern", "places": ("remote", "dc")},
    "it_tech": {"name": "IT technician", "title": "IT Technician", "places": ("remote", "dc")},
    "data_entry": {"name": "Data entry", "title": "Data Entry Clerk", "places": ("remote", "dc")},
}
PLACE_NAMES = {"remote": "remote", "dc": "Washington, DC", "suitland": "Suitland, MD"}

BLOCKED_SITES = ("jobleads.com",)
SCAM_REASON = "looks like a scam: "

# The Google Jobs searches the board starts with ("keywords @ place"). You can add, switch off or remove any.
GOOGLE_SEARCHES = [
    ("IT technician OR help desk technician OR IT support OR desktop support @ Washington, DC", "Google · IT technician · DC"),
    ("IT technician OR help desk technician OR IT support OR desktop support @ remote", "Google · IT technician · remote"),
    ("IT intern OR IT internship OR help desk intern OR information technology internship @ Washington, DC", "Google · IT internship · DC"),
    ("IT intern OR IT internship OR help desk intern OR information technology internship @ remote", "Google · IT internship · remote"),
    ("data entry OR data entry clerk OR data entry specialist OR data entry operator @ Washington, DC", "Google · Data entry · DC"),
    ("data entry OR data entry clerk OR data entry specialist OR data entry operator @ remote", "Google · Data entry · remote"),
]

# The same roles and places as Jooble searches. Each OR term is one Jooble request, so these stay short.
JOOBLE_SEARCHES = [
    ("IT technician OR help desk technician OR desktop support @ Washington, DC", "Jooble · IT technician · DC"),
    ("IT technician OR help desk technician OR IT support @ remote", "Jooble · IT technician · remote"),
    ("IT intern OR IT internship @ Washington, DC", "Jooble · IT internship · DC"),
    ("IT intern OR IT internship @ remote", "Jooble · IT internship · remote"),
    ("data entry OR data entry clerk @ Washington, DC", "Jooble · Data entry · DC"),
    ("data entry OR data entry clerk @ remote", "Jooble · Data entry · remote"),
]

# Employers' own Workday career sites: "site | search terms". Each term reads up to 3 pages of 20.
WORKDAY_SEARCHES = [
    ("gdit.wd5.myworkdayjobs.com/External_Career_Site | help desk Washington OR desktop support Washington OR IT technician Washington "
     "OR service desk Washington OR help desk remote OR IT intern", "GDIT careers · IT"),
    ("leidos.wd5.myworkdayjobs.com/External | help desk Washington OR desktop support Washington OR IT technician Washington OR IT intern",
     "Leidos careers · IT"),
    ("caci.wd1.myworkdayjobs.com/External | help desk Washington OR desktop support Washington OR IT technician", "CACI careers · IT"),
]

# Searches the board used to start with, for roles it no longer covers (stocking). Taken off once, when the roles changed.
RETIRED_SEARCHES = [
    ("google", "stocker OR stock associate OR overnight stocker OR merchandise stocker @ Washington, DC"),
    ("google", "stocker OR stock associate OR overnight stocker OR merchandise stocker @ Suitland, MD"),
    ("jooble", "stocker OR stock associate @ Washington, DC"),
    ("jooble", "stocker OR stock associate @ Suitland, MD"),
    ("workday", "target.wd5.myworkdayjobs.com/targetcareers | Washington DC OR Suitland"),
]

_IT_AREA = r"\b(it|i\.t\.|information technology|computer|desktop|pc|help ?desk|service ?desk|tech(nical)? support|end[- ]user|" \
           r"field (service|support)|hardware|network|systems?|infrastructure|technology|deskside|imac|av/it)\b"
_INTERN = r"\b(intern|interns|internship|co-?op|apprentice(ship)?)\b"
_TECH_ROLE = r"\b(technician|technicians|tech|support|specialist|associate|desk)\b"
_TECH_DIRECT = r"\b(help ?desk|service ?desk|desktop support|tech(nical)? support|it support|computer technician|pc technician|" \
               r"field technician|deskside|end[- ]user support)\b"
_TOO_SENIOR = r"\b(manager|director|architect|principal|vp|vice president|head of|chief)\b"
_NOT_IT = r"\b(pharmacy|veterinary|surgical|dental|medical assistant|nurse|hvac|automotive|auto|diesel|mechanic|electrician|plumb\w*|" \
          r"pest|lab(oratory)?|radiolog\w*|ultrasound|sterile|cable install\w*|appliance|elevator|wind|solar|aviation|aircraft|sales)\b"
_DATA_ENTRY = r"\b(data[- ]entry|data (clerk|keyer|input|typist)|data processing (clerk|associate|specialist|operator)|" \
              r"order entry|key ?entry|typist)\b"

_DC = r"\bwashington,?\s*(d\.?\s?c\.?|district of columbia)(?![a-z])|\bdistrict of columbia\b|,\s*dc\b|\bdc\s*\d{5}\b"
_SUITLAND = r"\bsuitland\b"
_REMOTE = r"\b(remote|anywhere|work from home|wfh|telework|virtual)\b"
# A remote job has to be open to someone in the US.
_REMOTE_FAR = r"\b(europe|emea|uk|united kingdom|germany|india|canada only|latam|latin america|apac|asia|australia|philippines|" \
              r"brazil|mexico|poland|spain|france|netherlands|ireland|portugal|africa|israel)\b"


def category(title):
    """Which of the board's roles a job title is, or None."""
    t = (title or "").lower()
    if re.search(_TOO_SENIOR, t):
        return None
    if re.search(_DATA_ENTRY, t):
        return "data_entry"
    if re.search(_INTERN, t) and re.search(_IT_AREA, t) and not re.search(_NOT_IT, t):
        return "it_intern"
    if re.search(_INTERN, t):
        return None
    if not re.search(_NOT_IT, t) and (re.search(_TECH_DIRECT, t) or (re.search(_IT_AREA, t) and re.search(_TECH_ROLE, t)
                                                                       and not re.search(r"\b(software|data|developer|devops|cloud|security|sre|ml|ai)\b", t))):
        return "it_tech"
    return None


def places(job):
    """Which of the board's places a job is in: a set of remote / dc / suitland."""
    where = (job.get("location") or "").lower()
    found = set()
    if re.search(_DC, where):
        found.add("dc")
    if re.search(_SUITLAND, where):
        found.add("suitland")
    if (job.get("work_model") == "remote" or re.search(_REMOTE, where)) and not re.search(_REMOTE_FAR, where):
        found.add("remote")
    return found


# Job sites that repost other employers' jobs under their own name. Matched on the company name.
_AGGREGATOR = re.compile(
    r"(?:jobs?\b|job ?(?:link|board|site|lead|conversion)|\bcareers?\b|\bhiring\b)|\b(?:recruit monitor|talentoma|feedinkoo|usasjb|remoteonline|remote ?career|"
    r"ziprecruiter|indeed|linkedin|glassdoor|simplyhired|monster|careerbuilder|lensa|jooble|talent\.com|adzuna|"
    r"jobgether|jobleads|whatjobs|learn4good|snagajob|getwork|jobsrmine|myjobhelper|jobilize|hireology)\b", re.I)
_NOT_AGGREGATOR = re.compile(r"\b(?:jobot|steve jobs|careerstaff|careersource)\b", re.I)


def aggregator(company):
    """True when the 'company' is a job site reposting someone else's job (Remote Career, AllJobs, Job.com…)."""
    c = company or ""
    return bool(_AGGREGATOR.search(c)) and not _NOT_AGGREGATOR.search(c)


# Remote jobs that only hire people living somewhere else. Read from the post: "Must reside in Pennsylvania".
_US_STATES = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas", "CA": "california", "CO": "colorado", "CT": "connecticut",
    "DE": "delaware", "FL": "florida", "GA": "georgia", "HI": "hawaii", "ID": "idaho", "IL": "illinois", "IN": "indiana", "IA": "iowa",
    "KS": "kansas", "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland", "MA": "massachusetts", "MI": "michigan",
    "MN": "minnesota", "MS": "mississippi", "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada", "NH": "new hampshire",
    "NJ": "new jersey", "NM": "new mexico", "NY": "new york", "NC": "north carolina", "ND": "north dakota", "OH": "ohio",
    "OK": "oklahoma", "OR": "oregon", "PA": "pennsylvania", "RI": "rhode island", "SC": "south carolina", "SD": "south dakota",
    "TN": "tennessee", "TX": "texas", "UT": "utah", "VT": "vermont", "VA": "virginia", "WA": "washington", "WV": "west virginia",
    "WI": "wisconsin", "WY": "wyoming", "DC": "district of columbia"}
_LIMIT = re.compile(
    r"[^.\n]{0,60}\b(?:must (?:reside|live|be located|be based)|resid(?:e|ents?|ing) (?:in|of|within)|(?:located|based|residing) (?:in|within)|"
    r"only (?:open|available) to|open (?:only )?to candidates (?:in|from)|hiring (?:only )?in the following states|eligible states|"
    r"commuting distance (?:of|to|from))[^.\n]{0,160}", re.I)
_DC_AREA = re.compile(r"\b(?:dmv|washington,?\s*d\.?c\.?|d\.c\. (?:metro|area)|national capital region|baltimore)\b", re.I)


def _states_in(text):
    found = set()
    for code, name in _US_STATES.items():
        if re.search(rf"\b{name}\b", text, re.I) or re.search(rf"(?<![A-Za-z]){code}(?![A-Za-z])", text):
            found.add(code)
    if "WA" in found and re.search(r"\bwashington,?\s*d\.?c\b", text, re.I) and not re.search(r"\bwashington state\b|,\s*WA\b", text):
        found.discard("WA")
    return found


def remote_limit(job):
    """For a remote job that says it only hires people in certain states or near a city that isn't yours: what it says
    (like 'Pennsylvania'), else None. A post open to the whole US, or that includes Maryland or DC, is fine."""
    for m in _LIMIT.finditer(job.get("description") or ""):
        part = m.group(0)
        if re.search(r"\b(?:united states|u\.s\.|usa|us-based|anywhere in the us|all 50 states|any state)\b", part, re.I) and not re.search(
                r"\bexcept\b|\bnot (?:in|available)\b", part, re.I):
            continue
        if _DC_AREA.search(part):
            continue
        states = _states_in(part)
        if states & HOME_STATES:
            continue
        if states:
            return ", ".join(_US_STATES[s].title() for s in sorted(states))[:80]
        if re.search(r"commuting distance", part, re.I):
            near = re.search(r"commuting distance (?:of|to|from)\s+([^,.;]{2,40}(?:,\s*[A-Z]{2})?)", part, re.I)
            return f"near {near.group(1).strip()}" if near else "near another city"
    return None


def remote_elsewhere(job):
    """A remote job listed in a city outside the DC area ('Tampa, FL'): its state code, else None. Often fine, sometimes not."""
    if job.get("work_model") != "remote":
        return None
    for part in re.split(r"\s+·\s+", job.get("location") or ""):
        m = re.search(r",\s*([A-Z]{2})\b", part)
        if m and m.group(1) in _US_STATES and m.group(1) not in HOME_STATES | {"VA"}:
            return part.strip()
    return None


def blocked(url):
    """True for a link to a site the board leaves out (jobleads.com)."""
    host = (urllib.parse.urlsplit(url or "").hostname or "").lower()
    return any(host == s or host.endswith("." + s) for s in BLOCKED_SITES)


def check(job):
    """(category id, None) when the job belongs on the board, else (None, why it was left out)."""
    if blocked(job.get("url")) or blocked(job.get("apply_url")):
        return None, "jobleads.com link"
    cat = category(job.get("title"))
    if not cat:
        return None, "not one of the roles"
    where = places(job) & set(CATEGORIES[cat]["places"])
    if not where:
        return None, "not in a place for that role"
    if where == {"remote"}:
        limit = remote_limit(job)
        if limit:
            return None, f"remote only for people in {limit}"
    fake, why = scam.is_scam(job, cat)
    if fake:
        return None, SCAM_REASON + why
    return cat, None


_COMPANY_SAME = {"general dynamics information technology": "gdit", "general dynamics it": "gdit", "booz allen hamilton": "booz allen",
                 "caci international": "caci", "target corporation": "target", "target stores": "target"}


def company_key(name):
    """A company name written plainly, so "Target Corporation" and "Target" match."""
    c = re.sub(r"[^a-z0-9& ]+", " ", (name or "").lower())
    c = re.sub(r"\b(inc|llc|l l c|corp|corporation|co|company|ltd|the|group|holdings|usa|us)\b", " ", c)
    c = re.sub(r"\s+", " ", c).strip()
    return _COMPANY_SAME.get(c, c)


def fingerprint(job):
    """The same job on two boards gets the same fingerprint: its title, company and place, written plainly.
    A street address counts as the place when there is one, so two Target stores stay two jobs."""
    title = re.sub(r"\b(remote|hybrid|on-?site|in-?office|full[- ]time|part[- ]time|wfh)\b", " ", (job.get("title") or "").lower())
    title = re.sub(r"[^a-z0-9]+", " ", title).strip()
    where = job.get("location") or ""
    m = re.search(r"\b(\d+)\s+([A-Za-z0-9]+)", where) if re.match(r"^\s*\d+\s", where) else None
    area = ",".join(sorted(places({"location": where})))
    place = f"{m.group(1)} {m.group(2).lower()}@{area}" if m else area or re.sub(r"[^a-z]+", " ", where.lower()).strip()
    return f"{title}|{company_key(job.get('company'))}|{place}"


def same_place(a, b):
    """Two fingerprints' places match: the same, or a street address and the city it's in ('3100 14th@dc' and 'dc')."""
    pa, pb = a.rsplit("|", 1)[-1], b.rsplit("|", 1)[-1]
    if pa == pb:
        return True
    if ("@" in pa) == ("@" in pb):
        return False
    area_a, area_b = set(pa.split("@")[-1].split(",")) - {""}, set(pb.split("@")[-1].split(",")) - {""}
    return bool(area_a & area_b)


def same_job_prefix(fp):
    """The title and company part of a fingerprint, for finding the same job listed with another place."""
    return fp.rsplit("|", 1)[0] + "|"


def describe():
    return [{"id": k, "name": c["name"], "places": [PLACE_NAMES[p] for p in c["places"]]} for k, c in CATEGORIES.items()]
