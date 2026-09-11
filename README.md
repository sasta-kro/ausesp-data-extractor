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
ground-truth/             hand-transcribed records, one file per work batch
ground-truth/discovery/   taxonomy research notes with page-level evidence
notes/                    maintainer notes: policies, decisions, traps, reviews
steps/                    preparation, conversion, and build tooling
output/                   deliverables
output/reviewed-import.csv    the import product (rebuilt, untracked)
output/enrichment/            logos, per-project records, repository links,
                              link liveness (tracked, see notes/enrichment-pass.md)
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
records; its known defects are in `notes/regex-pipeline-defects.md`. The
shipped CSV is built from the ground truth by `steps/build_reviewed_csv.py`,
which is the step that matters. Fix data in the batch records, never in the
CSV.

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

## Maintainer notes

- `notes/dataset-notes.md` — dataset contents, the five unimportable
  projects, where data fixes go.
- `notes/person-name-canonicalization.md` — the person dedup policies
  (Burmese names, student-id rules, spelling tie-breaks).
- `notes/enrichment-pass.md` — the logo and repository-link products and
  their open integration decisions.
- `notes/regex-pipeline-defects.md` — why step 3 is reference-only.
- `notes/document-traps.md` — recurring corpus patterns that break naive
  extraction.
- `notes/people-duplication-review.md` — the full 2026-09-11 duplication
  analysis behind the canonical name map.

## License

Unlicensed private tooling. All rights reserved.
