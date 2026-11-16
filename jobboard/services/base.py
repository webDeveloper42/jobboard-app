"""What every service shares: the app it belongs to, its database, and short ways to reach both."""


class Service:
    """A group of related actions (resumes, boards, applications…).

    `self.app` is the JobBoardApi that owns this service; reach other services through it, like
    `self.app.catalog.rescore_all()`. `self.run(fn)` runs database work (see storage/database.py), and inside it
    `self.con` is the SQLite connection.
    """

    def __init__(self, app):
        self.app = app

    @property
    def db(self):
        return self.app.db

    @property
    def con(self):
        return self.app.db.con

    def run(self, fn, *args):
        return self.app.db.run(fn, *args)
