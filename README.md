# Job Search Agent — a skill tree you can actually run

A clickable build map plus the pipeline it describes. The map is a transit
diagram: four services leaving one interchange. Click a stop and you get what it
does, how you know it's finished, and the prompt that builds it in Claude Code.

    web/index.html      the map — open it in a browser, no build step, no server
    web/setup.html      the setup page: upload a resume, answer the questions
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
python3 -m agent.jobsearch.queue   prepare <id> --dry-run  # resume + letter + answers + PDF
python3 -m agent.jobsearch.outreach find <id> --dry-run    # who to reach, and the searches
python3 -m agent.jobsearch.outreach referrals <id>         # who you already know there
python3 -m agent.jobsearch.queue   review <id>             # the human gate
python3 -m agent.jobsearch.queue   submit <id>             # after you clicked submit yourself
python3 -m agent.jobsearch.followup --dry-run              # what is due to be nudged today
python3 -m agent.jobsearch.queue   list                    # where everything stands
```

You tell the tracker what you did in the world — `queue submit`, `queue replied`,
`outreach sent <contact>`, `outreach replied <contact>` — and the ladders react:
any reply stops the follow-ups immediately, and each ladder caps at two rungs
before closing itself out.

## Make it yours

```bash
pip install -r requirements.txt
cp .env.example .env          # add ANTHROPIC_API_KEY
python3 -m agent.setup        # opens the setup page in your browser
```

The setup page takes your resume — PDF, Word, Markdown, plain text, or pasted —
and asks the rest: titles you want, cities, remote or not, work authorisation,
salary floor, notice period, deal-breakers, which company boards to watch. It
writes three files for you:

    agent/config/resume.md          your resume, structured, with a story bank
    agent/config/preferences.json   what to search for and what to reject
    agent/config/snippets.json      the answers you give on every form

All three are gitignored — your resume and your salary floor never reach the repo.
Prefer the terminal? `python3 -m agent.setup --cli` asks the same questions there.
Nothing is uploaded: the page is served by a program on your own machine, bound to
127.0.0.1, and your resume text goes to Claude only, only to be restructured.

The part worth your attention afterwards is **`## Story bank`** in `resume.md`.
It is the only place the tailoring step may take achievements from, so setup
flags every bullet that has no number in it. Ten to fifteen true bullets with real
numbers there produce better tailored resumes than a beautifully formatted CV.

Then:

```bash
python3 -m agent.run_daily
```

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

All 23 stops are implemented — the map is how you read the system, not a list of
homework. Every stop still carries the prompt that produced it, so when you want a
stop to work differently, click it, edit the prompt, and paste it into Claude Code
inside this repo. `CLAUDE.md` gives Claude the rules it needs to stay inside the
lines: no auto-submit, no invented experience, no LinkedIn scraping.

Good first changes: swap the `sources` list for the companies you actually want
(10.1), raise `score_threshold` until the digest is 5 roles instead of 15 (10.3),
and rewrite the `## Story bank` in your own resume until every line has a number in
it (00.2). That last one improves the output of everything downstream.

## Sharing it with someone else

Send them the repo. Each person runs it on their own machine, with their own API
key, and their own `agent/config/` — there is no shared server, no account, and
nobody's resume is ever visible to anybody else. What they need from you is one
line:

```bash
git clone <this repo> && cd JOB-Searching && pip install -r requirements.txt && python3 -m agent.setup
```

Setup is bilingual (English / فارسی, top right), so is the map, and both work
without an API key — with a key the resume gets properly structured, without one
it is copied through as-is so they can still see the whole thing run.

Two things worth telling them, because the tool will not bend on either: it never
submits an application for them, and it never claims experience they do not have.

---

## خلاصه فارسی

برای شروع، `python3 -m agent.setup` را اجرا کنید: صفحه‌ای در مرورگر باز می‌شود که
رزومه‌تان را می‌گیرد (PDF، Word، یا متن) و چند سؤال می‌پرسد — عنوان شغلی، شهر،
دورکاری، مجوز کار، حداقل حقوق. همه‌چیز روی کامپیوتر خودتان می‌ماند.

نقشه‌ی `web/index.html` را هم در مرورگر باز کنید و زبان را روی فارسی بگذارید. چهار
خط دارد: پیداکردن آگهی، بازنویسی رزومه، اپلای با تأیید انسانی، و رسیدن به مدیر
استخدام. روی هر ایستگاه بزنید تا پرامپت ساختش را بگیرید و در Claude Code داخل همین
مخزن اجرا کنید. برای دیدن کل خط لوله بدون هیچ کلید API:
`python3 -m agent.run_daily --dry-run`.

قانونی که تغییر نمی‌کند: ایجنت آماده می‌کند، شما تأیید می‌کنید. هیچ اپلیکیشن یا
پیامی به‌صورت خودکار ارسال نمی‌شود و هیچ تجربه‌ای که در رزومه‌تان نیست ساخته نمی‌شود.
