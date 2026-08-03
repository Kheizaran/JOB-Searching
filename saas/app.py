"""The web app.

    SAAS_SECRET_KEY=$(python3 -c "import secrets;print(secrets.token_urlsafe(48))") \\
      uvicorn saas.app:app --reload

Every request that touches a user's data runs inside `with workspace(...)` and
`with llm.use_key(...)`, so the pipeline modules stay exactly as the CLI uses
them and one user's files are unreachable from another's request.
"""

from __future__ import annotations

import json
import traceback
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from agent.jobsearch import digest, intake, llm, review, scrape, score, store, tailor
from agent.jobsearch.config import application_dir
from agent.jobsearch.workspace import workspace

from . import db, security, ui

app = FastAPI(title="Job Radar", docs_url=None, redoc_url=None)
COOKIE = "jr_session"
MAX_UPLOAD = 8 * 1024 * 1024


# ---------------------------------------------------------------- session

def current_user(request: Request):
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE token = ?", (token,)).fetchone()
        if not row or not security.session_alive(row["expires_at"]):
            return None
        return db.user_by_id(conn, row["user_id"])


def require_user(request: Request):
    user = current_user(request)
    if not user:
        raise _Redirect("/login")
    return user


class _Redirect(Exception):
    def __init__(self, url: str):
        self.url = url


@app.exception_handler(_Redirect)
async def _redirect_handler(request: Request, exc: _Redirect):
    return RedirectResponse(exc.url, status_code=303)


def html(body: str) -> HTMLResponse:
    return HTMLResponse(body)


def go(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def user_key(user) -> str | None:
    return security.decrypt_key(user["api_key_enc"])


# ---------------------------------------------------------------- public

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    user = current_user(request)
    return go("/dashboard") if user else html(ui.landing())


@app.get("/signup", response_class=HTMLResponse)
def signup_form():
    return html(ui.auth_page("signup"))


@app.post("/signup")
def signup(email: str = Form(...), password: str = Form(...)):
    with db.connect() as conn:
        if db.user_by_email(conn, email):
            return html(ui.auth_page("signup", error="That email already has an account."))
        try:
            pwd = security.hash_password(password)
        except ValueError as exc:
            return html(ui.auth_page("signup", error=str(exc)))
        user_id = db.create_user(conn, email, pwd)
        return _start_session(conn, user_id, "/onboarding")


@app.get("/login", response_class=HTMLResponse)
def login_form():
    return html(ui.auth_page("login"))


@app.post("/login")
def login(email: str = Form(...), password: str = Form(...)):
    with db.connect() as conn:
        user = db.user_by_email(conn, email)
        if not user or not security.verify_password(password, user["password_hash"]):
            return html(ui.auth_page("login", error="Wrong email or password."))
        target = "/dashboard" if user["onboarded_at"] else "/onboarding"
        return _start_session(conn, user["id"], target)


def _start_session(conn, user_id: str, target: str) -> RedirectResponse:
    token = security.new_session_token()
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
        (token, user_id, db.now(), security.session_expiry()),
    )
    conn.commit()
    response = go(target)
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 14)
    return response


@app.post("/logout")
def logout(request: Request):
    token = request.cookies.get(COOKIE)
    if token:
        with db.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
    response = go("/")
    response.delete_cookie(COOKIE)
    return response


# ---------------------------------------------------------------- onboarding

@app.get("/onboarding", response_class=HTMLResponse)
def onboarding_form(user=Depends(require_user)):
    return html(ui.onboarding(user))


@app.post("/onboarding")
async def onboarding_submit(request: Request, user=Depends(require_user)):
    form = await request.form()
    answers = {k: v for k, v in form.items() if not hasattr(v, "filename")}
    answers["remote_only"] = bool(form.get("remote_only"))
    answers["include_remoteok"] = bool(form.get("include_remoteok"))

    text = (form.get("resume_text") or "").strip()
    upload = form.get("resume_file")
    if isinstance(upload, UploadFile) and upload.filename:
        raw = await upload.read()
        if len(raw) > MAX_UPLOAD:
            return html(ui.onboarding(user, error="That file is larger than 8 MB."))
        try:
            text, _ = intake.extract_text(upload.filename, raw)
        except Exception as exc:
            return html(ui.onboarding(user, error=str(exc)))
    if not text:
        return html(ui.onboarding(user, error="Add your resume — upload a file or paste the text."))

    try:
        with workspace(db.workspace_for(user["id"])), llm.use_key(user_key(user)):
            result = intake.write_profile(text, answers, overwrite=True)
    except Exception as exc:
        return html(ui.onboarding(user, error=f"Could not build your profile: {exc}"))

    with db.connect() as conn:
        db.update_user(conn, user["id"], onboarded_at=db.now())
    missing = len(result.get("missing_metrics", []))
    note = (f"Profile created. {missing} achievement(s) have no number in them — "
            f"worth fixing, it is what makes a tailored resume land." if missing
            else "Profile created.")
    return _dashboard_response(user, message=note)


# ---------------------------------------------------------------- dashboard

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(user=Depends(require_user)):
    if not user["onboarded_at"]:
        return go("/onboarding")
    return _dashboard_response(user)


def _dashboard_response(user, message: str = "", error: str = "") -> HTMLResponse:
    with workspace(db.workspace_for(user["id"])):
        with store.connect() as conn:
            jobs = conn.execute(
                "SELECT * FROM jobs WHERE status IN "
                "('scored','approved','prepared','submitted','replied') "
                "ORDER BY score DESC LIMIT 40"
            ).fetchall()
    with db.connect() as conn:
        runs = db.recent_runs(conn, user["id"])
    return html(ui.dashboard(user, jobs, runs, message=message, error=error,
                             has_key=bool(user_key(user))))


@app.post("/run")
def run_now(user=Depends(require_user)):
    key = user_key(user)
    with db.connect() as conn:
        run_id = db.start_run(conn, user["id"])
    detail, status = "", "ok"
    try:
        with workspace(db.workspace_for(user["id"])), llm.use_key(key):
            llm.set_offline(not key)
            found = scrape.run(dry_run=not key)
            scored = score.run()
            digest.build()
            detail = f"{found['new']} new, {scored['passed']} above threshold"
    except Exception:
        status, detail = "failed", traceback.format_exc(limit=2)
    finally:
        llm.set_offline(False)
    with db.connect() as conn:
        db.finish_run(conn, run_id, user["id"], status, detail)
    return _dashboard_response(
        user,
        message=f"Search finished — {detail}" if status == "ok" else "",
        error="" if status == "ok" else "The run failed. See Recent runs for the detail.",
    )


# ---------------------------------------------------------------- one job

@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(job_id: str, user=Depends(require_user)):
    with workspace(db.workspace_for(user["id"])):
        with store.connect() as conn:
            job = store.get_job(conn, job_id)
            if not job:
                return go("/dashboard")
            analysis = json.loads(job["analysis"] or "{}")
            app_row = conn.execute(
                "SELECT * FROM applications WHERE job_id = ?", (job["id"],)
            ).fetchone()
        docs = {}
        if app_row and app_row["folder"]:
            folder = Path(app_row["folder"])
            for name in ("evidence.md", "letter.md", "answers.md", "outreach.md"):
                path = folder / name
                if path.exists():
                    docs[name] = path.read_text()[:12000]
            resume = folder / "resume.md"
            if resume.exists():
                docs["diff"] = review.resume_diff(resume)[:12000]
    return html(ui.job_detail(user, job, analysis, docs))


@app.post("/jobs/{job_id}/approve")
def approve(job_id: str, user=Depends(require_user)):
    with workspace(db.workspace_for(user["id"])):
        with store.connect() as conn:
            job = store.get_job(conn, job_id)
            if job:
                store.set_status(conn, job["id"], "approved")
                store.upsert_application(conn, job["id"])
    return _dashboard_response(user, message="Approved. Tailor it when you are ready.")


@app.post("/jobs/{job_id}/prepare")
def prepare(job_id: str, user=Depends(require_user)):
    key = user_key(user)
    try:
        with workspace(db.workspace_for(user["id"])), llm.use_key(key):
            llm.set_offline(not key)
            tailor.prepare(job_id)
    except SystemExit as exc:
        return _dashboard_response(user, error=str(exc))
    finally:
        llm.set_offline(False)
    return go(f"/jobs/{job_id}")


@app.post("/jobs/{job_id}/submitted")
def mark_submitted(job_id: str, user=Depends(require_user)):
    with workspace(db.workspace_for(user["id"])):
        with store.connect() as conn:
            job = store.get_job(conn, job_id)
            if job:
                store.set_status(conn, job["id"], "submitted")
                store.upsert_application(conn, job["id"], status="submitted",
                                         submitted_at=store.now())
    return _dashboard_response(user, message="Logged. Follow-ups start counting from today.")


# ---------------------------------------------------------------- settings

@app.get("/settings", response_class=HTMLResponse)
def settings(user=Depends(require_user)):
    key = user_key(user)
    return html(ui.settings(user, security.key_hint(key) if key else None))


@app.post("/settings/key")
def save_key(user=Depends(require_user), api_key: str = Form(...)):
    api_key = api_key.strip()
    if not api_key.startswith("sk-ant-"):
        return html(ui.settings(user, None, error="That does not look like an Anthropic key."))
    with db.connect() as conn:
        db.update_user(conn, user["id"], api_key_enc=security.encrypt_key(api_key))
    return html(ui.settings(user, security.key_hint(api_key),
                            message="Key saved, encrypted at rest."))


@app.post("/settings/daily")
def save_daily(user=Depends(require_user), daily_enabled: str = Form("")):
    with db.connect() as conn:
        db.update_user(conn, user["id"], daily_enabled=1 if daily_enabled else 0)
        user = db.user_by_id(conn, user["id"])
    key = user_key(user)
    return html(ui.settings(user, security.key_hint(key) if key else None,
                            message="Saved." if user["daily_enabled"] else "Daily search paused."))


@app.post("/account/delete")
def delete_account(user=Depends(require_user), confirm: str = Form("")):
    if confirm.strip().upper() != "DELETE":
        key = user_key(user)
        return html(ui.settings(user, security.key_hint(key) if key else None,
                                error="Type DELETE to confirm."))
    with db.connect() as conn:
        db.delete_user(conn, user["id"])
    response = go("/")
    response.delete_cookie(COOKIE)
    return response
