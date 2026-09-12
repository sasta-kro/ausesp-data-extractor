# Person-name canonicalization

Why `CANONICAL_PEOPLE` in `pipeline/build_reviewed_csv.py` exists and the
policies behind every entry, so they are not re-litigated. The full
duplication analysis that produced this is in
[people-duplication-review.md](people-duplication-review.md).

Documents print the same person under different spellings, and the AUSE
Discovery importer matches people by exact 7-digit student id or by
case/space-insensitive name, so any spelling that differs in letters becomes
a separate person row. The canonical map is applied after honorific
stripping. Dataset records stay verbatim.

## Policies

- Staff canonical form = the most frequent mention, cross-checked against
  real AU Vincent Mary faculty names. Fifteen professor spelling families
  collapsed (Anilkumar Kothalil Gopalakrishnan had six spellings alone,
  including initial and truncated forms. "Dean" is not in the honorific
  regex, so "Dean Suparwat Charoenvikrom" needed an explicit map entry).
- Burmese names carry no surname: every word is part of a single given name,
  spacing is not significant, and elements like Aung, Moe, Oo, Htet, Naing
  are name parts, not family names. Students sharing such elements are never
  the same person by that fact alone. Only a shared 7-digit student id proves
  identity. `Phone Pyae Kyaw Swar` is a manual fix: his documents print fused
  spellings (`PhonePyaeKyawSwar`, `PhonePyae KyawSwar`) and the map supplies
  the properly spaced form. There is no way to enforce the spacing rule
  generally, so fused Burmese spellings found in future extractions need
  manual map entries.
- Distinct student ids are definitive even when names are nearly identical:
  Vibolrottana Seng (6217429) and Vibolrottanak Seng (6118173) are two
  different students who share a title page, not a duplicate.
- The university has only student ids, no staff ids. A student always has an
  id in real life. A "student" without one is either a document that did not
  print it or a role error worth investigating.

## Spelling tie-breaks and their evidence

- Paranan **Vitpornnitipacha**: her own GitHub profile (SariPV) and LinkedIn
  both use this spelling. The alternative Vipornnitipacha appears only in one
  printed document.
- Taechasit Sarasitt: his GitHub username is `taechasit1001`.
- Jarukorn Thuengjitvilas: the sp-1727 record (his primary project).
- Kwangmin Kim: the only CSV-visible form.
- Setthanant Tetanonsakul: judgment call, no online trace exists. The
  spelling matches standard Thai romanization of the likely original
  (เสฏฐนันท์). Revisit if a self-spelled source ever turns up.

## Students without ids (documented exceptions)

Kamonchanok Arttanate, Nathanan Pornprapee, Nattalie Shinkoi, and Sai Kham
Sheng have no id printed anywhere in their documents. The ids cannot be
recovered through the university anymore (the students are gone from MS
Teams and their email accounts). Nattalie Shinkoi and Sai Kham Sheng
additionally had wrong ids extracted earlier, which were removed. They
import as students without ids. If the ids are ever recovered from paper
records, fill them into the batch records.
