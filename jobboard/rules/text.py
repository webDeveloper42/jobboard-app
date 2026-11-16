"""Reading job posts and resumes: HTML to text, skills, seniority, years, salary, work model, visa sponsorship.

Everything here is plain rules, so a match score can always say why it is what it is.
"""
import html
import re
from html.parser import HTMLParser

# ---------------------------------------------------------------- HTML to text

_BLOCK = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "header", "footer", "table"}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "li":
            self.out.append("\n• ")
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def fix_mojibake(value):
    """'Sothebyâ\x80\x99s' -> 'Sotheby’s': UTF-8 that was read as Latin-1 somewhere upstream."""
    if not value or not any(c in value for c in "âÃÂ"):
        return value
    for codec in ("cp1252", "latin-1"):
        try:
            fixed = value.encode(codec).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        return fixed
    return value


def html_to_text(value):
    """Job boards send HTML, sometimes escaped twice (Greenhouse). Returns tidy plain text."""
    if not value:
        return ""
    text = value
    if "&lt;" in text and "<" not in text:
        text = html.unescape(text)
    if "<" in text:
        parser = _Text()
        try:
            parser.feed(text)
            parser.close()
            text = "".join(parser.out)
        except Exception:  # noqa: BLE001 - broken HTML still has words in it
            text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------- skills

# name -> aliases (regex fragments, case-insensitive). The first is the display name.
SKILLS = {
    # languages
    "Python": [r"python"], "Java": [r"java(?!\s*script)"], "JavaScript": [r"javascript", r"(?<!\.)\bjs\b", r"ecmascript"],
    "TypeScript": [r"typescript"], "C++": [r"c\+\+", r"cpp"], "C#": [r"c#", r"\.net\b", r"dotnet"], "Go": [r"golang"],
    "Rust": [r"\brust\b(?!\s*belt)"], "Ruby": [r"\bruby\b"], "PHP": [r"\bphp\b"], "Kotlin": [r"kotlin"], "Swift": [r"\bswift\b(?!ly)"],
    "Scala": [r"\bscala\b"], "R": [], "SQL": [r"\bsql\b"], "Bash": [r"\bbash\b", r"shell scripting"], "Perl": [r"\bperl\b"],
    "MATLAB": [r"matlab"], "Elixir": [r"elixir"], "Dart": [r"\bdart\b"], "Objective-C": [r"objective-c"], "Solidity": [r"solidity"],
    "HTML": [r"\bhtml5?\b"], "CSS": [r"\bcss3?\b", r"\bsass\b", r"\bscss\b"],
    # frontend / mobile
    "React": [r"\breact(\.js|js)?\b(?! native)", r"\bmern\b"], "React Native": [r"react native"], "Vue": [r"\bvue(\.js|js)?\b"], "Angular": [r"\bangular(js)?\b"],
    "Next.js": [r"next\.?js"], "Svelte": [r"svelte"], "Redux": [r"redux"], "Tailwind": [r"tailwind"], "jQuery": [r"jquery"],
    "Flutter": [r"flutter"], "iOS": [r"\bios\b"], "Android": [r"android"], "Webpack": [r"webpack"], "GraphQL": [r"graphql"],
    # backend / frameworks
    "Node.js": [r"node\.?js", r"\bnode\b", r"\bmern\b"], "Django": [r"django"], "Flask": [r"\bflask\b"], "FastAPI": [r"fastapi"],
    "Spring": [r"\bspring( boot)?\b"], "Rails": [r"\brails\b", r"ruby on rails"], "Express": [r"express\.?js"], "Laravel": [r"laravel"],
    "REST APIs": [r"\brest(ful)?\b( apis?)?", r"\bapis?\b design"], "gRPC": [r"grpc"], "Microservices": [r"micro-?services"],
    "Kafka": [r"kafka"], "RabbitMQ": [r"rabbitmq"], "Redis": [r"redis"], "Elasticsearch": [r"elastic ?search", r"opensearch"],
    # data
    "PostgreSQL": [r"postgres(ql)?"], "MySQL": [r"mysql"], "MongoDB": [r"mongo(db)?", r"\bmern\b"], "SQLite": [r"sqlite"], "DynamoDB": [r"dynamodb"],
    "Snowflake": [r"snowflake"], "BigQuery": [r"bigquery"], "Redshift": [r"redshift"], "Databricks": [r"databricks"], "Spark": [r"\bspark\b", r"pyspark"],
    "Hadoop": [r"hadoop"], "Airflow": [r"airflow"], "dbt": [r"\bdbt\b"], "ETL": [r"\betl\b", r"\belt\b", r"data pipelines?"],
    "Pandas": [r"pandas"], "NumPy": [r"numpy"], "Tableau": [r"tableau"], "Power BI": [r"power ?bi"], "Looker": [r"looker"],
    "Excel": [r"\bexcel\b", r"spreadsheets?"], "Data Analysis": [r"data analy(sis|tics)", r"analytics"], "Statistics": [r"statistic(s|al)"],
    "A/B Testing": [r"a/b test", r"experimentation"], "Data Modeling": [r"data model(l)?ing"], "Data Visualization": [r"data visuali[sz]ation", r"(?:bi|analytics|reporting) dashboards?", r"dashboards? (?:in|with|using) (?:tableau|looker|power ?bi)"],
    # ML / AI
    "Machine Learning": [r"machine learning", r"\bml\b"], "Deep Learning": [r"deep learning", r"neural net"], "PyTorch": [r"pytorch"],
    "TensorFlow": [r"tensorflow", r"\bkeras\b"], "scikit-learn": [r"scikit", r"sklearn"], "NLP": [r"\bnlp\b", r"natural language processing"],
    "Computer Vision": [r"computer vision"], "LLMs": [r"\bllms?\b", r"large language models?", r"generative ai", r"\bgenai\b", r"\bgpt\b"],
    "RAG": [r"\brag\b", r"retrieval[- ]augmented"], "MLOps": [r"mlops"],
    # cloud / devops
    "AWS": [r"\baws\b", r"amazon web services", r"\bec2\b", r"\bs3\b", r"lambda"], "GCP": [r"\bgcp\b", r"google cloud"], "Azure": [r"\bazure\b"],
    "Docker": [r"docker", r"containers?\b"], "Kubernetes": [r"kubernetes", r"\bk8s\b", r"\beks\b", r"\bgke\b"], "Terraform": [r"terraform"],
    "Ansible": [r"ansible"], "CI/CD": [r"ci/cd", r"continuous integration", r"github actions", r"jenkins", r"circleci", r"gitlab ci"],
    "Linux": [r"linux", r"\bunix\b"], "Git": [r"\bgit\b", r"github", r"gitlab"], "Observability": [r"observability", r"datadog", r"prometheus", r"grafana", r"splunk", r"new relic"],
    "Networking": [r"networking", r"tcp/ip", r"\bdns\b", r"\bvpn\b"], "Security": [r"\bsecurity\b", r"infosec", r"cybersecurity"],
    "SRE": [r"\bsre\b", r"site reliability"], "Distributed Systems": [r"distributed systems?"], "System Design": [r"system design", r"systems architecture"],
    "Testing": [r"unit test", r"test automation", r"\bqa\b", r"quality assurance", r"selenium", r"cypress", r"pytest", r"\bjest\b"],
    # design / product
    "Figma": [r"figma"], "UX Design": [r"\bux\b", r"user experience", r"user research"], "UI Design": [r"\bui\b design", r"user interface", r"visual design"],
    "Adobe Creative Suite": [r"photoshop", r"illustrator", r"adobe creative", r"indesign", r"after effects", r"premiere"],
    "Product Management": [r"product management", r"product roadmap", r"roadmaps?", r"product strategy"], "Agile": [r"\bagile\b", r"\bscrum\b", r"kanban", r"sprints?"],
    "Jira": [r"\bjira\b", r"confluence"], "Project Management": [r"project management", r"\bpmp\b", r"program management"],
    # business
    "Salesforce": [r"salesforce", r"\bsfdc\b"], "HubSpot": [r"hubspot"], "CRM": [r"\bcrm\b"], "SEO": [r"\bseo\b", r"search engine optimi[sz]ation"],
    "Digital Marketing": [r"digital marketing", r"paid (social|search|media)", r"\bsem\b", r"google ads", r"performance marketing"],
    "Content Writing": [r"copywriting", r"content (writing|creation|strategy)", r"technical writing"], "Social Media": [r"social media"],
    "Sales": [r"\bsales\b", r"business development", r"quota", r"pipeline generation"], "Account Management": [r"account management", r"account manager"],
    "Customer Success": [r"customer success"], "Customer Service": [r"customer service", r"customer support"],
    "Accounting": [r"accounting", r"\bgaap\b", r"reconciliation", r"accounts (payable|receivable)", r"bookkeeping"],
    "Financial Modeling": [r"financial model(l)?ing", r"\bfp&a\b", r"forecasting", r"budgeting"], "QuickBooks": [r"quickbooks"],
    "Operations": [r"business operations", r"process improvement", r"operations management"], "Supply Chain": [r"supply chain", r"logistics", r"procurement", r"inventory"],
    "Recruiting": [r"recruit(ing|ment)", r"talent acquisition", r"sourcing candidates"], "HR": [r"human resources", r"\bhris\b", r"\bpeople ops\b"],
    "Communication": [r"communication skills", r"(?:excellent|strong|clear|effective|good|written|verbal|oral) communication", r"written and verbal", r"\bcommunicator\b"], "Leadership": [r"leadership", r"people management", r"mentor(ing|ship)?"],
    "Stakeholder Management": [r"stakeholders?", r"cross-functional"], "Negotiation": [r"negotiat"], "Public Speaking": [r"public speaking", r"presentation skills"],
    "Spanish": [r"spanish", r"bilingual"], "Microsoft Office": [r"microsoft office", r"\bms office\b", r"powerpoint", r"microsoft word", r"\boutlook\b(?! for)"],
    "Google Workspace": [r"google (workspace|sheets|docs)", r"\bg ?suite\b"], "Zendesk": [r"zendesk"], "SAP": [r"\bsap\b"], "ERP": [r"\berp\b", r"netsuite", r"oracle"],
    "Healthcare": [r"\bhipaa\b", r"\behr\b", r"\bemr\b", r"epic systems", r"clinical"], "Compliance": [r"compliance", r"\bsox\b", r"regulatory"],
    # IT support
    "Technical Support": [r"technical support", r"tech support", r"\bit support", r"desktop support", r"service desk", r"help ?desk", r"tier (?:1|2|i|ii) support"],
    "Troubleshooting": [r"troubleshoot"], "Active Directory": [r"active directory", r"entra id", r"azure ad\b"],
    "Windows": [r"\bwindows\b(?! (?:of|into))"], "macOS": [r"\bmac ?os\b", r"\bos x\b"], "SSH": [r"\bssh\b"],
    "Firewalls": [r"firewall"], "Remote Access": [r"remote access", r"remote desktop", r"\brdp\b", r"teamviewer", r"\bvnc\b"],
    "Ticketing Systems": [r"\btickets?\b", r"ticketing", r"servicenow", r"freshdesk", r"jira service"],
    "Documentation": [r"documentation", r"documenting", r"knowledge base", r"setup guides?", r"troubleshooting guides?"],
    "Microsoft 365": [r"office 365", r"microsoft 365", r"\bm365\b", r"\bo365\b", r"exchange online"],
    "Device Management": [r"\bmdm\b", r"intune", r"\bjamf\b", r"endpoint management"],
    "Hardware": [r"hardware", r"printers?\b", r"peripherals"], "ITIL": [r"\bitil\b"], "CompTIA": [r"comptia", r"\ba\+ cert", r"network\+", r"security\+"],
    "User Management": [r"user (?:management|accounts?|permissions|provisioning)", r"account and access", r"password resets?", r"reset(?:ting)? (?:user )?passwords?", r"onboarding/offboarding"],
    # clerical and data entry work
    "Data Entry": [r"data[- ]entry", r"keying (?:in )?data", r"data input"], "Typing": [r"\btyping\b", r"\btypist\b", r"\b\d{2,3}\+?\s*wpm\b", r"words per minute", r"keyboarding"],
    "10-Key": [r"\b10[- ]?key\b", r"\bten[- ]key\b"], "Attention to Detail": [r"attention to detail", r"detail[- ]oriented"],
    "Records Management": [r"records? management", r"record[- ]?keeping", r"\bfiling\b", r"document management"],
    "Data Verification": [r"data (?:verification|accuracy|integrity|validation)", r"verify(?:ing)? (?:data|information|records)"],
    "Scanning": [r"\bscanning\b", r"document imaging", r"digitiz\w+"], "Invoicing": [r"\binvoic\w+", r"accounts payable", r"accounts receivable"],
    "Payroll": [r"\bpayroll\b"], "Medical Records": [r"medical records", r"\behr\b", r"\bemr\b", r"health records"],
    "Blockchain": [r"blockchain", r"web3", r"crypto(currency)?"], "Embedded": [r"embedded", r"firmware", r"\brtos\b"], "Unity": [r"\bunity\b(?! of)"],
}
# A few names are ordinary words too, so they only count in exact case and in a list-like spot.
_CASED = {
    "Go": re.compile(r"(?:(?<=, )|(?<=/)|(?<=\())Go\b|\bGo(?=\s*[,/)])"),
    "R": re.compile(r"(?:(?<=, )|(?<=/)|(?<=\())R\b(?![&'’-])|\bR(?=\s*[,/)])(?![&'’-])"),
}
_PATTERNS = {name: re.compile("|".join(f"(?:{a})" for a in aliases), re.I) for name, aliases in SKILLS.items() if aliases}
_CANON = {name.lower(): name for name in SKILLS}


def canonical(skill):
    """'python ' -> 'Python'. A skill outside the list keeps your spelling."""
    s = re.sub(r"\s+", " ", str(skill)).strip()
    if not s:
        return ""
    if s.lower() in _CANON:
        return _CANON[s.lower()]
    for name, pattern in _PATTERNS.items():
        m = pattern.fullmatch(s)
        if m:
            return name
    return s


def skill_pattern(skill):
    """How to look for a skill in text, including ones you typed that aren't on the list."""
    if skill in _CASED:
        return _CASED[skill]
    if skill in _PATTERNS:
        return _PATTERNS[skill]
    return re.compile(r"(?<![\w+#])" + re.escape(skill) + r"(?![\w+#])", re.I)


# Some PDFs come out with spaces in the middle of words ("Windo ws", "Mong oDB", "Activ e Dir ect ory").
# Words that short and that odd are rare in normal writing, so a text full of them was read that way.
_SHORT_OK = {"a", "i", "an", "to", "of", "in", "on", "is", "it", "at", "by", "or", "as", "be", "we", "my", "up", "if", "so", "do", "no",
             "us", "me", "he", "go", "am", "vs", "id", "ai", "ui", "ux", "it", "pc", "os", "qa", "hr", "&", "ms", "js"}


def looks_split(value):
    """True when a text has many words broken apart by stray spaces, as some PDF readers produce."""
    toks = re.findall(r"[A-Za-z]+", value or "")
    if len(toks) < 40:
        return False
    odd = sum(1 for t in toks if len(t) <= 2 and t.lower() not in _SHORT_OK)
    return odd / len(toks) > 0.06


def _loosen(alias):
    """The same regex, but with an optional space allowed between any two letters or digits of a plain run."""
    out, i, prev_plain = [], 0, False
    while i < len(alias):
        c = alias[i]
        if c == "\\" and alias[i + 1:i + 2] == " ":   # re.escape writes a space as "\ "
            c, i = " ", i + 1
        if c == " ":
            out.append(" ?")
            i += 1
            prev_plain = True
            continue
        if c == "\\" and i + 1 < len(alias):
            piece, plain = alias[i:i + 2], alias[i + 1] in ".+-#/&"   # \. \+ are characters; \b \s are not
            i += 2
        elif c == "[":
            j = alias.index("]", i + 1)
            piece, plain, i = alias[i:j + 1], False, j + 1
        elif c == "(" and alias[i + 1:i + 2] == "?":
            m = re.match(r"\(\?(?:<[=!]|[:=!])", alias[i:])
            piece, plain = m.group(0), False
            i += len(piece)
        else:
            piece, plain = c, c.isalnum()
            i += 1
        if plain and prev_plain and out and out[-1] != " ?":
            out.append(" ?")
        out.append(piece)
        prev_plain = plain
    return "".join(out)


_LOOSE = {name: re.compile("|".join(f"(?:{_loosen(a)})" for a in aliases), re.I) for name, aliases in SKILLS.items() if aliases}


def mentions(skill, value):
    """Whether a text mentions a skill, also when the text came out of a PDF with words split apart."""
    if not value:
        return False
    if skill_pattern(skill).search(value):
        return True
    if skill in _CASED or not looks_split(value):
        return False
    pattern = _LOOSE.get(skill) or re.compile(r"(?<![\w+#])" + _loosen(re.escape(skill)) + r"(?![\w+#])", re.I)
    return bool(pattern.search(value))


def _literal(alias):
    """A plain piece every match of the pattern must contain, to check with `in` before running the regex.

    Groups and optional characters are dropped first, since a match needn't contain them."""
    a = alias
    while re.search(r"\([^()]*\)", a):
        a = re.sub(r"\([^()]*\)\??", "\x00", a)
    a = re.sub(r"\\[bBswdW]", "\x00", a)
    a = re.sub(r"\\(.)", r"\1", a)                 # \. \+ \- are the characters themselves
    a = re.sub(r".[?*]", "\x00", a)                # an optional character splits the piece
    a = re.sub(r"\[[^\]]*\]", "\x00", a)
    pieces = [x for x in re.split(r"[\x00|^$+{}]", a) if len(x.strip()) >= 2]
    return max(pieces, key=len).lower() if pieces else None


# A skill is looked for only if some plain piece of one of its patterns is in the text at all.
_HINTS = {name: [_literal(a) for a in SKILLS[name]] for name in _PATTERNS}


def find_skills(text, extra=()):
    """Skills mentioned in the text, most mentioned first. `extra` are your own skills to look for too."""
    if not text:
        return []
    low = text.lower()
    counts = {}
    for name, pattern in _PATTERNS.items():
        hints = _HINTS[name]
        if all(h is not None and h not in low for h in hints):
            continue
        hits = len(pattern.findall(text))
        if hits:
            counts[name] = hits
    for name in list(_CASED) + [e for e in extra if e and e not in SKILLS]:
        hits = len(skill_pattern(name).findall(text))
        if hits:
            counts[name] = hits
    return sorted(counts, key=lambda n: (-counts[n], n))


# ---------------------------------------------------------------- level, years, salary, place

LEVELS = ["intern", "entry", "mid", "senior", "lead", "manager", "director", "executive"]
LEVEL_NAMES = {"intern": "Internship", "entry": "Entry level", "mid": "Mid level", "senior": "Senior", "lead": "Staff / Lead",
               "manager": "Manager", "director": "Director", "executive": "Executive"}
_LEVEL_RULES = [
    ("intern", r"\bintern(ship)?\b|\bco-?op\b|working student|werkstudent"),
    ("executive", r"\b(chief|cto|ceo|cfo|coo|cmo|vp|vice president|svp|evp|head of)\b"),
    ("director", r"\bdirector\b"),
    ("manager", r"\b(manager|management)\b(?! of)"),
    ("lead", r"\b(staff|principal|lead|architect|distinguished)\b"),
    ("senior", r"\b(senior|sr\.?|iii|iv)\b"),
    ("entry", r"\b(junior|jr\.?|entry[- ]level|new grad(uate)?|graduate|associate|apprentice|trainee|i|tier ?(1|i)|level ?(1|i)|l1)\b(?!-)"),
    ("mid", r"\b(ii|mid[- ]level|intermediate|tier ?(2|ii)|level ?(2|ii)|l2)\b"),
]


def level_of(title, years=None):
    t = (title or "").lower()
    for level, rule in _LEVEL_RULES:
        if re.search(rule, t):
            # "Account Manager" and "Product Manager" are roles, not people managers.
            if level == "manager" and re.search(r"(account|product|project|program|community|case|office|success|marketing|social media|content) manager", t):
                break
            return level
    if years is not None:
        if years <= 1:
            return "entry"
        if years >= 6:
            return "senior"
        if years >= 3:
            return "mid"
    # Clerical and first-line support jobs are entry level unless the post says otherwise.
    if re.search(r"\b(data entry|data clerk|clerk|typist|keyer|order entry|receptionist|assistant|help ?desk|service ?desk|"
                 r"desktop support|it support|support technician|technician)\b", t):
        return "entry"
    return "mid"


_YEARS = re.compile(r"(\d{1,2})\s*(?:\+|plus)?\s*(?:-|–|to)?\s*(?:\d{1,2}\s*)?\+?\s*(?:years?|yrs?)(?:'|’)?\s*(?:of\s+)?(?:\w+\s+){0,4}?(?:experience|exp\b)", re.I)


def years_required(text):
    """The smallest 'N+ years of experience' a post asks for, if it says."""
    found = [int(m.group(1)) for m in _YEARS.finditer(text or "") if 0 < int(m.group(1)) <= 25]
    return min(found) if found else None


_RANGE_YEARS = re.compile(r"(?<![\d/])(?:\d{1,2}/)?((?:19|20)\d\d)\s*(?:-|–|—|to)\s*(?:\d{1,2}/)?((?:19|20)\d\d|present|current|now|today)\b", re.I)


def resume_years(text, this_year):
    """Years of work on a resume: an 'N years of experience' line, or the span of its date ranges."""
    m = re.search(r"(\d{1,2})\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:\w+\s+){0,3}?experience", text or "", re.I)
    if m:
        return int(m.group(1))
    spans = []
    for a, b in _RANGE_YEARS.findall(text or ""):
        start = int(a)
        end = this_year if not b[:1].isdigit() else int(b)
        if start <= end <= this_year:
            spans.append((start, end))
    if not spans:
        return None
    # Merge overlaps so two jobs held at once count once. Education ranges are counted too; you can correct it.
    spans.sort()
    total, (cur_a, cur_b) = 0, spans[0]
    for a, b in spans[1:]:
        if a <= cur_b:
            cur_b = max(cur_b, b)
        else:
            total += cur_b - cur_a
            cur_a, cur_b = a, b
    total += cur_b - cur_a
    return max(total, 0)


_MONEY = re.compile(r"(?:(?:US)?\$|USD\s*|€|£)\s?(\d{1,3}(?:[,.]\d{3})+|\d+(?:\.\d+)?)\s*([kK])?", re.I)


def salary_from(text):
    """(low, high, text) in yearly dollars from things like '$120K – $150K' or '$55/hr'. None when it can't tell."""
    if not text:
        return None, None, ""
    sample = text
    nums, spans = [], []
    for m in _MONEY.finditer(sample):
        raw = m.group(1).replace(",", "")
        if raw.count(".") == 1 and len(raw.split(".")[1]) == 3:
            raw = raw.replace(".", "")  # 120.000 written European style
        try:
            value = float(raw)
        except ValueError:
            continue
        if m.group(2):
            value *= 1000
        after = sample[m.end():m.end() + 24].lower()
        if re.match(r"\s*(?:-|–|to)?\s*(?:\$?\s*[\d.,]+[kK]?)?\s*(?:/|per|an|a)\s*(?:hr|hour)", after) or re.match(r"\s*/\s*h\b", after):
            value *= 2080
        elif re.match(r"\s*(?:-|–|to)?\s*(?:\$?\s*[\d.,]+[kK]?)?\s*(?:/\s*mo(?:nth)?\b|per month|a month|monthly)", after):
            value *= 12
        if 10_000 <= value <= 2_000_000:
            nums.append(int(value))
            spans.append(m.span())
        if len(nums) == 2:
            break
    if not nums:
        return None, None, ""
    low, high = min(nums), max(nums)
    a, b = spans[0][0], spans[-1][1]
    return low, high, re.sub(r"\s+", " ", sample[a:b + 4]).strip(" ,.;")


def work_model(*parts):
    t = " ".join(p for p in parts if p).lower()
    if re.search(r"\bhybrid\b", t):
        return "hybrid"
    if re.search(r"\b(remote|anywhere|work from home|wfh|distributed)\b", t) and not re.search(r"\bnot (a )?remote\b|\bno remote\b", t):
        return "remote"
    if re.search(r"\b(on-?site|in[- ]office|in person)\b", t):
        return "onsite"
    return "onsite" if t.strip() else "unknown"


def sponsorship(text):
    """'yes' when a post offers visa sponsorship, 'no' when it rules it out, else 'unknown'."""
    t = (text or "").lower()
    if re.search(r"(not|unable to|cannot|can't|won't|will not|no)\s+(?:\w+\s+){0,3}(sponsor|provide sponsorship|offer sponsorship)|without (?:the )?need for (?:visa )?sponsorship|sponsorship is not available|must be (?:a )?(?:us|u\.s\.) citizen|authorized to work .{0,40} without", t):
        return "no"
    if re.search(r"(will|can|able to|happy to|we)\s+(?:\w+\s+){0,3}sponsor|visa sponsorship (is )?(available|provided|offered)|h-?1b (sponsorship|transfer)", t):
        return "yes"
    return "unknown"


_CLEAR_WORD = r"(?:top secret|ts/sci|ts sci|secret|polygraph|security clearance|clearance)"


def clearance(desc, title=""):
    """'active' when a post needs a security clearance you already hold, 'obtain' when it needs one you can get
    (US citizens), else None. Many DC contractor help desks (GDIT, Leidos, CACI) need one."""
    t, d = (title or "").lower(), desc or ""
    if re.search(r"ts/sci|top secret|\bsecret clearance\b|w/\s?poly|polygraph|\bclearance required\b", t):
        return "active"
    m = re.search(r"must currently possess:\s*([^\n]+)", d, re.I)
    if m and not re.match(r"\s*(none|n/a|no)\b", m.group(1), re.I):
        return "active"
    found = None
    for line in re.split(r"(?<=[.!?])\s+|\n+", d):
        low = line.lower()
        if not re.search(_CLEAR_WORD, low) or re.search(r"must currently possess|must be able to obtain", low):
            continue
        can_get = re.search(r"\b(obtain|eligib\w*|ability to (?:get|be granted)|sponsor\w*|willing\w* to (?:obtain|undergo))\b", low)
        if not can_get and (re.search(r"\b(active|current|existing|possess(?:es)?|hold(?:s|ing)? an?)\b[^.\n]{0,30}\b(secret|top secret|ts/sci|ts|clearance)\b", low)
                            or re.search(r"\b(secret|top secret|ts/sci)\b[^.\n]{0,30}\brequired\b", low)):
            return "active"
        if can_get and re.search(r"\b(secret|top secret|ts/sci|clearance)\b", low):
            found = "obtain"
    m = re.search(r"must be able to obtain:\s*([^\n]+)", d, re.I)
    if m and not re.match(r"\s*(none|n/a|no)\b", m.group(1), re.I):
        found = "obtain"
    return found


def words(text):
    return re.findall(r"[a-z0-9+#]+", (text or "").lower())


_TITLE_SAME = {"swe": "software engineer", "sde": "software engineer", "dev": "developer", "eng": "engineer", "sr": "senior", "jr": "junior",
               "pm": "product manager", "ml": "machine learning", "ai": "artificial intelligence", "ux": "user experience", "ui": "user interface",
               "fe": "frontend", "be": "backend", "fullstack": "full stack", "front": "frontend", "back": "backend", "qa": "quality assurance",
               "devops": "devops", "programmer": "developer", "coder": "developer",
               # stocking jobs go by many names
               "stocker": "stock", "stockers": "stock", "stocking": "stock", "restock": "stock", "restocking": "stock", "restocker": "stock",
               "shelver": "stock", "replenishment": "stock", "inbound": "stock", "freight": "stock"}
_TITLE_NOISE = {"senior", "junior", "staff", "principal", "lead", "i", "ii", "iii", "iv", "the", "of", "and", "a", "an", "to", "for", "in", "at",
                "remote", "hybrid", "us", "usa", "new", "grad", "entry", "level", "mid", "f", "m", "w", "d", "x"}
_TITLE_EQUIV = {"developer": "engineer", "programmer": "engineer", "frontend": "front", "backend": "back", "end": ""}


def title_tokens(title):
    t = (title or "").lower().replace("front-end", "frontend").replace("back-end", "backend").replace("full-stack", "full stack")
    t = re.sub(r"\((?![^)]*stock)[^)]*\)|\[.*?\]", " ", t)   # "(Remote)" is noise, but Target's "(Stocking)" is the job
    out = []
    for w in words(t):
        w = _TITLE_SAME.get(w, w)
        for part in w.split():
            part = _TITLE_EQUIV.get(part, part)
            if part and part not in _TITLE_NOISE:
                out.append(part)
    return set(out)


def title_similarity(a, b):
    """0..1. Shared meaningful words, so 'Sr. Software Developer' matches 'Software Engineer'."""
    ta, tb = title_tokens(a), title_tokens(b)
    if not ta or not tb:
        return 0.0
    shared = ta & tb
    if not shared:
        return 0.0
    # How much of what you're looking for is in this title, softened by how much else the title is about.
    cover = len(shared) / len(tb)
    extra = len(shared) / len(ta)
    return round(0.75 * cover + 0.25 * extra, 3)
