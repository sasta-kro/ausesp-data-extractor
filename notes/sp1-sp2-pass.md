# SP1/SP2 classification pass (decision record)

Record of the third corpus pass, completed 2026-09-12. Every decision applied
in this pass is written here.

## Agreed decisions (2026-09-12, maintainer)

1. **What SP1/SP2 means.** SP1 and SP2 are unrelated projects, each with its
   own proposal, report, code, and slides. The existing `phase` field
   (proposal/final) describes the document type and must NOT be used to
   decide SP1 vs SP2.
2. **Classification method, in order:**
   1. Explicit statement in the document (cover text like "Senior Project
      2 Report", "CS 4200 Senior Project II").
   2. If not explicit: educated inference from the project's printed course
      code via the dictionary below. Inference requires every mapped code on
      the document to agree; mixed-code documents stay unspecified.
   3. Only if both fail: unspecified (`senior_project`).
3. **The course-code dictionary lives here, never in the CSV.** Codes change
   over the years and differ between programs, so every mapping lists its
   sighting count and exceptions.
4. **Slide-only projects (2021, 2031, 2032).** No report files exist anywhere
   in the corpus (verified twice). All three were transcribed from their full
   slide decks (37, 99, and 32 pages, every page read visually plus the text
   layer) into `ground-truth/batches/batch-slideonly.json`.
5. **Duplicate culling.** The worse side of each pair is fully deleted
   (ground-truth record, enrichment record, logo PNG, manifest entries, CSV
   row). Decisions below.
6. **Logo manifest generation** now filters to projects present in the
   metadata CSV (handled by `steps/apply_sp_pass.py`), replacing the
   temporary hardcoded exclusion of 2021.

## Course-code dictionary

Built from 228+ explicit document statements. Clean mappings used for
inference:

| Code | Maps to | Explicit sightings | Known exceptions |
|---|---|---|---|
| CS 3200 | SP1 | 43 | 1823, 2222 print "Senior Project II" under it (verified consistent documents; their own explicit claim won) |
| CS 4200 | SP2 | 41 | none |
| CSX 3010 | SP1 | 25 | 26022, 26030, 25117 print SP2 under it (verified consistent) |
| CSX 3011 | SP2 | 26 | none |
| IT 4291 | SP1 | 20 | none (1906's claim came from its culling-removed broken document) |
| IT 4292 | SP2 | 26 | none |
| IT 4299 | SP1 | 2 | none |
| CS 3010 | SP1 | 1 | single sighting (26033) |
| IT 3200 | SP1 | 1 | single sighting (26034) |
| ITX 3011 | SP2 | 1 | single sighting (26031) |
| ITX 3200 | SP2 | 1 | single sighting (26037) |

Excluded from inference (conflicted, no dominant reading): ITX 3009, ITX 3010,
SC 4299. SC/TS 4299 are legacy umbrella codes appearing with both courses.

Pattern worth knowing: the modern CS/ITX pairs are SP1 = CSX3010/ITX3009 and
SP2 = CSX3011/ITX3010, but several 2025 documents print the SP1 code next to
an explicit SP2 statement (or vice versa). Per-document explicit statements
always override the dictionary.

## Student cross-check (added after review, 2026-09-12)

Maintainer rule: when a project's course cannot be told from its own
documents, check its students' other corpus projects. SP1 and SP2 form a
pair per student, so a student whose other project is SP1 means this one is
SP2, and vice versa.

| Project | Cross-evidence | Outcome |
|---|---|---|
| 1823 | Kamonchanok Arttanate's only other project (1616) is SP1 | confirms the document's own SP2 claim |
| 2222 | both students' other projects (2102, 2042) are SP1 | confirms SP2 |
| 26022 / 26030 / 25117 | no student has another project | document claims stand |
| 2031 | all three students' only other project (2116) is SP2 | resolved to SP1 |
| 2032 | two students' other project (2017) is SP1 | resolved to SP2 (same team's dental work continued from SP1 to SP2) |
| 1933 | conflicting: one member's other project (1927) is SP1, two members' (2001) is SP2 | stays unspecified; cross-evidence itself contradicts |
| 1636 / 1653 / 1657 / 1801 / 25101 | no student has another project | stay unspecified |

## Culling decisions per pair

| Pair | Kept | Deleted | Reason |
|---|---|---|---|
| 1703/1711 | 1703 | 1711 | identical documents and records; kept the first filing |
| 1934/2003 | 1934 | 2003 | same project; kept the side whose title was verified against its cover |
| 1906/2004 | 2004 | 1906 | same project; kept the readable PDF over the broken legacy .doc; course taken from the pair's combined evidence (1906 printed "IT 4292 Senior Project 2") |
| 1827/1920 | 1920 | 1827 | same project; kept the later, more complete record |
| 2579/26009 | 2579 | 26009 | identical records; kept the first filing |
| 2113/2145 | 2113 | 2145 | identical records; kept the first filing |

## Slide-only transcriptions

| Project | Title | Course | Period | People |
|---|---|---|---|---|
| 2021 | Randevoo: Online Reservation Platform | sp2 (explicit, "CS4200 Senior Project II" on every slide footer) | 2/2021 inferred from deck content | Sokvathara Lin and Menh Keo, ids attached from their projects 1950/1646 |
| 2031 | Hotel Management System | unspecified (no course line anywhere) | 2/2020 inferred from the Gantt chart | 3 students, ids printed on slides |
| 2032 | Dental Inventory Management System | unspecified (no course line; deck references Senior Project I as prior work) | 2/2020 inferred from the Gantt chart | Tanakorn Navanugraha and Rajbir Singh ids attached from project 2017; Kan Wuthithepbunha has no id anywhere (documented exception) |

None of the three names an advisor or committee. Their semester/year values
are the only inferred academic periods in the dataset; every other row's
period is printed in its document.

## Verification outcomes (old residuals)

- **2238 student list**: verified complete. Exactly three students with
  matching ids; no fourth student appears. The old "missed student" note
  applied to the regex pipeline, not the hand record.
- **1934 title**: verified clean. The stored title matches the cover exactly;
  the sentence below it is a tagline, never absorbed. No change.

## Pass results

- CSV: 209 rows (212 minus 6 culled plus 3 slide-only), course split after
  the student cross-check: 103 senior_project_1 / 100 senior_project_2 /
  6 unspecified.
- Unspecified projects (6): 1636, 1653, 1657, 1801, 1933, 25101 — no explicit
  statement, codes absent or conflicted, and no student cross-evidence (1933's
  cross-evidence is self-contradictory). (2004 resolved to sp2 through its
  culled twin's explicit statement; 2031/2032 resolved by student
  cross-check.)
- Logo manifest: 69 entries, generated filtered to CSV membership; the
  hardcoded 2021 exclusion is gone (2021 now has both metadata and logo).
- Evidence files: raw cover reads in `output/sp-course/` (202 JSON),
  contradiction re-reads and verifications in `.tmp-enrichment/slideonly/`
  (untracked working data).
