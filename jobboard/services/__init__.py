"""The engine's services. Each one owns one area and is reached through the app, like `app.resumes.add(...)`.

    profiles      ProfileService      your profile and skills
    resumes       ResumeService       several resumes, which one is primary, the roles it shows
    settings      SettingsService     API keys, the Sheets switch, SerpApi usage
    boards        BoardService        job boards: add, switch, remove, refresh, full posts
    catalog       JobCatalog          saving, merging, closing and scoring jobs
    feed          FeedService         what the page reads: job list, counts, one job, chat
    applications  ApplicationService  saving, statuses, notes, hiding, CSV export, job sheets
    writing       WritingService      tailored resumes, cover letters, Coach, Docs and Notes
    migrations    Migrations          one-time changes to saved data
"""
from .applications import ApplicationService
from .boards import BoardService
from .catalog import JobCatalog
from .feed import FeedService
from .migrations import Migrations
from .profile import ProfileService
from .resumes import ResumeService
from .settings import SettingsService
from .writing import WritingService

__all__ = ["ApplicationService", "BoardService", "FeedService", "JobCatalog", "Migrations", "ProfileService", "ResumeService",
           "SettingsService", "WritingService"]
