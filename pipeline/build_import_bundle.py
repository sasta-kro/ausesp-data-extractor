#!/usr/bin/env python3
"""Assemble the AUSE Discovery real-content import bundle.

Combines four extractor products into one portable bundle for
`ausectl project-content import-manifest`:

- output/ause-discovery-projects-metadata-import.csv   project membership
- output/extraction-evidence/manifest.json             logos and repo links
- output/logos/                                        square PNG logos
- _workspace/extracted-sources/                        staged project files

Bundle layout (BUNDLE_ROOT, inside the main repository):

  project-content-manifest.json
  logos/<identifier>.png
  projects/sp-<identifier>/<file>

Only projects present in the metadata CSV are included, so culled or
unimportable projects can never reference a Project that has no database
row. The bundle is rebuilt from scratch on every run and is safe to
delete at any time: it is a derived copy, never the only copy.

Usage: python3 pipeline/build_import_bundle.py [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image

# --- configuration --------------------------------------------------------

EXTRACTOR_ROOT = Path(__file__).resolve().parents[1]
MAIN_REPO_ROOT = EXTRACTOR_ROOT.parents[1]

METADATA_CSV = EXTRACTOR_ROOT / "output" / "ause-discovery-projects-metadata-import.csv"
EVIDENCE_MANIFEST = EXTRACTOR_ROOT / "output" / "extraction-evidence" / "manifest.json"
LOGOS_DIR = EXTRACTOR_ROOT / "output" / "logos"
SOURCES_DIR = EXTRACTOR_ROOT / "_workspace" / "extracted-sources"
BUNDLE_ROOT = MAIN_REPO_ROOT / "resources" / "REAL_IMPORT_BUNDLE"
BUNDLE_MANIFEST_NAME = "project-content-manifest.json"

# --------------------------------------------------------------------------

# Corpus filename -> (artifact type, public display name). Must stay within
# the extension table the application enforces (backend artifact validator:
# report pdf/docx, slides pdf/ppt/pptx, poster pdf/png/jpg/jpeg, ...).
FILE_RULES = {
    "report.pdf": ("report", "Final report"),
    "report.docx": ("report", "Final report"),
    "slides.pdf": ("slides", "Presentation slides"),
    "poster.pdf": ("poster", "Project poster"),
    "poster.png": ("poster", "Project poster"),
    "poster.jpg": ("poster", "Project poster"),
    "poster.jpeg": ("poster", "Project poster"),
}
FILE_ORDER = {"report": 0, "slides": 1, "poster": 2, "other": 3}

# Supplementary material staged in external/ imports under the "other" type
# when its extension is permitted there (pdf). Each corpus name is unique,
# so every importable file gets an explicit public display name. Award
# images (jpg, png) have no permitted type and stay out with a warning.
EXTERNAL_EXTENSIONS = {".pdf"}
EXTERNAL_DISPLAY = {
    "IAIT2020_submission21.pdf": "IAIT 2020 conference paper",
    "HPBDIS_2021_paper_106.pdf": "HPBDIS 2021 conference paper",
    "20211108_confirmation_app_development.pdf": "Client confirmation letter",
    "User_Feedback_Reprt.pdf": "User feedback report",
    "Research_Paper_26014_.pdf": "Research paper",
    "Research_Paper_26016_.pdf": "Research paper",
}

# Legacy corpus files converted to PDF before bundling, because the
# application admits .doc nowhere and .pptx not under the poster type.
# The 1636 report.doc is a real report, and the decks named poster.pptx in
# 1638 and 1703 are presentation slides mislabeled by the corpus (verified
# by inspection, 2026-09-12), so both convert and bundle as their true kind.
# A staged file already carrying the target name wins over a conversion.
CONVERSIONS = {
    "report.doc": "report.pdf",
    "poster.pptx": "slides.pdf",
}
SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
CONVERTED_CACHE = EXTRACTOR_ROOT / "_workspace" / "converted"

# Extraction byproducts staged beside the real files, never bundle content.
# external/ is not in this set: it holds supplementary material that the
# "other" artifact type imports when its extension is permitted.
SKIP_DIRS = {"media", "doc-convert"}

# Evidence liveness status -> application availability enum.
AVAILABILITY = {"public": "accessible", "not_found": "not_accessible", "unknown": "unverified"}

# Application upload limits, enforced locally so an invalid bundle never
# reaches the importer (defaults from the backend configuration).
FILE_MAX_BYTES = 262_144_000       # 250 MiB per Project File
LOGO_MAX_BYTES = 2 * 1024 * 1024   # 2 MiB per logo
LOGO_MAX_SIDE = 1600               # pixels

# Detected-content sniffing, mirroring the application's extension checks:
# pdf must start with %PDF-, docx/pptx are ZIP containers, jpg starts with
# the JPEG SOI marker.
MAGIC = {
    "pdf": b"%PDF-",
    "docx": b"PK\x03\x04",
    "pptx": b"PK\x03\x04",
    "jpg": b"\xff\xd8\xff",
    "jpeg": b"\xff\xd8\xff",
    "png": b"\x89PNG\r\n\x1a\n",
}

RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$")


def read_members() -> list[str]:
    with open(METADATA_CSV, newline="", encoding="utf-8") as handle:
        keys = [row["import_key"] for row in csv.DictReader(handle)]
    if not keys:
        sys.exit(f"no import keys found in {METADATA_CSV}")
    return sorted(keys, key=lambda k: int(k.split("-", 1)[1]))


def converted_source(identifier: str, item: Path, dry_run: bool) -> Path | None:
    """Return the cached or freshly produced PDF for a legacy corpus file."""
    cached = CONVERTED_CACHE / f"{identifier}-{CONVERSIONS[item.name]}"
    if cached.is_file():
        return cached
    if dry_run:
        return None
    CONVERTED_CACHE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        result = subprocess.run(
            [SOFFICE, "--headless", "--convert-to", "pdf", "--outdir", work, str(item)],
            capture_output=True, text=True, timeout=300)
        produced = Path(work) / f"{item.stem}.pdf"
        if result.returncode != 0 or not produced.is_file():
            print(result.stderr.strip() or result.stdout.strip(), file=sys.stderr)
            return None
        shutil.copy2(produced, cached)
    return cached


def collect_external_files(identifier: str, directory: Path) -> tuple[list[dict], list[str]]:
    """Plan the supplementary material in one project's external/ directory
    as "other" artifacts. Returns (entries, warnings)."""
    entries: list[dict] = []
    warnings: list[str] = []
    for item in sorted(directory.iterdir()):
        label = f"external/{item.name}"
        if not item.is_file():
            warnings.append(f"sp-{identifier}: unexpected non-file entry '{label}'")
            continue
        if item.suffix.lower() not in EXTERNAL_EXTENSIONS:
            warnings.append(f"sp-{identifier}: skipped '{label}', no permitted artifact type admits its extension")
            continue
        byte_count = item.stat().st_size
        if byte_count > FILE_MAX_BYTES:
            warnings.append(f"sp-{identifier}: skipped '{label}', {byte_count} bytes exceeds the {FILE_MAX_BYTES} byte limit")
            continue
        with open(item, "rb") as handle:
            prefix = handle.read(8)
        if not prefix.startswith(MAGIC["pdf"]):
            warnings.append(f"sp-{identifier}: skipped '{label}', content does not match its extension")
            continue
        display_name = EXTERNAL_DISPLAY.get(item.name) or item.stem.replace("_", " ").strip()
        entries.append({
            "artifact_type": "other",
            "display_name": display_name,
            "original_filename": item.name,
            "file_path": f"projects/sp-{identifier}/{item.name}",
            "_source": item,
            "_bytes": byte_count,
        })
    return entries, warnings


def collect_files(identifier: str, dry_run: bool) -> tuple[list[dict], list[str], list[str]]:
    """Plan the file entries for one project.

    Returns (entries, warnings, conversions).
    """
    source_dir = SOURCES_DIR / identifier
    if not source_dir.is_dir():
        sys.exit(f"member sp-{identifier} has no staged source directory: {source_dir}")

    entries: list[dict] = []
    warnings: list[str] = []
    conversions: list[str] = []
    for item in sorted(source_dir.iterdir()):
        if item.name == "external" and item.is_dir():
            external_entries, external_warnings = collect_external_files(identifier, item)
            entries.extend(external_entries)
            warnings.extend(external_warnings)
            continue
        if item.name in SKIP_DIRS:
            continue
        if not item.is_file():
            warnings.append(f"sp-{identifier}: unexpected non-file entry '{item.name}'")
            continue
        rule = FILE_RULES.get(item.name)
        source = item
        bundle_name = item.name
        converted = False
        if rule is None:
            target_name = CONVERSIONS.get(item.name)
            if target_name is None:
                warnings.append(f"sp-{identifier}: skipped '{item.name}', no rule maps it to a supported artifact type")
                continue
            if (source_dir / target_name).is_file():
                warnings.append(f"sp-{identifier}: skipped '{item.name}', '{target_name}' is already staged")
                continue
            rule = FILE_RULES[target_name]
            bundle_name = target_name
            source = converted_source(identifier, item, dry_run)
            converted = True
            if source is None and not dry_run:
                warnings.append(f"sp-{identifier}: skipped '{item.name}', conversion to PDF failed")
                continue
        artifact_type, display_name = rule
        byte_count = source.stat().st_size if source is not None else 0
        if source is not None:
            if byte_count > FILE_MAX_BYTES:
                warnings.append(f"sp-{identifier}: skipped '{item.name}', {byte_count} bytes exceeds the {FILE_MAX_BYTES} byte limit")
                continue
            extension = bundle_name.rsplit(".", 1)[-1].lower()
            with open(source, "rb") as handle:
                prefix = handle.read(8)
            if not prefix.startswith(MAGIC[extension]):
                warnings.append(f"sp-{identifier}: skipped '{item.name}', content does not match its extension")
                continue
        if converted:
            conversions.append(f"sp-{identifier}: {item.name} -> {bundle_name} (planned)" if dry_run else f"sp-{identifier}: {item.name} -> {bundle_name}")
        entries.append({
            "artifact_type": artifact_type,
            "display_name": display_name,
            "original_filename": bundle_name,
            "file_path": f"projects/sp-{identifier}/{bundle_name}",
            "_source": source,
            "_bytes": byte_count,
        })
    entries.sort(key=lambda e: (FILE_ORDER[e["artifact_type"]], e["original_filename"]))
    return entries, warnings, conversions


def plan_logo(identifier: str, record: dict) -> tuple[dict | None, list[str]]:
    """Plan the logo entry for one project. Returns (entry, warnings)."""
    logo = record.get("logo") or {}
    output = logo.get("output")
    if not output:
        return None, []
    source = LOGOS_DIR / Path(output).name
    if not source.is_file():
        return None, [f"sp-{identifier}: evidence names logo '{output}' but {source} is missing"]
    byte_count = source.stat().st_size
    if byte_count > LOGO_MAX_BYTES:
        return None, [f"sp-{identifier}: logo {source.name} is {byte_count} bytes, over the {LOGO_MAX_BYTES} byte limit"]
    try:
        with Image.open(source) as image:
            if image.format != "PNG":
                raise ValueError(f"format is {image.format}, not PNG")
            width, height = image.size
            image.verify()
    except Exception as error:
        return None, [f"sp-{identifier}: logo {source.name} failed PNG validation: {error}"]
    if width > LOGO_MAX_SIDE or height > LOGO_MAX_SIDE:
        return None, [f"sp-{identifier}: logo {source.name} is {width}x{height}, over the {LOGO_MAX_SIDE}px limit"]
    return {
        "file_path": f"logos/{source.name}",
        "_source": source,
        "_bytes": byte_count,
    }, []


def plan_links(identifier: str, record: dict) -> tuple[list[dict] | None, list[str]]:
    """Plan the links array for one project. Returns (links, warnings).

    None means "omit the field" so the application leaves existing
    repository links untouched, while an empty list would actively remove them.
    """
    repo_links = [l for l in (record.get("links") or []) if l.get("kind") == "project_repo"]
    if not repo_links:
        return None, []

    warnings: list[str] = []
    planned: list[dict] = []
    seen: set[str] = set()
    for link in repo_links:
        url = link.get("normalized") or link.get("url") or ""
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.fragment:
            warnings.append(f"sp-{identifier}: dropped link '{url}', not a clean absolute HTTPS URL")
            continue
        if any(ord(character) < 0x20 or ord(character) == 0x7f for character in url):
            warnings.append(f"sp-{identifier}: dropped link '{url}', control characters")
            continue
        if len(url) > 2048 or url in seen:
            warnings.append(f"sp-{identifier}: dropped link '{url}', duplicate or over 2048 characters")
            continue
        seen.add(url)
        liveness = link.get("liveness") or {}
        checked_at = liveness.get("checked_at") or ""
        if not RFC3339.match(checked_at):
            warnings.append(f"sp-{identifier}: dropped link '{url}', missing or invalid liveness timestamp")
            continue
        datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
        planned.append({
            "url": url,
            "primary": bool(link.get("primary")),
            "availability": AVAILABILITY.get(liveness.get("status"), "unverified"),
            "checked_at": checked_at,
        })

    if not planned:
        return None, warnings
    if sum(1 for l in planned if l["primary"]) != 1:
        sys.exit(f"sp-{identifier}: repository link set must carry exactly one primary link")
    return planned, warnings


def build_plan(dry_run: bool) -> tuple[list[dict], list[str], list[str]]:
    members = read_members()
    with open(EVIDENCE_MANIFEST, encoding="utf-8") as handle:
        evidence = json.load(handle)

    plan: list[dict] = []
    warnings: list[str] = []
    conversions: list[str] = []
    for key in members:
        identifier = key.split("-", 1)[1]
        record = evidence.get(identifier) or {}
        files, file_warnings, project_conversions = collect_files(identifier, dry_run)
        logo, logo_warnings = plan_logo(identifier, record)
        links, link_warnings = plan_links(identifier, record)
        warnings.extend(file_warnings + logo_warnings + link_warnings)
        conversions.extend(project_conversions)
        if not files and not logo and not links:
            warnings.append(f"sp-{identifier}: no bundle content (no importable files, no logo, no links), entry omitted")
            continue
        entry: dict = {"project_import_key": key}
        if logo:
            entry["logo"] = {"file_path": logo["file_path"]}
            entry["_logo_source"] = logo["_source"]
            entry["_logo_bytes"] = logo["_bytes"]
        if files:
            entry["files"] = files
        if links is not None:
            entry["links"] = links
        plan.append(entry)
    return plan, warnings, conversions


def clean_entry(entry: dict) -> dict:
    """Strip the planning-only keys (sources, byte counts) the loader would
    reject as unknown fields."""
    clean: dict = {"project_import_key": entry["project_import_key"]}
    if "logo" in entry:
        clean["logo"] = {"file_path": entry["logo"]["file_path"]}
    if "files" in entry:
        clean["files"] = [
            {field: file_entry[field]
             for field in ("artifact_type", "display_name", "original_filename", "file_path")}
            for file_entry in entry["files"]
        ]
    if "links" in entry:
        clean["links"] = entry["links"]
    return clean


def write_bundle(plan: list[dict]) -> None:
    if BUNDLE_ROOT.exists():
        shutil.rmtree(BUNDLE_ROOT)
    (BUNDLE_ROOT / "logos").mkdir(parents=True)
    for entry in plan:
        if "_logo_source" in entry:
            shutil.copy2(entry["_logo_source"], BUNDLE_ROOT / "logos" / entry["_logo_source"].name)
        for file_entry in entry.get("files", []):
            destination = BUNDLE_ROOT / file_entry["file_path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_entry["_source"], destination)

    # The application loader rejects unknown fields at every level, so the
    # emitted entries carry exactly the contract keys and nothing else.
    manifest = {
        "version": 1,
        "projects": [clean_entry(entry) for entry in plan],
    }
    manifest_path = BUNDLE_ROOT / BUNDLE_MANIFEST_NAME
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def report(plan: list[dict], warnings: list[str], conversions: list[str], dry_run: bool) -> None:
    logo_count = sum(1 for entry in plan if "logo" in entry)
    link_count = sum(len(entry.get("links", [])) for entry in plan)
    file_total = sum(len(entry.get("files", [])) for entry in plan)
    byte_total = sum(entry.get("_logo_bytes", 0) + sum(f["_bytes"] for f in entry.get("files", [])) for entry in plan)
    by_type: dict[str, int] = {}
    for entry in plan:
        for file_entry in entry.get("files", []):
            by_type[file_entry["artifact_type"]] = by_type.get(file_entry["artifact_type"], 0) + 1

    mode = "dry run, nothing written" if dry_run else f"written to {BUNDLE_ROOT}"
    print(f"bundle plan: {mode}")
    print(f"  projects in metadata CSV membership: {len(read_members())}")
    print(f"  manifest entries: {len(plan)}")
    print(f"  logos: {logo_count}")
    print(f"  files: {file_total} ({', '.join(f'{v} {k}' for k, v in sorted(by_type.items()))})")
    print(f"  links: {link_count} ({sum(1 for e in plan for l in e.get('links', []) if l['availability'] == 'accessible')} accessible, "
          f"{sum(1 for e in plan for l in e.get('links', []) if l['availability'] == 'not_accessible')} not accessible, "
          f"{sum(1 for e in plan for l in e.get('links', []) if l['availability'] == 'unverified')} unverified)")
    print(f"  total bytes: {byte_total:,}")
    if conversions:
        print(f"  legacy conversions ({len(conversions)}):")
        for conversion in conversions:
            print(f"    - {conversion}")
    if warnings:
        print(f"  warnings ({len(warnings)}):")
        for warning in warnings:
            print(f"    - {warning}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="validate and plan without writing the bundle")
    arguments = parser.parse_args()

    plan, warnings, conversions = build_plan(arguments.dry_run)
    report(plan, warnings, conversions, arguments.dry_run)
    if not arguments.dry_run:
        write_bundle(plan)
        print(f"bundle written to {BUNDLE_ROOT}")


if __name__ == "__main__":
    main()
