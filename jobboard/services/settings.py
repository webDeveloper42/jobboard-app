"""Your API keys (SerpApi for Google Jobs, Jooble), the Sheets switch, SerpApi usage, and hide rules.

Keys are kept in the database's settings table, or come from the environment (config.ENV_*). They're never sent to the page.
"""
import datetime as dt
import json
import os
import re
import urllib.parse

from .. import boards
from .. import validation as validate
from ..errors import JobBoardError
from ..rules import focus
from ..storage import db
from .base import Service


class SettingsService(Service):
    HIDE_RULES = "hide_rules"   # settings key: {"companies": [...], "words": [...]}

    def __init__(self, app):
        super().__init__(app)
        self._rules = None      # cached hide rules: (companies as company keys, word patterns, the rules as saved)

    # ---- hide rules: companies you never want to see, and words that rule a job out

    def hide_rules(self):
        """Your hide rules as saved: {"companies": [...], "words": [...]}. Runs on the database thread."""
        return self._load_rules()[2]

    def _load_rules(self):
        if self._rules is None:
            saved = db.loads(db.setting(self.con, self.HIDE_RULES), {}) or {}
            rules = {"companies": list(saved.get("companies") or []), "words": list(saved.get("words") or [])}
            companies = {focus.company_key(c) for c in rules["companies"]}
            words = [re.compile(rf"(?<!\w){re.escape(w.lower())}(?!\w)") for w in rules["words"]]
            self._rules = (companies, words, rules)
        return self._rules

    def rule_hit(self, company, title, description):
        """1 when a job breaks one of your hide rules. Used in SQL as hidden_by_rule(company, title, description).
        Only reads the cache: call hide_rules() first (FeedService.visible_sql does)."""
        companies, words, _ = self._rules or (set(), [], None)
        if companies and focus.company_key(company) in companies:
            return 1
        if words:
            blob = f"{title or ''}\n{description or ''}".lower()
            return 1 if any(p.search(blob) for p in words) else 0
        return 0

    def add_hide_rule(self, d):
        """Never show jobs from a company (kind "company") or that mention a word or phrase (kind "word")."""
        kind = d.get("kind")
        if kind not in ("company", "word"):
            raise JobBoardError("Pick what to hide: a company or a word")
        value = validate.text(d.get("value"), 80, "a company name" if kind == "company" else "a word or phrase", required=True)
        if kind == "word" and len(value) < 2:
            raise JobBoardError("Enter at least two letters")

        def go():
            rules = dict(self.hide_rules())
            key = "companies" if kind == "company" else "words"
            if value.lower() not in {x.lower() for x in rules[key]}:
                rules[key] = rules[key] + [value]
            return self._save_rules(rules)
        return self.run(go)

    def remove_hide_rule(self, d):
        kind, value = d.get("kind"), str(d.get("value") or "")

        def go():
            rules = dict(self.hide_rules())
            key = "companies" if kind == "company" else "words"
            rules[key] = [x for x in rules.get(key, []) if x.lower() != value.lower()]
            return self._save_rules(rules)
        return self.run(go)

    def _save_rules(self, rules):
        db.set_setting(self.con, self.HIDE_RULES, json.dumps(rules))
        self.con.commit()
        self._rules = None
        return {"hide_rules": self.hide_rules()}

    def google_key(self):
        return db.setting(self.con, "serpapi_key") or os.environ.get("SERPAPI_KEY") or ""

    def jooble_key(self):
        return db.setting(self.con, "jooble_key") or os.environ.get("JOOBLE_KEY") or ""

    def set_google_key(self, d):
        """Save (or, when blank, forget) the SerpApi key that Google Jobs searches use. It's never sent back to the page."""
        key = validate.text(d.get("key"), 200, "the key")
        if key and not re.fullmatch(r"[A-Za-z0-9_-]{20,128}", key):
            raise JobBoardError("That doesn't look like a SerpApi key. Copy it from serpapi.com/manage-api-key")

        def go():
            if key:
                db.set_setting(self.con, "serpapi_key", key)
            else:
                self.con.execute("DELETE FROM settings WHERE key = 'serpapi_key'")
            self.con.commit()
            return {"google_key": bool(self.google_key())}
        return self.run(go)

    def set_sheets_sync(self, d):
        """Turn writing applications to the Sheets tab on or off. Without 'on', just says which it is."""
        def go():
            if "on" in d:
                db.set_setting(self.con, "sheets_sync", "on" if d["on"] in (True, 1, "1", "true", "on") else "off")
                self.con.commit()
            return {"sheets_sync": db.setting(self.con, "sheets_sync", "on") != "off"}
        return self.run(go)

    def set_jooble_key(self, d):
        """Save (or, when blank, forget) the Jooble API key. It's never sent back to the page."""
        key = validate.text(d.get("key"), 200, "the key")
        if key and not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", key):
            raise JobBoardError("That doesn't look like a Jooble API key. Copy it from the email Jooble sent you")

        def go():
            if key:
                db.set_setting(self.con, "jooble_key", key)
            else:
                self.con.execute("DELETE FROM settings WHERE key = 'jooble_key'")
            self.con.commit()
            return {"jooble_key": bool(self.jooble_key())}
        return self.run(go)

    def serpapi_usage(self, d=None):
        """How many SerpApi searches are left this month, from SerpApi's account page (checking it is free). Cached 10 minutes."""
        def cached():
            return db.loads(db.setting(self.con, "serpapi_usage"), {}), self.google_key()
        info, key = self.run(cached)
        if not key:
            return {"has_key": False}
        fresh = (d or {}).get("fresh") in (True, 1, "1", "true")
        if info.get("at") and not fresh and (dt.datetime.now() - dt.datetime.fromisoformat(info["at"])).total_seconds() < 600:
            return info | {"has_key": True}
        try:
            acct = boards.http.get_json("https://serpapi.com/account.json?" + urllib.parse.urlencode({"api_key": key}))
        except boards.SourceError as e:
            return {"has_key": True, "error": f"SerpApi's account page didn't answer ({e})"}
        if acct.get("error"):
            return {"has_key": True, "error": f"SerpApi: {acct['error']}"}
        info = {"at": db.now(), "plan": acct.get("plan_name") or "", "per_month": acct.get("searches_per_month"),
                "used": acct.get("this_month_usage"), "left": acct.get("total_searches_left", acct.get("plan_searches_left"))}
        self.run(lambda: (db.set_setting(self.con, "serpapi_usage", json.dumps(info)), self.con.commit()))
        return info | {"has_key": True}
