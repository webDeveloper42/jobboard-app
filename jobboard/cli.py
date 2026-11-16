"""The terminal side: `jobboard --help`."""
import argparse
import json
import shutil
import sys
import textwrap

from . import boards
from .api import JobBoardApi
from .errors import JobBoardError
from .rules import text
from .storage import db

BOLD, DIM, GREEN, YELLOW, RED, RESET = ("\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[31m", "\033[0m") if sys.stdout.isatty() else ("",) * 6


def _width():
    return min(shutil.get_terminal_size((100, 20)).columns, 120)


def _score(value):
    if value is None:
        return f"{DIM} -- {RESET}"
    color = GREEN if value >= 80 else YELLOW if value >= 65 else "" if value >= 50 else DIM
    return f"{color}{BOLD}{value:>3}%{RESET}"


def _pay(j):
    lo, hi = j.get("salary_min"), j.get("salary_max")
    if not lo:
        return ""
    k = lambda n: f"${round(n / 1000)}K"
    return k(lo) if not hi or hi == lo else f"{k(lo)}–{k(hi)}"


def _row(j):
    status = f" [{j['status']}]" if j.get("status") else ""
    where = f"{j['work_model']}" + (f" · {j['location'][:28]}" if j.get("location") and j["work_model"] != "remote" else "")
    line = f"{_score(j['score'])}  {DIM}#{j['id']:<5}{RESET} {BOLD}{j['title'][:52]}{RESET} · {j['company'][:24]}{status}"
    extra = "  ".join(x for x in (where, _pay(j), j.get("posted") or "") if x)
    return f"{line}\n        {DIM}{extra}{RESET}"


def cmd_status(api, a):
    st = api.state({"view": "recommended"})
    p = st["profile"]
    c = st["counts"]
    print(f"{BOLD}Job board{RESET}  {c['active']} open jobs, {c['strong']} strong matches, {c['new']} new today"
          + (f"  ·  last refresh {st['last_refresh'][:16].replace('T', ' ')}" if st["last_refresh"] else ""))
    if not p["ready"]:
        print(f"\n{YELLOW}Set up your profile first:{RESET} jobboard resume ~/resume.pdf   (or: jobboard profile --titles 'Data Analyst' --skills 'SQL, Excel')")
    if not st["last_refresh"]:
        print(f"{YELLOW}Then fetch jobs:{RESET} jobboard refresh")
    ins = st["insights"]
    print(f"Applied {ins['applied']} ({ins['this_week']} this week)" + (f", {ins['response_rate']}% heard back" if ins["response_rate"] is not None else ""))
    for d in ins["due"][:4]:
        print(f"  {YELLOW}{d['next_date']}{RESET} {d['next_step'] or 'follow up'} · {d['title']} at {d['company']}  {DIM}#{d['job_id']}{RESET}")
    if st["jobs"]:
        print(f"\n{BOLD}Top matches{RESET}")
        for j in st["jobs"][:a.n]:
            print(_row(j))


def cmd_jobs(api, a):
    f = {"view": "hidden" if a.hidden else "recommended", "q": " ".join(a.query), "min_score": a.min, "days": a.days, "sort": a.sort,
         "work_model": ",".join(a.where or []), "show_tracked": "1" if a.all else "", "salary": "1" if a.paid else ""}
    st = api.state(f)
    for j in st["jobs"][:a.n]:
        print(_row(j))
    print(f"{DIM}{len(st['jobs'][:a.n])} of {st['total']} shown{RESET}")


def cmd_show(api, a):
    j = api.job(a.id)
    d = j["score_detail"]
    w = _width()
    print(f"{_score(j['score'])}  {BOLD}{j['title']}{RESET}  {DIM}{d.get('label', '')}{RESET}")
    print(f"      {j['company']} · {j['location'] or j['work_model']} · {j['work_model']} · {j['level_name']}" + (f" · {_pay(j)}" if _pay(j) else ""))
    print(f"      {DIM}{j['apply_url'] or j['url']}{RESET}")
    parts = d.get("parts", {})
    if parts:
        print("\n  " + "   ".join(f"{k} {v}%" for k, v in parts.items()))
    for reason in d.get("why", []):
        print(f"  • {reason}")
    cov = j["coverage"]
    if cov["present"] or cov["absent"]:
        print(f"\n  Resume keywords: {cov['percent']}%  {GREEN}{', '.join(cov['present'])}{RESET}" + (f"  {RED}missing: {', '.join(cov['absent'])}{RESET}" if cov["absent"] else ""))
    if j["sponsorship"] != "unknown":
        print(f"  Visa sponsorship: {j['sponsorship']}")
    if j["application"]:
        ap = j["application"]
        print(f"\n  {BOLD}{db.STATUS_NAMES[ap['status']]}{RESET}" + (f" · next: {ap['next_step']} {ap['next_date'] or ''}" if ap["next_step"] or ap["next_date"] else ""))
        if ap["notes"]:
            print(textwrap.indent(ap["notes"], "    "))
    if a.full:
        print()
        for para in (j["description"] or "").split("\n"):
            print(textwrap.fill(para, w - 4, initial_indent="    ", subsequent_indent="    ") if para.strip() else "")
    else:
        print(f"\n  {DIM}jobboard show {j['id']} --full  for the whole post{RESET}")


def cmd_profile(api, a):
    changes = {}
    for key in ("name", "email", "phone", "location", "headline"):
        if getattr(a, key) is not None:
            changes[key] = getattr(a, key)
    if a.titles is not None:
        changes["target_titles"] = a.titles
    if a.skills is not None:
        changes["skills"] = a.skills
    if a.add_skills:
        changes["skills"] = api.profile()["skills"] + [s.strip() for s in a.add_skills.split(",")]
    if a.cities is not None:
        changes["locations"] = a.cities
    if a.work is not None:
        changes["work_models"] = a.work
    if a.years is not None:
        changes["years_exp"] = a.years
    if a.level is not None:
        changes["level"] = a.level
    if a.min_salary is not None:
        changes["min_salary"] = a.min_salary
    if a.sponsorship is not None:
        changes["needs_sponsorship"] = a.sponsorship == "yes"
    if changes:
        api.do("profile", changes)
        print(f"{GREEN}Saved.{RESET} Every job was re-scored.")
    p = api.profile()
    show = [("Name", p["name"]), ("Email", p["email"]), ("Phone", p["phone"]), ("Lives in", p["location"]), ("Headline", p["headline"]),
            ("Looking for", ", ".join(p["target_titles"])), ("Level", text.LEVEL_NAMES.get(p["level"], "")), ("Years", p["years_exp"]),
            ("Work", ", ".join(p["work_models"])), ("Places", ", ".join(p["locations"])), ("Min pay", f"${p['min_salary']:,}" if p["min_salary"] else ""),
            ("Needs visa", "yes" if p["needs_sponsorship"] else "no"), ("Skills", ", ".join(p["skills"])),
            ("Resume", f"{p['resume_file'] or 'pasted'} ({len(p['resume_text'])} characters)" if p["resume_text"] else "")]
    for k, v in show:
        print(f"  {DIM}{k:<12}{RESET}{v if v not in (None, '') else DIM + '—' + RESET}")


def cmd_resume(api, a):
    if a.file == "-":
        out = api.do("resume_text", {"text": sys.stdin.read(), "file": "pasted"})
    else:
        out = api.do("resume_file", {"path": a.file})
    print(f"{GREEN}Resume saved.{RESET} Found {len(out['found_skills'])} skills: {', '.join(out['found_skills'][:20])}")
    if out.get("found_years") is not None:
        print(f"Looks like about {out['found_years']} years of experience (change it with: jobboard profile --years N)")
    if not out["target_titles"]:
        print(f"{YELLOW}Tell it what you're looking for:{RESET} jobboard profile --titles 'Software Engineer, Backend Engineer'")


def cmd_boards(api, a):
    st = api.state({})
    for s in st["sources"]:
        state = f"{GREEN}on {RESET}" if s["enabled"] else f"{DIM}off{RESET}"
        err = f"  {RED}{s['last_error']}{RESET}" if s["last_error"] else ""
        print(f"  {DIM}#{s['id']:<3}{RESET} {state} {s['name']:<28} {DIM}{s['kind']}{(':' + s['slug']) if s['slug'] else ''}{RESET}  {s['jobs']} jobs{err}")
    print(f"\n{DIM}Add a company: jobboard board add greenhouse stripe   (or lever / ashby, or paste the jobs page link){RESET}")
    print(f"{DIM}Add a Google Jobs search: jobboard board add google 'computer technician @ Washington, DC'   (or @ remote){RESET}")
    if not st["google_key"]:
        print(f"{YELLOW}Google Jobs needs a free SerpApi key:{RESET} jobboard google-key YOUR_KEY   (serpapi.com)")
    if not st["jooble_key"]:
        print(f"{YELLOW}Jooble needs an API key:{RESET} jobboard jooble-key YOUR_KEY   (jooble.org/api/about)")


def cmd_board(api, a):
    if a.action == "add":
        if not a.args:
            raise JobBoardError("Say which board, like: jobboard board add greenhouse stripe")
        kind, slug = (a.args[0], a.args[1]) if len(a.args) > 1 else (boards.slug_from(a.args[0])[0] or a.args[0], boards.slug_from(a.args[0])[1] if boards.slug_from(a.args[0])[0] else "")
        out = api.do("source_add", {"kind": kind, "slug": slug})
        _report(out)
    elif a.action in ("on", "off"):
        api.do("source_toggle", {"id": int(a.args[0]), "enabled": a.action == "on"})
        print("Done.")
    elif a.action == "rm":
        api.do("source_remove", {"id": int(a.args[0])})
        print("Removed. Jobs you were tracking from it are kept.")


def _report(out):
    for r in out.get("report", []):
        if r.get("error"):
            print(f"  {RED}✗{RESET} {r['source']}: {r['error']}")
        else:
            print(f"  {GREEN}✓{RESET} {r['source']}: {r['found']} jobs, {r['new']} new")


def cmd_google_key(api, a):
    out = api.do("google_key", {"key": a.key or ""})
    print("SerpApi key saved. Google Jobs searches run on: jobboard refresh" if out["google_key"] else "SerpApi key removed.")


def cmd_jooble_key(api, a):
    out = api.do("jooble_key", {"key": a.key or ""})
    print("Jooble key saved. Jooble searches run on: jobboard refresh" if out["jooble_key"] else "Jooble key removed.")


def cmd_refresh(api, a):
    print("Fetching boards…", flush=True)
    _report(api.do("refresh", {}))


def cmd_daily(api, a):
    from . import morning  # noqa: PLC0415
    out = morning.run(api, auto=a.auto)
    if out.get("skipped"):
        print(f"Nothing to do: {out['skipped']}.")
        return
    print(f"Checked {out['boards']} boards{' (with Google and Jooble, as it is Monday)' if out['keyed'] else ''}. "
          f"{len(out['jobs'])} new matches scoring {morning.MIN_SCORE}+" + (", emailed." if out["emailed"] else "."))
    for j in out["jobs"]:
        print(f"  {GREEN}{j['score']}{RESET} {j['title']} — {j['company']} ({j['location']})")
    for e in out["errors"]:
        print(f"  {RED}✗{RESET} {e}")


def cmd_sheets(api, a):
    out = api.do("sheets_sync", {"on": a.state == "on"} if a.state else {})
    print("Applications are written to your job sheets in the Sheets tab." if out["sheets_sync"] else "Applications are no longer written to the Sheets tab.")


def _track(status):
    def run(api, a):
        api.do("status", {"id": a.id, "status": status})
        print(f"#{a.id} is now {db.STATUS_NAMES[status].lower()}.")
    return run


def cmd_move(api, a):
    api.do("status", {"id": a.id, "status": a.status})
    print(f"#{a.id} is now {a.status}.")


def cmd_next(api, a):
    api.do("track", {"id": a.id, "next_step": " ".join(a.step), "next_date": a.date or ""})
    print("Saved.")


def cmd_note(api, a):
    j = api.job(a.id)
    old = (j["application"] or {}).get("notes") or ""
    api.do("track", {"id": a.id, "notes": (old + "\n" if old else "") + f"[{db.today()}] " + " ".join(a.text)})
    print("Noted.")


def cmd_tracker(api, a):
    st = api.state({})
    for s in db.STATUSES:
        items = st["board"].get(s, [])
        if not items and s in ("withdrawn",):
            continue
        print(f"{BOLD}{db.STATUS_NAMES[s]}{RESET} ({len(items)})")
        for it in items:
            nxt = f"  {YELLOW}{it['next_date'] or ''} {it['next_step']}{RESET}" if it["next_step"] or it["next_date"] else ""
            print(f"  {_score(it['score'])} {DIM}#{it['job_id']:<5}{RESET} {it['title'][:48]} · {it['company'][:22]}{nxt}")


def _doc(kind):
    def run(api, a):
        print("Writing… (the local model takes a minute)", flush=True)
        out = api.do(kind, {"id": a.id, "ai": not a.quick})
        print(f"\n{out['body']}\n\n{DIM}Saved to job #{a.id}{' · ' + out['model'] if out['model'] else ' · template'}{RESET}")
    return run


def cmd_ask(api, a):
    print("Thinking…", flush=True)
    out = api.do("ask", {"q": " ".join(a.question), "id": a.job})
    print(f"\n{out['answer']}")


def cmd_add(api, a):
    desc = sys.stdin.read() if not sys.stdin.isatty() else ""
    out = api.do("add_job", {"title": a.title, "company": a.company, "url": a.url or "", "location": a.location or "", "description": desc})
    print(f"Added as #{out['id']} ({out['score']}% match) and saved to your tracker.")


def cmd_export(api, a):
    sys.stdout.buffer.write(api.export_csv())


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jobboard", description="Local AI job search: matches, tracker, resume tailoring, copilot.")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("status", help="overview and top matches (the default)")
    p.add_argument("-n", type=int, default=10)
    p.set_defaults(fn=cmd_status)
    p = sub.add_parser("jobs", help="list matching jobs")
    p.add_argument("query", nargs="*")
    p.add_argument("--min", type=int, help="minimum match score")
    p.add_argument("--days", type=int, help="posted in the last N days")
    p.add_argument("--where", action="append", choices=db.WORK_MODELS)
    p.add_argument("--sort", choices=["score", "recent", "salary", "company"], default="score")
    p.add_argument("--paid", action="store_true", help="only jobs that list pay")
    p.add_argument("--all", action="store_true", help="include jobs you're already tracking")
    p.add_argument("--hidden", action="store_true", help="jobs you marked not interested")
    p.add_argument("-n", type=int, default=25)
    p.set_defaults(fn=cmd_jobs)
    p = sub.add_parser("show", help="one job with its match breakdown")
    p.add_argument("id", type=int)
    p.add_argument("--full", action="store_true")
    p.set_defaults(fn=cmd_show)
    p = sub.add_parser("profile", help="show or change your profile")
    for k in ("name", "email", "phone", "location", "headline"):
        p.add_argument(f"--{k}")
    p.add_argument("--titles", help="job titles you want, comma separated")
    p.add_argument("--skills", help="replace your skills, comma separated")
    p.add_argument("--add-skills", help="add skills, comma separated")
    p.add_argument("--cities", help="places you'd work, comma separated")
    p.add_argument("--work", help="remote,hybrid,onsite")
    p.add_argument("--years", type=int)
    p.add_argument("--level", choices=text.LEVELS)
    p.add_argument("--min-salary", type=int)
    p.add_argument("--sponsorship", choices=["yes", "no"], help="do you need visa sponsorship")
    p.set_defaults(fn=cmd_profile)
    p = sub.add_parser("resume", help="load your resume (.pdf .docx .txt .md, or - for stdin)")
    p.add_argument("file")
    p.set_defaults(fn=cmd_resume)
    p = sub.add_parser("boards", help="job boards you pull from")
    p.set_defaults(fn=cmd_boards)
    p = sub.add_parser("board", help="add / on / off / rm a board")
    p.add_argument("action", choices=["add", "on", "off", "rm"])
    p.add_argument("args", nargs="*")
    p.set_defaults(fn=cmd_board)
    p = sub.add_parser("google-key", help="save your SerpApi key for Google Jobs searches (blank removes it)")
    p.add_argument("key", nargs="?")
    p.set_defaults(fn=cmd_google_key)
    p = sub.add_parser("jooble-key", help="save your Jooble API key for Jooble searches (blank removes it)")
    p.add_argument("key", nargs="?")
    p.set_defaults(fn=cmd_jooble_key)
    p = sub.add_parser("daily", help="the morning run: refresh boards, then summarize new matches (cron uses --auto)")
    p.add_argument("--auto", action="store_true", help="skip if today's run already happened")
    p.set_defaults(fn=cmd_daily)
    p = sub.add_parser("sheets", help="write applications to your job sheets in the Sheets tab (on / off)")
    p.add_argument("state", nargs="?", choices=["on", "off"])
    p.set_defaults(fn=cmd_sheets)
    p = sub.add_parser("refresh", help="fetch new jobs from your boards")
    p.set_defaults(fn=cmd_refresh)
    for name, status in (("save", "saved"), ("apply", "applied"), ("interview", "interviewing"), ("offer", "offer"), ("reject", "rejected")):
        p = sub.add_parser(name, help=f"mark a job {status}")
        p.add_argument("id", type=int)
        p.set_defaults(fn=_track(status))
    p = sub.add_parser("move", help="set any status")
    p.add_argument("id", type=int)
    p.add_argument("status", choices=db.STATUSES)
    p.set_defaults(fn=cmd_move)
    p = sub.add_parser("next", help="set the next step for a job: jobboard next 12 'Send thank-you' --date 2026-11-12")
    p.add_argument("id", type=int)
    p.add_argument("step", nargs="*")
    p.add_argument("--date")
    p.set_defaults(fn=cmd_next)
    p = sub.add_parser("note", help="add a dated note to a job")
    p.add_argument("id", type=int)
    p.add_argument("text", nargs="+")
    p.set_defaults(fn=cmd_note)
    p = sub.add_parser("tracker", help="your applications by stage")
    p.set_defaults(fn=cmd_tracker)
    for name, kind, about in (("tailor", "tailor", "tailor your resume to a job"), ("letter", "letter", "write a cover letter for a job")):
        p = sub.add_parser(name, help=about)
        p.add_argument("id", type=int)
        p.add_argument("--quick", action="store_true", help="template only, no AI")
        p.set_defaults(fn=_doc(kind))
    p = sub.add_parser("ask", help="ask the coach")
    p.add_argument("question", nargs="+")
    p.add_argument("--job", type=int)
    p.set_defaults(fn=cmd_ask)
    p = sub.add_parser("add", help="add a job from anywhere (description on stdin)")
    p.add_argument("title")
    p.add_argument("company")
    p.add_argument("--url")
    p.add_argument("--location")
    p.set_defaults(fn=cmd_add)
    p = sub.add_parser("export", help="your tracker as CSV")
    p.set_defaults(fn=cmd_export)
    p = sub.add_parser("json", help="the full state as JSON, for scripts")
    p.set_defaults(fn=lambda api, a: print(json.dumps(api.state({}), indent=1, default=str)))

    p = sub.add_parser("serve", help="the Jobs page on its own, at http://127.0.0.1:8820/jobs/ (no dashboard needed)")
    p.add_argument("--port", type=int, default=8820)

    a = ap.parse_args(argv)
    if not a.cmd:
        a = ap.parse_args(["status"])
    if a.cmd == "serve":
        from .server import serve  # noqa: PLC0415
        serve(a.port)
        return 0
    api = JobBoardApi()
    try:
        a.fn(api, a)
    except JobBoardError as e:
        print(f"{RED}{e}{RESET}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    finally:
        api.close()
    return 0
