#!/usr/bin/env python3
"""Build the reviewed import CSV from the hand-transcribed ground truth.

Inputs: every JSON file in dataset/project-records/. Output:
output/ause-discovery-projects-metadata-import.csv in the exact AUSE Discovery import schema.
Records missing an abstract or a title are dropped and reported; the
application rejects such rows anyway.

Usage: python3 pipeline/build_reviewed_csv.py [--taxonomy <values.yaml>]
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
COURSE_KEYS = {"sp1": "senior_project_1", "sp2": "senior_project_2"}
FACET_COLUMNS = {
    "category": "categories", "platform": "platforms", "domain": "domains",
    "topic": "topics", "technology": "technologies",
}
SEMESTERS = {"1": "first", "2": "second", "summer": "summer"}


def squish(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# Person names are stored bare: no Mr/Ms honorifics and no academic titles
# (Dr, Doc, Prof, Asst. Prof., A., ...), which vary inconsistently across
# documents and add nothing to search or dedup. Ground-truth records stay
# verbatim; this normalization happens only at CSV build time.
HONORIFIC = re.compile(
    r"^(?:(?:Mrs|Miss|Ms|Mr|Professor|Assistant|Associate|Ajarn|Asst|Assoc"
    r"|Prof|Doctor|Doc|Dr|Aj|A)(?:\.|\b)\s*)+")
DOCTORATE = re.compile(r",?\s*Ph\.?\s*D\.?\s*$", re.IGNORECASE)

# Hand-reviewed canonical forms for people whose names print inconsistently
# across documents. Applied AFTER honorific stripping, keyed by the squished
# lowercase name. Ground-truth records stay verbatim; this map is the single
# place where spelling variants collapse. Rationale for each judgment call is
# recorded in the README ("Person-name canonicalization").
CANONICAL_PEOPLE = {
    # staff (AU Vincent Mary faculty; canonical = most frequent mention,
    # cross-checked against real faculty names)
    "anilkumar kothalil gopalakrishnan": "Anilkumar Kothalil Gopalakrishnan",
    "anilkumar k. gopalakrishnan": "Anilkumar Kothalil Gopalakrishnan",
    "anilkumar kothalil": "Anilkumar Kothalil Gopalakrishnan",
    "anilkumar kothalil gopalakrishna": "Anilkumar Kothalil Gopalakrishnan",
    "anilkumar kothalil gopalkrishnan": "Anilkumar Kothalil Gopalakrishnan",
    "darun": "Darun Kesrarat",
    "phyo min htun": "Phyo Min Tun",
    "thanachai thumthawatworm": "Thanachai Thumthawatworn",
    "benjawan sirsura": "Benjawan Srisura",
    "benjawin srisura": "Benjawan Srisura",
    "chayapol meomeng": "Chayapol Moemeng",
    "chayapol meomong": "Chayapol Moemeng",
    "chayapol momeng": "Chayapol Moemeng",
    "chokdee liopanich": "Chokdee Liophanich",
    "atthipat hirunadisuan": "Athiphat Hirunadisuan",
    "jichun lu": "Jinchun Lu",
    "lu jinchun": "Jinchun Lu",
    "kwankamol knongpong": "Kwankamol Nongpong",
    "mana thanachan": "Mana Tanachan",
    "piyakul tillpart": "Piyakul Tillapart",
    "dobri batovski": "Dobri Atanassov Batovski",
    "dean suparwat charoenvikrom": "Suparwat Charoenvikrom",
    "supawat charoenvikrom": "Suparwat Charoenvikrom",
    "tang tianai": "Tianai Tang",
    # students (verified by shared student_id; display spelling picked by the
    # evidence noted in the README)
    "jarukorn theungjitvilas": "Jarukorn Thuengjitvilas",
    "kwang min kim": "Kwangmin Kim",
    "paranan vipornnitipacha": "Paranan Vitpornnitipacha",
    "sethanant tetanonsakul": "Setthanant Tetanonsakul",
    "tachasit sarasitt": "Taechasit Sarasitt",
    "phonepyaekyawswar": "Phone Pyae Kyaw Swar",
    "phonepyae kyawswar": "Phone Pyae Kyaw Swar",
    "artisd c.": "Artisd Chanyawadee",
    "chawan v.": "Chawan Vattanalap",
    "brighton t. shanji": "Brighton Tapiwa Shanji",
    "chinnawat w.": "Chinnawat Wongpatamajaroen",
    "alexander j. fuller": "Alexander James Fuller",
}


def person_name(name: str) -> str:
    cleaned = HONORIFIC.sub("", DOCTORATE.sub("", squish(name))).strip()
    cleaned = cleaned or squish(name)
    return CANONICAL_PEOPLE.get(cleaned.lower(), cleaned)


def load_taxonomy(path: Path) -> dict[str, set[str]]:
    keys: dict[str, set[str]] = {}
    for match in re.finditer(r"dimension:\s*(\w+),\s*key:\s*([\w_]+)", path.read_text()):
        keys.setdefault(match.group(1), set()).add(match.group(2))
    return keys


def student_json(students: list[dict]) -> list[dict]:
    result = []
    for student in students:
        entry = {"display_name": person_name(student.get("name") or "")}
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
    sources = sorted((root / "dataset" / "project-records").glob("*.json"))
    for source in sources:
        loaded = json.loads(source.read_text())
        # sample.json is keyed by id; batch files are lists of records.
        entries = loaded.values() if isinstance(loaded, dict) else loaded
        for record in entries:
            records[record["id"]] = record

    def clean_aliases(raw_aliases: list, title: str) -> list[str]:
        """Keep each alias once: non-empty, not repeating the title, and not
        repeating an earlier alias, all compared case/space-insensitively
        (the importer rejects rows with duplicate aliases)."""
        cleaned: list[str] = []
        seen = {title.lower()}
        for alias in raw_aliases:
            squished = squish(alias)
            key = squished.lower()
            if squished and key not in seen:
                seen.add(key)
                cleaned.append(squished)
        return cleaned

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
            # The source-file numbers are opaque legacy identifiers from a
            # previous system: semantics unknown, internal use only. They are
            # stored in reference_code (visible to admins, searchable) and
            # hidden from the public UI.
            "reference_code": project_id,
            "abstract": abstract,
            "academic_year": year,
            "semester": semester,
            "program_key": record.get("program") or "computer_science",
            "major_key": "",
            # SP1/SP2 classification from the course pass (notes/sp1-sp2-pass.md);
            # records without a classification stay on the unspecified course.
            "course_key": COURSE_KEYS.get(record.get("course"), "senior_project"),
            "title_aliases": json.dumps(clean_aliases(record.get("aliases", []), title), ensure_ascii=False),
            "students": json.dumps(student_json(record.get("students", [])), ensure_ascii=False),
            "advisors": json.dumps([{"display_name": person_name(record["advisor"])}] if squish(record.get("advisor") or "") else [], ensure_ascii=False),
            "co_advisors": json.dumps([], ensure_ascii=False),
            "committee_members": json.dumps([{"display_name": person_name(name)} for name in record.get("committee", []) if squish(name)], ensure_ascii=False),
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

    output = root / "output" / "ause-discovery-projects-metadata-import.csv"
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
