"""The morning run: refresh the boards on their own, then a short list of the new jobs worth a look.

`jobboard daily --auto` (cron runs it every half hour from 7 to noon, since the server isn't always on) does this
once a day:

* refreshes the free boards and employer career sites every day, and the keyed searches (Google Jobs via SerpApi,
  Jooble) only on Mondays, so the daily run doesn't use up your API searches
* reads the whole post for the best new matches that came with only a few lines (AUTO_FULL of them): the employer's
  page first, which is free, then a Google Jobs lookup for up to AUTO_GOOGLE of them (one SerpApi search each)
* keeps the new jobs scoring MIN_SCORE or more as today's summary, shown at the top of the Jobs page
* emails the summary too, when mail is set up (the same Gmail settings the daily dashboard email uses:
  ~/.config/discover-tools/mail.json with {"user", "pass" (a Gmail app password), "to"})
"""
import datetime as dt
import html
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from . import boards
from .storage import db

MIN_SCORE = 65
AUTO_FULL = 10      # best new snippet-only matches to read in full each morning
AUTO_GOOGLE = 5     # of those, how many may use a SerpApi search when the employer's page can't be read
SNIPPET = 1500      # a description shorter than this is treated as a snippet
KEYED_DAY = 0  # Monday
MAIL_FILE = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "discover-tools" / "mail.json"


def mail_config():
    try:
        cfg = json.loads(MAIL_FILE.read_text())
    except (OSError, ValueError):
        return None
    if not cfg.get("user") or not cfg.get("pass"):
        return None
    return {"to": cfg["user"], "host": "smtp.gmail.com", "port": 465, **cfg}


def build(api, since):
    """Today's summary: new, untracked, unhidden jobs since `since` that score MIN_SCORE or more, best first."""
    def go():
        rows = api.con.execute(f"""SELECT id, title, company, location, score, score_detail, salary_min, salary_max, url, travel, posted
                                  FROM jobs WHERE active AND NOT hidden AND first_seen >= ? AND coalesce(score, 0) >= ?
                                  AND {api.visible_sql()} AND id NOT IN (SELECT job_id FROM applications) ORDER BY score DESC LIMIT 25""", (since, MIN_SCORE)).fetchall()
        out = []
        for r in rows:
            j = db.job_row(r)
            d = j.pop("score_detail")
            out.append({"id": j["id"], "title": j["title"], "company": j["company"], "location": j["location"], "score": j["score"],
                        "label": d.get("label", ""), "flags": d.get("flags", [])[:3], "url": j["url"], "travel": j.get("travel") or {},
                        "pay": _pay(j)})
        return out
    return api.run_in_db(go)


def _pay(j):
    low, high = j.get("salary_min"), j.get("salary_max")
    if not low:
        return ""
    if high and high <= 150_000 and low % 2080 == 0 and high % 2080 == 0:
        return f"${low // 2080}–${high // 2080}/hr" if high != low else f"${low // 2080}/hr"
    return f"${low // 1000}k–${high // 1000}k" if high and high != low else f"${low // 1000}k"


def render(jobs, day):
    """(subject, html, text) for the email."""
    subject = f"{len(jobs)} new job match{'es' if len(jobs) != 1 else ''} for {day:%A, %B %-d}"
    lines, items = [], []
    for j in jobs:
        extra = " · ".join(x for x in (j["pay"], f"{j['travel']['transit']} min by Metro/bus" if j["travel"].get("transit") else "") if x)
        lines.append(f"{j['score']}  {j['title']} — {j['company']} ({j['location']}){'  ' + extra if extra else ''}\n    {j['url']}")
        flags = "".join(f"<div style='color:#a15c00;font-size:12px'>⚠ {html.escape(f)}</div>" for f in j["flags"])
        items.append(f"<tr><td style='padding:10px 0;border-bottom:1px solid #eee'><b style='font-size:18px;color:#1a7f37'>{j['score']}</b></td>"
                     f"<td style='padding:10px 12px;border-bottom:1px solid #eee'><a href='{html.escape(j['url'])}' style='font-weight:600;color:#0b57d0'>"
                     f"{html.escape(j['title'])}</a><div>{html.escape(j['company'])} · {html.escape(j['location'])}</div>"
                     f"<div style='color:#555;font-size:13px'>{html.escape(extra)}</div>{flags}</td></tr>")
    body = (f"<div style='font-family:system-ui,sans-serif;max-width:640px'><h2 style='margin:0 0 8px'>{html.escape(subject)}</h2>"
            f"<p style='color:#555'>New since yesterday, scoring {MIN_SCORE} or more. Open the Jobs tab to save or apply.</p>"
            f"<table style='border-collapse:collapse;width:100%'>{''.join(items)}</table></div>")
    return subject, body, subject + "\n\n" + "\n".join(lines)


def send(subject, body, plain, cfg):
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, f"Job board <{cfg['user']}>", cfg["to"]
    msg.set_content(plain)
    msg.add_alternative(body, subtype="html")
    with smtplib.SMTP_SSL(cfg["host"], int(cfg["port"]), context=ssl.create_default_context(), timeout=30) as s:
        s.login(cfg["user"], cfg["pass"])
        s.send_message(msg)


def fill_snippets(api, since):
    """Read the whole post for the best new matches that only have a few lines. Returns {'read', 'google'}."""
    rows = api.run_in_db(lambda: [r[0] for r in api.con.execute(
        f"""SELECT id FROM jobs WHERE active AND NOT hidden AND full_text = 0 AND length(coalesce(description, '')) < ?
            AND first_seen >= ? AND coalesce(score, 0) >= ? AND {api.visible_sql()} ORDER BY score DESC LIMIT ?""",
        (SNIPPET, since, MIN_SCORE - 10, AUTO_FULL))])
    read = google = 0
    for job_id in rows:
        allow = google < AUTO_GOOGLE
        try:
            out = api.full_post({"id": job_id, "google": allow})
        except Exception:   # noqa: BLE001 - one job's failure (SerpApi out of searches, a dead link) mustn't stop the run
            continue
        if out.get("found"):
            read += 1
            google += out.get("via") == "Google Jobs"
        elif allow and api.run_in_db(api.settings.google_key):
            google += 1     # a lookup that found nothing still used a search
    return {"read": read, "google": google, "tried": len(rows)}


def run(api, auto=False, today=None, mail=True):
    """One morning run. With auto, does nothing if today's run already happened. Returns what it did."""
    today = today or dt.date.today()
    if auto and api.run_in_db(lambda: db.setting(api.con, "daily_last")) == today.isoformat():
        return {"skipped": "already ran today"}
    since = api.run_in_db(lambda: db.setting(api.con, "daily_since")) or (dt.datetime.now() - dt.timedelta(days=1)).isoformat()
    started = dt.datetime.now().isoformat(timespec="seconds")
    enabled = api.run_in_db(lambda: [dict(r) for r in api.con.execute("SELECT id, kind FROM sources WHERE enabled = 1 AND kind != 'manual'")])
    keyed_today = today.weekday() == KEYED_DAY
    report = []
    for b in enabled:
        if b["kind"] in boards.KEYED and not keyed_today:
            continue
        report += api.refresh({"source": b["id"]})["report"]
    full = fill_snippets(api, since)
    jobs = build(api, since)
    summary = {"day": today.isoformat(), "at": started, "jobs": jobs, "boards": len(report),
               "errors": [f"{r['source']}: {r['error']}" for r in report if r.get("error")], "keyed": keyed_today, "full_posts": full}
    emailed = None
    cfg = mail_config() if mail else None
    if cfg and jobs:
        try:
            send(*render(jobs, today), cfg)
            emailed = cfg["to"]
        except (OSError, smtplib.SMTPException) as e:
            summary["errors"].append(f"email: {e}")
    summary["emailed"] = bool(emailed)

    def save():
        db.set_setting(api.con, "daily_summary", json.dumps(summary))
        db.set_setting(api.con, "daily_last", today.isoformat())
        db.set_setting(api.con, "daily_since", started)
        api.con.commit()
    api.run_in_db(save)
    return summary
