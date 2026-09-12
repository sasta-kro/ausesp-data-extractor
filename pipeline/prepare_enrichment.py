#!/usr/bin/env python3
"""Stage per-project sources for the enrichment pass (logos, repository links).

Walks the raw corpus and stages one normalized folder per project under
_workspace/extracted-sources/<id>/ with report.pdf (or report.docx), slides.pdf,
poster.pdf, extracted external-evidence files, and media images pulled out of
DOCX reports. Writes _workspace/extracted-sources-manifest.json describing exactly
what was found per project, including anomalies.

Usage: python3 pipeline/prepare_enrichment.py [--source <corpus-dir>] [--clean]
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

MEMBER_IGNORE = ["*slide*", "*slides*", "*poster*", "*presentation*", "*external*exposure*"]
SANITIZE = re.compile(r"[^A-Za-z0-9._-]+")


def matches_any(name: str, patterns: list[str]) -> bool:
    lowered = name.casefold()
    return any(fnmatch.fnmatch(lowered, pattern) for pattern in patterns)


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}__{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def archive_members(source: Path, scratch: Path) -> tuple[list[Path], str]:
    """Extract a ZIP (or RAR-named-zip) archive into scratch and return files."""
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    try:
        with zipfile.ZipFile(source) as archive:
            members = [i for i in archive.infolist() if not i.is_dir()
                       and not i.filename.replace("\\", "/").startswith("__MACOSX/")]
            archive.extractall(scratch, members=members)
        how = "zip"
    except zipfile.BadZipFile:
        # Some archives carry RAR bytes under a .zip name; unar reads both.
        result = subprocess.run(["unar", "-f", "-o", str(scratch), str(source)],
                                capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"unar failed: {result.stderr.strip()[:200]}")
        how = "unar"
    files = [p for p in scratch.rglob("*") if p.is_file()]
    return sorted(files), how


def pick_report(files: list[Path]) -> tuple[Path | None, str, list[str]]:
    """Choose the report document from extracted archive files."""
    notes: list[str] = []
    pdfs = [f for f in files if f.suffix.casefold() == ".pdf"
            and not matches_any(f.name, MEMBER_IGNORE)]
    docs = [f for f in files if f.suffix.casefold() in (".docx", ".doc")]
    if len(pdfs) == 1:
        return pdfs[0], "only_pdf", notes
    if len(pdfs) > 1:
        report_named = [f for f in pdfs if "report" in f.name.casefold()]
        if len(report_named) == 1:
            notes.append(f"{len(pdfs)} pdfs, unique report-named chosen")
            return report_named[0], "unique_report_named", notes
        largest = max(pdfs, key=lambda f: f.stat().st_size)
        notes.append(f"{len(pdfs)} pdfs, largest chosen: {largest.name}")
        return largest, "largest_pdf", notes
    if docs:
        chosen = docs[0] if len(docs) == 1 else max(docs, key=lambda f: f.stat().st_size)
        notes.append(f"no pdf, {len(docs)} word docs, chose {chosen.name}")
        return chosen, "doc_only" if chosen.suffix.casefold() == ".doc" else "docx_only", notes
    return None, "none", notes + [f"no report document in archive ({len(files)} files)"]


def extract_docx_media(docx: Path, target_dir: Path) -> list[str]:
    """Pull word/media/* images out of a DOCX report."""
    extracted: list[str] = []
    try:
        with zipfile.ZipFile(docx) as archive:
            for info in archive.infolist():
                name = info.filename.replace("\\", "/")
                if info.is_dir() or not name.startswith("word/media/"):
                    continue
                dest = unique_path(target_dir / SANITIZE.sub("_", Path(name).name))
                dest.write_bytes(archive.read(info))
                extracted.append(dest.name)
    except zipfile.BadZipFile:
        extracted.append("ERROR: docx unreadable as zip")
    return sorted(extracted)


def convert_doc_media(doc: Path, target_dir: Path) -> tuple[str, list[str]]:
    """Convert a legacy .doc through textutil rtfd to recover its embedded images."""
    run_dir = target_dir.parent / "doc-convert"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    result = subprocess.run(["textutil", "-convert", "rtfd", "-output", str(run_dir), str(doc)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        return f"ERROR: textutil failed: {result.stderr.strip()[:150]}", []
    images: list[str] = []
    for file in sorted(run_dir.rglob("*")):
        if file.is_file() and file.suffix.casefold() != ".rtf" and file.name != "TXT.rtf":
            dest = unique_path(target_dir / SANITIZE.sub("_", file.name))
            shutil.copy2(file, dest)
            images.append(dest.name)
    return "", images


def extract_pptx_media(pptx: Path, target_dir: Path) -> list[str]:
    """Pull ppt/media/* images out of a PPTX poster."""
    extracted: list[str] = []
    try:
        with zipfile.ZipFile(pptx) as archive:
            for info in archive.infolist():
                name = info.filename.replace("\\", "/")
                if info.is_dir() or not name.startswith("ppt/media/"):
                    continue
                dest = unique_path(target_dir / f"poster-{SANITIZE.sub('_', Path(name).name)}")
                dest.write_bytes(archive.read(info))
                extracted.append(dest.name)
    except zipfile.BadZipFile:
        extracted.append("ERROR: pptx unreadable as zip")
    return sorted(extracted)


def stage(source_dir: Path, prepared: Path, base: Path, clean: bool) -> dict:
    if clean and prepared.exists():
        shutil.rmtree(prepared)
    prepared.mkdir(parents=True, exist_ok=True)
    scratch_root = base / "scratch"
    if scratch_root.exists():
        shutil.rmtree(scratch_root)
    scratch_root.mkdir(parents=True)

    ids = sorted({p.name.split("_")[0] for p in source_dir.iterdir()
                  if p.is_file() and re.match(r"^\d+_", p.name)})
    manifest: dict[str, dict] = {}

    for project_id in ids:
        entry: dict = {"report": None, "slides": None, "poster": None,
                       "external": [], "media": [], "anomalies": []}
        project_dir = prepared / project_id
        project_dir.mkdir(exist_ok=True)
        prefix = source_dir / project_id

        report_source = next((p for p in source_dir.iterdir()
                              if p.name.startswith(f"{project_id}_Report")), None)
        if report_source is None:
            entry["anomalies"].append("no report source file")
        elif report_source.suffix.casefold() == ".pdf":
            shutil.copy2(report_source, project_dir / "report.pdf")
            entry["report"] = {"file": "report.pdf", "from": report_source.name, "how": "direct_pdf"}
        else:
            try:
                files, how = archive_members(report_source, scratch_root / f"{project_id}-report")
                chosen, method, notes = pick_report(files)
                entry["anomalies"].extend(notes)
                if chosen is None:
                    entry["anomalies"].append("report archive yielded no document")
                elif chosen.suffix.casefold() == ".pdf":
                    shutil.copy2(chosen, project_dir / "report.pdf")
                    entry["report"] = {"file": "report.pdf", "from": report_source.name,
                                       "how": method, "archive": how}
                else:
                    staged_name = "report.doc" if chosen.suffix.casefold() == ".doc" else "report.docx"
                    shutil.copy2(chosen, project_dir / staged_name)
                    entry["report"] = {"file": staged_name, "from": report_source.name,
                                       "how": method, "archive": how}
                    media_dir = project_dir / "media"
                    media_dir.mkdir(exist_ok=True)
                    if staged_name == "report.docx":
                        entry["media"] = extract_docx_media(chosen, media_dir)
                    else:
                        error, images = convert_doc_media(chosen, media_dir)
                        entry["media"] = images
                        if error:
                            entry["anomalies"].append(error)
            except Exception as exc:  # noqa: BLE001 - record and continue with other projects
                entry["anomalies"].append(f"report archive failed: {exc}")

        slide_source = next((p for p in source_dir.iterdir()
                             if p.name.startswith(f"{project_id}_Slide")), None)
        if slide_source is not None:
            if slide_source.suffix.casefold() == ".pdf":
                shutil.copy2(slide_source, project_dir / "slides.pdf")
                entry["slides"] = {"file": "slides.pdf", "from": slide_source.name}
            else:
                try:
                    files, how = archive_members(slide_source, scratch_root / f"{project_id}-slides")
                    pdfs = [f for f in files if f.suffix.casefold() == ".pdf"]
                    if pdfs:
                        shutil.copy2(pdfs[0], project_dir / "slides.pdf")
                        entry["slides"] = {"file": "slides.pdf", "from": slide_source.name,
                                           "how": "first_pdf", "archive": how}
                    else:
                        entry["anomalies"].append(f"slide archive has no pdf ({len(files)} files)")
                except Exception as exc:  # noqa: BLE001
                    entry["anomalies"].append(f"slide archive failed: {exc}")

        poster_source = next((p for p in source_dir.iterdir()
                              if p.name.startswith(f"{project_id}_Poster")), None)
        if poster_source is not None:
            try:
                files, how = archive_members(poster_source, scratch_root / f"{project_id}-poster")
                pdfs = [f for f in files if f.suffix.casefold() == ".pdf"]
                pptxs = [f for f in files if f.suffix.casefold() == ".pptx"]
                if pdfs:
                    shutil.copy2(pdfs[0], project_dir / "poster.pdf")
                    entry["poster"] = {"file": "poster.pdf", "from": poster_source.name,
                                       "how": "first_pdf", "archive": how}
                elif pptxs:
                    media_dir = project_dir / "media"
                    media_dir.mkdir(exist_ok=True)
                    shutil.copy2(pptxs[0], project_dir / "poster.pptx")
                    entry["poster"] = {"file": "poster.pptx", "from": poster_source.name,
                                       "how": "pptx_media", "archive": how,
                                       "media": extract_pptx_media(pptxs[0], media_dir)}
                else:
                    images = [f for f in files if f.suffix.casefold() in (".jpg", ".jpeg", ".png")]
                    if images:
                        largest = max(images, key=lambda f: f.stat().st_size)
                        shutil.copy2(largest, project_dir / f"poster{largest.suffix.casefold()}")
                        entry["poster"] = {"file": f"poster{largest.suffix.casefold()}",
                                           "from": poster_source.name, "how": "image",
                                           "archive": how}
                    else:
                        entry["anomalies"].append(
                            f"poster archive has no pdf/pptx/image ({len(files)} files)")
            except Exception as exc:  # noqa: BLE001
                entry["anomalies"].append(f"poster archive failed: {exc}")

        external_sources = [p for p in source_dir.iterdir()
                            if p.name.startswith(f"{project_id}_External")]
        for external_source in external_sources:
            try:
                files, how = archive_members(external_source, scratch_root / f"{project_id}-external")
                external_dir = project_dir / "external"
                external_dir.mkdir(exist_ok=True)
                for file in files:
                    dest = unique_path(external_dir / SANITIZE.sub("_", file.name))
                    shutil.copy2(file, dest)
                    entry["external"].append(dest.name)
            except Exception as exc:  # noqa: BLE001
                entry["anomalies"].append(f"external archive failed: {exc}")

        manifest[project_id] = entry

    return manifest


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path,
                        default=root / ".." / ".." / "resources" / "all-sp-projects")
    parser.add_argument("--clean", action="store_true",
                        help="Delete the prepared tree before staging")
    args = parser.parse_args()

    prepared = root / "_workspace" / "prepared"
    manifest = stage(args.source.resolve(), prepared, root / "_workspace", args.clean)
    (root / "_workspace" / "extracted-sources.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1))

    total = len(manifest)
    with_report = sum(1 for e in manifest.values() if e["report"])
    with_slides = sum(1 for e in manifest.values() if e["slides"])
    with_poster = sum(1 for e in manifest.values() if e["poster"])
    with_external = sum(1 for e in manifest.values() if e["external"])
    with_media = sum(1 for e in manifest.values() if e["media"])
    print(f"projects: {total}")
    print(f"report staged: {with_report} (docx+media: {with_media})")
    print(f"slides staged: {with_slides}, poster staged: {with_poster}, external: {with_external}")
    anomalies = {pid: e["anomalies"] for pid, e in manifest.items() if e["anomalies"]}
    if anomalies:
        print(f"anomalies in {len(anomalies)} projects:")
        for pid, notes in anomalies.items():
            print(f"  {pid}: {'; '.join(notes)}")
    return 0 if with_report == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
