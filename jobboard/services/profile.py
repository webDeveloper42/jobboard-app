"""Your profile: contact details, what you're looking for, and skills. Saving it re-scores every job.
"""
import json

from .. import validation as validate
from ..errors import JobBoardError
from ..rules import text
from ..storage import db
from .base import Service


class ProfileService(Service):
    def profile_out(self, prof):
        out = dict(prof)
        out["resume_chars"] = len(prof["resume_text"])
        out["ready"] = bool(prof["skills"] or prof["target_titles"] or prof["resume_text"])
        out.pop("resume_text")
        return out

    def save(self, d):
        def go():
            prof = db.profile(self.con)
            fields = {}
            for key, limit in (("name", 120), ("email", 200), ("phone", 60), ("location", 120), ("headline", 200), ("links", 600),
                               ("home_address", 200)):
                if key in d:
                    fields[key] = validate.text(d[key], limit, key)
            if "target_titles" in d:
                fields["target_titles"] = json.dumps(validate.str_list(d["target_titles"], 12, 100))
            if "skills" in d:
                fields["skills"] = json.dumps([text.canonical(s) for s in validate.str_list(d["skills"], 80)])
            if "locations" in d:
                fields["locations"] = json.dumps(validate.str_list(d["locations"], 12, 100))
            if "work_models" in d:
                fields["work_models"] = json.dumps([m for m in validate.str_list(d["work_models"]) if m in db.WORK_MODELS] or db.WORK_MODELS)
            if "years_exp" in d:
                fields["years_exp"] = validate.number(d["years_exp"], "years of experience", 0, 60)
            if "level" in d:
                level = validate.text(d["level"], 20, "level")
                if level and level not in text.LEVELS:
                    raise JobBoardError("Pick a level from the list")
                fields["level"] = level
            if "min_salary" in d:
                fields["min_salary"] = validate.number(d["min_salary"], "minimum salary", 0, 5_000_000)
            if "needs_sponsorship" in d:
                fields["needs_sponsorship"] = 1 if d["needs_sponsorship"] in (True, 1, "1", "true", "yes") else 0
            if not fields:
                return db.profile(self.con)
            fields["updated"] = db.now()
            self.con.execute(f"UPDATE profile SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = 1", list(fields.values()))
            self.con.commit()
            self.app.catalog.rescore_all()
            return self.profile_out(db.profile(self.con)) | {"rescored": True, "was": bool(prof)}
        return self.run(go)
