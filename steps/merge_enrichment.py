#!/usr/bin/env python3
"""Validate enrichment records and merge them into the final manifest.

Reads output/enrichment/records/*.json (one per project), text-grep.json, and
liveness.json, validates every record against the schema and the staged file
universe, merges text and visual link sightings per project (deduplicated by
normalized URL, first text sighting marked primary), attaches liveness state,
and writes output/enrichment/manifest.json plus a summary at
output/enrichment/summary.md. Any validation failure is reported and fails
the run.

Usage: python3 steps/merge_enrichment.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

REASONS = {"au_crest_only", "no_logo_found", "no_viewable_source"}
NORMALIZE_STRIP = re.compile(r"\.git$", re.IGNORECASE)


def normalize(url: str) -> str:
    url = url.strip().rstrip("/")
    url = NORMALIZE_STRIP.sub("", url)
    return url.lower()


def validate_record(project_id: str, record: dict, errors: list[str]) -> None:
    def fail(message: str) -> None:
        errors.append(f"{project_id}: {message}")

    if record.get("id") != project_id:
        fail("id mismatch")
    logo = record.get("logo")
    if not isinstance(logo, dict):
        fail("missing logo object")
        return
    has_logo = logo.get("has_logo")
    if has_logo is True:
        if logo.get("reason") is not None:
            fail("reason must be null when has_logo is true")
        if logo.get("extracted") is True:
            if not logo.get("output"):
                fail("extracted true requires output")
            if logo.get("verified") is not True:
                fail("extracted true requires verified true")
            source = logo.get("source")
            if not isinstance(source, dict):
                fail("extracted true requires a source object")
            elif "pdf" in source:
                box = source.get("box")
                if not (isinstance(box, list) and len(box) == 4
                        and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in box)
                        and box[0] < box[2] and box[1] < box[3]):
                    fail("bad crop box")
                if not isinstance(source.get("page"), int):
                    fail("bad crop page")
    elif has_logo is False:
        if logo.get("reason") not in REASONS:
            fail(f"has_logo false requires a valid reason, got {logo.get('reason')!r}")
    else:
        fail("has_logo must be boolean")
    for link in record.get("links", []):
        if not isinstance(link.get("url"), str) or not link["url"].startswith("https://"):
            fail(f"bad link url {link.get('url')!r}")
        if not isinstance(link.get("found_in"), list) or not link["found_in"]:
            fail("link requires found_in")


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    base = root / ".tmp-enrichment"
    prepared = json.loads((base / "prepared-manifest.json").read_text())
    records_dir = root / "output" / "enrichment" / "records"
    logos_dir = root / "output" / "enrichment" / "logos"
    grep_file = root / "output" / "enrichment" / "text-grep.json"
    liveness_file = root / "output" / "enrichment" / "liveness.json"

    errors: list[str] = []
    records: dict[str, dict] = {}
    for record_file in sorted(records_dir.glob("*.json")):
        project_id = record_file.stem
        try:
            record = json.loads(record_file.read_text())
        except json.JSONDecodeError as exc:
            errors.append(f"{project_id}: invalid json ({exc})")
            continue
        validate_record(project_id, record, errors)
        records[project_id] = record

    expected = set(prepared)
    missing = expected - set(records)
    extra = set(records) - expected
    for project_id in sorted(missing):
        errors.append(f"{project_id}: no record written")
    for project_id in sorted(extra):
        errors.append(f"{project_id}: record for unknown project")

    for project_id, record in records.items():
        output = record["logo"].get("output")
        if record["logo"].get("extracted") and output:
            path = logos_dir / Path(output).name
            if not path.exists():
                errors.append(f"{project_id}: logo output {path.name} missing on disk")

    text_grep = json.loads(grep_file.read_text()) if grep_file.exists() else []
    liveness = {entry["url"]: entry for entry in
                (json.loads(liveness_file.read_text()) if liveness_file.exists() else [])}
    kinds_file = root / "output" / "enrichment" / "link-kinds.json"
    kinds = json.loads(kinds_file.read_text()) if kinds_file.exists() else {}

    if errors:
        print(f"VALIDATION FAILED ({len(errors)} problems):")
        for error in errors:
            print(f"  - {error}")
        return 1

    manifest: dict[str, dict] = {}
    for project_id in sorted(records):
        record = records[project_id]
        merged: dict[str, dict] = {}
        for sighting in text_grep:
            if sighting.get("id") != project_id or not sighting.get("url"):
                continue
            url = sighting["url"]
            kind = kinds.get(url, {}).get("kind")
            if kind == "dropped":
                continue
            entry = merged.setdefault(url, {
                "url": url, "normalized": normalize(url), "found_in": [], "primary": False,
                "kind": kind or "third_party_reference",
                "liveness": liveness.get(url, {"status": "unchecked"})})
            entry["found_in"].append({"file": sighting["file"], "page": sighting.get("page"),
                                      "method": "text"})
        for link in record.get("links", []):
            url = link["url"].rstrip("/")
            entry = merged.setdefault(url, {
                "url": url, "normalized": normalize(url), "found_in": [], "primary": False,
                "kind": kinds.get(url, {}).get("kind", "project_repo"),
                "liveness": liveness.get(url, {"status": "unchecked"})})
            entry["found_in"].extend(link["found_in"])
        ordered = sorted(merged.values(),
                         key=lambda e: (0 if e["kind"] == "project_repo" else 1,
                                        0 if any(f["method"] == "text" for f in e["found_in"]) else 1,
                                        e["url"]))
        if ordered:
            ordered[0]["primary"] = True
        manifest[project_id] = {"logo": record["logo"], "links": ordered}

    output = root / "output" / "enrichment" / "manifest.json"
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))

    logo_counts = Counter(r["logo"].get("reason") or ("extracted" if r["logo"].get("extracted")
                                                      else "found_not_extracted")
                          for r in manifest.values())
    link_projects = sum(1 for r in manifest.values() if r["links"])
    link_total = sum(len(r["links"]) for r in manifest.values())
    repo_projects = sum(1 for r in manifest.values()
                        if any(l["kind"] == "project_repo" for l in r["links"]))
    statuses = Counter(l["liveness"].get("status", "unchecked")
                       for r in manifest.values() for l in r["links"])

    summary = root / "output" / "enrichment" / "summary.md"
    summary.write_text(
        "# Enrichment pass summary\n\n"
        f"- projects: {len(manifest)}\n"
        f"- logos extracted: {logo_counts.get('extracted', 0)}\n"
        f"- logos au_crest_only: {logo_counts.get('au_crest_only', 0)}\n"
        f"- logos no_logo_found: {logo_counts.get('no_logo_found', 0)}\n"
        f"- logos no_viewable_source: {logo_counts.get('no_viewable_source', 0)}\n"
        f"- projects with links: {link_projects}, total distinct links: {link_total}\n"
        f"- projects with their own project_repo link: {repo_projects}\n"
        f"- liveness: {dict(statuses)}\n")
    print(f"manifest: {len(manifest)} projects, logos extracted {logo_counts.get('extracted', 0)}, "
          f"links {link_total} across {link_projects} projects, liveness {dict(statuses)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
