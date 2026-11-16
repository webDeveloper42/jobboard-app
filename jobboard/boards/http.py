"""Talking to job boards over HTTP, and the one job shape every reader returns.

Every board reader calls `http.get_json` / `http.post_json` (never urllib directly), so tests can stub the network
in one place: `mock.patch.object(boards.http, "get_json", ...)`.
"""
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from ..rules import text

AGENT = "jobboard-local/1.0 (personal job search)"
TIMEOUT = 40


class SourceError(RuntimeError):
    """A board couldn't be read. The message is shown to you as-is, so keep it plain."""


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise SourceError("that board wasn't found. Check the company's slug") from None
        raise SourceError(f"the board answered {e.code}") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise SourceError(f"couldn't reach the board ({getattr(e, 'reason', e)})") from None
    except ValueError:
        raise SourceError("the board sent something that isn't JSON") from None


def post_json(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"User-Agent": AGENT, "Accept": "application/json", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise SourceError(f"the board answered {e.code}") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise SourceError(f"couldn't reach the board ({getattr(e, 'reason', e)})") from None
    except ValueError:
        raise SourceError("the board sent something that isn't JSON") from None


def parse_date(value):
    """Board dates come as ISO text, epoch seconds or epoch milliseconds."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            n = float(value)
            if n > 10_000_000_000:
                n /= 1000
            return datetime.fromtimestamp(n, tz=timezone.utc).date().isoformat()
        return str(value)[:10] if re.match(r"\d{4}-\d\d-\d\d", str(value)) else None
    except (ValueError, OSError, OverflowError):
        return None


def make_job(kind, slug, ext_id, **fields):
    fields.setdefault("company", slug.replace("-", " ").title() if slug else "")
    fields["key"] = f"{kind}:{slug}:{ext_id}"
    for name in ("title", "company", "location", "url", "apply_url", "employment_type", "department", "description", "salary_text"):
        value = text.fix_mojibake(str(fields.get(name) or ""))
        fields[name] = value if name == "description" else re.sub(r"\s+", " ", value).strip()
    fields["apply_url"] = fields["apply_url"] or fields["url"]
    return fields


def days_ago(value):
    """'3 days ago' (Google, Workday) as a 'YYYY-MM-DD' date, or None."""
    m = re.match(r"(\d+)\+?\s*(minute|hour|day|week|month)", (value or "").lower())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    days = {"minute": 0, "hour": 0, "day": n, "week": 7 * n, "month": 30 * n}[unit]
    return (datetime.now().date() - timedelta(days=days)).isoformat()
