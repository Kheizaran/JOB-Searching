"""Stop 20.4 — render the tailored resume as an ATS-safe PDF.

Single column, real text, standard fonts, no tables, no boxes, no icons. The
parsers that read this file are not impressed by design; they are looking for
headings and bullets in reading order. After writing, we check exactly that.

    python3 -m agent.jobsearch.render <job_id>
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import store
from .config import application_dir

CHROME_CANDIDATES = [
    "chromium", "chromium-browser", "google-chrome", "google-chrome-stable",
    "/opt/pw-browsers/chromium",
]

CSS = """
@page { size: A4; margin: 16mm 15mm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 10.5pt; line-height: 1.38;
       color: #000; max-width: 100%; }
h1 { font-size: 17pt; margin: 0 0 2pt; letter-spacing: -0.2pt; }
h2 { font-size: 11pt; margin: 13pt 0 4pt; text-transform: uppercase; letter-spacing: 0.6pt;
     border-bottom: 0.6pt solid #000; padding-bottom: 2pt; }
h3 { font-size: 10.5pt; margin: 8pt 0 2pt; }
p  { margin: 0 0 5pt; }
ul { margin: 0 0 6pt; padding-left: 14pt; }
li { margin: 0 0 2.5pt; }
a  { color: #000; text-decoration: none; }
.contact { margin: 0 0 8pt; font-size: 9.5pt; }
"""


def md_to_html(md: str) -> str:
    """Just enough Markdown for a resume: headings, bullets, bold, links."""
    def inline(s: str) -> str:
        s = html.escape(s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
        return s

    out: list[str] = []
    in_list = False
    for raw in md.splitlines():
        line = raw.rstrip()
        if line.startswith("<!--"):
            continue
        bullet = re.match(r"^\s*[-*]\s+(.*)", line)
        if bullet:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{inline(bullet.group(1))}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if not line.strip():
            continue
        heading = re.match(r"^(#{1,4})\s+(.*)", line)
        if heading:
            level = min(len(heading.group(1)), 3)
            out.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
        elif len(out) <= 1 and ("·" in line or "@" in line):
            out.append(f'<p class="contact">{inline(line)}</p>')
        else:
            out.append(f"<p>{inline(line)}</p>")
    if in_list:
        out.append("</ul>")
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>{CSS}</style></head><body>\n" + "\n".join(out) + "\n</body></html>"
    )


def _chrome() -> str | None:
    for name in CHROME_CANDIDATES:
        found = shutil.which(name) or (name if Path(name).exists() else None)
        if found:
            return found
    return None


def html_to_pdf(html_text: str, pdf_path: Path) -> str:
    """weasyprint if it is installed, otherwise headless Chromium."""
    try:
        from weasyprint import HTML  # type: ignore

        HTML(string=html_text).write_pdf(str(pdf_path))
        return "weasyprint"
    except ImportError:
        pass

    chrome = _chrome()
    if not chrome:
        raise SystemExit(
            "No PDF engine found. Either `pip install weasyprint` or install Chromium."
        )
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as fh:
        fh.write(html_text)
        source = fh.name
    subprocess.run(
        [chrome, "--headless", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
         f"--print-to-pdf={pdf_path}", f"file://{source}"],
        check=True, capture_output=True,
    )
    Path(source).unlink(missing_ok=True)
    return Path(chrome).name


def verify(pdf_path: Path, resume_md: str) -> list[str]:
    """Read the PDF back the way a parser would. Returns warnings."""
    if not shutil.which("pdftotext"):
        return ["pdftotext not installed — could not verify the text layer"]
    text = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"], capture_output=True, text=True
    ).stdout
    warnings = []
    if len(text.split()) < 80:
        warnings.append("PDF has very little extractable text — check the engine")
    bullets = [b.strip("-* ").strip() for b in resume_md.splitlines() if b.strip().startswith(("-", "*"))]
    flat = " ".join(text.split())
    missing = [b for b in bullets[:6] if b and " ".join(b.split()[:5]) not in flat]
    if missing:
        warnings.append(f"{len(missing)} of the first bullets did not survive into the PDF")
    return warnings


def render(job_ref: str) -> str:
    with store.connect() as conn:
        job = store.get_job(conn, job_ref)
        if not job:
            raise SystemExit(f"No job matching {job_ref}")
        folder = application_dir(job["id"], job["company"], job["title"])
        source = folder / "resume.md"
        if not source.exists():
            raise SystemExit("No tailored resume yet — run `queue prepare` first")

        md = source.read_text()
        first = md.lstrip("# ").splitlines()[0].strip() if md.startswith("#") else "Resume"
        name = " ".join(first.split()[:4])[:40]  # the H1 is the candidate's name
        safe = lambda s: re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")
        pdf_path = folder / f"{safe(name)}-{safe(job['company'])}-{safe(job['title'])}.pdf"

        engine = html_to_pdf(md_to_html(md), pdf_path)
        warnings = verify(pdf_path, md)

    print(f"  pdf ({engine}) → {pdf_path}")
    for w in warnings:
        print(f"  ! {w}")
    return str(pdf_path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Render an ATS-safe resume PDF")
    ap.add_argument("job_id")
    render(ap.parse_args().job_id)
