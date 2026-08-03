"""Server-rendered pages.

Same visual system as web/index.html — the transit palette, one accent per
service line — so the product and its map look like one thing. Plain HTML and
forms: no client framework, nothing to hydrate, works with JavaScript off.
"""

from __future__ import annotations

import html
from datetime import date

CSS = """
:root{
  --paper:#eef1f5;--surface:#fff;--surface-2:#e4e9ef;--ink:#11141a;--ink-2:#48515e;
  --ink-3:#78828f;--rule:#cdd5de;--radar:#0c7c77;--forge:#b0521c;--dispatch:#2a4fb8;
  --bridge:#7a3b96;--ok:#1a7f4b;--warn:#b0521c;
  --shadow:0 1px 2px rgba(17,20,26,.06),0 8px 24px rgba(17,20,26,.07);
  --sans:"Helvetica Neue",Helvetica,"Segoe UI",Roboto,Arial,sans-serif;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root{
  --paper:#0e1116;--surface:#161a21;--surface-2:#1e242d;--ink:#e8edf3;--ink-2:#a9b4c1;
  --ink-3:#7c8794;--rule:#2b323c;--radar:#2ab3ac;--forge:#e0813f;--dispatch:#6188f0;
  --bridge:#b473d0;--ok:#3fbb79;--warn:#e0813f;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.35);}}
*{box-sizing:border-box}html,body{margin:0;padding:0}
body{background:var(--paper);color:var(--ink);font:16px/1.5 var(--sans);-webkit-font-smoothing:antialiased}
a{color:var(--dispatch)}
button,input,select,textarea{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--dispatch);outline-offset:2px;border-radius:4px}
.shell{max-width:960px;margin:0 auto;padding:22px 20px 72px}
.nav{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;
  padding-bottom:14px;border-bottom:1px solid var(--rule);margin-bottom:26px}
.brand{font-weight:700;letter-spacing:-.02em;font-size:17px;text-decoration:none;color:var(--ink)}
.brand span{color:var(--radar)}
.nav-right{display:flex;align-items:center;gap:14px;font-size:13.5px;color:var(--ink-2)}
h1{margin:0 0 8px;font-size:clamp(23px,3.4vw,32px);line-height:1.12;letter-spacing:-.02em;text-wrap:balance}
h2{margin:30px 0 10px;font-size:19px;letter-spacing:-.015em}
.lede{margin:0 0 22px;color:var(--ink-2);max-width:64ch}
.card{background:var(--surface);border:1px solid var(--rule);border-radius:10px;
  box-shadow:var(--shadow);padding:20px;margin-bottom:16px}
.card.tight{padding:14px 16px}
.eyebrow{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);font-weight:700;margin:0 0 6px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:640px){.grid{grid-template-columns:1fr}}
.field{display:flex;flex-direction:column;gap:5px;margin-bottom:14px}
.field.wide{grid-column:1/-1}
label{font-size:13.5px;font-weight:700}
.sub{font-size:12.5px;color:var(--ink-3);font-weight:400}
input[type=text],input[type=email],input[type=password],input[type=file],textarea,select{
  background:var(--surface-2);border:1px solid var(--rule);border-radius:7px;padding:9px 11px;font-size:14px;width:100%}
textarea{min-height:130px;font-family:var(--mono);font-size:12.5px}
.btn{display:inline-block;background:var(--surface);border:1px solid var(--rule);border-radius:7px;
  padding:9px 15px;font-size:14px;cursor:pointer;text-decoration:none;color:var(--ink)}
.btn:hover{border-color:var(--ink-3)}
.btn-primary{background:var(--radar);border-color:transparent;color:#fff;font-weight:700}
.btn-danger{color:var(--warn);border-color:var(--warn)}
.btn-sm{padding:5px 10px;font-size:12.5px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3);
  padding:0 10px 8px 0;font-weight:700}
td{padding:10px 10px 10px 0;border-top:1px solid var(--rule);vertical-align:top}
td.num{font-variant-numeric:tabular-nums;font-weight:700;white-space:nowrap}
.score{display:inline-block;min-width:34px;text-align:center;border-radius:4px;padding:2px 6px;
  font-size:12.5px;font-weight:700;color:#fff;background:var(--radar)}
.score.mid{background:var(--forge)}
.pill{display:inline-block;font-size:11px;letter-spacing:.08em;text-transform:uppercase;font-weight:700;
  padding:3px 8px;border-radius:99px;background:var(--surface-2);color:var(--ink-2)}
.pill.new{color:var(--radar)}.pill.prepared{color:var(--forge)}
.pill.submitted{color:var(--dispatch)}.pill.replied{color:var(--ok)}
.msg{border-left:3px solid var(--radar);background:var(--surface-2);border-radius:0 7px 7px 0;
  padding:11px 13px;margin-bottom:16px;font-size:13.5px}
.msg.bad{border-left-color:var(--warn)}
.muted{color:var(--ink-3);font-size:13px}
pre{background:var(--surface-2);border:1px solid var(--rule);border-radius:7px;padding:12px;
  overflow-x:auto;font-family:var(--mono);font-size:12.5px;line-height:1.5;white-space:pre-wrap}
pre.diff .add{color:var(--ok)}pre.diff .del{color:var(--warn)}
.footer{margin-top:34px;font-size:12.5px;color:var(--ink-3);line-height:1.6}
"""


def e(value) -> str:
    return html.escape(str(value if value is not None else ""))


def layout(title: str, body: str, user=None, message: str = "", error: str = "") -> str:
    nav_right = (
        f'<span>{e(user["email"])}</span>'
        f'<a href="/settings">Settings</a>'
        f'<form method="post" action="/logout" style="display:inline">'
        f'<button class="btn btn-sm" type="submit">Sign out</button></form>'
        if user else '<a href="/login">Sign in</a>'
    )
    banner = ""
    if message:
        banner += f'<div class="msg">{e(message)}</div>'
    if error:
        banner += f'<div class="msg bad">{e(error)}</div>'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><style>{CSS}</style></head><body><div class="shell">
<nav class="nav"><a class="brand" href="/">job<span>·</span>radar</a>
<div class="nav-right">{nav_right}</div></nav>
{banner}{body}
<p class="footer">Your resume stays in your own workspace and is never shown to another user.
The agent never submits an application and never claims experience you do not have.
<a href="/settings">Delete everything</a> whenever you like.</p>
</div></body></html>"""


def landing() -> str:
    return layout("Job Radar — a job search that runs itself", """
<h1>Every morning, five jobs worth your time — and the resume already rewritten for them.</h1>
<p class="lede">You bring a resume and a few preferences. Overnight it reads the boards you care
about, scores every posting against your actual experience, and has a tailored resume, a cover
letter and the hiring manager's name waiting when you wake up. You read, you approve, you send.
It never applies for you and never invents experience you do not have.</p>
<div class="row"><a class="btn btn-primary" href="/signup">Create an account</a>
<a class="btn" href="/login">Sign in</a></div>
<div class="grid" style="margin-top:30px">
  <div class="card"><p class="eyebrow" style="color:var(--radar)">Job radar</p>
  <p>Greenhouse, Lever, Ashby and RemoteOK, filtered by your rules, scored against your resume.</p></div>
  <div class="card"><p class="eyebrow" style="color:var(--forge)">Resume forge</p>
  <p>One tailored resume and letter per role, reordered and reworded — every number kept exact.</p></div>
  <div class="card"><p class="eyebrow" style="color:var(--dispatch)">Dispatch</p>
  <p>Documents and screening answers ready. You do the final click, always.</p></div>
  <div class="card"><p class="eyebrow" style="color:var(--bridge)">Human bridge</p>
  <p>Who owns the role, and a message written for them that you send from your own account.</p></div>
</div>""")


def auth_page(kind: str, error: str = "") -> str:
    signup = kind == "signup"
    title = "Create your account" if signup else "Sign in"
    extra = ('<p class="sub">At least 10 characters. We store a scrypt hash, never the password.</p>'
             if signup else "")
    other = ('<p class="muted" style="margin-top:14px">Already have one? <a href="/login">Sign in</a>.</p>'
             if signup else '<p class="muted" style="margin-top:14px">New here? <a href="/signup">Create an account</a>.</p>')
    return layout(title, f"""
<h1>{title}</h1>
<div class="card" style="max-width:440px">
<form method="post" action="/{kind}">
  <div class="field"><label for="email">Email</label>
    <input id="email" name="email" type="email" required autocomplete="email"></div>
  <div class="field"><label for="password">Password</label>
    <input id="password" name="password" type="password" required
      autocomplete="{'new-password' if signup else 'current-password'}">{extra}</div>
  <button class="btn btn-primary" type="submit">{title}</button>
</form>
{other}
</div>""", error=error)


ONBOARD_FIELDS = [
    ("titles", "Job titles you want", "data engineer, analytics engineer", True,
     "Comma separated. Matched against posting titles."),
    ("exclude_titles", "Title words to skip", "intern, sales, director", False, ""),
    ("seniority", "Your level", "mid to senior", False, ""),
    ("locations", "Cities you would work in", "berlin, amsterdam", False, ""),
    ("work_authorisation", "Work authorisation", "EU citizen — no sponsorship needed", False, ""),
    ("salary_floor", "Lowest you would accept", "€70,000", False, ""),
    ("salary_expectation", "What you say when asked", "€78,000–€88,000", False, ""),
    ("notice_period", "Notice period", "four weeks", False, ""),
    ("why_leaving", "Why you are leaving", "one honest sentence", False, ""),
    ("exclude_keywords", "Deal-breakers in the posting", "unpaid, commission only", False, ""),
    ("boards", "Company job boards", "greenhouse:stripe, lever:ramp", False,
     "From the careers URL: boards.greenhouse.io/stripe → greenhouse:stripe."),
    ("linkedin", "LinkedIn URL", "", False, ""),
]


def onboarding(user, error: str = "") -> str:
    fields = ""
    for name, label, placeholder, required, sub in ONBOARD_FIELDS:
        star = ' <span style="color:var(--warn)">*</span>' if required else ""
        hint = f'<span class="sub">{e(sub)}</span>' if sub else ""
        wide = " wide" if name in ("titles", "boards", "exclude_keywords") else ""
        fields += (f'<div class="field{wide}"><label for="{name}">{e(label)}{star}</label>{hint}'
                   f'<input id="{name}" name="{name}" type="text" placeholder="{e(placeholder)}"'
                   f'{" required" if required else ""}></div>')
    return layout("Set up your profile", f"""
<h1>Set up your profile</h1>
<p class="lede">Your resume is read on the server, turned into a structured profile in your own
workspace, and never shown to another user. It takes about three minutes.</p>
<form method="post" action="/onboarding" enctype="multipart/form-data">
  <div class="card">
    <p class="eyebrow">1 — your resume</p>
    <div class="field"><label for="resume_file">Upload a file</label>
      <span class="sub">PDF, Word, Markdown or plain text.</span>
      <input id="resume_file" name="resume_file" type="file" accept=".pdf,.docx,.md,.txt,.rtf"></div>
    <div class="field"><label for="resume_text">…or paste the text</label>
      <textarea id="resume_text" name="resume_text" spellcheck="false"></textarea></div>
  </div>
  <div class="card">
    <p class="eyebrow">2 — what you are looking for</p>
    <div class="grid">{fields}</div>
    <div class="field"><label><input type="checkbox" name="remote_only" value="1"> Remote roles only</label></div>
    <div class="field"><label><input type="checkbox" name="include_remoteok" value="1" checked> Also search RemoteOK</label></div>
  </div>
  <button class="btn btn-primary" type="submit">Create my profile</button>
</form>""", user=user, error=error)


def _score_pill(score) -> str:
    score = int(score or 0)
    cls = "score" if score >= 80 else "score mid"
    return f'<span class="{cls}">{score}</span>'


def dashboard(user, jobs, runs, message: str = "", error: str = "", has_key: bool = True) -> str:
    if not has_key:
        message = message or "Add your Anthropic API key in Settings — until then runs use fixtures."
    rows = ""
    for job in jobs:
        rows += f"""<tr>
  <td class="num">{_score_pill(job['score'])}</td>
  <td><a href="/jobs/{e(job['id'])}"><strong>{e(job['title'])}</strong></a><br>
      <span class="muted">{e(job['company'])} · {e(job['location'] or '—')}</span></td>
  <td><span class="pill {e(job['status'])}">{e(job['status'])}</span></td>
  <td style="text-align:right">{_actions(job)}</td></tr>"""
    if not rows:
        rows = ('<tr><td colspan="4" class="muted" style="padding:18px 0">'
                'Nothing yet. Run the search and your shortlist appears here.</td></tr>')

    history = "".join(
        f'<li class="muted">{e(r["started_at"][:16].replace("T", " "))} — {e(r["status"])}'
        f'{" · " + e(r["detail"]) if r["detail"] else ""}</li>' for r in runs
    ) or '<li class="muted">No runs yet.</li>'

    return layout("Your shortlist", f"""
<h1>Today, {date.today().strftime('%-d %B')}</h1>
<p class="lede">Scored against your resume. Approve the ones worth the effort — tailoring runs
only on those, so it stays cheap.</p>
<form method="post" action="/run" style="margin-bottom:18px">
  <button class="btn btn-primary" type="submit">Run the search now</button>
</form>
<div class="card"><table><thead><tr><th>Score</th><th>Role</th><th>State</th><th></th></tr></thead>
<tbody>{rows}</tbody></table></div>
<h2>Recent runs</h2><ul style="padding-left:18px;margin:0">{history}</ul>""",
        user=user, message=message, error=error)


def _actions(job) -> str:
    status = job["status"]
    if status == "scored":
        return (f'<form method="post" action="/jobs/{e(job["id"])}/approve">'
                f'<button class="btn btn-sm btn-primary" type="submit">Approve</button></form>')
    if status == "approved":
        return (f'<form method="post" action="/jobs/{e(job["id"])}/prepare">'
                f'<button class="btn btn-sm" type="submit">Tailor it</button></form>')
    return f'<a class="btn btn-sm" href="/jobs/{e(job["id"])}">Open</a>'


def job_detail(user, job, analysis, docs, message: str = "") -> str:
    gaps = ", ".join(analysis.get("missing_skills", [])) or "—"
    matches = ", ".join(analysis.get("matched_skills", [])) or "—"
    sections = ""
    for name, label in (("evidence.md", "Requirement → your evidence"),
                        ("diff", "What changed versus your master resume"),
                        ("letter.md", "Cover letter"),
                        ("answers.md", "Screening answers"),
                        ("outreach.md", "Outreach drafts")):
        content = docs.get(name)
        if content:
            body = _diff_html(content) if name == "diff" else e(content)
            cls = ' class="diff"' if name == "diff" else ""
            sections += f"<h2>{e(label)}</h2><pre{cls}>{body}</pre>"

    prepare = ""
    if job["status"] == "approved":
        prepare = (f'<form method="post" action="/jobs/{e(job["id"])}/prepare">'
                   f'<button class="btn btn-primary" type="submit">Tailor it</button></form>')
    submitted = ""
    if job["status"] == "prepared":
        submitted = (f'<form method="post" action="/jobs/{e(job["id"])}/submitted">'
                     f'<button class="btn" type="submit">I applied — log it</button></form>')

    return layout(f"{job['title']} — {job['company']}", f"""
<h1>{e(job['title'])}</h1>
<p class="lede">{e(job['company'])} · {e(job['location'] or '—')} · {e(job['salary_raw'] or 'salary not stated')}</p>
<div class="card tight"><div class="row" style="justify-content:space-between">
  <div>{_score_pill(job['score'])} <span class="pill {e(job['status'])}">{e(job['status'])}</span></div>
  <div class="row">{prepare}{submitted}
  <a class="btn" href="{e(job['url'])}" target="_blank" rel="noreferrer noopener">Open the posting</a></div>
</div></div>
<div class="card"><p><strong>Verdict.</strong> {e(analysis.get('verdict', '—'))}</p>
<p class="muted"><strong>Matches:</strong> {e(matches)}<br><strong>Gaps:</strong> {e(gaps)}</p></div>
{sections}
<p class="muted" style="margin-top:20px">Nothing here has been sent. You apply on the company's
site yourself, and you send the messages from your own account.</p>""", user=user, message=message)


def _diff_html(text: str) -> str:
    out = []
    for line in text.splitlines():
        safe = e(line)
        if line.startswith("+") and not line.startswith("+++"):
            out.append(f'<span class="add">{safe}</span>')
        elif line.startswith("-") and not line.startswith("---"):
            out.append(f'<span class="del">{safe}</span>')
        else:
            out.append(safe)
    return "\n".join(out)


def settings(user, key_hint: str | None, message: str = "", error: str = "") -> str:
    current = (f'<p class="muted">Currently set: <code>{e(key_hint)}</code></p>'
               if key_hint else '<p class="muted">No key yet — runs fall back to fixtures.</p>')
    return layout("Settings", f"""
<h1>Settings</h1>
<div class="card">
  <p class="eyebrow">Your Anthropic API key</p>
  <p class="lede">Every call runs on your key, so you see exactly what you spend and we never
  meter you. It is encrypted before it is stored, and shown back only as a hint.</p>
  {current}
  <form method="post" action="/settings/key">
    <div class="field"><label for="api_key">Key</label>
      <input id="api_key" name="api_key" type="password" placeholder="sk-ant-…" required></div>
    <button class="btn btn-primary" type="submit">Save key</button>
  </form>
</div>
<div class="card">
  <p class="eyebrow">Daily run</p>
  <form method="post" action="/settings/daily">
    <label><input type="checkbox" name="daily_enabled" value="1"
      {'checked' if user['daily_enabled'] else ''}> Search for me every weekday morning</label>
    <div style="margin-top:12px"><button class="btn" type="submit">Save</button></div>
  </form>
</div>
<div class="card">
  <p class="eyebrow">The daily email</p>
  <p class="lede">One email each morning with the roles that cleared your threshold — the part
  most people actually use. Every message carries a one-click unsubscribe.</p>
  <form method="post" action="/settings/email">
    <label><input type="checkbox" name="daily_email" value="1"
      {'checked' if user['daily_email'] else ''}> Email me the shortlist every morning</label>
    <div style="margin-top:12px" class="row"><button class="btn" type="submit">Save</button></div>
  </form>
  <form method="post" action="/email/test" style="margin-top:10px">
    <button class="btn btn-sm" type="submit">Send me one now</button>
  </form>
</div>
<div class="card">
  <p class="eyebrow">Delete everything</p>
  <p class="lede">Your account row, your resume, your tracker and every document generated for
  you. Immediate and irreversible — no soft delete, no backup we keep.</p>
  <form method="post" action="/account/delete"
        onsubmit="return confirm('Delete your account and all your files?')">
    <div class="field" style="max-width:320px"><label for="confirm">Type DELETE to confirm</label>
      <input id="confirm" name="confirm" type="text" required></div>
    <button class="btn btn-danger" type="submit">Delete my account</button>
  </form>
</div>""", user=user, message=message, error=error)


def simple_page(title: str, body: str) -> str:
    """For pages reached from an email, where nobody is signed in."""
    return layout(title, f'<h1>{e(title)}</h1><p class="lede">{e(body)}</p>'
                         f'<a class="btn" href="/login">Sign in</a>')
