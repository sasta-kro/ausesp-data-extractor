#!/usr/bin/env python3
"""Render the candidate pages for the enrichment pass to PNG.

For every staged project: report pages 1-4, slide pages 1-8, poster pages 1-2,
and up to four pages of each external-evidence PDF, at screen resolution.
Writes _workspace/renders/<id>/<name>-p<N>.png and
_workspace/renders-manifest.json listing what exists per project.

Usage: python3 steps/render_enrichment.py [--dpi 150] [--clean]
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pymupdf

PLAN = [("report.pdf", "report", 4), ("slides.pdf", "slides", 8), ("poster.pdf", "poster", 2)]


def render_pdf(pdf: Path, name: str, max_pages: int, out_dir: Path, zoom: float,
               notes: list[str]) -> list[str]:
    rendered: list[str] = []
    try:
        doc = pymupdf.open(pdf)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"{name}: cannot open ({exc})")
        return rendered
    with doc:
        for page_num in range(min(max_pages, doc.page_count)):
            try:
                pix = doc[page_num].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            except Exception as exc:  # noqa: BLE001
                notes.append(f"{name} page {page_num + 1}: render failed ({exc})")
                continue
            out = out_dir / f"{name}-p{page_num + 1}.png"
            pix.save(out)
            rendered.append(out.name)
    return rendered


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dpi", type=float, default=150.0)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    base = root / "_workspace"
    prepared = base / "prepared"
    render_dir = base / "render"
    if args.clean and render_dir.exists():
        shutil.rmtree(render_dir)

    manifest = json.loads((base / "intermediate-data" / "extracted-sources.json").read_text())
    zoom = args.dpi / 72.0
    out_manifest: dict[str, dict] = {}
    failure_count = 0

    for project_id, entry in manifest.items():
        project_dir = prepared / project_id
        out_dir = render_dir / project_id
        out_dir.mkdir(parents=True, exist_ok=True)
        record: dict = {"pages": {}, "notes": []}
        record["media"] = sorted(set(entry.get("media", [])
                                     + (entry.get("poster") or {}).get("media", [])))
        for filename, name, max_pages in PLAN:
            source = project_dir / filename
            if source.exists():
                record["pages"][name] = render_pdf(source, name, max_pages, out_dir,
                                                   zoom, record["notes"])
        for image_suffix in (".jpg", ".jpeg", ".png"):
            poster_image = project_dir / f"poster{image_suffix}"
            if poster_image.exists():
                record["pages"]["poster"] = [poster_image.name]
        external_dir = project_dir / "external"
        if external_dir.exists():
            for index, pdf in enumerate(sorted(external_dir.glob("*.pdf")), start=1):
                if index > 2:
                    record["notes"].append("external: more than 2 pdfs, extra skipped")
                    break
                record["pages"][f"external{index}"] = render_pdf(
                    pdf, f"external{index}", 4, out_dir, zoom, record["notes"])
        if not record["pages"] and not record["media"]:
            record["notes"].append("nothing renderable for this project")
        out_manifest[project_id] = record
        if any("cannot open" in note or "render failed" in note for note in record["notes"]):
            failure_count += 1

    (base / "intermediate-data" / "renders-manifest.json").write_text(json.dumps(out_manifest, ensure_ascii=False, indent=1))

    total_pages = sum(len(p) for r in out_manifest.values() for p in r["pages"].values())
    projects_with_pages = sum(1 for r in out_manifest.values() if r["pages"])
    print(f"projects with rendered pages: {projects_with_pages}/{len(out_manifest)}")
    print(f"total rendered pages: {total_pages}")
    print(f"projects with render failures: {failure_count}")
    for project_id, record in out_manifest.items():
        if record["notes"]:
            print(f"  {project_id}: {'; '.join(record['notes'])}")
    return 0 if failure_count == 0 and projects_with_pages == len(out_manifest) else 1


if __name__ == "__main__":
    raise SystemExit(main())
