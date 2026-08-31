# SP Frontmatter Extractor

A small Python pipeline for preparing and trimming senior-project reports before sending them to an LLM or other downstream processing.

The goal is to keep only the useful front matter, such as the cover, approval pages, abstract, acknowledgements, table of contents, lists of figures/tables, and similar material, while stopping at the start of Chapter 1 or a plain `Introduction` section.

## Pipeline

```text
raw reports / ZIPs
      |
      v
prepare_reports.py
      |
      v
normalized report PDFs
      |
      v
trim_frontmatter.py
      |
      v
short frontmatter PDFs + CSV logs
```

`prepare_reports.py` is optional if your input folder already contains clean report PDFs.

## Requirements

- Python 3
- PyMuPDF

Install dependencies:

```bash
pip install -r requirements.txt
```

## Quick start

### 1. Prepare raw PDFs and ZIP archives

```bash
python prepare_reports.py \
  ./all-senior-projects \
  ./prepared-reports \
  --clean
```

By default, the preparation step considers:

```text
*_Report*.pdf
*_Report*.zip
```

Direct report PDFs are copied into the staging folder. Report ZIPs are inspected and a usable report PDF is extracted when it can be selected safely.

To prepare files and immediately run the slicer:

```bash
python prepare_reports.py \
  ./all-senior-projects \
  ./prepared-reports \
  --clean \
  --run-slicer ./output
```

### 2. Trim front matter

```bash
python trim_frontmatter.py ./prepared-reports ./output
```

By default, the slicer processes:

```text
*_Report*.pdf
```

It scans only the first 15 physical PDF pages and looks for boundaries such as:

```text
Chapter 1: Introduction
Chapter 1
Introduction
1. Introduction
1.0 Introduction
I. Introduction
Introduction
```

If the boundary begins near the top of a page, that page is excluded. If it begins far enough down the page, the whole page is kept so useful front matter above the heading is not lost. The default threshold is 35% down the page.

## File filtering

Both scripts support repeatable shell-style glob filters. Quote globs in zsh/bash so the shell does not expand them first.

Add ignores on top of the defaults:

```bash
python trim_frontmatter.py ./input ./output \
  --ignore "*draft*" \
  --ignore "*old*"
```

Replace the default include pattern:

```bash
python trim_frontmatter.py ./input ./output \
  --include "*.pdf" \
  --ignore "*_Slide.pdf" \
  --ignore "*_Poster.pdf"
```

Multiple `--include` arguments are allowed.

For ZIP contents, `prepare_reports.py` already ignores obvious slide, poster, presentation, and external-exposure PDFs. Add more member-level ignores with:

```bash
--member-ignore "*appendix*.pdf"
```

## Useful options

### `trim_frontmatter.py`

```text
--scan-pages N
```

Maximum number of physical PDF pages to inspect. Default: `15`.

```text
--include-if-after FRACTION
```

Keep the boundary page if the heading starts after this fraction of page height. Default: `0.35`.

### `prepare_reports.py`

```text
--clean
```

Delete the staging folder before preparing files.

```text
--run-slicer OUTPUT_FOLDER
```

Run `trim_frontmatter.py` automatically after preparation.

```text
--slicer PATH
```

Use a custom path to the slicer script.

## Logs and statuses

The preparation step writes:

```text
prepared-reports/preparation_report.csv
```

Common preparation statuses include:

- `READY`: PDF successfully staged
- `DOCX_ONLY`: ZIP contains DOCX files but no usable PDF
- `NO_PDF_IN_ZIP`: no usable PDF found
- `AMBIGUOUS_ZIP`: multiple plausible PDFs were found and the script refused to guess
- `BAD_ZIP` / `ZIP_ERROR`: archive problem

The slicer writes:

```text
output/processing_report.csv
```

Common slicing statuses include:

- `OK`: boundary found and output created
- `BOUNDARY_NOT_FOUND`: readable text exists, but no supported boundary was detected
- `NO_TEXT_IN_SCAN`: little or no extractable text was found in the scanned pages, often indicating an image-only/scanned PDF
- `BOUNDARY_AT_START`: the report starts immediately at the detected boundary
- `ERROR: ...`: processing failed

The CSV also records the detected boundary page, heading, position on the page, whether that page was included, and how many pages were saved.

## Notes and limitations

- The slicer does not use an LLM.
- It does not process the whole report. Only the first `N` pages are inspected.
- PDF pages are copied directly, so original text, images, and formatting are preserved.
- OCR fallback is not currently included. Image-only PDFs may appear as `NO_TEXT_IN_SCAN`.
- DOCX-to-PDF conversion is not currently included. ZIPs containing only DOCX files are reported as `DOCX_ONLY`.
- ZIP extraction is conservative. When multiple plausible PDFs exist, the script reports `AMBIGUOUS_ZIP` instead of guessing.

## Typical repository layout

```text
sp-frontmatter-extractor/
├── prepare_reports.py
├── trim_frontmatter.py
├── requirements.txt
├── all-senior-projects/
├── prepared-reports/
└── output/
```
