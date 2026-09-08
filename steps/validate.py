#!/usr/bin/env python3
"""Validate extracted metadata against ground truth.

Two references:
  1. The corpus analysis workbook's Projects sheet (all thinned projects):
     canonical title, student IDs, advisor, academic period.
  2. The reviewed ground-truth sample (tools/sp-import/ground-truth/sample.json):
     everything above plus classification facets, built by independent
     document reading rather than the extractor.

Usage:
  .venv/bin/python validate.py --metadata output/metadata \
      --corpus /tmp/corpus_analysis.json --sample ground-truth/sample.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SEMESTER_NAMES = {"1": "first", "2": "second", "summer": "summer"}


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def load_corpus(path: Path) -> dict[str, dict]:
    rows = json.loads(path.read_text())["Projects"]
    header = rows[0]
    index = {name: i for i, name in enumerate(header)}
    corpus = {}
    for row in rows[1:]:
        entry = {}
        for column in ("Project ID", "Canonical Title", "Academic Year", "Student IDs Candidate", "Advisor Candidate"):
            value = row[index[column]] if index[column] < len(row) else ""
            entry[column] = value.strip() if isinstance(value, str) else ""
        corpus[entry["Project ID"]] = {
            "title": entry["Canonical Title"],
            "period": entry["Academic Year"],
            "student_ids": [part.strip() for part in re.split(r"[;,\s]+", entry["Student IDs Candidate"]) if part.strip().isdigit()],
            "advisor": entry["Advisor Candidate"],
        }
    return corpus


def compare(meta: dict, reference: dict) -> list[str]:
    issues = []
    if norm(meta.get("canonical_title") or "") != norm(reference["title"]):
        aliases = [norm(alias) for alias in meta.get("aliases", [])]
        if norm(reference["title"]) not in aliases:
            issues.append(f"title: extracted {meta.get('canonical_title')!r} vs reference {reference['title']!r}")
    extracted_ids = {student["student_id"] for student in meta.get("students", [])}
    reference_ids = set(reference["student_ids"])
    if extracted_ids != reference_ids:
        issues.append(f"students: extracted {sorted(extracted_ids)} vs reference {sorted(reference_ids)}")
    reference_advisor = norm(reference["advisor"])
    extracted_advisor = norm(meta.get("advisor") or "")
    if reference_advisor and extracted_advisor and reference_advisor not in extracted_advisor and extracted_advisor not in reference_advisor:
        issues.append(f"advisor: extracted {meta.get('advisor')!r} vs reference {reference['advisor']!r}")
    if reference.get("period"):
        expected = f"{SEMESTER_NAMES[reference['period'].split('/')[0]]} {reference['period'].split('/')[1]}"
        actual = f"{meta.get('semester')} {meta.get('academic_year')}"
        if actual != expected:
            issues.append(f"period: extracted {actual} vs reference {expected}")
    return issues


def compare_classification(meta: dict, reference: dict) -> list[str]:
    issues = []
    extracted = meta.get("classification", {})
    for facet, expected_keys in reference.items():
        actual_keys = set(extracted.get(facet, []))
        missing = set(expected_keys) - actual_keys
        extra = actual_keys - set(expected_keys)
        if missing:
            issues.append(f"{facet}: missing {sorted(missing)}")
        if extra:
            issues.append(f"{facet}: spurious {sorted(extra)}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--sample", type=Path, required=True)
    args = parser.parse_args()

    corpus = load_corpus(args.corpus)
    sample = json.loads(args.sample.read_text())
    for reference in sample.values():
        students = reference.pop("students", {})
        reference.setdefault("student_ids", list(students))

    corpus_issues = 0
    print("== Corpus workbook comparison (all projects)")
    for project_id, reference in sorted(corpus.items()):
        meta_path = args.metadata / f"{project_id}.json"
        if not meta_path.exists():
            print(f"- {project_id}: no extracted metadata")
            corpus_issues += 1
            continue
        meta = json.loads(meta_path.read_text())
        for issue in compare(meta, reference):
            print(f"- {project_id}: {issue}")
            corpus_issues += 1
    checked = len(corpus)
    print(f"-- {checked} projects compared, {corpus_issues} issue lines")

    print()
    print("== Ground-truth sample comparison (people plus classification)")
    sample_issues = 0
    for project_id, reference in sorted(sample.items()):
        meta = json.loads((args.metadata / f"{project_id}.json").read_text())
        issues = compare(meta, reference)
        issues += compare_classification(meta, reference.get("classification", {}))
        if issues:
            for issue in issues:
                print(f"- {project_id}: {issue}")
            sample_issues += len(issues)
    print(f"-- {len(sample)} projects compared, {sample_issues} issue lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
