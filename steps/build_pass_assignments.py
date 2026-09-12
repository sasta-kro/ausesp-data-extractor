#!/usr/bin/env python3
"""Build agent assignment prompt files for the enrichment pass.

Reads _workspace/renders-manifest.json, skips the pilot and no-source
projects (records for the latter are written mechanically), chunks the rest
into groups, and writes one complete prompt per group under
_workspace/prompts/group-NN.md. The shared rules block matches the pilot
prompt so behavior stays identical across waves.

Usage: python3 steps/build_pass_assignments.py [--group-size 6]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

PILOT_IDS = {"2207", "26010", "1908"}

RULES = """You are extracting enrichment data (project logos and repository links) for a university senior-project archive. You own the projects listed below. Work ONE project completely, then move to the next, in the order given.

# ABSOLUTE TOOL RULES (violating these breaks the workflow)

1. Your ONLY allowed tools:
   - Read: on the exact image/PNG paths listed below, on output PNGs you produced, and on your JSON records to verify them.
   - Bash: ONLY the exact `crop_logo.py` command template shown below, with values filled in. Nothing else. No other commands, ever.
   - Write: exactly one JSON record per project at its exact path given below.
2. NEVER parse PDFs yourself, never run python yourself, never install anything, never convert or extract anything with your own shell commands. The preparation and cropping tooling already exists. Your job is to LOOK at rendered images and DECIDE.
3. NEVER use network tools. Do not fetch, curl, or ping any URL you see. Recording a URL as text is all you do.
4. If an image fails to open or is completely blank: mention it in that project's record note and move on. Do not try to fix or re-render anything.
5. One crop attempt failing is normal: the script prints FAIL with a reason. Adjust the box and retry (max 3 attempts). If it still fails, set extracted false with a note and move on.

# WHAT COUNTS AS A LOGO

A logo IS: a designed emblem, icon, stylized/lettered wordmark, mascot, or team/product brand mark that belongs to THIS project (the product name, team brand, or app identity), typically on the report cover, title slide, or slide headers.

A logo is NOT:
- the Assumption University crest/seal or any university/department/ABAC identity
- plain text titles written in a standard font (Times, Calibri, plain bold text)
- screenshots of apps, websites, code, terminals, or databases
- diagrams, charts, ER diagrams, architecture figures
- photos of people, buildings, campus
- third-party brand logos (GitHub, Android, React, AWS and similar)
When the same logo appears in several places, use the largest, cleanest, fully visible occurrence.

# COMMAND TEMPLATE (run from this exact directory)

cd /Users/saiaikeshwetunaung/Developer/WebApps/ause-discover/tools/ausesp-data-extractor && .venv/bin/python steps/crop_logo.py --pdf _workspace/extracted-sources/<ID>/report.pdf --page <N> --box 0.20,0.05,0.80,0.25 --out output/logos/<ID>.png

- page numbers are 1-based and must be within the page ranges stated for that document below.
- box is x0,y0,x1,y1 fractions of the page, 0.0-1.0, measured from the TOP-LEFT, with x0<x1 and y0<y1; give generous margins because the script auto-trims.
- use slides.pdf or poster.pdf in place of report.pdf as stated in the project block.
- for DOCX projects the template is instead:
  ... crop_logo.py --media _workspace/extracted-sources/<ID>/media/<FILENAME> --out output/logos/<ID>.png

After a successful crop you MUST Read output/logos/<ID>.png and confirm it actually shows the logo (not blank, not the wrong region, not the university crest). If wrong, crop again with a corrected box.

# WHILE VIEWING PAGES: REPOSITORY LINKS

Record every DISTINCT repository URL you see ON SCREEN (github.com/..., gitlab.com/..., bitbucket.org/...), whether rendered as text or inside a screenshot. Typical places: slide footers, "source code" or demo slides, references pages. Write the full URL (add https:// if only github.com/team/repo is shown). Do not invent or complete partial paths. Ignore QR codes you cannot read. Set method "visual". If you see none, links is an empty list.

# RECORD SCHEMA (exact, no extra keys, write one file per project)

{
  "id": "<project id>",
  "logo": {
    "has_logo": true|false,
    "reason": null | "au_crest_only" | "no_logo_found" | "no_viewable_source",
    "extracted": true|false,
    "source": null | {"pdf": "report.pdf"|"slides.pdf"|"poster.pdf", "page": <int>, "box": [x0, y0, x1, y1]}
                  | {"media": "<filename.png>"},
    "output": null | "logos/<id>.png",
    "verified": true|false,
    "note": null | "<short string>"
  },
  "links": [
    {"url": "https://github.com/team/repo",
     "found_in": [{"file": "slides.pdf"|"report.pdf"|"poster.pdf"|"media/<filename>", "page": <int>|null, "method": "visual"}]}
  ]
}

Rules for fields:
- has_logo false requires a reason: "au_crest_only" when university/department marks are all that exist, "no_logo_found" when there is simply no mark, "no_viewable_source" when there was nothing readable to judge from.
- reason must be null when has_logo is true.
- extracted true requires output set and verified true (you read the PNG back and it shows the logo).
- box values are the fractions you actually used in the successful crop command.

# FINAL REPORT (text, after all records are written)

One line per project: id, logo yes/no (+reason if no), crop source (file:page or media file), count of visual URLs. Nothing else. Keep it under 20 lines.
"""

DOC_LIMIT = 25


def project_block(project_id: str, record: dict, manifest_entry: dict) -> str | None:
    pages = record.get("pages", {})
    media = record.get("media", [])
    lines = [f"# PROJECT {project_id}", ""]

    if not pages and not media:
        return None

    if pages:
        lines.append("Read these images:")
        for group, files in pages.items():
            if group == "poster" and len(files) == 1 and not files[0].startswith("poster-p"):
                lines.append(f"- poster (image file, in _workspace/extracted-sources/{project_id}/): {files[0]}")
            else:
                prefix = {"report": "_workspace/renders", "slides": "_workspace/render"}.get(group, "_workspace/render")
                joined = " ".join(files)
                lines.append(f"- {group} (in _workspace/renders/{project_id}/): {joined}")
        lines.append("")
        lines.append("Crop sources (page must be within the range shown):")
        report = manifest_entry.get("report") or {}
        if report.get("file") == "report.pdf":
            lines.append(f"- report.pdf: pages 1-{min(4, 99)} (only the pages you saw rendered)")
        slides = manifest_entry.get("slides") or {}
        if slides:
            lines.append("- slides.pdf: pages 1-8 (only the pages you saw rendered)")
        poster = manifest_entry.get("poster") or {}
        if poster.get("file") == "poster.pdf":
            lines.append("- poster.pdf: pages 1-2 (only the pages you saw rendered)")
        elif poster.get("file") == "poster.pptx":
            lines.append(f"- poster pptx media images (in _workspace/extracted-sources/{project_id}/media/): "
                         + ", ".join(poster.get("media", [])[:20]))
        elif poster.get("file", "").startswith("poster.") and not poster.get("file") == "poster.pdf":
            lines.append(f"- poster image: _workspace/extracted-sources/{project_id}/{poster['file']}")
        externals = manifest_entry.get("external") or []
        if externals:
            lines.append(f"- external evidence (view the rendered external pages): pages as rendered")
    if media:
        if pages:
            lines.append("")
            lines.append(f"DOCX fallback: if no logo is found on rendered pages, the report's embedded images "
                         f"are in _workspace/extracted-sources/{project_id}/media/ ({len(media)} files). "
                         f"Read up to {DOC_LIMIT} of them in order.")
        else:
            lines.append("This project has a Word report: no rendered pages exist. The report's embedded "
                         f"images are in _workspace/extracted-sources/{project_id}/media/ ({len(media)} files). "
                         f"Read them in order, up to {DOC_LIMIT}, stopping early once you have confidently "
                         f"found the best project logo. Cover art usually comes first. If none of the images "
                         "is a project-specific logo, record has_logo false. Use the --media crop template.")
    lines.append("")
    lines.append(f"Record path: output/extraction-evidence/logo-and-link-records/{project_id}.json")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    base = root / "_workspace"
    render_manifest = json.loads((base / "intermediate-data" / "renders-manifest.json").read_text())
    prepared_manifest = json.loads((base / "intermediate-data" / "extracted-sources.json").read_text())

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group-size", type=int, default=6)
    args = parser.parse_args()

    prompts_dir = base / "assignment-prompts"
    prompts_dir.mkdir(exist_ok=True)
    for old in prompts_dir.glob("group-*.md"):
        old.unlink()

    no_source = []
    assignable = []
    for project_id in sorted(render_manifest):
        if project_id in PILOT_IDS:
            continue
        record = render_manifest[project_id]
        if not record.get("pages") and not record.get("media"):
            no_source.append(project_id)
            continue
        assignable.append(project_id)

    groups = [assignable[i:i + args.group_size]
              for i in range(0, len(assignable), args.group_size)]
    for index, group in enumerate(groups, start=1):
        blocks = [project_block(pid, render_manifest[pid], prepared_manifest[pid])
                  for pid in group]
        body = "\n".join(b for b in blocks if b)
        header = (f"You own {len(group)} projects in this exact order: {', '.join(group)}.\n\n")
        (prompts_dir / f"group-{index:02d}.md").write_text(
            RULES + "\n" + header + body)

    print(f"assignable projects: {len(assignable)} in {len(groups)} groups of <= {args.group_size}")
    print(f"pilot (already covered): {sorted(PILOT_IDS)}")
    print(f"no viewable source (mechanical records): {no_source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
