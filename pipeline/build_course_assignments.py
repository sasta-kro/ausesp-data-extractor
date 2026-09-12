#!/usr/bin/env python3
"""Build cover-read assignment prompts for the SP1/SP2 classification pass.

One prompt per group under _workspace/prompts/course-group-NN.md. Each
assigned project has a rendered cover at _workspace/renders/<id>/report-p1.png.
Agents read the cover, capture the course statement verbatim, and write one
JSON per project to _workspace/sp-course-code-tracking/<id>.json. Word-doc projects are excluded
(covered mechanically through textutil).

Usage: python3 pipeline/build_course_assignments.py [--group-size 17]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

TEMPLATE = """You are classifying university senior-project documents by course. You own the projects listed below, in order. Work one at a time.

# ABSOLUTE TOOL RULES

Your ONLY tools are Read (on the exact image paths below) and Write (one JSON file per project at its exact path). No shell, no bash, no network, nothing else. If an image fails to open, write the JSON with explicit null and a note, and move on.

# TASK, per project

1. Read _workspace/renders/{pid}/report-p1.png (the report cover). If the cover looks like it continues or the course line might sit on the approval page instead, also read report-p2.png and report-p3.png (they exist for every project).
2. Find every line that states the senior-project course. Examples of what counts: "Senior Project 1 Report", "Senior Project 2", "SENIOR PROJECT I FINAL REPORT", "ITX3010 Senior Project 2 (2/2025)", "CS 3200 Senior Project 1".
3. Record:
   - explicit: "sp1" if the document literally says Senior Project 1 / I / First (any casing, digit or roman numeral); "sp2" if it literally says Senior Project 2 / II / Second; null if it only names a course code or nothing.
   - evidence: the exact words as printed (verbatim, keep casing), or null.
   - course_code_printed: the course code as printed (like "IT 4291", "CSX3011", "IT4292"), or null if none appears.
   - source_page: which cover image the evidence came from (1, 2, or 3).
4. NEVER guess or complete from memory. Only what is printed. Roman numerals I and II count as explicit; the word "Proposal" or "Final" alone does NOT (a final report exists in both courses).

# OUTPUT (exact schema, one file per project)

Write to _workspace/sp-course-code-tracking/{pid}.json:
{{
  "id": "{pid}",
  "explicit": "sp1" | "sp2" | null,
  "evidence": "verbatim text or null",
  "course_code_printed": "verbatim code or null",
  "source_page": 1 | 2 | 3 | null,
  "note": null | "short note if something was unreadable"
}}

# YOUR PROJECTS

{blocks}

# FINAL REPORT

One line per project: id, explicit or dash, printed code. Nothing else.
"""


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    base = root / "_workspace"
    render = json.loads((base / "intermediate-data" / "renders-manifest.json").read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group-size", type=int, default=17)
    args = parser.parse_args()

    prompts = base / "assignment-prompts"
    prompts.mkdir(exist_ok=True)
    for old in prompts.glob("course-group-*.md"):
        old.unlink()

    ids = sorted(pid for pid, r in render.items()
                 if any(f.startswith("report-p") for f in r.get("pages", {}).get("report", [])))
    out_dir = root / "_workspace" / "sp-course-code-tracking"
    out_dir.mkdir(exist_ok=True)

    groups = [ids[i:i + args.group_size] for i in range(0, len(ids), args.group_size)]
    for index, group in enumerate(groups, start=1):
        blocks = "\n".join(f"- {pid} -> write _workspace/sp-course-code-tracking/{pid}.json" for pid in group)
        (prompts / f"course-group-{index:02d}.md").write_text(
            TEMPLATE.format(pid="<ID>", blocks=blocks))
    print(f"{len(ids)} cover-readable projects in {len(groups)} groups of <= {args.group_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
