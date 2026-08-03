"""Setup — the app's front door.

    python3 -m agent.setup          # opens the setup page in your browser
    python3 -m agent.setup --cli    # same questions, in the terminal

Serves on 127.0.0.1 only. The resume you upload is read on this machine and
written to agent/config/ on this machine; nothing is sent anywhere except, if
you have set an API key, the resume text to Claude to be restructured.
"""

from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from agent.jobsearch import intake, llm
from agent.jobsearch.config import CONFIG_DIR, ROOT

PAGE = ROOT / "web" / "setup.html"
MAX_UPLOAD = 8 * 1024 * 1024

QUESTIONS = [
    ("titles", "Job titles you want (comma separated)", "data engineer, analytics engineer"),
    ("exclude_titles", "Title words that mean 'not for me'", "intern, sales"),
    ("seniority", "Your level", "mid to senior"),
    ("locations", "Cities you would work in", "berlin, amsterdam"),
    ("remote_only", "Remote only? (y/N)", ""),
    ("work_authorisation", "Work authorisation", "EU citizen, no sponsorship needed"),
    ("salary_floor", "Lowest salary you would accept", "€70,000"),
    ("salary_expectation", "What you tell them when they ask", "€78,000–€88,000"),
    ("exclude_keywords", "Deal-breakers to filter out", "unpaid, commission only"),
    ("boards", "Company boards, as type:name", "greenhouse:stripe, lever:ramp"),
    ("notice_period", "Your notice period", "four weeks"),
    ("why_leaving", "Why you are leaving, in one sentence", ""),
    ("linkedin", "LinkedIn URL", ""),
]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the terminal readable
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict) -> None:
        self._send(code, json.dumps(payload).encode(), "application/json")

    def do_GET(self):
        if self.path in ("/", "/index.html", "/setup.html"):
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/status":
            self._json(200, {
                "configured": [n for n in ("resume.md", "preferences.json", "snippets.json")
                               if (CONFIG_DIR / n).exists()],
                "has_key": llm.available(),
            })
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD:
            return self._json(413, {"error": "That file is larger than 8 MB."})
        raw = self.rfile.read(length)

        if self.path == "/api/extract":
            name = self.headers.get("X-Filename", "resume.txt")
            try:
                text, warning = intake.extract_text(name, raw)
            except Exception as exc:
                return self._json(400, {"error": str(exc)})
            return self._json(200, {"text": text, "warning": warning, "filename": name})

        if self.path == "/api/generate":
            try:
                payload = json.loads(raw or b"{}")
                result = intake.write_profile(
                    payload.get("resume_text", ""),
                    payload.get("answers", {}),
                    overwrite=bool(payload.get("overwrite")),
                )
            except Exception as exc:
                return self._json(400, {"error": str(exc)})
            return self._json(200, result)

        self._json(404, {"error": "not found"})


def serve(port: int = 8765, open_browser: bool = True) -> None:
    server = HTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"  Setup is open at {url}")
    print("  It only listens on this machine. Press Ctrl-C when you are done.\n")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Setup closed.")


def cli() -> None:
    print("\n  Setup — three minutes of questions, then you are ready.\n")
    path = input("  Path to your resume (pdf, docx, md, txt): ").strip().strip("'\"")
    resume = Path(path).expanduser()
    if not resume.exists():
        raise SystemExit(f"  No file at {resume}")
    text, warning = intake.extract_text(resume.name, resume.read_bytes())
    print(f"  Read {len(text.split())} words from {resume.name}")
    if warning:
        print(f"  ! {warning}")

    answers: dict = {}
    print()
    for key, question, example in QUESTIONS:
        hint = f" (e.g. {example})" if example else ""
        value = input(f"  {question}{hint}: ").strip()
        answers[key] = value.lower().startswith("y") if key == "remote_only" else value

    result = intake.write_profile(text, answers)
    if result.get("needs_confirmation"):
        print(f"\n  These already exist: {', '.join(result['existing'])}")
        if not input("  Overwrite them? The old ones are kept as .bak [y/N] ").strip().lower().startswith("y"):
            raise SystemExit("  Nothing written.")
        result = intake.write_profile(text, answers, overwrite=True)
    report(result)


def report(result: dict) -> None:
    print("\n  Written:")
    for path in result["written"]:
        print(f"    {path}")
    if result.get("backups"):
        print(f"  Previous versions kept as: {', '.join(result['backups'])}")
    if result.get("offline"):
        print("\n  ! No ANTHROPIC_API_KEY, so your resume was copied through as-is.")
        print("    Add the key and run setup again to get a properly structured story bank.")
    if result.get("missing_metrics"):
        print(f"\n  {len(result['missing_metrics'])} achievement(s) have no number in them.")
        print("  Numbers are what make a tailored resume land — add them in agent/config/resume.md:")
        for bullet in result["missing_metrics"][:5]:
            print(f"    · {bullet[:88]}")
    print("\n  Next:  python3 -m agent.run_daily\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Set up your job search profile")
    ap.add_argument("--cli", action="store_true", help="ask the questions in the terminal instead")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    cli() if args.cli else serve(args.port, not args.no_browser)
