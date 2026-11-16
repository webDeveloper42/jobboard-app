# Job Board

A private job search app that runs on your own computer. It collects jobs from many job sites, keeps only the ones
you want, scores each one against your resume, and tracks your applications.

* No account and nothing to sign up for. Your data stays on your machine.
* Plain Python and SQLite, so there is nothing to install.
* Use it in the browser or from the terminal.

## What it shows

Only these jobs, either remote or in Washington, DC:

* **IT technician**: help desk, desktop support, IT support, service desk
* **IT internship**
* **Data entry**: data entry clerk, operator or specialist, typist

Everything else is left out when jobs are fetched. You can change this in `jobboard/rules/focus.py`.

## Features

* **Jobs from many places.** Company job boards (Greenhouse, Lever, Ashby, Workday), Remotive, Remote OK, Arbeitnow,
  Jobicy, Google Jobs and Jooble.
* **One job, shown once.** If the same job is on several sites, you see it once, with all its links.
* **Match score.** Each job gets a score out of 100, with the reasons behind it: the skills you have, the skills
  you're missing, and how the title, level, place and pay fit.
* **Scam filter.** Posts that look like scams are hidden (fees to start, texting a number to apply, asking for bank
  details, and so on).
* **Warnings.** Jobs that need a security clearance, old posts and posts that keep getting reposted are flagged.
* **Travel time.** For on-site jobs, it estimates the trip by Metro/bus and by car.
* **Resumes.** Upload a PDF, Word or text resume. You can keep more than one, for example one for IT and one for
  data entry.
* **Writing help.** A tailored resume and cover letter for any job, written by a local AI model (Ollama). It is told
  never to make things up.
* **Coach.** Chat about your search or about one job: interview prep, salary talk, follow-ups.
* **Application tracker.** Saved → Applied → Interviewing → Offer / Rejected, with notes, dates, contacts and a CSV
  export.
* **Morning summary.** A daily run that fetches new jobs and lists the best ones, by email if you set that up.

## Getting started

Open the page on its own:

    bin/jobboard serve

Or use the terminal:

    bin/jobboard                          # overview and top matches
    bin/jobboard resume ~/resume.pdf      # load your resume
    bin/jobboard refresh                  # fetch new jobs and score them
    bin/jobboard jobs --min 70            # jobs scoring 70 or more
    bin/jobboard show 42                  # one job and its score
    bin/jobboard apply 42                 # mark job 42 as applied
    bin/jobboard tracker                  # your applications
    bin/jobboard --help                   # every command

Tip: link `bin/jobboard` into a folder on your PATH so you can type just `jobboard`.

## Optional keys

Most job sites need no key. Two do:

| Site        | Where to get a key       | How to add it                                     |
|-------------|--------------------------|---------------------------------------------------|
| Google Jobs | serpapi.com (free plan)  | *Job boards → Google Jobs*, or `jobboard google-key KEY` |
| Jooble      | jooble.org/api/about     | *Job boards → Jooble*, or `jobboard jooble-key KEY`      |

Keys are saved in your local database, never in the code.

## Morning run

    jobboard daily

This fetches new jobs and puts the best new matches at the top of the page. To run it every morning, add a line
like this to your crontab:

    */30 7-12 * * * $HOME/.local/bin/jobboard daily --auto

## Where things are

```
bin/jobboard       the command
jobboard/          the app (Python)
  api.py             the main object the page and the terminal use
  boards/            one file per job site
  rules/             which jobs to keep, scam checks, scoring, travel times
  services/          profile, resumes, feed, applications, writing
  storage/           the database
web/               the page (JavaScript and CSS, no build step)
tests/             tests (no internet, never your real data)
docs/HOW-TO.md     where to change what
dev                ./dev test, ./dev check
```

Your data lives in `data/jobboard.db`. Set `JOBBOARD_DATA_DIR` to keep it somewhere else. The `data/` folder is never
committed.

## Tests

    ./dev test     # app and page tests
    ./dev check    # tests, then clicks through the page in a browser

The tests also run on GitHub on every push.

## Good to know

* Scanned PDFs have no text in them. Paste your resume instead.
* Local AI models write decent drafts but can still get things wrong. Read every letter before you send it.
