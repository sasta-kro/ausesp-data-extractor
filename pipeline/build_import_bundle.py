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
import sys
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
FILE_ORDER = {"report": 0, "slides": 1, "poster": 2}

# Staged beside the core files but never bundle content: "media" and
# "doc-convert" are extraction byproducts, "external" holds supplementary
# material submitted with the report (published conference papers, award
# certificates, feedback reports), which is not a classified deliverable.
SKIP_DIRS = {"media", "doc-convert", "external"}

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


def collect_files(identifier: str) -> tuple[list[dict], list[str]]:
    """Plan the file entries for one project. Returns (entries, warnings)."""
    source_dir = SOURCES_DIR / identifier
    if not source_dir.is_dir():
        sys.exit(f"member sp-{identifier} has no staged source directory: {source_dir}")

    entries: list[dict] = []
    warnings: list[str] = []
    for item in sorted(source_dir.iterdir()):
        if item.name in SKIP_DIRS:
            continue
        if not item.is_file():
            warnings.append(f"sp-{identifier}: unexpected non-file entry '{item.name}'")
            continue
        rule = FILE_RULES.get(item.name)
        if rule is None:
            warnings.append(f"sp-{identifier}: skipped '{item.name}', no rule maps it to a supported artifact type")
            continue
        artifact_type, display_name = rule
        byte_count = item.stat().st_size
        if byte_count > FILE_MAX_BYTES:
            warnings.append(f"sp-{identifier}: skipped '{item.name}', {byte_count} bytes exceeds the {FILE_MAX_BYTES} byte limit")
            continue
        extension = item.suffix.lstrip(".").lower()
        with open(item, "rb") as source:
            prefix = source.read(8)
        if not prefix.startswith(MAGIC[extension]):
            warnings.append(f"sp-{identifier}: skipped '{item.name}', content does not match its extension")
            continue
        entries.append({
            "artifact_type": artifact_type,
            "display_name": display_name,
            "original_filename": item.name,
            "file_path": f"projects/sp-{identifier}/{item.name}",
            "_source": item,
            "_bytes": byte_count,
        })
    entries.sort(key=lambda e: (FILE_ORDER[e["artifact_type"]], e["original_filename"]))
    return entries, warnings


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


def build_plan() -> tuple[list[dict], list[str]]:
    members = read_members()
    with open(EVIDENCE_MANIFEST, encoding="utf-8") as handle:
        evidence = json.load(handle)

    plan: list[dict] = []
    warnings: list[str] = []
    for key in members:
        identifier = key.split("-", 1)[1]
        record = evidence.get(identifier) or {}
        files, file_warnings = collect_files(identifier)
        logo, logo_warnings = plan_logo(identifier, record)
        links, link_warnings = plan_links(identifier, record)
        warnings.extend(file_warnings + logo_warnings + link_warnings)
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
    return plan, warnings


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


def report(plan: list[dict], warnings: list[str], dry_run: bool) -> None:
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
    if warnings:
        print(f"  warnings ({len(warnings)}):")
        for warning in warnings:
            print(f"    - {warning}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="validate and plan without writing the bundle")
    arguments = parser.parse_args()

    plan, warnings = build_plan()
    report(plan, warnings, arguments.dry_run)
    if not arguments.dry_run:
        write_bundle(plan)
        print(f"bundle written to {BUNDLE_ROOT}")


if __name__ == "__main__":
    main()
