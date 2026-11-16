"""Checking what comes in from the page or the terminal. Every service runs its inputs through these.

Each function either returns a clean value or raises JobBoardError with a message meant for you.
"""
import datetime as dt
import re

from .errors import JobBoardError


def text(value, limit, label, required=False):
    """A trimmed string, cut to `limit` characters. `label` finishes the sentence "Enter …"."""
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise JobBoardError(f"Enter {label}")
    value = value.strip()[:limit]
    if required and not value:
        raise JobBoardError(f"Enter {label}")
    return value


def number(value, label, low=None, high=None, blank_ok=True):
    """A whole number. Accepts "90k", "$40,000" and the like. Blank gives None unless blank_ok is False."""
    if value in (None, "") and blank_ok:
        return None
    if isinstance(value, bool):
        raise JobBoardError(f"Enter a number for {label}")
    if isinstance(value, str):
        value = value.strip().replace(",", "").replace("$", "")
        mult = 1000 if value.lower().endswith("k") else 1
        value = value.rstrip("kK")
        try:
            value = int(float(value) * mult)
        except ValueError:
            raise JobBoardError(f"Enter a number for {label}") from None
    if not isinstance(value, int):
        raise JobBoardError(f"Enter a number for {label}")
    if (low is not None and value < low) or (high is not None and value > high):
        raise JobBoardError(f"{label.capitalize()} is out of range")
    return value


def str_list(value, limit=60, item_len=80):
    """A list of unique, trimmed strings, from a list or from text split on commas, semicolons or new lines."""
    if isinstance(value, str):
        value = re.split(r"[,\n;]+", value)
    if not isinstance(value, list):
        return []
    out = []
    for v in value:
        if isinstance(v, str) and v.strip():
            out.append(re.sub(r"\s+", " ", v).strip()[:item_len])
    return list(dict.fromkeys(out))[:limit]


def day(value, label):
    """A 'YYYY-MM-DD' date, or None when blank."""
    if value in (None, ""):
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        raise JobBoardError(f"{label} doesn't look like a date") from None


def job_id(value):
    """A job's id from a number or a string of digits."""
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, str) and value.isdigit():
            return int(value)
        raise JobBoardError("Pick a job")
    return value
