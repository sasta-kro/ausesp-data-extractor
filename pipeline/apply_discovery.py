#!/usr/bin/env python3
"""Aggregate discovery results and fold them into the canonical batches.

Reads dataset/taxonomy-research/research-*.json and does two things:

1. Writes output/discovery-report.md: every suggested taxonomy key that is
   not already in values.yaml, ranked by how many projects genuinely use it
   ("used" evidence), with "cited"-only counts shown separately.
2. Merges each discovery record into the existing dataset/project-records record
   for the same id: fills a missing abstract, replaces classification arrays,
   and fills null metadata fields. Never overwrites non-null existing values
   except classification, which the discovery pass re-examined in full.

Usage: python3 pipeline/apply_discovery.py [--taxonomy <values.yaml>] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

DIMENSIONS = ("category", "platform", "domain", "topic", "technology")


def load_taxonomy(path: Path) -> dict[str, set[str]]:
    keys: dict[str, set[str]] = {}
    for match in re.finditer(r"dimension:\s*(\w+),\s*key:\s*([\w_]+)", path.read_text()):
        keys.setdefault(match.group(1), set()).add(match.group(2))
    return keys


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--taxonomy", type=Path,
                        default=Path("../../../ause-discover/config/taxonomy/values.yaml"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    taxonomy = load_taxonomy(args.taxonomy) if args.taxonomy.exists() else {}

    # ---- aggregate suggestions -------------------------------------------
    stats: dict[str, dict[str, dict]] = {d: defaultdict(lambda: {"label": "", "used": [], "cited": []}) for d in DIMENSIONS}
    records = []
    for chunk in sorted((root / "dataset" / "taxonomy-research").glob("research-*.json")):
        for record in json.loads(chunk.read_text()):
            records.append(record)
            for dimension, suggestions in (record.get("discoveries") or {}).items():
                for suggestion in suggestions or []:
                    entry = stats[dimension][suggestion["key"]]
                    entry["label"] = suggestion.get("label") or entry["label"]
                    bucket = "cited" if suggestion.get("status") == "cited" else "used"
                    entry[bucket].append(record["id"])

    lines = ["# Taxonomy discovery report", "",
             f"From {len(records)} re-read projects. 'Used' means the project was",
             "built with or on it. 'Cited' means it only appeared in related",
             "work. Keys already present in values.yaml are omitted.", ""]
    for dimension in DIMENSIONS:
        fresh = {k: v for k, v in stats[dimension].items() if k not in taxonomy.get(dimension, set())}
        if not fresh:
            continue
        lines.append(f"## {dimension}")
        lines.append("")
        for key, entry in sorted(fresh.items(), key=lambda item: -len(item[1]["used"])):
            used = ", ".join(sorted(entry["used"]))
            cited_note = f" (+{len(entry['cited'])} cited only)" if entry["cited"] else ""
            lines.append(f"- {key} ({entry['label']}): {len(entry['used'])} used{cited_note}. Projects: {used}")
        lines.append("")

    report = root / "output" / "discovery-report.md"
    if not args.dry_run:
        report.parent.mkdir(exist_ok=True)
        report.write_text("\n".join(lines))
    print(f"{len(records)} discovery records aggregated; report has {len(lines)} lines -> {report}")

    if args.dry_run:
        return 0

    # ---- merge into canonical batches ------------------------------------
    batch_dir = root / "dataset" / "project-records"
    canonical: dict[str, tuple[Path, dict]] = {}
    for batch in sorted(batch_dir.glob("*.json")):
        data = json.loads(batch.read_text())
        entries = data.values() if isinstance(data, dict) else data
        for record in entries:
            canonical[str(record["id"])] = (batch, record)

    changes = 0
    for record in records:
        pid = str(record["id"])
        if pid not in canonical:
            print(f"  new id {pid} not in canonical batches, skipped")
            continue
        batch, existing = canonical[pid]
        changed = False
        if not existing.get("abstract") and record.get("abstract"):
            existing["abstract"] = record["abstract"]
            changed = True
            print(f"  {pid}: abstract filled ({record.get('abstract_source')})")
        for field in ("course_code", "program", "semester", "academic_year", "advisor"):
            if existing.get(field) in (None, "") and record.get(field) not in (None, ""):
                existing[field] = record[field]
                changed = True
                print(f"  {pid}: {field} filled")
        if record.get("classification") and record["classification"] != existing.get("classification"):
            existing["classification"] = record["classification"]
            changed = True
        if changed:
            changes += 1

    if changes:
        pass

    # ---- complete truncated person names ---------------------------------
    # The importer keys people by normalized display name, so a bare
    # "Paitoon" next to "Paitoon Porntrakoon" would create a duplicate
    # person. Complete any name that is a strict word-boundary prefix of
    # exactly one longer name used elsewhere. Ambiguous prefixes are
    # reported, not touched.
    def normalize(name: str) -> str:
        return re.sub(r"\s+", " ", name.strip().lower())

    def names_of(record: dict) -> list[str]:
        out = [record.get("advisor") or ""]
        out += [s.get("name") or "" for s in record.get("students", [])]
        out += record.get("committee") or []
        return [n for n in out if n]

    every = [names_of(record) for _, record in canonical.values()]
    long_forms: dict[str, str] = {}
    for group in every:
        for name in group:
            long_forms.setdefault(normalize(name), name)
    completions: dict[str, str] = {}
    ambiguous = set()
    for short in list(long_forms):
        candidates = [long_ for long_ in long_forms if long_ != short and long_.startswith(short + " ")]
        if len(candidates) == 1:
            completions[short] = long_forms[candidates[0]]
        elif len(candidates) > 1:
            ambiguous.add(short)
    fixed_names = 0
    for batch, record in canonical.values():
        def complete(name: str) -> str:
            nonlocal fixed_names
            replacement = completions.get(normalize(name))
            if replacement and replacement != name:
                fixed_names += 1
                return replacement
            return name
        if record.get("advisor"):
            record["advisor"] = complete(record["advisor"])
        for student in record.get("students", []):
            if student.get("name"):
                student["name"] = complete(student["name"])
        record["committee"] = [complete(n) for n in record.get("committee") or []]
    if completions:
        print("name completions applied:")
        for short, long_ in sorted(completions.items()):
            print(f"  {short!r} -> {long_!r}")
    if ambiguous:
        print("ambiguous name prefixes left alone:", sorted(ambiguous))
    print(f"truncated names completed: {fixed_names}")

    dirty = {path for path, _ in canonical.values()}
    for batch in dirty:
        data = json.loads(batch.read_text())
        if isinstance(data, dict):
            for pid, (_, record) in canonical.items():
                if str(record.get("id")) == pid:
                    data[pid] = record
        else:
            data = [canonical[str(r["id"])][1] for r in data if str(r["id"]) in canonical]
        batch.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"merged changes into {changes} records across {len(dirty)} batch files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
