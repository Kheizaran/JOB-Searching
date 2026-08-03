---
description: Find the hiring manager for a job and draft the message I will send
argument-hint: <job-id>
---

For job `$1`:

1. `python3 -m agent.jobsearch.outreach find $1` and show me the search URLs.
2. Wait. I will run them in my browser and paste back a profile — do not try to
   fetch LinkedIn yourself.
3. When I paste it: save it to a temp file and run
   `python3 -m agent.jobsearch.outreach verify $1 --profile <file>`.
   If no strong hook came back, tell me the contact is not worth messaging yet
   and what would make a good hook.
4. Then `python3 -m agent.jobsearch.outreach draft <contact-id>` and show me the
   three variants with their character counts. Flag anything that sounds like a
   template or opens with "I am writing to apply".

I send the messages myself, from my own account.
