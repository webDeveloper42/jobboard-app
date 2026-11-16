"""Spotting fake job posts, so they never reach the board.

Each sign of a scam adds points; a post with SCAM_AT or more is left out. Plain rules, so the reason can always be shown.

    3  the sure signs: interviews or contact over Telegram / WhatsApp / Signal, a check to deposit or equipment to buy,
       a fee to start, reshipping packages or moving money, asking for an SSN or bank details up front
    2  strong hints: a free email address (gmail, yahoo…) to apply to, hiring with no interview, pay far above
       what the role pays
    1  weak hints: no company name, "urgent hiring" pressure, a post that's barely there, shouting in capitals

Remote data entry is the most common job scam, so data entry posts get extra checks (_DATA_ENTRY_SIGNS): texting a
phone number to apply, "work from your phone", a too-easy pitch, a company named after the job itself, and a lower
pay ceiling (real data entry pays about $15-25 an hour).

Real employers often warn about scams in their posts ("we will never ask you to pay or contact you on WhatsApp").
Sentences like that are dropped before looking, so a warning against scams never counts as one.
"""
import re

SCAM_AT = 3

_FLAGS = re.I | re.S
_APPS = r"(?:telegram|whats\s?app|signal(?: app| messenger)?|wickr|kik|wechat|google hangouts?|hangouts?|google chat|skype chat)"

# (points, why, pattern)
_SIGNS = [
    (3, "asks you to talk on a messaging app", re.compile(
        r"\b(?:contact|text|message|reach(?: out to)?|add|chat with|interview(?:ed|s)?(?: will be)?(?: held| conducted)?|apply|send|dm|connect)\b"
        r"[^.\n]{0,40}?\b(?:on|via|through|over|using|at|in)\s+" + _APPS + r"\b"
        r"|\b" + _APPS + r"\s*(?:id|handle|number|no\.?)?\s*[:@+]\s*[@+]?\w"
        r"|\b(?:telegram|whats\s?app|signal)\s+(?:interview|chat|screening)\b", _FLAGS)),
    (3, "sends you a check or has you buy equipment", re.compile(
        r"\b(?:send|mail|issue|provide|give)s?\s+you\s+(?:a\s+)?(?:check|cheque|payment)\b[^.\n]{0,60}\b(?:equipment|laptop|software|supplies|deposit)"
        r"|\bdeposit\s+(?:the|a|this)\s+(?:check|cheque)\b|\b(?:check|cheque)\s+(?:to|for)\s+(?:purchase|buy)\b"
        r"|\b(?:purchase|buy)\s+(?:your\s+)?(?:own\s+)?(?:equipment|laptop|software|office supplies)\s+(?:from|through)\s+(?:our|a|the)\s+(?:approved\s+|preferred\s+)?(?:vendor|supplier)", _FLAGS)),
    (3, "wants a fee to start", re.compile(
        r"\b(?:training|registration|application|onboarding|processing|enrollment|certification|starter kit|equipment)\s+(?:fee|deposit|cost)s?\s+(?:of|is|are|:)\s*\$"
        r"|\b(?:pay|send|deposit)\s+(?:a\s+|the\s+|an?\s+)?(?:small\s+|one[- ]time\s+|refundable\s+)?(?:fee|deposit)\b"
        r"|\brefundable deposit\b|\bstarter kit\s+(?:for|at|costs?)\s+\$", _FLAGS)),
    (3, "moves packages or money for someone", re.compile(
        r"\breship(?:ping|per)?\b|\bpackage (?:forwarding|reshipping)\b|\breceive\s+(?:and|&)\s+(?:re-?)?ship\s+(?:packages|parcels)\b"
        r"|\bprocess(?:ing)?\s+payments?\s+(?:for|from|on behalf of)\s+(?:our\s+)?(?:clients|customers)\b|\bmoney transfer agent\b"
        r"|\btransfer(?:ring)?\s+funds\s+(?:to|for|between)\b|\b(?:buy|purchase|purchasing|buying)\s+gift cards\b|\bbitcoin atm\b", _FLAGS)),
    (3, "asks for your SSN or bank details up front", re.compile(
        r"\b(?:send|provide|include|submit|email|text)\b[^.\n]{0,40}\b(?:ssn|social security (?:number|card)|bank (?:account|details|routing|login)"
        r"|routing number|credit card(?: number)?|photo of your (?:id|driver'?s licen[cs]e))\b", _FLAGS)),
    (2, "apply through a personal email address", re.compile(
        r"[\w.+-]+@(?:gmail|yahoo|ymail|hotmail|outlook|live|aol|icloud|me|proton(?:mail)?|gmx|mail)\.(?:com|net|me|ch)\b", re.I)),
    (2, "hires without an interview", re.compile(
        r"\bno (?:interview|interviews) (?:required|needed|necessary)\b|\bhired (?:immediately|on the spot|same day) without\b"
        r"|\binterview(?:s|ed)?\s+(?:will be\s+)?(?:done\s+|held\s+|conducted\s+)?(?:by|via|over|through)\s+(?:text|chat|instant messag)", _FLAGS)),
    (2, "promises easy money", re.compile(
        r"\bearn (?:up to )?\$\s?\d[\d,]*\+?\s*(?:per|a|/|every)\s*(?:day|week)\b|\$\s?\d{3,}[\d,]*\s*(?:per|a|/)\s*day\b"
        r"|\bget paid (?:daily|to type)\b|\bguaranteed (?:income|earnings|pay)\b|\bunlimited earning", _FLAGS)),
    (1, "pressure to act fast", re.compile(
        r"\burgent(?:ly)? (?:hiring|needed)\b|\bimmediate (?:hire|hiring|start)\b|\bact (?:fast|now)\b|\blimited (?:spots|positions|openings) available\b"
        r"|\bhiring immediately\b|\bstart today\b", _FLAGS)),
]

_NO_COMPANY = re.compile(r"^\s*(?:|confidential|private|anonymous|undisclosed|n/?a|unknown|hiring|company|employer|private employer|confidential company)\s*$", re.I)
# A sentence that warns about scams, or says what the employer will never do.
_DISCLAIMER = re.compile(r"\b(?:never|will not|won't|do not|don't|does not|doesn't|cannot|not ask|beware|fraud\w*|scam\w*|phishing|purport\w*|"
                         r"impersonat\w*|fake|suspicious|report it|legitimate)\b", re.I)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")

# Extra checks for data entry posts only.
_DATA_ENTRY_SIGNS = [
    (2, "asks you to text a phone number to apply", re.compile(
        r"\b(?:text|sms|message|call)\b[^.\n]{0,40}?(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", _FLAGS)),
    (2, "work from your phone", re.compile(r"\b(?:work|type|earn)\s+(?:from|on|using)\s+(?:your\s+)?(?:phone|smartphone|mobile)\b", _FLAGS)),
    (2, "pays you before you start or for training", re.compile(
        r"\b(?:sign[- ]on|signing)\s+bonus\b[^.\n]{0,40}\b(?:before|upon|on)\s+(?:you\s+)?(?:start|hire|accept)|\bpaid training\s+(?:via|on|through)\s+(?:chat|text|telegram|whatsapp)", _FLAGS)),
    (1, "too-easy pitch (no experience, any hours, high pay)", re.compile(
        r"(?=[\s\S]*\bno (?:prior |previous )?experience (?:needed|required|necessary)\b)(?=[\s\S]*\b(?:flexible (?:hours|schedule)|set your own (?:hours|schedule)|work (?:anytime|whenever))\b)", _FLAGS)),
]
_JOB_TYPE_COMPANY = re.compile(r"\b(?:data entry|typing|typist|online jobs?|remote jobs?|work from home|wfh)\b", re.I)

# A yearly pay above this for an entry-level role in these categories is too good to be true.
_PAY_CEILING = {"it_intern": 110_000, "it_tech": 130_000, "data_entry": 62_000}


def _plain(desc):
    """The description without sentences that warn about scams."""
    return " ".join(s for s in _SENTENCE.split(desc or "") if s and not _DISCLAIMER.search(s))


def assess(job, category=None):
    """(points, reasons) for one job. points >= SCAM_AT means it looks like a scam."""
    desc = job.get("description") or ""
    body = _plain(desc)
    hay = f"{job.get('title') or ''}\n{body}"
    points, why = 0, []
    for value, reason, pattern in _SIGNS:
        if pattern.search(hay):
            points += value
            why.append(reason)
    if _NO_COMPANY.match(job.get("company") or ""):
        points += 1
        why.append("no company name")
    if category == "data_entry":
        for value, reason, pattern in _DATA_ENTRY_SIGNS:
            if pattern.search(hay):
                points += value
                why.append(reason)
        if _JOB_TYPE_COMPANY.search(job.get("company") or ""):
            points += 1
            why.append("the company is named after the job, not an employer")
    # Jooble only sends a short snippet of each post, so a short text there says nothing about the job.
    if desc and len(desc.strip()) < 150 and not str(job.get("key") or "").startswith("jooble:"):
        points += 1
        why.append("almost no description")
    words = re.findall(r"[A-Za-z]{4,}", f"{job.get('title') or ''} {desc[:1500]}")
    if len(words) >= 20 and sum(w.isupper() for w in words) / len(words) > 0.3 or desc.count("!!") >= 2 or "$$$" in desc:
        points += 1
        why.append("written like an ad")
    ceiling = _PAY_CEILING.get(category)
    top = job.get("salary_max") or job.get("salary_min")
    try:
        top = int(top) if top else None
    except (TypeError, ValueError):
        top = None
    if ceiling and top and top > ceiling:
        points += 2
        why.append(f"pay (${top:,}) far above what this role pays")
    return points, why


def is_scam(job, category=None):
    """(True, 'why') when a job post looks fake."""
    points, why = assess(job, category)
    return points >= SCAM_AT, ", ".join(why)
