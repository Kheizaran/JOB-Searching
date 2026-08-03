---
description: Tailor, review and prepare an application for one job id
argument-hint: <job-id>
---

Prepare the application for job `$1`:

1. `python3 -m agent.jobsearch.queue prepare $1`
2. Read `evidence.md` in the application folder and tell me plainly which
   must-haves have weak or missing evidence. Do not paper over a gap — I would
   rather know before the interview.
3. Show me the resume diff versus the master and justify every change in one
   line. If any change adds a claim that is not in `agent/config/resume.md`,
   fix it before showing me.
4. Then stop and tell me to run `python3 -m agent.jobsearch.queue review $1`.

You do not submit anything. Ever.
