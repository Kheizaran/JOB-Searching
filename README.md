# Job Search Agent — a skill tree you can actually run

A clickable build map plus the pipeline it describes. The map is a transit
diagram: four services leaving one interchange. Click a stop and you get what it
does, how you know it's finished, and the prompt that builds it in Claude Code.

    web/index.html      the map — open it in a browser, no build step, no server
    agent/              the pipeline the map describes

Open the map: `open web/index.html` (or `python3 -m http.server` and visit `/web/`).
Progress is stored in your browser, and the language toggle switches the whole map
to Farsi.

## The four lines

| Line | What it does | Where it lives |
|---|---|---|
| **00 Setup** | Profile, preferences, tracker DB — everything else depends on it | `store.py`, `config/` |
| **10 Job Radar** | Every morning: scrape boards, filter, score against your resume, write a digest | `sources.py`, `scrape.py`, `score.py`, `digest.py` |
| **20 Resume Forge** | Per job: parse the posting, map your evidence, rewrite the resume, draft the letter | `tailor.py` |
| **30 Dispatch** | Queue, screening answers, **human approval gate**, submit + log, follow-ups | `queue.py`, `review.py` |
| **40 Human Bridge** | Work out who the hiring manager is, verify them, draft the message you send | `outreach.py` |

## Run it in two minutes

```bash
python3 -m agent.run_daily --dry-run
```

No API key, no network: it runs against `agent/fixtures/jobs.json`, scores with
deterministic stand-ins, and writes `data/digests/<today>.md`. Then walk one job
through the whole pipeline:

```bash
python3 -m agent.jobsearch.digest  --approve <id>          # from the digest
python3 -m agent.jobsearch.queue   prepare <id> --dry-run  # resume + letter + evidence map
python3 -m agent.jobsearch.outreach find <id> --dry-run    # who to reach, and the searches
python3 -m agent.jobsearch.queue   review <id>             # the human gate
python3 -m agent.jobsearch.queue   list                    # where everything stands
```

## Make it yours

```bash
cp .env.example .env                                        # add ANTHROPIC_API_KEY
cp agent/config/preferences.example.json agent/config/preferences.json
cp agent/config/resume.example.md        agent/config/resume.md
pip install -r requirements.txt
python3 -m agent.run_daily
```

Both real config files are gitignored — your resume and your salary floor never
reach the repo. Edit `preferences.json` first: `target_titles`, `locations`,
`score_threshold`, and the `sources` list (Greenhouse / Lever / Ashby board names
for the companies you actually want, plus RemoteOK as a wide net).

In `resume.md`, the section that matters most is **`## Story bank`**. It is the
only place the tailoring step is allowed to take achievements from. Ten to fifteen
true bullets with real numbers there produce better tailored resumes than a
beautifully formatted CV.

## Run it every morning

`.github/workflows/daily.yml` runs the pipeline on weekdays at 07:00 and commits
the digest back, so your shortlist is waiting when you wake up. Locally, cron works
just as well:

```
0 7 * * 1-5 cd ~/JOB-Searching && python3 -m agent.run_daily >> data/logs/cron.log 2>&1
```

## The rule that doesn't move

The agent prepares. A human approves. Nothing is submitted or sent by code —
`review.py` has no bypass flag, and adding one is out of scope by design. Two
reasons, both practical: automated applications get accounts banned and CVs
blacklisted, and a resume that claims things you can't defend fails at the
interview instead of at the screen. Tailoring reorders and rewords what is true;
it never invents.

LinkedIn is used the way a person uses it. The agent works out who to talk to and
writes the message; you open the browser and press send.

## Building the rest with Claude Code

Every stop on the map carries a prompt. Open the map, click a stop, copy the
prompt, paste it into Claude Code inside this repo — `CLAUDE.md` gives it the
rules it needs to stay inside the lines. What's already implemented: the whole of
Setup, Job Radar, the tailoring pass, the queue, the human gate, and the outreach
drafts. Left as prompts: the ATS-safe PDF renderer (20.4), screening-answer
snippets (30.2), the follow-up ladders (30.5 / 40.4), and referral matching (40.5).

---

## خلاصه فارسی

نقشه‌ی `web/index.html` را در مرورگر باز کنید و زبان را روی فارسی بگذارید. چهار خط
دارد: پیداکردن آگهی، بازنویسی رزومه، اپلای با تأیید انسانی، و رسیدن به مدیر استخدام.
روی هر ایستگاه بزنید تا پرامپت ساختش را بگیرید و در Claude Code داخل همین مخزن
اجرا کنید. برای دیدن کل خط لوله بدون هیچ کلید API:
`python3 -m agent.run_daily --dry-run`.

قانونی که تغییر نمی‌کند: ایجنت آماده می‌کند، شما تأیید می‌کنید. هیچ اپلیکیشن یا
پیامی به‌صورت خودکار ارسال نمی‌شود و هیچ تجربه‌ای که در رزومه‌تان نیست ساخته نمی‌شود.
