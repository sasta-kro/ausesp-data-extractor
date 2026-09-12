# Dataset notes

Working record of what the dataset contains and why some records are the way
they are. Read before touching `dataset/` or rebuilding the CSV.

- `dataset/project-records/` holds one JSON record per project, transcribed
  directly from the source documents: verbatim titles and abstracts, people
  as printed, classifications restricted to the keys defined in the main
  repository. Where a document prints no abstract, a short factual summary
  based on the document's own content stands in. Fix data in the record
  files, never in the CSV.
- Person names are normalized at build time (see
  [person-name-canonicalization.md](person-name-canonicalization.md)):
  honorifics and academic titles are stripped, spelling variants collapse
  through a hand-reviewed canonical map, truncated surname-less forms are
  completed against the rest of the corpus, and spelling variants of the same
  person merge through their shared student id.
- Aliases equal to their row title (case-insensitive) are filtered out at
  build time. The importer rejects them.
- Five projects print no semester or academic year anywhere and cannot
  import: 1651, 1661, 1813, 1904, 2146. Four more print no advisor in any
  staged document (verified by full-text search, 2026-09-13): 1800 report
  and 2021, 2031, 2032 slide-only decks. The importer rejects a row
  without an advisor, so `DROPPED_NO_ADVISOR` in
  `pipeline/build_reviewed_csv.py` keeps them out of the CSV until the
  application downgrades a missing advisor to a warning (MVP improvement
  backlog item 20 in the main repository). Their records stay as ground
  truth. Project 1628 also prints no advisor in its report, but its slides
  name the SP1 presenting panel, which now supplies the advisor
  (Kwankamol Nongpong) and committee (Paitoon Porntrakoon, Thanachai
  Thumthawatworn), and its MATLAB simulation study classifies as platform
  `none` because it is not a deployable product.
- 220 projects total in the corpus views: 217 report-bearing plus three
  slide-only projects (2021, 2031, 2032) that have no report document.
- Two legacy .doc reports (1636, 1906) yield no recoverable embedded images
  and no renderable pages. 1906's project is also filed as 2004, which has a
  proper PDF, so nothing is lost.
