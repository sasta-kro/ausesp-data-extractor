#!/usr/bin/env python3
"""Build the reviewed import CSV from agent-read ground truth.

Inputs: ground-truth/sample.json (first reviewed batch) plus every JSON file
in ground-truth/batches/. Output: output/reviewed-import.csv in the exact
AUSE Discovery import schema. Records missing an abstract or a title are
dropped and reported; the application rejects such rows anyway.

Usage: python3 steps/build_reviewed_csv.py [--taxonomy <values.yaml>]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

CSV_HEADERS = [
    "import_key", "title", "reference_code", "abstract", "academic_year",
    "semester", "program_key", "major_key", "course_key", "title_aliases",
    "students", "advisors", "co_advisors", "committee_members",
    "categories", "platforms", "domains", "topics", "technologies",
]
FACET_COLUMNS = {
    "category": "categories", "platform": "platforms", "domain": "domains",
    "topic": "topics", "technology": "technologies",
}
SEMESTERS = {"1": "first", "2": "second", "summer": "summer"}


def squish(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def load_taxonomy(path: Path) -> dict[str, set[str]]:
    keys: dict[str, set[str]] = {}
    for match in re.finditer(r"dimension:\s*(\w+),\s*key:\s*([\w_]+)", path.read_text()):
        keys.setdefault(match.group(1), set()).add(match.group(2))
    return keys


def student_json(students: list[dict]) -> list[dict]:
    result = []
    for student in students:
        entry = {"display_name": squish(student.get("name") or "")}
        if not entry["display_name"]:
            continue
        student_id = student.get("student_id")
        if student_id and re.fullmatch(r"\d{7}", str(student_id)):
            entry["student_id"] = str(student_id)
        result.append(entry)
    return result


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--taxonomy", type=Path,
                        default=Path("../../../ause-discover/config/taxonomy/values.yaml"))
    args = parser.parse_args()

    records: dict[str, dict] = {}
    sources = sorted((root / "ground-truth" / "batches").glob("*.json"))
    for source in sources:
        loaded = json.loads(source.read_text())
        # sample.json is keyed by id; batch files are lists of records.
        entries = loaded.values() if isinstance(loaded, dict) else loaded
        for record in entries:
            records[record["id"]] = record

    taxonomy = load_taxonomy(args.taxonomy) if args.taxonomy.exists() else {}
    invalid_keys: list[tuple[str, str, str]] = []
    rows: list[dict] = []
    dropped: list[str] = []
    for project_id in sorted(records):
        record = records[project_id]
        title = squish(record.get("canonical_title") or "")
        abstract = squish(record.get("abstract") or "")
        semester = SEMESTERS.get(str(record.get("semester") or ""), "")
        year = record.get("academic_year")
        if not title or not abstract or not semester or not year:
            dropped.append(f"{project_id}: missing " + ", ".join(
                name for name, value in [("title", title), ("abstract", abstract),
                                         ("semester", semester), ("year", year)] if not value))
            continue
        row = {
            "import_key": f"sp-{project_id}",
            "title": title,
            "reference_code": project_id,
            "abstract": abstract,
            "academic_year": year,
            "semester": semester,
            "program_key": record.get("program") or "computer_science",
            "major_key": "",
            "course_key": "senior_project",
            "title_aliases": json.dumps([squish(alias) for alias in record.get("aliases", []) if squish(alias)], ensure_ascii=False),
            "students": json.dumps(student_json(record.get("students", [])), ensure_ascii=False),
            "advisors": json.dumps([{"display_name": squish(record["advisor"])}] if squish(record.get("advisor") or "") else [], ensure_ascii=False),
            "co_advisors": json.dumps([], ensure_ascii=False),
            "committee_members": json.dumps([{"display_name": squish(name)} for name in record.get("committee", []) if squish(name)], ensure_ascii=False),
        }
        classification = record.get("classification", {})
        for facet, column in FACET_COLUMNS.items():
            keys = classification.get(facet) or []
            if taxonomy and facet in taxonomy:
                for key in keys:
                    if key not in taxonomy[facet]:
                        invalid_keys.append((project_id, facet, key))
            row[column] = json.dumps(keys, ensure_ascii=False)
        rows.append(row)

    output = root / "output" / "reviewed-import.csv"
    output.parent.mkdir(exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {len(rows)} rows to {output}")
    if dropped:
        print("dropped:")
        for line in dropped:
            print(f"  - {line}")
    if invalid_keys:
        print("invalid taxonomy keys:")
        for project_id, facet, key in invalid_keys:
            print(f"  - {project_id} {facet}:{key}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
