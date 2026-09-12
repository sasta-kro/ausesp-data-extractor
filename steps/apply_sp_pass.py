#!/usr/bin/env python3
"""Apply the SP1/SP2 pass: classify records, cull duplicate pairs, fold in
the slide-only transcriptions, rebuild the CSV and logo manifest.

Every mutation is printed as it happens. Run steps/apply_course_classification.py
first (produces .tmp-enrichment/course-final.json).

Usage: python3 steps/apply_sp_pass.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CULLED = {
    # pair -> (keep, delete, reason)
    ("1703", "1711"): "identical documents and records; kept the first filing",
    ("1934", "2003"): "same project; kept 1934 whose title was verified against its cover",
    ("2004", "1906"): "same project; kept 2004's readable PDF over the broken legacy .doc",
    ("1920", "1827"): "same project; kept the later, more complete record",
    ("2579", "26009"): "identical records; kept the first filing",
    ("2113", "2145"): "identical records; kept the first filing",
}

# ids attachable from the same students' other corpus projects; name spelling
# normalized to the known corpus entry so builder matching stays consistent
ID_ATTACH = {
    ("2021", "SOKVATHARA LIN (LEX)"): ("Sokvathara Lin", "6018002", "1646-era spelling, id from project 1950"),
    ("2021", "MENH KEO (XELL)"): ("Menh Keo", "6038302", "id from project 1646"),
    ("2032", "Tanakorn Navanugraha"): ("Tanakorn Navanugraha", "6025106", "id from project 2017"),
    ("2032", "Rajbir Singh"): ("Rajbir Singh", "6015184", "id from project 2017"),
}

# kept-side overrides after combining evidence across a culled twin
COURSE_OVERRIDES = {
    "2004": ("sp2", "duplicate-explicit",
             'culled twin 1906 printed "IT 4292 Senior Project 2"; 2004 itself prints mixed codes'),
}

COURSE_KEYS = {"sp1": "senior_project_1", "sp2": "senior_project_2"}


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    batches = root / "ground-truth" / "batches"
    course = json.loads((root / ".tmp-enrichment" / "course-final.json").read_text())
    delete_ids = {d for _, d in CULLED}

    # 1. write course fields into every kept record, culling as we go
    touched = {}
    for source in sorted(batches.glob("*.json")):
        data = json.loads(source.read_text())
        is_map = isinstance(data, dict)
        entries = list(data.values()) if is_map else data
        kept = []
        for record in entries:
            pid = record["id"]
            if pid in delete_ids:
                print(f"culled {pid}")
                continue
            if pid in COURSE_OVERRIDES:
                value, basis, evidence = COURSE_OVERRIDES[pid]
            else:
                info = course.get(pid, {})
                value = info.get("course", "unspecified")
                basis = info.get("basis", "none")
                evidence = info.get("evidence")
            record["course"] = value
            record["course_basis"] = basis
            if evidence:
                record["course_evidence"] = evidence
            kept.append(record)
        source.write_text(json.dumps(data.__class__(kept) if not is_map else
                                     {r["id"]: r for r in kept}, ensure_ascii=False, indent=1))
        touched[source.name] = len(kept)

    # 2. fold in the slide-only transcriptions
    slideonly = []
    for pid in ("2021", "2031", "2032"):
        raw = json.loads((root / ".tmp-enrichment" / "slideonly" / f"{pid}.json").read_text())
        students = []
        for s in raw["students"]:
            override = ID_ATTACH.get((pid, s["name"]))
            if override:
                students.append({"name": override[0], "student_id": override[1],
                                 "id_source": override[2]})
            else:
                students.append({"name": s["name"], "student_id": s.get("student_id")})
        record = {
            "id": pid,
            "canonical_title": raw["canonical_title"],
            "aliases": raw.get("aliases", []),
            "phase": raw["phase"],
            "course_code": raw.get("course_code"),
            "course": raw.get("course_explicit") or "unspecified",
            "course_basis": "explicit" if raw.get("course_explicit") else "none",
            "program": raw["program"],
            "semester": str(raw["semester"]),
            "academic_year": raw["academic_year"],
            "students": students,
            "advisor": raw.get("advisor"),
            "committee": raw.get("committee", []),
            "abstract": raw["abstract"],
            "reported_keywords": [],
            "classification": raw["classification"],
            "note": ("slide deck only, no report document exists; " +
                     (raw.get("note") or "")),
        }
        attach_notes = [f"{s['name']}: id attached from {s['id_source']}"
                        for s in students if "id_source" in s]
        if attach_notes:
            record["note"] += "; " + "; ".join(attach_notes)
        if raw.get("course_evidence"):
            record["course_evidence"] = raw["course_evidence"]
        slideonly.append(record)
        print(f"added {pid} {record['canonical_title']!r} course={record['course']}")
    (batches / "batch-slideonly.json").write_text(
        json.dumps(slideonly, ensure_ascii=False, indent=1))

    # 3. drop culled enrichment records, logos, and manifest entries
    enr_root = root / "output" / "enrichment"
    manifest = json.loads((enr_root / "manifest.json").read_text())
    for pid in delete_ids:
        manifest.pop(pid, None)
        (enr_root / "records" / f"{pid}.json").unlink(missing_ok=True)
        (enr_root / "logos" / f"{pid}.png").unlink(missing_ok=True)
        print(f"enrichment cleaned for {pid}")
    (enr_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))

    # 4. rebuild the CSV
    result = subprocess.run(
        [sys.executable, "steps/build_reviewed_csv.py", "--taxonomy",
         str(root / ".." / ".." / "config" / "taxonomy" / "values.yaml")],
        cwd=root, capture_output=True, text=True)
    print(result.stdout.strip())
    if result.returncode != 0:
        print(result.stderr.strip())
        return 1

    # 5. logo manifest filtered by actual CSV membership (no hardcoded ids)
    import csv
    keys = {row["import_key"] for row in csv.DictReader(
        (root / "output" / "reviewed-import.csv").open(encoding="utf-8"))}
    logo_projects = [{"project_import_key": key,
                      "logo": {"file_path": manifest[key[len("sp-"):]]["logo"]["output"]},
                      "files": []}
                     for key in sorted(keys)
                     if key[len("sp-"):] in manifest
                     and manifest[key[len("sp-"):]]["logo"].get("output")]
    (enr_root / "logo-manifest.json").write_text(json.dumps(
        {"version": 1, "projects": logo_projects}, ensure_ascii=False, indent=1))
    print(f"logo manifest: {len(logo_projects)} entries, filtered to CSV membership")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
