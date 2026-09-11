# AUSESP Data Extractor

![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![Status](https://img.shields.io/badge/status-extraction%20complete-brightgreen)
![Made for](https://img.shields.io/badge/made%20for-AUSE%20Discovery-8A2BE2)

Tooling for turning the raw Assumption University software engineering
senior-project (AUSESP) report archive into an import-ready CSV for
[AUSE Discovery](https://github.com/sasta-kro/ause-discover), the public
searchable archive of historical senior projects.

The extraction work itself is finished: all 217 report-bearing projects in
the corpus were read cover to cover and transcribed into the batch records
under `ground-truth/`. The final stretch of that work was done by hand,
directly against the source PDFs and Word documents, with this repository
providing the record format, the preparation and conversion steps, and the
CSV build tooling throughout. The repository is kept as the reproducible
recipe and the home of the dataset itself.

## How it fits with AUSE Discovery

AUSE Discovery accepts bulk metadata through a CSV import: exact headers,
taxonomy keys from `config/taxonomy/values.yaml`, people as JSON fields.
This repository exists to produce that CSV from the university's raw report
files. The main project consumes only the result CSV; how it is produced is
this repository's concern alone.

Repository split:

- Main repo: `ause-discover` (the application). Ignores `tools/` entirely.
- This repo: `ausesp-data-extractor`, pushed to
  `git@github.com:sasta-kro/ausesp-data-extractor.git`.

## Repository layout

```text
ground-truth/batches/    hand-transcribed records, one file per work batch
ground-truth/discovery/  taxonomy research notes with page-level evidence
enrichment/              second-pass products: logos, repository links, liveness
steps/                   preparation, conversion, and build tooling
output/reviewed-import.csv   the import product (untracked)
```

## Pipeline

```text
resources/all-sp-projects/        raw corpus: 220 projects, ZIPs and PDFs
        |
        v
steps/1_prepare.py               unzip, normalize, clean -> reports/
        |
        v
steps/2_trim.py                  keep front matter only -> thinned/
        |
        v
steps/3_extract_and_build_csv.py extract metadata, classify, emit CSV
        |
        v
output/import.csv                import into AUSE Discovery admin UI
```

Steps 1 and 2 came from the earlier frontmatter-extractor project. Step 3
is regex-based and never reached the quality of the hand-transcribed
records; its known defects are listed below. The shipped CSV is built from
the ground truth by `steps/build_reviewed_csv.py`, which is the step that
matters.

## Usage

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Step 1: prepare raw reports (only needed for a fresh corpus copy)
.venv/bin/python steps/1_prepare.py <raw-dir> <reports-dir>

# Step 2: trim to front matter
.venv/bin/python steps/2_trim.py <reports-dir> <thinned-dir>

# Step 3: regex extraction (defective, kept for reference)
.venv/bin/python steps/3_extract_and_build_csv.py \
  --pdfs <thinned-dir> \
  --taxonomy <path-to>/ause-discover/config/taxonomy/values.yaml \
  --output output

# Build the reviewed CSV from the hand-transcribed ground truth
.venv/bin/python steps/build_reviewed_csv.py \
  --taxonomy <path-to>/ause-discover/config/taxonomy/values.yaml

# Regenerate the taxonomy research report and fold corrections into batches
.venv/bin/python steps/apply_discovery.py

# Validate a pipeline run against the ground truth
.venv/bin/python steps/validate.py \
  --metadata output/metadata \
  --corpus <corpus-analysis.json> \
  --sample ground-truth/sample.json
```

The taxonomy file comes from the main repository. The extractor can only
emit keys that file defines. Key additions happen there, then sync to the
database with `ausectl catalog sync`.

## Dataset notes

- `ground-truth/batches/` holds one JSON record per project, transcribed
  directly from the source documents: verbatim titles and abstracts, people
  as printed, classifications restricted to the keys defined in the main
  repository. Where a document prints no abstract, a short factual summary
  based on the document's own content stands in. Fix data in the batch
  records, never in the CSV.
- Person names are normalized at build time: honorifics and academic titles
  are stripped, truncated surname-less forms are completed against the rest
  of the corpus, and spelling variants of the same person merge through
  their shared student id.
- Aliases equal to their row title (case-insensitive) are filtered out at
  build time; the importer rejects them.
- Five projects print no semester or academic year anywhere and cannot
  import: 1651, 1661, 1813, 1904, 2146. Two more print no advisor
  (1628, 1800); both stay in the dataset with an empty advisor list.

## Enrichment pass (project logos and repository links)

A second pass over the full corpus produced, per project:

- `enrichment/logos/<id>.png` — the project's own logo, cropped at 300 DPI from
  the report cover or slide title page. Only project-specific marks are taken:
  reports carrying just the university crest record `au_crest_only` and get no
  image. 72 of 220 projects have a logo.
- `enrichment/records/<id>.json` and `enrichment/manifest.json` — logo
  provenance (source file, page, crop box) plus every repository URL found in
  the documents, each classified as `project_repo` (the team's own repository,
  17 across the corpus) or `third_party_reference` (a cited library such as
  tesseract or zxing, kept for provenance but not for display).
- `enrichment/liveness.json` — public accessibility of each URL at check time:
  `public` (200, green), `not_found` (404, private or deleted, shown as
  "Not accessible (private or deleted)"), `unknown` (rate limit or network
  error, "Unverified"). Renamed repositories resolve to their new home through
  the recorded final URL.

The pipeline is `steps/prepare_enrichment.py` (stage per-project sources,
including RAR archives, legacy .doc media, and PPTX posters) →
`steps/render_enrichment.py` (render candidate pages) →
`steps/grep_repo_urls.py` (text-layer URL harvest) → `steps/crop_logo.py`
(crop or copy, with blank and sliver rejection) → `steps/check_link_liveness.py`
→ `steps/classify_links.py` (hand-reviewed owner/repo classification) →
`steps/merge_enrichment.py` (validation and manifest). Promotion of a logo to
the AUSE Discovery UI, and where the bytes live (representative-image field or
a new artifact kind on pluggable artifact storage), is a decision recorded in
the main repository, deferred until integration.

## Known defects of the regex pipeline (step 3)

Observed in real import output, 2026-09-05:

- Advisor parsing produced `).` for project 2006 (Face Mask Detection):
  parenthesized signature artifacts leak into the advisor field.
- Committee parsing produced literal underscores for project 2121:
  signature-line separators are not filtered.
- Some projects with a real abstract extracted none (2121 among them).
- Titles sometimes swallow following student names or course lines.
- Word-per-line PDF extraction mode misses some students (2238).
- Classification uses title and abstract only, so methodology tools
  (Qt, Spring Boot, and similar) are never tagged. Full-document keyword
  matching was tried and rejected: literature-review mentions create false
  tags. The workable fix is reading the tools chapters specifically.

## Known document traps

- Stale template titles: `Text Classification for Education Publication`
  appears on approval pages and headers of unrelated projects.
- Fictional placeholder approvers: Hal Emmerich, Frank Jaeger, and Drago
  Pettrovich Madnar (video-game character names) on project 2596.
- Cover/approval spelling conflicts: RANGOON vs YANGOON (26006),
  Vipornnitipacha vs Vitpornnitipacha (2148).
- Cover team brands instead of titles: AutoWise (26010).
- Student IDs print as `ddd-dddd`, seven digits total, and can sit before
  or after names, in parentheses, or on the following line.
- The same project is filed under two numbers in six places: 1703/1711,
  1934/2003, 1906/2004, 1827/1920, 2579/26009, and 2113/2145. Both sides
  are kept; deselect one at import time.
- Some 2022-onward PDFs render blank in common text extraction paths. The
  preparation step keeps plain-text conversions alongside them.

## License

Unlicensed private tooling. All rights reserved.
