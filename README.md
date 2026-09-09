# AUSESP Data Extractor

Extraction pipeline for Assumption University software engineering senior
projects (AUSESP). Converts raw senior-project report files into an
import-ready CSV for the AUSE Discovery archive.

## Relevance to AUSE Discovery

AUSE Discovery (the main repository this tool lives beside, ignored by its
git) is the public searchable archive of historical senior projects. It
accepts bulk metadata through a CSV import: exact headers, taxonomy keys
from `config/taxonomy/values.yaml`, people as JSON fields. This tool exists
to produce that CSV from the university's raw report files. The main project
consumes only the result CSV. How the CSV is produced, by code or by manual
extraction, is this repository's concern alone.

Repository split:

- Main repo: `ause-discover` (the application). Ignores `tools/` entirely.
- This repo: `ausesp-data-extractor`. Remote
  `git@github.com:sasta-kro/ausesp-data-extractor.git`. Separate history,
  separate concerns, free to iterate.

## Pipeline

```text
resources/all-sp-projects/        raw corpus: 221 projects, ZIPs and PDFs
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

Steps 1 and 2 came from the original sp-frontmatter-extractor history and
already produced the current thinned corpus. Step 3 is newer and still has
known defects; see the handoff section.

## Usage

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Step 1: prepare raw reports (optional when the folder already holds clean PDFs)
.venv/bin/python steps/1_prepare.py <raw-dir> <reports-dir>

# Step 2: trim to front matter
.venv/bin/python steps/2_trim.py <reports-dir> <thinned-dir>

# Step 3: extract and build the import CSV
.venv/bin/python steps/3_extract_and_build_csv.py \
  --pdfs <thinned-dir> \
  --taxonomy <path-to>/ause-discover/config/taxonomy/values.yaml \
  --output output

# Validate against references
.venv/bin/python steps/validate.py \
  --metadata output/metadata \
  --corpus <corpus-analysis.json> \
  --sample ground-truth/sample.json
```

`ground-truth/sample.json` holds records extracted by independent document
reading (LLM agents reading the PDFs), not by the code. It is the quality
reference. Extend it, do not weaken it to match the code.

The taxonomy file comes from the main repository. The extractor can only
emit keys that file defines. Key additions happen there, then sync to the
database with `ausectl catalog sync`.

## Handoff notes for the next agent

Goal: produce a trustworthy import CSV for all 221 projects. Approach is
open: fix the pipeline, fan out manual extraction agents over the unzipped
reports, or combine both. The AUSE project only consumes the result.

Known defects observed in real import output (2026-09-05, thinned corpus):

- Advisor parsing produced `).` for project 2006 (Face Mask Detection).
  Parenthesized signature artifacts leak into the advisor field.
- Committee parsing produced literal underscores for project 2121
  (Wearable Biosensing Device). Signature-line separators are not filtered.
- Some projects with a real abstract extracted none (2121 among them).
- Titles sometimes swallow following student names or course lines.
- Word-per-line PDF extraction mode misses some students (2238).
- Classification uses title and abstract only. Evidence deeper in the
  document (methodology tools such as Qt, Spring Boot) is never tagged.
  Full-document classification was tried and rejected: literature-review
  mentions create false tags. A better fix is reading tools/acknowledgement
  chapters specifically, not the whole document.
- Proposal-phase front matter has no abstract and cannot import. The
  application rejects such rows by design. Import them once final reports
  exist.

Known document traps (see also the corpus design note inside the AUSE repo,
`docs/dev-notes/archvies/CORPUS_AND_SEARCH_DESIGN.md`):

- Stale template titles: `Text Classification for Education Publication`
  appears on approval pages and headers of unrelated projects.
- Fictional placeholder approvers: Hal Emmerich, Frank Jaeger,
  Drago Pettrovich Madnar (Metal Gear names) on project 2596.
- Cover/approval spelling conflicts: RANGOON vs YANGOON (26006),
  Vipornnitipacha vs Vitpornnitipacha (2148).
- Cover team brands instead of titles: AutoWise (26010).
- Student IDs print as `ddd-dddd`, seven digits total, and can sit before
  or after names, in parentheses, or on the following line.

A reviewed, manually verified CSV built from agent-read documents is produced
by `steps/build_reviewed_csv.py` from the JSON records in
`ground-truth/batches/` (one file per extraction batch; all 217 report
projects covered as of 2026-09-09, including verbatim abstracts, generated
grounded descriptions where documents print none, and cleaned people fields
with honorifics and academic titles stripped at build time). Output lands at
`output/reviewed-import.csv` (untracked). It is the safe import source until
the pipeline reaches that quality. Extend the batch records rather than the
script when corrections come up.

A second full-corpus pass (2026-09-09) produced `ground-truth/discovery/`
records: whole-document technology and domain evidence with used-versus-cited
status, plus grounded abstracts for abstractless documents. Run
`steps/apply_discovery.py` to regenerate `output/discovery-report.md` (ranked
taxonomy key suggestions not yet in values.yaml) and fold corrections into
the canonical batches. `steps/extract_discovery.py` pulls a result JSON out
of an agent transcript file. The prepared extraction cache lives in
`.tmp-prepared/` (gitignored, kept on disk).

Corpus quirks found during the 100-project run (2026-09-08):

- The same project filed under two numbers: 1703/1711 (byte-identical ZIPs),
  1934/2003 (same game and team), 1827/1920 (SAMT Master), and 1906 (final)
  vs 2004 (proposal) of the same Elderly Care project. All kept; the import
  owner decides whether to skip the duplicates.
- 1651, 1902, 1940 are RAR archives; nothing on the machine unpacks them
  (`brew install unar` would).
- 14 reports are Word documents, converted to plain text with
  pandoc/textutil before reading.
- `php` appears in two reports but is not a taxonomy key; it was stripped.
  Consider adding it to the main repo's values.yaml if that stack matters.
- sp-1800 prints no advisor anywhere in the document.
