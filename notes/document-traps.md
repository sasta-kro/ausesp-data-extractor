# Known document traps

Patterns that repeatedly break naive extraction from this corpus. Check this
list before diagnosing "weird" data.

- Stale template titles: `Text Classification for Education Publication`
  appears on approval pages and headers of unrelated projects.
- Fictional placeholder approvers: Hal Emmerich, Frank Jaeger, and Drago
  Pettrovich Madnar (video-game character names) on project 2596.
- Cover/approval spelling conflicts: RANGOON vs YANGOON (26006),
  Vipornnitipacha vs Vitpornnitipacha (2148; resolved to Vitpornnitipacha by
  the person's own online profiles, see
  [person-name-canonicalization.md](person-name-canonicalization.md)).
- Cover team brands instead of titles: AutoWise (26010).
- Student IDs print as `ddd-dddd`, seven digits total, and can sit before
  or after names, in parentheses, or on the following line.
- The same project is filed under two numbers in six places: 1703/1711,
  1934/2003, 1906/2004, 1827/1920, 2579/26009, and 2113/2145. Both sides
  are kept; deselect one at import time.
- Some 2022-onward PDFs render blank in common text extraction paths. The
  preparation step keeps plain-text conversions alongside them.
- Burmese names print with inconsistent spacing and fused syllables; Thai
  names romanize inconsistently (aspirated vs plain consonants). See the
  canonicalization note before treating a spelling difference as a
  different person.
