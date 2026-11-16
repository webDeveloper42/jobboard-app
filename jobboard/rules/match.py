"""Match scores: one number out of 100, plus the reasons behind it.

    skills     40   how many of the job's key skills you have
    title      25   how close the job title is to the titles you're after
    level      15   seniority and years of experience
    location   12   remote / hybrid / on-site and where
    salary      8   whether the pay reaches your minimum

Anything a job doesn't say (no salary, no years) counts as neutral rather than as a miss.
"""
import re
from datetime import date

from . import focus, text

WEIGHTS = {"skills": 40, "title": 25, "level": 15, "location": 12, "salary": 8}
KEY_SKILLS = 12   # a post mentions many things; the most-mentioned ones are what it's really asking for


def enrich(job):
    """Fill in what the post implies: work model, level, years, salary, skills, sponsorship."""
    desc = job.get("description") or ""
    head = f"{job.get('title', '')}\n{job.get('location', '')}"
    if not job.get("salary_min"):
        low, high, said = text.salary_from(job.get("salary_text") or "")
        if not low:
            low, high, said = text.salary_from(desc)
        guess = job.pop("salary_guess", None) or (None, None)
        if not low and guess[0]:
            low, high = int(guess[0]), int(guess[1] or guess[0])  # the board's own estimate, used only when the post says nothing
        job["salary_min"], job["salary_max"] = low, high
        job["salary_text"] = job.get("salary_text") or said
    else:
        try:
            job["salary_min"] = int(float(job["salary_min"]))
            job["salary_max"] = int(float(job.get("salary_max") or job["salary_min"]))
        except (TypeError, ValueError):
            job["salary_min"] = job["salary_max"] = None
        if job["salary_min"] and job["salary_min"] < 1000:
            job["salary_min"] = job["salary_max"] = None
    hint = job.pop("workplace", "") or ""
    job["work_model"] = text.work_model(hint) if hint else text.work_model(head, desc[:600])
    job["years_min"] = text.years_required(desc)
    job["level"] = text.level_of(job.get("title"), job["years_min"])
    tags = " ".join(job.pop("tags", []) or [])
    title_skills = text.find_skills(job.get("title", ""))
    body = text.find_skills(f"{desc}\n{tags}")
    job["skills"] = list(dict.fromkeys(title_skills + body))
    job["sponsorship"] = text.sponsorship(desc)
    return job


def enrich_skills(job):
    """Read the skills again after the description changed (a full post replacing a snippet)."""
    tags = " ".join(job.get("tags") or [])
    job["skills"] = list(dict.fromkeys(text.find_skills(job.get("title", "")) + text.find_skills(f"{job.get('description') or ''}\n{tags}")))
    job["years_min"] = text.years_required(job.get("description") or "")
    return job


def _skill_part(job, prof, resume_text):
    have = {s.lower() for s in prof["skills"]}
    key = job["skills"][:KEY_SKILLS]
    # Your own skills count when the job mentions them, even if they're past the top few.
    blob = f"{job.get('title', '')}\n{job.get('description', '')}"
    extra = [s for s in prof["skills"] if s.lower() not in {k.lower() for k in key} and text.skill_pattern(s).search(blob)]
    matched = [s for s in key if s.lower() in have] + extra
    missing = [s for s in key if s.lower() not in have]
    # A skill in your resume text but not your list still shows you have it.
    in_resume = [s for s in missing if text.mentions(s, resume_text)]
    missing = [s for s in missing if s not in in_resume]
    matched += in_resume
    if not key and not extra:
        return 0.5, matched, missing
    # A post that names only a skill or two says little, so it's pulled toward the middle.
    total = len(key) + len(extra)
    prior = 3
    return min(1.0, (len(matched) + 0.5 * prior) / (total + prior) if total < 6 else len(matched) / total), matched, missing


def _title_part(job, prof):
    targets = prof["target_titles"] or ([prof["headline"]] if prof["headline"] else [])
    if not targets:
        return 0.5, ""
    best, which = 0.0, ""
    for t in targets:
        s = text.title_similarity(job.get("title", ""), t)
        if s > best:
            best, which = s, t
    return best, which


def _level_part(job, prof):
    want = prof["level"] or (text.level_of("", prof["years_exp"]) if prof["years_exp"] is not None else "")
    notes = []
    if not want:
        return 0.6, notes
    order = text.LEVELS
    a, b = order.index(job["level"]) if job["level"] in order else 2, order.index(want) if want in order else 2
    # Individual-contributor ladder and the management ladder sit side by side; one step either way is close.
    gap = abs(a - b)
    score = {0: 1.0, 1: 0.65}.get(gap, 0.25 if gap == 2 else 0.05)
    if a < b and job["level"] != "intern":
        # A job below your level is still one you can get, just less of a step up.
        score = 0.9 if gap == 1 else 0.75
    if job["level"] != want:
        notes.append(f"{text.LEVEL_NAMES.get(job['level'], job['level'])} role; you're {text.LEVEL_NAMES.get(want, want).lower()}")
    yrs, mine = job.get("years_min"), prof["years_exp"]
    if yrs is not None and mine is not None:
        if mine >= yrs:
            score = min(1.0, score + 0.15)
            notes.append(f"asks {yrs}+ years; you have {mine}")
        else:
            short = yrs - mine
            score *= 0.8 if short <= 1 else 0.5 if short <= 3 else 0.25
            notes.append(f"asks {yrs}+ years; you have {mine}")
    return round(score, 3), notes


def _place_part(job, prof):
    models = prof["work_models"] or ["remote", "hybrid", "onsite"]
    jm = job["work_model"]
    where = (job.get("location") or "").lower() + " | " + (job.get("title") or "").lower()
    near = any(loc.lower().split(",")[0].strip() and loc.lower().split(",")[0].strip() in where for loc in prof["locations"])
    if jm == "remote":
        ok = "remote" in models
        # "Remote (EU only)" and similar don't help someone elsewhere.
        restricted = re.search(r"\b(eu|europe|emea|uk|india|apac|latam|canada|germany|brazil)\b(?! or us)", where) and not re.search(r"\b(us|usa|united states|americas|worldwide|anywhere|global)\b", where)
        if restricted and not near:
            return (0.35 if ok else 0.1), "remote, but limited to " + job.get("location", "")
        return (1.0 if ok else 0.4), "remote"
    if jm in ("hybrid", "onsite"):
        if jm not in models:
            return 0.15, f"{jm} and you'd rather not"
        if not prof["locations"]:
            return 0.7, jm
        if not near:
            return 0.3, f"{jm} in {job.get('location') or 'another city'}"
        trip = job.get("travel") or {}
        if trip.get("transit"):
            # Closer is better, and by Metro or bus, since that's how most of these trips would go.
            m = trip["transit"]
            score = 1.0 if m <= 35 else 0.85 if m <= 55 else 0.65 if m <= 75 else 0.45
            return score, travel_note(trip)
        return 1.0, f"{jm} in a place you picked"
    return 0.6, "location not stated"


def travel_note(trip):
    return f"about {trip['transit']} min by Metro/bus, {trip['drive']} min driving from Suitland (estimate)"


def _age_days(job):
    try:
        return (date.today() - date.fromisoformat(str(job.get("posted"))[:10])).days
    except (TypeError, ValueError):
        return None


def _pay_part(job, prof):
    floor = prof["min_salary"]
    top = job.get("salary_max") or job.get("salary_min")
    if not floor:
        # No minimum set: a post that says what it pays is a better bet than one that doesn't.
        return (0.85, "") if top else (0.65, "pay not listed")
    if not top:
        return 0.7, "pay not listed"
    if top >= floor:
        return 1.0, "pays at least your minimum"
    return max(0.0, 1 - (floor - top) / floor * 2.5), "pays under your minimum"


def score(job, prof):
    """(0..100, detail) for one job against your profile."""
    resume = prof.get("resume_text") or ""
    sk, matched, missing = _skill_part(job, prof, resume)
    ti, which = _title_part(job, prof)
    lv, level_notes = _level_part(job, prof)
    pl, place_note = _place_part(job, prof)
    pay, pay_note = _pay_part(job, prof)
    parts = {"skills": sk, "title": ti, "level": lv, "location": pl, "salary": pay}
    total = sum(WEIGHTS[k] * v for k, v in parts.items())
    flags = []
    if prof["needs_sponsorship"] and job.get("sponsorship") == "no":
        total *= 0.5
        flags.append("Says it won't sponsor a visa")
    elif prof["needs_sponsorship"] and job.get("sponsorship") == "yes":
        flags.append("Offers visa sponsorship")
    # A title that's nothing like what you want caps the score, however many skills line up.
    if (prof["target_titles"] or prof["headline"]) and ti == 0:
        total = min(total, 59)
    # Where and how you work are deal-breakers, not just a few points.
    if pl <= 0.15:
        total = min(total, 50)
        flags.append(f"{job['work_model'].capitalize()}, which you've ruled out")
    elif pl <= 0.35:
        total = min(total, 64)
    # Security clearances: most DC contractor help desks need one you already hold.
    need = text.clearance(job.get("description"), job.get("title"))
    if need == "active" and not prof.get("has_clearance"):
        total = min(total, 55)
        flags.append("Needs an active security clearance")
    elif need == "obtain":
        flags.append("Needs a clearance you'd get on the job (US citizens)")
    # Old posts and ones that keep coming back are often already filled, or always "open".
    age = _age_days(job)
    if age is not None and age > 30:
        total -= 10 if age > 60 else 5
        flags.append(f"Posted {age} days ago, so it may already be filled")
    if age is not None and age <= 3:
        total += 3     # posted in the last few days: early applicants get read first
    if focus.aggregator(job.get("company")):
        total -= 8
        flags.append(f"Listed by a job site ({job.get('company')}), not the employer")
    elsewhere = focus.remote_elsewhere(job)
    if elsewhere:
        total -= 3
        flags.append(f"Remote, but listed in {elsewhere}; check it's open to people in Maryland")
    if (job.get("reposts") or 0) >= 2:
        total -= 5
        flags.append(f"Posted again {job['reposts']} times; it may be always open")
    value = max(0, min(100, round(total)))
    detail = {
        "parts": {k: round(v * 100) for k, v in parts.items()},
        "matched": matched, "missing": missing, "title_match": which,
        "level_notes": level_notes, "place": place_note, "pay": pay_note, "flags": flags,
        "label": label(value), "clearance": need, "age": age, "fresh": age is not None and age <= 3,
    }
    detail["why"] = reasons(job, detail)
    return value, detail


def label(value):
    if value >= 80:
        return "Strong match"
    if value >= 65:
        return "Good match"
    if value >= 50:
        return "Fair match"
    return "Weak match"


def reasons(job, d):
    """A few plain sentences: why this job is or isn't a fit."""
    out = []
    if d["matched"]:
        out.append(f"You have {len(d['matched'])} of the skills it asks for: " + ", ".join(d["matched"][:6]) + ("…" if len(d["matched"]) > 6 else ""))
    if d["missing"]:
        out.append("Not on your profile yet: " + ", ".join(d["missing"][:5]))
    if d["title_match"]:
        if d["parts"]["title"] >= 70:
            out.append(f"The title lines up with \"{d['title_match']}\"")
        elif d["parts"]["title"] == 0:
            out.append("The title isn't one you're looking for")
    out += [n[0].upper() + n[1:] for n in d["level_notes"]]
    if d["place"]:
        out.append(d["place"][0].upper() + d["place"][1:])
    if d["pay"]:
        out.append(d["pay"][0].upper() + d["pay"][1:])
    if d.get("fresh"):
        out.append("Posted in the last few days, so you'd be an early applicant")
    out += d["flags"]
    return out


def keyword_coverage(job, resume_text):
    """ATS-style check: which of the job's skills your resume text actually mentions."""
    present, absent = [], []
    for s in job["skills"][:20]:
        (present if text.mentions(s, resume_text) else absent).append(s)
    total = len(present) + len(absent)
    return {"present": present, "absent": absent, "percent": round(100 * len(present) / total) if total else 0}
