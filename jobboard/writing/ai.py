"""The writing help, from your local Ollama models. Nothing leaves this machine.

If Ollama isn't running, tailoring and cover letters fall back to a plain template built from
your match, so those buttons always give you something to start from.
"""
import json
import os
import re
import urllib.error
import urllib.request

HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
if not HOST.startswith("http"):
    HOST = "http://" + HOST
PREFERRED = ["qwen2.5:3b", "llama3.2:3b", "llama3.2:1b"]
OPTIONS = {"temperature": 0.3, "top_p": 0.9, "repeat_penalty": 1.08, "num_ctx": 6144}
JOB_CHARS = 3500
RESUME_CHARS = 4000


class AiError(RuntimeError):
    pass


def _req(path, body=None, timeout=600):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(HOST + path, data=data, headers={"Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error", str(e))
        except ValueError:
            msg = str(e)
        raise AiError(msg) from None
    except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
        raise AiError(f"can't reach Ollama at {HOST} ({getattr(e, 'reason', e)})") from None


def models():
    with _req("/api/tags", timeout=4) as r:
        return [m["name"] for m in json.load(r).get("models", [])]


def pick(wanted=None):
    try:
        have = models()
    except AiError:
        return None
    names = {n.removesuffix(":latest"): n for n in have}
    for m in [wanted] + PREFERRED:
        if m and (m in have or m in names):
            return m
    return have[0] if have else None


def chat(model, messages, max_tokens=700):
    body = {"model": model, "messages": messages, "stream": False, "keep_alive": "20m",
            "options": dict(OPTIONS, num_predict=max_tokens)}
    with _req("/api/chat", body) as r:
        out = json.load(r)
    return (out.get("message") or {}).get("content", "").strip()


# ---------------------------------------------------------------- prompts

def _profile_block(p):
    lines = [f"Name: {p['name'] or '(not given)'}"]
    if p["headline"]:
        lines.append(f"Headline: {p['headline']}")
    if p["target_titles"]:
        lines.append("Looking for: " + ", ".join(p["target_titles"]))
    if p["years_exp"] is not None:
        lines.append(f"Years of experience: {p['years_exp']}")
    if p["skills"]:
        lines.append("Skills: " + ", ".join(p["skills"]))
    resume = (p["resume_text"] or "").strip()
    if resume:
        lines.append("Resume:\n" + resume[:RESUME_CHARS])
    return "\n".join(lines)


def _job_block(job):
    head = f"{job['title']} at {job['company']}" + (f" ({job['location']})" if job.get("location") else "")
    pay = f"\nPay: {job['salary_text']}" if job.get("salary_text") else ""
    return f"Job: {head}{pay}\nKey skills: {', '.join(job['skills'][:12])}\nPosting:\n{(job.get('description') or '')[:JOB_CHARS]}"


HONEST = ("Use only facts from the candidate's resume and profile. Never invent employers, titles, degrees, numbers or skills. "
          "Don't inflate what they did: if the resume says 'built', don't write 'led'. "
          "If the job asks for something the candidate doesn't show, say so plainly instead of claiming it.")


def tailor(model, prof, job, match_detail, coverage):
    system = "You are a careful resume coach. " + HONEST
    prompt = (f"{_profile_block(prof)}\n\n{_job_block(job)}\n\n"
              f"Skills the resume already shows for this job: {', '.join(coverage['present']) or 'none'}\n"
              f"Job skills missing from the resume: {', '.join(coverage['absent']) or 'none'}\n\n"
              "Write, in plain text with these exact headings:\n"
              "SUMMARY: a 2-3 sentence professional summary aimed at this job.\n"
              "BULLETS: 4-6 resume bullet points rewritten from the candidate's real experience, using the job's wording where it truthfully fits. Start each with '- '.\n"
              "KEYWORDS: missing keywords worth adding only if the candidate truly has them.\n"
              "GAPS: anything important the candidate lacks, and one honest way to address it.")
    return chat(model, [{"role": "system", "content": system}, {"role": "user", "content": prompt}], 800)


def cover_letter(model, prof, job, match_detail):
    system = "You write short, specific cover letters in a warm, confident, plain voice. " + HONEST
    prompt = (f"{_profile_block(prof)}\n\n{_job_block(job)}\n\n"
              f"Strengths that match: {', '.join(match_detail.get('matched', [])[:8]) or 'see resume'}\n\n"
              "Write a cover letter of about 220 words: three short paragraphs, no placeholders in brackets, no address block. "
              f"Open with why this role at {job['company']} specifically. Sign off with the candidate's name.")
    return chat(model, [{"role": "system", "content": system}, {"role": "user", "content": prompt}], 600)


def ask(model, prof, job, history, question, stats):
    system = ("You are a a practical job-search copilot for one person. You know their profile and, when given, one job. "
              "Answer briefly and concretely: interview prep, how to pitch themselves, what to ask, salary talk, follow-ups, what to learn next. "
              + HONEST + "\n\n" + _profile_block(prof) + (f"\n\nTheir search so far:\n{stats}" if stats else "")
              + (f"\n\nThe job they're looking at:\n{_job_block(job)}" if job else ""))
    messages = [{"role": "system", "content": system}]
    for m in history[-8:]:
        messages.append({"role": m["role"], "content": m["content"][:2000]})
    messages.append({"role": "user", "content": question})
    return chat(model, messages, 600)


# ---------------------------------------------------------------- when Ollama is off

def tailor_fallback(prof, job, match_detail, coverage):
    lines = ["SUMMARY:",
             f"{prof['headline'] or 'Professional'} with {str(prof['years_exp']) + '+ years of ' if prof['years_exp'] else ''}experience in "
             f"{', '.join(coverage['present'][:4]) or ', '.join(prof['skills'][:4]) or 'your field'}, looking to bring that to the {job['title']} role at {job['company']}.",
             "", "KEYWORDS already in your resume (keep them near the top):", "- " + (", ".join(coverage["present"]) or "none found")]
    if coverage["absent"]:
        lines += ["", "KEYWORDS the job uses that your resume doesn't (add only the ones you really have):", "- " + ", ".join(coverage["absent"])]
    if match_detail.get("level_notes"):
        lines += ["", "GAPS:"] + [f"- {n}" for n in match_detail["level_notes"]]
    lines += ["", "(Ollama isn't running, so this is the quick version. Start it with `ollama serve` for rewritten bullets.)"]
    return "\n".join(lines)


def letter_fallback(prof, job, match_detail):
    strengths = match_detail.get("matched", [])[:4]
    skills = ", ".join(strengths[:-1]) + (f" and {strengths[-1]}" if len(strengths) > 1 else (strengths[0] if strengths else "")) if strengths else "the skills you list"
    name = prof["name"] or "Your name"
    return (f"Dear {job['company']} hiring team,\n\n"
            f"I'm applying for the {job['title']} role. What drew me to {job['company']} is the work this team is doing, "
            f"and I believe my background fits what you're looking for.\n\n"
            f"{('With ' + str(prof['years_exp']) + ' years of experience, ') if prof['years_exp'] else ''}I've built my work around {skills}, "
            f"which this role relies on. I'd welcome the chance to bring that to your team and keep growing with it.\n\n"
            f"Thank you for your time. I'd be glad to talk about how I can help.\n\nSincerely,\n{name}\n\n"
            "(Template version: Ollama isn't running. Start it with `ollama serve` for a letter written for this job.)")


def clean(textout):
    """Small models sometimes wrap answers in code fences or echo the headings in bold."""
    textout = re.sub(r"^```\w*\n?|\n?```$", "", textout.strip())
    return re.sub(r"\*\*(.+?)\*\*", r"\1", textout)
