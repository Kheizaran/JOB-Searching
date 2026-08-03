# Job Radar — the hosted version

A working vertical slice: sign up, upload a resume, get a scored shortlist,
tailor an application, approve it. Built on the same pipeline the CLI uses, not
a reimplementation of it.

    SAAS_SECRET_KEY=$(python3 -c "import secrets;print(secrets.token_urlsafe(48))") \
      uvicorn saas.app:app --reload
    # then http://127.0.0.1:8000

    python3 -m saas.worker        # the nightly pass over every active user

## How one codebase serves both

The pipeline was single-tenant: one `agent/config/`, one `data/tracker.db`. Rather
than fork it, every path now resolves through `agent/jobsearch/workspace.py`, a
ContextVar the request handler sets:

```python
with workspace(db.workspace_for(user_id)), llm.use_key(user_key):
    scrape.run(); score.run(); digest.build()
```

Inside that block, `scrape`, `score`, `tailor`, `outreach` and `review` behave
exactly as they do on your laptop — they just read and write someone else's
directory, under someone else's API key. A ContextVar rather than a global so
concurrent requests cannot leak into each other.

That means one user is one directory:

    data/saas/workspaces/<user_id>/config/{resume.md,preferences.json,snippets.json}
    data/saas/workspaces/<user_id>/data/{tracker.db,applications/,digests/}

Deleting an account is a row and an `rmtree`. There is no shared jobs table to
untangle, and no query that can accidentally cross tenants — a user's jobs are
only reachable through their own SQLite file.

## What is in the slice

| Route | What it does |
|---|---|
| `/` | Landing page |
| `/signup`, `/login`, `/logout` | Email + password, scrypt hashed, 14-day session cookie |
| `/onboarding` | Resume upload (PDF/DOCX/MD/TXT) + preferences → their profile |
| `/dashboard` | Today's shortlist, scored, with run history |
| `/run` | Run the search now |
| `/jobs/{id}` | Verdict, evidence map, resume diff, letter, screening answers |
| `/jobs/{id}/approve`, `/prepare`, `/submitted` | The approve → tailor → applied path |
| `/settings` | API key, daily run on/off, delete everything |

Tested end to end with FastAPI's test client: signup → onboarding → run → approve
→ tailor produces a real diff, letter and answers; a second user cannot see the
first user's jobs, and requesting their job URL directly redirects rather than
leaking.

## Decisions baked in — change them if you disagree

**Users bring their own API key.** Every call runs on the key in their settings,
encrypted at rest with `SAAS_SECRET_KEY`. You carry no AI cost, need no metering,
and cannot be bankrupted by one enthusiastic user. The price is a signup step that
some non-technical users will not get through.

**No payments yet.** Billing is the easiest thing to add once people come back a
second week, and the most wasted work if they do not.

**SQLite for the control plane.** Fine to a few hundred users. The schema is
ordinary SQL; moving to Postgres is a connection change, not a rewrite.

**Server-rendered HTML, no client framework.** Works with JavaScript off, nothing
to hydrate, one language end to end.

## What this is not yet — the honest list

Before real users, in rough order:

1. **Email.** No verification, no password reset, no daily digest in the inbox.
   A digest email is probably the product's real surface — most people will never
   open a dashboard daily, but they will read an email.
2. **Rate limiting and abuse controls.** Nothing stops signup spam or a script
   hammering `/run`.
3. **Background jobs.** `/run` executes inside the request. Fine for a demo,
   wrong the moment a scrape takes 40 seconds. Needs a queue.
4. **CSRF protection.** Cookie sessions plus state-changing POSTs without tokens.
   Add a per-session token before this is public.
5. **A privacy policy and a data agreement.** You are holding CVs — personal data
   under GDPR — and sending them to Anthropic, which makes Anthropic a
   subprocessor you must disclose. Deletion works today; the paperwork does not
   exist.
6. **Backups, monitoring, error reporting.** None.
7. **Payments.** Note that Stripe and Paddle do not serve Iran; if your first
   users pay in rials this goes through a local gateway and changes both the
   billing code and where you can host.

## The uncomfortable part

Hosting this means holding other people's resumes and their API keys. That is a
real obligation, not a deployment detail: a leaked `SAAS_SECRET_KEY` exposes every
stored key at once, and a leaked workspace directory exposes people's employment
history. Keep the secret in a manager rather than an env file on a shared box,
encrypt the disk, and take the deletion path seriously — it is the one feature
users will judge you on if anything ever goes wrong.
