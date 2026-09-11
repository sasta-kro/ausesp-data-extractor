# Enrichment pass: project logos and repository links

Record of the second full-corpus pass (2026-09-11), what it produced, and
decisions that still matter. Products live in `output/enrichment/`.

## What was produced

- `output/enrichment/logos/<id>.png` — the project's own logo, cropped at
  300 DPI from the slide title page or report cover, auto-trimmed, max
  1600 px. 71 of 220 projects have one. Only project-specific marks are
  taken: reports carrying just the university crest record `au_crest_only`
  and get no image. The title slide of the presentation deck is where teams
  put their brand mark (41 of 71 logos come from slide page 1); report
  covers are crest-only territory in almost every era, and exactly one logo
  came from a poster.
- `output/enrichment/records/<id>.json` and `manifest.json` — logo
  provenance (source file, page, crop box) plus every repository URL found
  in the documents, classified as `project_repo` (the team's own
  repository, 17 URLs across 14 projects) or `third_party_reference` (a
  cited library such as tesseract or zxing, kept for provenance but not for
  display).
- `output/enrichment/liveness.json` — public accessibility of each URL at
  check time: `public` (200), `not_found` (404, private or deleted,
  indistinguishable from outside), `unknown` (rate limit or network error).
  Renamed repositories resolve to their new home through the recorded final
  URL. Statuses go stale; re-run `steps/check_link_liveness.py` before any
  launch.

## Decisions and open items

- All repository URLs came from the text layer (mechanical grep). Slide
  decks show demo links (herokuapp, railway, github.io) but no repository
  links; those demo sites could become a future "deployed site" link type.
- Link classification is hand-curated in `steps/classify_links.py` (owner
  matched against ground-truth student names, repo name matched against
  project titles). Third-party references must never display as project
  repos.
- Audit spot-check downgraded 2148 (a UI pill button, not a logo) and
  re-cropped 1824 from its poster; 2119 was kept (a stylized wordmark
  counts as a logo).
- Promotion of logos and links into the AUSE Discovery UI, and where the
  bytes live (representative-image field vs a new artifact kind on the
  pluggable artifact storage), is deliberately deferred to a review in the
  main repository. The import CSV has no columns for either.

## Pipeline

`steps/prepare_enrichment.py` (stage per-project sources, including RAR
archives, legacy .doc media, and PPTX posters) → `render_enrichment.py`
(render candidate pages) → `grep_repo_urls.py` (text-layer URL harvest) →
`crop_logo.py` (crop or copy, with blank and sliver rejection) →
`build_pass_assignments.py` (per-worker assignment prompts) →
`check_link_liveness.py` → `classify_links.py` → `merge_enrichment.py`
(validation and manifest).
