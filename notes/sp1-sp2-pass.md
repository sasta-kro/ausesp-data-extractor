# SP1/SP2 classification pass (decision record)

Running record of the third corpus pass. Every decision is written here
before or as it is applied, so nothing lands silently.

## Agreed decisions (2026-09-12, maintainer)

1. **What SP1/SP2 means.** SP1 and SP2 are unrelated projects, each with its
   own proposal, report, code, and slides. The existing `phase` field
   (proposal/final) describes the document type and must NOT be used to
   decide SP1 vs SP2.
2. **Classification method, in order:**
   1. Explicit statement in the document (cover text like "Senior Project
      2 Report", "ITX3010 Senior Project 2").
   2. If not explicit: educated inference from the project's printed course
      code via a data dictionary built from step 1 evidence.
   3. Only if both fail: unspecified (`senior_project`).
3. **Course-code dictionary.** Every explicit sighting records the course
   code printed alongside it. Codes accumulate into a dictionary mapping
   code -> SP1/SP2 with context (program IT vs CS, year range), because
   codes change over the years and differ between programs. The dictionary
   lives in this note, never in the CSV.
4. **Slide-only projects (2021, 2031, 2032).** No report files exist
   anywhere in the corpus (verified twice). All three get full-effort
   transcription from their slide decks: every page read visually AND text
   extraction, all fields including abstract (factual stand-in summary if
   the slides print none, same policy as reports). They then enter the CSV.
5. **Duplicate culling.** The six duplicate pairs (1703/1711, 1934/2003,
   1906/2004, 1827/1920, 2579/26009, 2113/2145) are fully resolved: the
   better side stays, the worse side is deleted everywhere (ground-truth
   record, enrichment record, logo PNG, logo manifest, CSV row). Better =
   final report over proposal, complete data over thin, readable document
   over broken. The chosen side per pair is recorded below when decided.
   Nothing is "deselected at import" anymore.
6. **Logo manifest exclusion removal.** The hardcoded `select(.key !=
   "2021")` in the main repository's operator note
   (`.memory/sasta-dev-notes/project-content-import.md`, their commit
   `73c303c`) is temporary. After this pass 2021 has metadata, so the
   exclusion is removed and replaced by a robust rule: the manifest export
   filters to projects present in the metadata CSV, so it can never again
   reference a project without a database row.
7. **Also folded in:** verify 2238's student list (an old residual said a
   student was missed) and 1934's title (an old residual said cover text
   merged into the title).

## Course-code dictionary

(Filled during the pass from explicit sightings: code, program, year,
SP1/SP2, evidence project.)

## Culling decisions per pair

(Filled during the pass: kept side, deleted side, reason.)

## Pass results

(Filled at the end: counts per outcome, CSV effect.)
