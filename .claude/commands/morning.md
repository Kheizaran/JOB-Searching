---
description: Run today's job search and walk me through the shortlist
---

Run `python3 -m agent.run_daily` (add `--dry-run` if there is no ANTHROPIC_API_KEY),
then read today's file in `data/digests/`.

Present the shortlist to me as a short ranked list — role, company, score, and the
single most important gap for each. Recommend which two or three are worth the
tailoring effort and say why, in one line each. Do not approve anything yourself;
wait for me to name the ids, then run
`python3 -m agent.jobsearch.digest --approve <ids>`.
