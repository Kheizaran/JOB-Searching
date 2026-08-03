# Job Search Agent — rules for Claude Code

This repo automates the boring half of a job search. The rules below are not
style preferences; they are what keeps the output usable and the accounts alive.

## Hard rules

1. **A human approves before anything leaves the machine.** No application is
   submitted, no email is sent, no LinkedIn message is delivered by code.
   `agent/jobsearch/review.py` is the gate and it has no bypass flag. Do not add one.
2. **Never invent experience.** Tailoring reorders, reframes and rewords what is
   already in `agent/config/resume.md`. New employers, dates, titles, tools or
   metrics are a bug, not a feature. When a requirement has no backing, it is a
   gap — report it as interview prep.
3. **Keep metrics exact.** If the master resume says 38%, the tailored one says 38%.
4. **Do not scrape LinkedIn**, or any site whose terms forbid it. The Human Bridge
   line prepares searches and messages; the person runs them in their browser.
5. **Rate-limit and cache every source.** Six-hour disk cache, descriptive
   User-Agent, back off on 429.
6. **Secrets come from `.env`.** Only `.env.example` is committed. `preferences.json`,
   `resume.md` and `snippets.json` are personal and gitignored; the `*.example.*`
   files are the committed templates.
7. **Setup stays local.** `agent/setup.py` binds to 127.0.0.1 and nothing else.
   A resume is read on the user's disk and written back to their disk; the only
   thing that ever leaves is the resume text going to Claude to be restructured.
   Do not add uploads, analytics, or a hosted mode without the user asking for it.

## Shape of the code

- `agent/jobsearch/` — one module per pipeline stage, each runnable on its own
  with `python3 -m agent.jobsearch.<module>`.
- Every module that calls a model goes through `llm.py` and passes a `mock=`
  value, so `--dry-run` exercises the same code path with no API key.
- `store.py` is the only place that touches SQLite. Job ids are content hashes,
  so re-scraping is idempotent.
- Stdlib only, except `anthropic`. Do not add a framework to solve a 40-line problem.

## Before you commit

    python3 -m agent.run_daily --dry-run

It must pass with no credentials and no network.
