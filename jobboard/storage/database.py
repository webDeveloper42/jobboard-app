"""The job database, used from one thread.

SQLite connections can't be shared between threads, and the dashboard calls the engine from many. So every piece of
database work goes through `Database.run(fn)`, which runs `fn` on the database's own thread and returns its result.

Rules (they keep you out of trouble):
  * Inside `fn`, use `database.con`. Outside it, `database.con` raises an error instead of silently breaking.
  * `run` may be called from inside another `run`; it then just calls `fn` directly, so it can never deadlock.
  * Slow work (fetching boards, AI writing) belongs outside `run`, with only its result saved inside.
"""
import datetime as dt
import os
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

from .. import config
from . import db


class Database:
    def __init__(self, path, on_open=None):
        """`path` is the .db file. `on_open(database)` runs once, on the database thread, right after connecting."""
        self.path = str(path)
        self._on_open = on_open
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jobboard-db")
        self._thread = None
        self._con = None

    # ---- public

    def run(self, fn, *args):
        """Run `fn(*args)` on the database thread and return what it returns (or raise what it raises)."""
        if self._on_db_thread():
            return fn(*args)
        return self._pool.submit(self._call, fn, *args).result()

    @property
    def con(self):
        """The SQLite connection. Only valid inside `run`."""
        if not self._on_db_thread():
            raise RuntimeError("Use the database inside Database.run(...); it only works on the database thread")
        if self._con is None:
            self._open()
        return self._con

    def close(self):
        def shut():
            if self._con is not None:
                self._con.close()
                self._con = None
        self._pool.submit(shut).result()
        self._pool.shutdown()

    # ---- inside

    def _on_db_thread(self):
        return self._thread is not None and threading.current_thread() is self._thread

    def _call(self, fn, *args):
        self._thread = threading.current_thread()
        if self._con is None:
            self._open()
        return fn(*args)

    def _open(self):
        self._con = db.connect(self.path)
        os.chmod(self.path, 0o600)
        self._backup_daily()
        if self._on_open:
            self._on_open(self)

    def _backup_daily(self):
        """One copy a day in data/backups, keeping the newest config.KEEP_BACKUPS. A failed backup never stops the app."""
        try:
            folder = os.path.join(os.path.dirname(self.path), "backups")
            os.makedirs(folder, mode=0o700, exist_ok=True)
            target = os.path.join(folder, f"jobboard-{dt.date.today().isoformat()}.db")
            if not os.path.exists(target):
                out = sqlite3.connect(target)
                try:
                    self._con.backup(out)
                finally:
                    out.close()
                os.chmod(target, 0o600)
            old = sorted(f for f in os.listdir(folder) if f.startswith("jobboard-") and f.endswith(".db"))
            for name in old[:-config.KEEP_BACKUPS]:
                os.remove(os.path.join(folder, name))
        except (OSError, sqlite3.Error):
            pass
