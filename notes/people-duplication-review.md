# Person deduplication report (for review — no changes applied yet)

Date: 2026-09-11. Scope: every human name in `ground-truth/batches/` (486 raw spellings, 416 distinct after the builder's honorific stripping, 220 projects), cross-checked against the 212-row `output/reviewed-import.csv`. Method: normalized-equality clustering, prefix/token-subset matching, edit-distance matching, student_id cross-referencing (per the rule: a student always has a 7-digit id, staff never do), role-consistency checks, and frequency + real-world faculty knowledge for canonical forms.

## Verdict summary

| # | Cluster | Verdict | Action |
|---|---------|---------|--------|
| 1 | Anilkumar Kothalil Gopalakrishnan (6 spellings) | same person, professor | FIX: collapse to 1 |
| 2 | Darun / Darun Kesrarat | same person, professor | FIX |
| 3 | Phyo Min Tun / Phyo Min Htun | same person, professor | FIX |
| 4 | Thanachai Thumthawatworn / ...worm | same person, professor | FIX |
| 5 | Benjawan Srisura / Sirsura / Benjawin Srisura | same person, professor | FIX |
| 6 | Chayapol Moemeng / Meomeng / Meomong / Momeng | same person, professor | FIX |
| 7 | Chokdee Liophanich / Liopanich | same person, professor | FIX |
| 8 | Athiphat / Atthipat Hirunadisuan | same person, professor | FIX |
| 9 | Jinchun Lu / Jichun Lu / Lu Jinchun | same person, professor | FIX |
| 10 | Kwankamol Nongpong / Knongpong | same person, professor | FIX |
| 11 | Mana Tanachan / Thanachan | same person, professor | FIX |
| 12 | Piyakul Tillapart / Tillpart | same person, professor | FIX |
| 13 | Dobri Atanassov Batovski / Dobri Batovski | same person, professor | FIX |
| 14 | Suparwat Charoenvikrom / Dean Suparwat... / Supawat... | same person, professor | FIX |
| 15 | Tianai Tang / Tang Tianai | same person, professor | FIX |
| 16 | AnilKumar K. Gopalakrishnan | part of cluster 1 | covered by 1 |
| 17 | Jarukorn Thuengjitvilas / Theungjitvilas | same student, same id | merged by importer already; fix spelling at source |
| 18 | Kwangmin Kim / Kwang Min Kim | same student, same id | merged already; CSV shows only Kwangmin Kim |
| 19 | Paranan Vitpornnitipacha / Vipornnitipacha | same student, same id | merged already; TIE on spelling, confirm |
| 20 | Setthanant / Sethanant Tetanonsakul | same student, same id | merged already; TIE on spelling, confirm |
| 21 | Taechasit / Tachasit Sarasitt | same student, same id | merged already; Taechasit matches his own GitHub username |
| 22 | PhonePyae KyawSwar / PhonePyaeKyawSwar | same student, same id | merged already; spacing |
| 23 | Initial-form students (Artisd C., Chawan V., Brighton T. Shanji, Chinnawat W., Alexander J. Fuller) | same students as full forms, same ids | merged already; canonicalize full forms |
| 24 | Vibolrottana Seng / Vibolrottanak Seng | DIFFERENT people (distinct ids) | keep separate, confirm |
| 25 | Shared-surname students (Aung, Moe, Oo, Zhou, etc.) | different people, distinct ids | keep separate, no action |
| 26 | 4 students with no id printed anywhere | real students, ids unverified | YOUR DECISION |
| 27 | Abbreviated-only students (Charoenkeith W., Daran S., Parin M., Natthawat P., Siwapong C., Thanawat U., Shahin R., Daniel M. Porter) | only form the documents print | no action possible |

## A. Clusters that create separate people in the app (the real bugs)

All of these are staff (professor) spelling variants. The importer merges people by exact student_id or case/space-insensitive display_name, so any variant that differs in letters becomes its own Person row. Fixes go into a canonical-name map in `steps/build_reviewed_csv.py` (ground-truth records deliberately stay verbatim as printed). Canonical form = most frequent mention, consistent with real AU Vincent Mary faculty.

### 1. Anilkumar Kothalil Gopalakrishnan — 6 spellings, 1 person

| Variant | Mentions | Roles |
|---|---|---|
| Anilkumar Kothalil Gopalakrishnan | 21 | advisor 3, committee 18 |
| AnilKumar Kothalil Gopalakrishnan | 4 | committee 4 |
| Anilkumar Kothalil | 1 | committee 1 |
| Anilkumar Kothalil Gopalakrishna | 1 | committee 1 |
| Anilkumar Kothalil Gopalkrishnan | 1 | advisor 1 |
| AnilKumar K. Gopalakrishnan | 1 | advisor 1 |

Real AU CS faculty (Asst. Prof. Dr.). Canonical: **Anilkumar Kothalil Gopalakrishnan**. Produces 5 extra people today.
Note: in the current CSV he is NEVER a student. If your app shows him as a student, that row came from an earlier import (see section D).

### 2. Darun / Darun Kesrarat — advisor 2 vs advisor 15 + committee 15

Truncated first-name-only form in two records. Real AU IT faculty (Asst. Prof. Dr. Darun Kesrarat).
Canonical: **Darun Kesrarat**.

### 3. Phyo Min Tun / Phyo Min Htun — this is your "2 Phyo Min Tun" screenshot

| Variant | Roles |
|---|---|
| Phyo Min Tun | advisor 5, committee 6 |
| Phyo Min Htun | advisor 1 |

Both are staff roles; one record romanizes the Burmese name with "Htun". AU lecturer; publishes as Phyo Min Tun.
Canonical: **Phyo Min Tun**. Not students, no id issue.

### 4. Thanachai Thumthawatworn / Thumthawatworm

"worm" is a typo in one record (advisor 1). Real AU faculty surname ends in -worn (7 advisor + 6 committee mentions).
Canonical: **Thanachai Thumthawatworn**. This is your "Thana chai" screenshot.

### 5. Benjawan Srisura family

Sirsura (committee 1), Benjawin Srisura (advisor 1) vs Srisura (advisor 7, committee 50). Real AU IT faculty.
Canonical: **Benjawan Srisura**.

### 6. Chayapol Moemeng family

Meomeng (1), Meomong (1), Momeng (1) vs Moemeng (advisor 43, committee 43). Real AU CS faculty.
Canonical: **Chayapol Moemeng**.

### 7. Chokdee Liophanich / Liopanich

Real AU faculty; -ph- spelling dominates (advisor 2 + committee 5 vs advisor 2).
Canonical: **Chokdee Liophanich**.

### 8. Athiphat / Atthipat Hirunadisuan

Same AU lecturer, doubled-t romanization in 2 of 6 mentions.
Canonical: **Athiphat Hirunadisuan**.

### 9. Jinchun Lu / Jichun Lu / Lu Jinchun

Chinese given/family order flip plus a missing n. AU CS lecturer (advisor of 26010, printed there as Jinchun Lu).
Canonical: **Jinchun Lu**.

### 10. Kwankamol Nongpong / Knongpong

Dropped n in 1 of 40 mentions. Real AU faculty.
Canonical: **Kwankamol Nongpong**.

### 11. Mana Tanachan / Mana Thanachan

Thai aspirated-t variant; 4 vs 1 mentions.
Canonical: **Mana Tanachan**.

### 12. Piyakul Tillapart / Tillpart

Missing syllable in 2 of 26 mentions. Real AU faculty.
Canonical: **Piyakul Tillapart**.

### 13. Dobri Atanassov Batovski / Dobri Batovski

Short form once. Real AU faculty (Bulgarian full name).
Canonical: **Dobri Atanassov Batovski**.

### 14. Suparwat Charoenvikrom family

| Variant | Roles |
|---|---|
| Suparwat Charoenvikrom | advisor 2, committee 9 |
| Dean Suparwat Charoenvikrom | committee 2 |
| Supawat Charoenvikrom | committee 1 |

Real ABAC/VMS dean. The "Dean" prefix survives because the builder's honorific regex does not include it (only Mr/Ms/Dr/Prof/Asst/Assoc/Ajarn variants). Canonical: **Suparwat Charoenvikrom**.

### 15. Tianai Tang / Tang Tianai

Chinese name-order flip (advisor 3 + committee 8 vs 1 + 1).
Canonical: **Tianai Tang**.

## B. Same person, already merged by the importer (no app duplicates), spelling fixed at source anyway

These share one student_id, so the importer already treats them as one Person. Listed for completeness and because the display name should still be canonical:

- **Jarukorn Thuengjitvilas** (sp-1727) / Theungjitvilas (sp-1829), id 5810228. Propose Thuengjitvilas.
- **Kwangmin Kim** (sp-1825) / Kwang Min Kim (sp-1661, a dropped row), id 5738001. CSV contains only Kwangmin Kim. No action.
- **Paranan Vitpornnitipacha** (sp-2214) / Vipornnitipacha (sp-2148), id 6135118. TIE (1 mention each) — this is the documented 2148 cover/approval spelling conflict. NEEDS YOUR CALL: which spelling is the real one?
- **Setthanant Tetanonsakul** (sp-2207) / Sethanant (sp-2244), id 6115269. TIE (1 each). NEEDS YOUR CALL.
- **Taechasit Sarasitt** (sp-1719) / Tachasit (sp-2126), id 6110032. Propose **Taechasit**: his personal GitHub username in the report is `taechasit1001`, a self-spelling.
- **PhonePyae KyawSwar** (sp-2021) / PhonePyaeKyawSwar (sp-2031), id 6118156. Spacing only. Propose PhonePyae KyawSwar.
- Initial forms with full twins (same id): Artisd C. (sp-1800) = Artisd Chanyawadee (sp-1651); Chawan V. (sp-1800) = Chawan Vattanalap (sp-1651); Brighton T. Shanji (sp-1627) = Brighton Tapiwa Shanji (sp-1904, dropped row); Chinnawat W. (sp-1710) = Chinnawat Wongpatamajaroen (sp-1822); Alexander J. Fuller (sp-1802) = Alexander James Fuller (sp-1809). Canonicalize the full forms.

## C. Kept separate on purpose

- **Vibolrottana Seng (id 6217429, sp-2252 + sp-2146) and Vibolrottanak Seng (id 6118173, sp-2146)** — different ids, so by the id rule they are two different students (possibly relatives; both printed on 2146's title page, and 2146 is a dropped row anyway). NOT merged. Flagged for your confirmation since the names are one letter apart.
- Shared-surname students (Aung x6, Moe x4, Oo x6, Zhou x3, Singh x3, etc.) — all carry distinct ids. Normal Burmese/Chinese/Thai surname commonality. No merges.

## D. Not the current CSV's fault (app-side residue)

- **Anikumar as a student**: the current CSV never lists any Anilkumar variant as a student. The app row you screenshotted came from an earlier import (the VM's two-batch import and/or the local seed-demo used older CSV versions with worse spellings). The current CSV's Anilkumar problem is 6 staff spellings = 5 extra people, not a role error.
- After the fixes, existing databases (local + VM) still hold the old misspelled people and stale participations. The clean path is a fresh import into a clean database; re-importing the fixed CSV over the old data would merge by name into the correct rows but leave the old misspelled people as orphan rows needing admin deletion.

## E. Students with no id printed anywhere — your decision

| Name | Projects | Note |
|---|---|---|
| Kamonchanok Arttanate | 1616, 1823 | appears twice, both docs omit the id |
| Nathanan Pornprapee | 1616, 1811 | same |
| Nattalie Shinkoi | 1616, 1829 | her earlier extracted id was wrong (belonged to another student) and was nulled |
| Sai Kham Sheng | 1710 | extracted id was wrong and nulled |

These are real students on title pages. Options: (a) you supply the real ids from the university records, (b) they import as students without ids (works, but unverifiable). Per your rule that a student always has an id, these are the only rows where the CSV cannot prove it.

## F. Proposed implementation (after your approval)

1. Add a `CANONICAL_PEOPLE` map to `steps/build_reviewed_csv.py`: squished variant name -> canonical display name, covering all of section A plus the student spellings in section B (keyed by id where one exists, so future re-extractions can't regress).
2. Rebuild `output/reviewed-import.csv`; verify each cluster collapses to exactly one display name (automated check comparing before/after distinct names).
3. No ground-truth records change (verbatim policy).
4. Fresh-import guidance for local + VM after you have the fixed CSV.

Open questions for you: Paranan spelling (B), Setthanant spelling (B), Seng pair confirmation (C), the 4 no-id students (E).

## Resolutions (2026-09-11, after review)

All section A fixes applied via `CANONICAL_PEOPLE` in the builder. Distinct CSV names went 411 -> 380 (35 variants collapsed). User decisions: Burmese names have no surnames (never merge on shared elements; spaces insignificant; Phone Pyae Kyaw Swar is a manual spaced form); Seng pair stays separate (different ids); the 4 no-id students import without ids as documented exceptions. Tie-breaks: Vitpornnitipacha (self-spelled on her GitHub/LinkedIn), Setthanant (Thai-romanization judgment, no online trace), Taechasit (his GitHub username), Jarukorn Thuengjitvilas (sp-1727), Kwangmin Kim. See the README section "Person-name canonicalization" for the durable record.
