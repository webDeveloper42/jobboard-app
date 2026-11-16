"""Personal job board engine.

    api.py          JobBoardApi: the one object the page and the terminal use (start reading here)
    config.py       settings you might change by hand (home town, limits)
    services/       one class per area: resumes, boards, applications… (see services/__init__.py)
    boards/         readers for each kind of job board
    rules/          what counts as your role and place, scam checks, scoring, text helpers, commute times
    storage/        the SQLite schema, the one-thread Database, one-time migrations
    links/          writing to the other dashboard apps: Sheets, Docs, Notes
    writing/        AI writing (Ollama) and reading resume files
    http_routes.py  which URL does what for the Jobs page (used by the dashboard and server.py)
    server.py       `jobboard serve`: the page on its own, without the dashboard
    cli.py          the `jobboard` terminal command
    morning.py      the morning run (cron): refresh, read full posts, summary email
"""
from .api import JobBoardApi
from .errors import JobBoardError

__all__ = ["JobBoardApi", "JobBoardError"]
