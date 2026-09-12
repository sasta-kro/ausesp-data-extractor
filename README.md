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
under `dataset/`. The final stretch of that work was done by hand,
directly against the source PDFs and Word documents, with this repository
providing the record format, the preparation and conversion steps, and the
CSV build tooling throughout. The repository is kept as the reproducible
recipe and the home of the dataset itself.

## How it fits with AUSE Discovery

AUSE Discovery accepts bulk metadata through a CSV import: exact headers,
taxonomy keys from `config/taxonomy/values.yaml`, people as JSON fields.
This repository exists to produce that CSV from the university's raw report
files. The main project consumes only the result CSV. How it is produced is
this repository's concern alone.

Repository split:

- Main repo: `ause-discover` (the application). Ignores `tools/` entirely.
- This repo: `ausesp-data-extractor`, pushed to
  `git@github.com:sasta-kro/ausesp-data-extractor.git`.

## Repository layout

```text
dataset/                  the hand-transcribed dataset
dataset/project-records/  one JSON record per project: title, people, period,
                          course, abstract, classification
dataset/taxonomy-research/ vocabulary research notes with page-level evidence
dataset/sample.json       the original pilot sample used by validate.py
notes/                    maintainer notes: policies, decisions, traps, reviews
pipeline/                 preparation, conversion, and build tooling
output/                   deliverables
output/ause-discovery-projects-metadata-import.csv   project metadata for the
                          AUSE Discovery import (rebuilt from ground truth, untracked)
output/logos/             one square PNG per project that has its own logo
output/extraction-evidence/  where every logo was cropped from, which repository
                          links were found and whether they were reachable:
                          per-project records, logo verification results,
                          repository-link evidence, and the combined manifest
_workspace/               regenerable working area for the corpus passes
_workspace/extracted-sources/      corpus unpacked and staged per project
_workspace/sp-course-code-tracking/ cover readings behind the SP1/SP2 course map
_workspace/assignment-prompts/     per-batch work assignments
_workspace/review-outputs/         verification outputs and review samples
_workspace/intermediate-data/      pass intermediates (course map, link greps)
```

## Pipeline

```text
resources/all-sp-projects/        raw corpus: 220 projects, ZIPs and PDFs
        |
        v
pipeline/1_prepare.py               unzip, normalize, clean -> reports/
        |
        v
pipeline/2_trim.py                  keep front matter only -> thinned/
        |
        v
pipeline/3_extract_and_build_csv.py extract metadata, classify, emit CSV (scratch)
        |
        v
pipeline/build_reviewed_csv.py      ground truth -> the AUSE Discovery import CSV
```

Steps 1 and 2 came from the earlier frontmatter-extractor project. Step 3
is regex-based and never reached the quality of the hand-transcribed
records. Its known defects are in `notes/regex-pipeline-defects.md`. The
shipped CSV is built from the ground truth by `pipeline/build_reviewed_csv.py`,
which is the step that matters. Fix data in the batch records, never in the
CSV.

## Usage

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Step 1: prepare raw reports (only needed for a fresh corpus copy)
.venv/bin/python pipeline/1_prepare.py <raw-dir> <reports-dir>

# Step 2: trim to front matter
.venv/bin/python pipeline/2_trim.py <reports-dir> <thinned-dir>

# Step 3: regex extraction (defective, kept for reference)
.venv/bin/python pipeline/3_extract_and_build_csv.py \
  --pdfs <thinned-dir> \
  --taxonomy <path-to>/ause-discover/config/taxonomy/values.yaml \
  --output output

# Build the AUSE Discovery import CSV from the hand-transcribed ground truth
.venv/bin/python pipeline/build_reviewed_csv.py \
  --taxonomy <path-to>/ause-discover/config/taxonomy/values.yaml

# Regenerate the taxonomy research report and fold corrections into batches
.venv/bin/python pipeline/apply_discovery.py

# Validate a pipeline run against the ground truth
.venv/bin/python pipeline/validate.py \
  --metadata output/metadata \
  --corpus <corpus-analysis.json> \
  --sample dataset/sample.json
```

The taxonomy file comes from the main repository. The extractor can only
emit keys that file defines. Key additions happen there, then sync to the
database with `ausectl catalog sync`.

## Maintainer notes

- `notes/dataset-notes.md`: dataset contents, the five unimportable
  projects, where data fixes go.
- `notes/person-name-canonicalization.md`: the person dedup policies
  (Burmese names, student-id rules, spelling tie-breaks).
- `notes/enrichment-pass.md`: the logo and repository-link products and
  their open integration decisions.
- `notes/regex-pipeline-defects.md`: why step 3 is reference-only.
- `notes/document-traps.md`: recurring corpus patterns that break naive
  extraction.
- `notes/people-duplication-review.md`: the full 2026-09-11 duplication
  analysis behind the canonical name map.
- `notes/sp1-sp2-pass.md`: the SP1/SP2 course classification record,
  course-code dictionary, and culling decisions.

## License

Unlicensed private tooling. All rights reserved.
