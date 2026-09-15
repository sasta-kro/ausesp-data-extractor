# New batch comparison: sp-projects-raw-NEW (2016 to 2022)

Compared 2026-09-15. Source: `resources/sp-projects-raw-NEW/` in the main
repository, received from the other admins, labeled 2016 to 2022. The batch
holds 237 files (960 MB) plus a readme. Comparison method: project ids from
filenames, then a byte-level SHA-256 comparison of every extracted document
against the staged corpus. The import CSV was read, never modified.

## Verdict

Nothing new. Every project in the batch is already in our corpus, and every
import-relevant document is byte-identical to material we already processed.
No extraction pass is needed for this batch.

## Headline numbers

| Measure | Value |
|---|---|
| Unique project ids in the batch | 162 |
| Brand-new ids (not in our 220-project corpus) | 0 |
| Already imported in the CSV | 152 |
| In the batch but not importable (see below) | 10 |
| Corpus projects the batch does not cover | 58 |

## The 10 not-importable ones, and why

| Project | Reason |
|---|---|
| sp-1651 | Documents print no semester and no academic year anywhere. The import schema requires both. Its two archives in this batch are also corrupt (members fail CRC checks). |
| sp-1661 | No semester or academic year printed anywhere. |
| sp-1813 | No semester or academic year printed anywhere. |
| sp-1904 | No semester or academic year printed anywhere. |
| sp-1800 | No advisor printed in any document. The importer requires at least one advisor per project. An app-side change to make this a warning is planned (backlog item 20). |
| sp-1711 | Duplicate filing of sp-1703. Same project under two numbers. We keep 1703. |
| sp-1827 | Duplicate filing of sp-1920. We keep 1920. |
| sp-1906 | Duplicate filing of sp-2004. We keep 2004, which has a proper PDF. |
| sp-2003 | Duplicate filing of sp-1934. We keep 1934. |
| sp-2145 | Duplicate filing of sp-2113. We keep 2113. |

## Coverage by academic year

The batch label checks out: it covers 2016 through 2022 almost completely.
The gaps below are exactly our newer cohorts plus a few known strays.

| Academic year | Corpus projects | In batch | Not in batch |
|---|---|---|---|
| 2016 | 1 | 1 | 0 |
| 2017 | 24 | 24 | 0 |
| 2018 | 22 | 22 | 0 |
| 2019 | 26 | 26 | 0 |
| 2020 | 22 | 19 | 3 |
| 2021 | 33 | 31 | 2 |
| 2022 | 27 | 27 | 0 |
| 2023 | 3 | 3 | 0 |
| 2025 | 50 | 0 | 50 |
| 2026 | 1 | 0 | 1 |
| no year printed | 5 | 4 | 1 |
| year unknown (culled sides) | 6 | 5 | 1 |
| **Total** | **220** | **162** | **58** |

## The 58 we hold that the batch lacks

- The entire 2025 cohort, 50 projects: 2579, 2593 through 2599, 25100
  through 25102, 25104, 25105, 25113, 25115 through 25118, 26002 through
  26008, 26010 through 26014, 26016 through 26024, 26026, 26027, 26029
  through 26033, 26035 through 26038.
- sp-26034, academic year 2026.
- sp-2014 and sp-2102, both imported and fine. The admins' batch simply
  omits them.
- sp-2021, sp-2031, sp-2032: the slide-only projects with no report. This
  batch does not fix that gap.
- sp-2146: no semester or year printed, same situation as the drops above.
- sp-26009: culled duplicate side of sp-2579.

## Byte-level findings

All import-relevant documents match our staged copies exactly. Three
projects carry extra bytes we do not have, none of it valuable:

- sp-1650: the editable DOCX source of a report we already carry as an
  identical PDF.
- sp-1661: one extra literature-chapter PDF. The project stays
  unimportable for its missing period either way.
- sp-1702: website images and old timestamped drafts bundled with the
  source code. Not archive material.

## Problems in the batch worth telling the other admins

- `1902_Report.zip` and `1940_Report.zip` are RAR archives renamed to .zip.
- `1651_Poster.zip` and `1651_Report.zip` are corrupt: members fail their
  CRC checks and cannot be fully extracted.
