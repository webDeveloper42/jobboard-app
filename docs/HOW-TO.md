# How to change things by hand

A cookbook for common changes. After any change run `./dev check` (all tests, then a click-through of the page),
and restart the dashboard so it picks the change up. The engine also reloads when the dashboard restarts on its own
every 5 minutes.

## Where things are

| You want to change… | Open |
| --- | --- |
| your home town, the states you can work from, limits | `jobboard/config.py` |
| which job titles count as your roles, and their places | `jobboard/rules/focus.py` (`CATEGORIES`, `category()`) |
| the default searches for Google Jobs / Jooble / Workday | `jobboard/rules/focus.py` (`GOOGLE_SEARCHES`, …) |
| scam checks | `jobboard/rules/scam.py` (`_SIGNS`, `_DATA_ENTRY_SIGNS`) |
| how the match score is worked out | `jobboard/rules/match.py` (`WEIGHTS`, `score()`); keep `SCORE_WEIGHTS` in `web/js/core/constants.js` the same (a test checks) |
| how a job board is read | `jobboard/boards/<board>.py` |
| what an action does (save, refresh, tailor…) | the service named in `ACTIONS` in `jobboard/api.py` |
| the morning run | `jobboard/morning.py` |
| companies or words you never want to see | the **Hide rules** panel on the Profile screen (or More → Never show jobs from … on a job) |
| which URL does what | `jobboard/http_routes.py` (the dashboard and `jobboard serve` both use it) |
| how the page looks | `web/css/blocks/<block>.css`, colours and sizes in `web/css/base/tokens.css` |
| what the page shows | `web/js/screens/<screen>.js` and `web/js/components/` |

## Recipes

**Add a role** (say, "Customer support", remote or DC)
1. `rules/focus.py`: add `"support": {"name": "Customer support", "title": "Customer Support Representative", "places": ("remote", "dc")}`
   to `CATEGORIES`, a title pattern, and a branch in `category()` that returns `"support"`.
2. Add searches for it to `GOOGLE_SEARCHES` / `JOOBLE_SEARCHES`, and a one-time step in
   `services/migrations.py` that inserts them for your existing board (follow the `roles_v2` step).
3. Add title cases to `tests/test_focus.py` (`test_roles`).

**Add a kind of job board**: see the steps at the top of `jobboard/boards/__init__.py`.

**Add a page action**: see the top of `jobboard/api.py`.

**Change saved data once** (rename a search, fix old rows): add a step at the end of `Migrations.upgrade` in
`jobboard/services/migrations.py` with a new flag name. It runs once, the next time the database opens.

**Add something to the page**: see `web/README.md`.

## Tests

* `./dev check` on the server: every test plus a click-through of the page on a copy of your data.
* GitHub runs the engine and page unit tests on every push (`.github/workflows/tests.yml`). Tests that need the
  Sheets, Docs or Notes apps are skipped there; they run on the server.

## Rules that keep you out of trouble

* Database work only inside `self.run(...)` (services) or `api.run_in_db(...)`. Outside it, `.con` raises a clear
  error instead of corrupting anything. Slow work (fetching, AI) goes outside `run`; only its result goes in.
* Inputs from the page always go through `jobboard/validation.py`. Errors you raise for the user are
  `JobBoardError("A plain sentence.")`.
* Text from job posts goes into the page only through `h()` (text nodes), never as HTML.
* Tests never touch your real data: a test `JobBoardApi(path=…)` can't write to your Sheets, Docs or Notes, and the
  network is stubbed (`boards.http`, `boards.google_lookup`, `fulltext.fetch`, `travel.geocode`).
* `data/` (your database, resumes, API keys) is never committed.
