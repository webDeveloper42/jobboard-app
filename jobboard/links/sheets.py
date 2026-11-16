"""Your job sheets in the Sheets tab, kept up to date from the tracker.

When you apply to a job (or move it on to interviewing, offer, rejected…), its row in the matching workbook is added
or updated: IT jobs go to the "IT" workbook, data entry jobs to "Data Entry". A workbook that doesn't exist yet is made
with the same layout as your other job sheets (the same column names, column widths and frozen panes), named the
same way ("Book(Data Entry)"). Columns are found by their names, so renaming or moving one keeps rows lined up; older
sheets that still keep the headers in row 1 work too.

The columns are the ones your sheets already use:

    Company | Position | Platform | Offer | Ask | Progress | Where | Type

A row that's already there (same company, a matching position) only has its Progress changed, so anything you typed
in the other columns stays. Every change goes through the Sheets app's own save, with a version-history snapshot
first, so it can be undone from File → Version history.
"""
import os
import re
import sys
from pathlib import Path

from ..rules import focus, text

HEADERS = ["Company", "Position", "Platform", "Offer", "Ask", "Progress", "Where", "Type"]
BOOKS = {"it_tech": "IT", "it_intern": "IT", "data_entry": "Data Entry"}
PROGRESS = {"applied": "Applied", "interviewing": "Interviewing", "offer": "Offer", "rejected": "Rejected", "withdrawn": "Withdrawn"}
PLATFORM = {"google": "Google", "jooble": "Jooble", "jobicy": "Jobicy", "remotive": "Remotive", "remoteok": "Remote OK", "arbeitnow": "Arbeitnow",
            "greenhouse": "Website", "lever": "Website", "ashby": "Website", "workday": "Website", "manual": "Website"}


class SheetsLinkError(RuntimeError):
    pass


def _store():
    """The Sheets app's own storage code, so every save follows its rules."""
    app = Path(os.environ.get("SHEETS_APP_DIR") or Path.home() / "sheets-app")
    if not (app / "sheets" / "store.py").exists():
        raise SheetsLinkError("the Sheets app isn't installed")
    if str(app) not in sys.path:
        sys.path.insert(0, str(app))
    from sheets import store  # noqa: PLC0415
    return store


# ---------------------------------------------------------------- what goes in each column

def _money(n, hourly):
    if hourly:
        v = n / 2080
        return f"{v:.0f}" if abs(v - round(v)) < 0.05 else f"{v:.2f}"
    return f"{n / 1000:.0f}"


def _is_hourly(job):
    low, high = job.get("salary_min"), job.get("salary_max") or job.get("salary_min")
    if re.search(r"\b(hr|hour|hourly)\b|/h\b", job.get("salary_text") or "", re.I):
        return True
    return bool(low and high and high <= 150_000 and low % 2080 == 0 and high % 2080 == 0)


def offer(job):
    """'66-85k', '15-18', '19/hr', '66k' or 'N/A', the way your sheets write pay."""
    low, high = job.get("salary_min"), job.get("salary_max") or job.get("salary_min")
    if not low:
        return "N/A"
    hourly = _is_hourly(job)
    a, b = _money(low, hourly), _money(high, hourly)
    if a == b:
        return f"{a}/hr" if hourly else f"{a}k"
    return f"{a}-{b}" if hourly else f"{a}-{b}k"


def ask(job, prof):
    """The top of the posted pay, or your minimum when the post doesn't say."""
    top = job.get("salary_max") or job.get("salary_min")
    if top:
        return f"{_money(top, True)}/hr" if _is_hourly(job) else f"{_money(top, False)}k"
    floor = prof.get("min_salary")
    return f"{floor / 1000:.0f}k" if floor else "N/A"


def where(job):
    """A street address when there is one, 'Remote', 'City ST(Hybrid)', or the city."""
    parts = [p.strip() for p in re.split(r"\s+·\s+", job.get("location") or "") if p.strip()]
    if job.get("work_model") == "remote" or (parts and all(re.search(r"\bremote\b", p, re.I) for p in parts)):
        return "Remote"
    pick = next((p for p in parts if re.match(r"^\d+\s", p)), None) \
        or next((p for p in parts if focus.places({"location": p}) & {"dc", "suitland"}), None) or (parts[0] if parts else "")
    pick = re.sub(r",\s*(US|USA|United States)$", "", pick)
    if not re.match(r"^\d+\s", pick):
        pick = re.sub(r",\s*", " ", pick)   # "Washington, DC" -> "Washington DC", like your sheets
    return f"{pick}(Hybrid)" if job.get("work_model") == "hybrid" else pick or "N/A"


def job_type(job):
    t = (job.get("employment_type") or "").lower()
    for pattern, name in ((r"intern", "Internship"), (r"part", "Parttime"), (r"contract|temp|seasonal", "Contract"), (r"full", "Fulltime")):
        if re.search(pattern, t):
            return name
    if re.search(r"\bintern(ship)?\b", job.get("title") or "", re.I):
        return "Internship"
    if re.search(r"\bseasonal\b", job.get("title") or "", re.I):
        return "Seasonal"
    return "N/A"


def row_values(job, prof, status, kind):
    return [job.get("company") or "N/A", job.get("title") or "N/A", PLATFORM.get(kind or "manual", "Website"), offer(job), ask(job, prof),
            PROGRESS.get(status, status.title()), where(job), job_type(job)]


# ---------------------------------------------------------------- the workbook

def _cell_text(cell):
    if not cell:
        return ""
    v = cell.get("t", cell.get("v"))
    return "" if v is None else str(v).strip()


def _plain(value):
    v = str(value)
    return "'" + v if v[:1] in "=+@" else v   # a company name is never a formula


def _same(a_company, a_title, b_company, b_title):
    if focus.company_key(a_company) != focus.company_key(b_company):
        return False
    x, y = a_title.lower().strip(), b_title.lower().strip()
    return x == y or (len(x) > 4 and len(y) > 4 and (x in y or y in x)) or text.title_similarity(x, y) >= 0.8


def _headers(sheet):
    """{column index: header text} from the sheet's column names, or from row 1 in an older sheet without them."""
    names = {int(k): v for k, v in (sheet.get("names") or {}).items() if str(k).isdigit()}
    if names:
        return names, True
    row1 = {}
    for key, cell in (sheet.get("cells") or {}).items():
        m = re.match(r"^([A-Z])1$", key)
        if m and _cell_text(cell):
            row1[ord(m.group(1)) - 65] = _cell_text(cell)
    return row1, False


def _is_job_sheet(sheet):
    heads = {v.strip().lower() for v in _headers(sheet)[0].values()}
    return {"company", "position"} <= heads


def _columns(sheet):
    """Which column each of the job fields goes in, found by header name, so renamed or moved columns still line up.
    A field whose header isn't found keeps its usual place (A to H)."""
    heads, _ = _headers(sheet)
    by_name = {v.strip().lower(): c for c, v in heads.items()}
    return [by_name.get(h.lower(), i) for i, h in enumerate(HEADERS)]


def _template(conn, store):
    """Your job sheet layout: the first workbook whose headers include Company and Position. Prefers one that
    uses column names."""
    found = None
    for row in conn.execute("SELECT id, doc FROM books ORDER BY id"):
        try:
            sheet = __import__("json").loads(row["doc"])["sheets"][0]
        except (ValueError, KeyError, IndexError, TypeError):
            continue
        if _is_job_sheet(sheet):
            if sheet.get("names"):
                return sheet
            found = found or sheet
    return found


def _new_book(conn, store, name):
    """A workbook laid out like your other job sheets: the same column names (or header row), widths and panes."""
    model = _template(conn, store)
    sheet = store.blank_sheet(f"Book({name})")
    if model:
        if model.get("names"):
            sheet["names"] = dict(model["names"])
        else:
            heads, _ = _headers(model)
            sheet["cells"] = {f"{chr(65 + c)}1": dict(model["cells"][f"{chr(65 + c)}1"]) for c in heads}
        sheet["lists"] = [dict(rule) for rule in model.get("lists") or []]   # the Progress dropdown, colours and all
        sheet["colW"] = dict(model.get("colW") or {})
        sheet["freeze"] = dict(model.get("freeze") or {"r": 0, "c": 0})
        sheet["rows"], sheet["cols"] = model.get("rows", 1000), model.get("cols", 26)
    else:
        sheet["names"] = {str(i): h for i, h in enumerate(HEADERS)}
    return store.add_book(conn, name, {"sheets": [sheet], "active": 0})


def _letter(c):
    out = ""
    c += 1
    while c:
        c, rem = divmod(c - 1, 26)
        out = chr(65 + rem) + out
    return out


def _index(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def book_for(category):
    return BOOKS.get(category or "", "IT")


def record(job, prof, status, kind, path=None):
    """Add or update this job's row. Returns {'book', 'row', 'action'} ('added', 'updated' or 'unchanged')."""
    import json  # noqa: PLC0415
    if status not in PROGRESS:
        return None
    store = _store()
    conn = store.connect(path)
    try:
        name = book_for(focus.category(job.get("title")))
        found = conn.execute("SELECT id FROM books WHERE lower(name) = lower(?) ORDER BY id LIMIT 1", (name,)).fetchone()
        created = not found
        book_id = found["id"] if found else _new_book(conn, store, name)
        row = store.book_row(conn, book_id)
        doc = json.loads(row["doc"])
        sheet = doc["sheets"][0]
        cells = sheet.setdefault("cells", {})
        values = row_values(job, prof, status, kind)
        cols = _columns(sheet)
        _, named = _headers(sheet)
        first = 1 if named else 2          # with column names, the data starts at row 1
        addr = lambda c, r: f"{_letter(c)}{r}"  # noqa: E731
        last, hit = first - 1, None
        wanted = set(cols)
        for key in cells:
            m = re.match(r"^([A-Z]{1,2})(\d+)$", key)
            if m and _index(m.group(1)) in wanted and _cell_text(cells[key]):
                last = max(last, int(m.group(2)))
        for r in range(first, last + 1):
            if _same(_cell_text(cells.get(addr(cols[0], r))), _cell_text(cells.get(addr(cols[1], r))), values[0], values[1]):
                hit = r
                break
        progress = addr(cols[5], hit) if hit else None
        if hit:
            if _cell_text(cells.get(progress)) == values[5]:
                return {"book": name, "row": hit, "action": "unchanged"}
            cells[progress] = {**{k: v for k, v in (cells.get(progress) or {}).items() if k == "s"}, "v": values[5]}
            note, action, at = f"Before Jobs set {values[0]} to {values[5]}", "updated", hit
        else:
            at = last + 1
            for c, v in zip(cols, values):
                cells[addr(c, at)] = {"v": _plain(v)}
            sheet["rows"] = max(sheet.get("rows", 1000), at + 50)
            note, action = f"Before Jobs added {values[0]}", "added"
        with conn:
            store.snapshot(conn, book_id, row["doc"], note)
        store.save(conn, book_id, row["rev"], doc)
        return {"book": name, "row": at, "action": action, "created": created}
    finally:
        conn.close()
