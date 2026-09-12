#!/usr/bin/env python3
"""Grep staged document text layers for repository host URLs.

Scans every staged report, slide deck, poster, and external-evidence PDF page
by page for github.com / gitlab.com / bitbucket.org URLs, and converts DOCX
reports to text through macOS textutil (no page numbers there). Writes
output/extraction-evidence/repo-link-evidence/text-grep.json with one record per sighting.

Usage: python3 steps/grep_repo_urls.py
"""
from __future__ import annotations

import json
import re
import subprocess
import zipfile
from collections import Counter
from pathlib import Path

import pypdf

HOSTS = r"(?:github\.com|gitlab\.com|bitbucket\.org)"
URL_RE = re.compile(rf"(?:https?://)?{HOSTS}/[A-Za-z0-9_.\-/]+", re.IGNORECASE)
TRAILING = ".,;:)]}>\"'"
NORMALIZE_STRIP = re.compile(r"\.git$", re.IGNORECASE)


def normalize(url: str) -> str:
    url = url.rstrip(TRAILING).rstrip("/")
    url = NORMALIZE_STRIP.sub("", url)
    return f"https://{url[len('https://'):] if url.startswith('https://') else url}".lower()


def page_urls(text: str) -> list[str]:
    return [normalize(match.group(0)) for match in URL_RE.finditer(text)]


def scan_pdf(pdf: Path, project_id: str, name: str, records: list[dict]) -> None:
    try:
        reader = pypdf.PdfReader(pdf)
    except Exception as exc:  # noqa: BLE001
        records.append({"id": project_id, "file": name, "page": None, "url": None,
                        "context": f"unreadable: {exc}"})
        return
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - scanned or odd pages simply have no text
            continue
        for url in page_urls(text):
            line = next((ln.strip() for ln in text.splitlines() if url[8:] in ln), "")
            records.append({"id": project_id, "file": name, "page": index,
                            "url": url, "context": line[:200]})


def scan_pptx(pptx: Path, project_id: str, name: str, records: list[dict]) -> None:
    """Read slide text out of a PPTX by stripping run tags from slide XML."""
    try:
        with zipfile.ZipFile(pptx) as archive:
            slide_names = sorted(n for n in archive.namelist()
                                 if re.fullmatch(r"ppt/slides/slide\d+\.xml", n))
            for index, slide_name in enumerate(slide_names, start=1):
                xml = archive.read(slide_name).decode("utf-8", errors="ignore")
                text = re.sub(r"<a:t>", " ", xml)
                text = re.sub(r"<[^>]+>", "", text)
                for url in page_urls(text):
                    records.append({"id": project_id, "file": name, "page": index,
                                    "url": url, "context": ""})
    except Exception as exc:  # noqa: BLE001
        records.append({"id": project_id, "file": name, "page": None, "url": None,
                        "context": f"unreadable: {exc}"})


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    base = root / "_workspace"
    prepared = base / "prepared"
    manifest = json.loads((base / "intermediate-data" / "extracted-sources.json").read_text())

    records: list[dict] = []
    for project_id, entry in manifest.items():
        project_dir = prepared / project_id
        for key in ("report", "slides", "poster"):
            staged = entry.get(key)
            if staged and staged["file"].endswith(".pdf"):
                scan_pdf(project_dir / staged["file"], project_id, staged["file"], records)
        external_dir = project_dir / "external"
        if external_dir.exists():
            for pdf in sorted(external_dir.glob("*.pdf")):
                scan_pdf(pdf, project_id, f"external/{pdf.name}", records)
        report_docx = project_dir / "report.docx"
        for word_name in ("report.docx", "report.doc"):
            word_file = project_dir / word_name
            if word_file.exists():
                result = subprocess.run(["textutil", "-convert", "txt", "-stdout", str(word_file)],
                                        capture_output=True, text=True)
                for url in page_urls(result.stdout):
                    records.append({"id": project_id, "file": word_name, "page": None,
                                    "url": url, "context": ""})
        poster_pptx = project_dir / "poster.pptx"
        if poster_pptx.exists():
            scan_pptx(poster_pptx, project_id, "poster.pptx", records)

    output = root / "output" / "extraction-evidence" / "repo-link-evidence" / "text-grep.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(records, ensure_ascii=False, indent=1))

    hits = [r for r in records if r["url"]]
    projects = Counter(r["id"] for r in hits)
    print(f"sightings: {len(hits)} across {len(projects)} projects (+{len(records) - len(hits)} unreadable)")
    for host in ("github.com", "gitlab.com", "bitbucket.org"):
        count = sum(1 for r in hits if host in r["url"])
        print(f"  {host}: {count}")
    print("projects with at least one URL:")
    for project_id, count in sorted(projects.items()):
        print(f"  {project_id}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
