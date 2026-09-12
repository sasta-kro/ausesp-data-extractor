# Known defects of the regex pipeline (step 3)

Observed in real import output, 2026-09-05. Step 3 is regex-based and never
reached the quality of the hand-transcribed records. Kept for reference only.
The shipped CSV is built from the ground truth by
`pipeline/build_reviewed_csv.py`.

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
