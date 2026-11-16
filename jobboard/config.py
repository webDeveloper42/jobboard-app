"""Settings you might want to change by hand, all in one place.

Change a value here, run the tests (`./dev test`), and restart the dashboard. Nothing else needs editing.
"""
from pathlib import Path

# ---- Where your data lives: <repo>/data unless JOBBOARD_DATA_DIR says otherwise (see storage/db.default_path).
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

# ---- Where you live. Commute times are measured from HOME; remote jobs must be open to people in HOME_STATES.
HOME = ("Suitland, MD", 38.8487, -76.9239)   # (name, latitude, longitude) of your town, not your street address
HOME_STATES = {"MD", "DC"}                     # two-letter codes of the states you can work from

# ---- Limits
PAGE_SIZE = 60          # jobs sent to the page per request
MAX_TEXT = 60_000       # longest description or resume text kept, in characters
KEEP_BACKUPS = 14       # daily database copies kept in data/backups

# ---- Environment variables that override saved settings
ENV_SERPAPI_KEY = "SERPAPI_KEY"
ENV_JOOBLE_KEY = "JOOBLE_KEY"
ENV_DATA_DIR = "JOBBOARD_DATA_DIR"
