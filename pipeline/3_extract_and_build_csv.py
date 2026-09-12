#!/usr/bin/env python3
"""Extract import-ready metadata from trimmed senior-project front-matter PDFs.

Pipeline for one PDF directory:
  1. Extract front-matter candidates (title, people, period, abstract, keywords)
     with multi-candidate scoring, because several reports carry stale template
     titles on approval pages or running headers.
  2. Classify title + abstract + keywords into the repository taxonomy keys
     read from config/taxonomy/values.yaml, so the emitted CSV can only
     reference keys the import adapter will accept.
  3. Emit the repository import CSV plus small reports.

Rows without an abstract are excluded from the CSV (the import adapter treats
a missing abstract as a commit-blocking error) and listed in the report.

Usage:
  .venv/bin/python sp_import.py --pdfs ../../resources/sp-heads/thinned-outputs \
      --taxonomy ../../config/taxonomy/values.yaml --output output
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

CSV_HEADERS = [
    "import_key", "title", "reference_code", "abstract", "academic_year",
    "semester", "program_key", "major_key", "course_key", "title_aliases",
    "students", "advisors", "co_advisors", "committee_members",
    "categories", "platforms", "domains", "topics", "technologies",
]

PROGRAM_KEY = "computer_science"
PROGRAM_KEY_IT = "information_technology"
COURSE_KEY = "senior_project"

# Candidate titles observed as template residue across the corpus
# (docs/dev-notes/archvies/CORPUS_AND_SEARCH_DESIGN.md). Values appearing in
# several unrelated reports are also detected by cross-file frequency.
KNOWN_TEMPLATE_TITLES = {
    "text classification for education publication",
}

SEMESTER_NAMES = {"1": "first", "2": "second", "summer": "summer"}

# Fictional placeholder names found in template residue on some approval pages.
PLACEHOLDER_NAMES = {"hal emmerich", "drago pettrovich madnar", "frank jaeger"}


@dataclass
class Metadata:
    project_id: str
    file: str
    pages: int = 0
    title_candidates: list[dict] = field(default_factory=list)
    canonical_title: str = ""
    aliases: list[str] = field(default_factory=list)
    phase: str = ""
    course_code: str = ""
    semester: str = ""
    academic_year: int | None = None
    students: list[dict] = field(default_factory=list)
    advisor: str | None = None
    committee: list[str] = field(default_factory=list)
    abstract: str | None = None
    keywords: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "id": self.project_id, "file": self.file, "pages": self.pages,
            "title_candidates": self.title_candidates,
            "canonical_title": self.canonical_title, "aliases": self.aliases,
            "phase": self.phase, "course_code": self.course_code,
            "semester": self.semester, "academic_year": self.academic_year,
            "students": self.students, "advisor": self.advisor,
            "committee": self.committee, "abstract": self.abstract,
            "keywords": self.keywords, "conflicts": self.conflicts,
        }


def squish(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def norm_title(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", squish(text).lower())


# ---------------------------------------------------------------- extraction

STUDENT_ID = re.compile(r"\b(\d{3})\s*-\s*(\d{4})\b")
PERIOD = re.compile(r"(?:Semester|Academic\s+Y\s?ear)\s*:?\s*\[?\s*([12]|summer)\s*/\s*(\d{4})", re.IGNORECASE)
PERIOD_PARENTHESES = re.compile(r"Senior Project\s*(?:1|2|I{1,3})?\s*\(?\s*([12]|summer)\s*/\s*(\d{4})\)?", re.IGNORECASE)
COURSE_CODE = re.compile(r"\b([A-Z]{2,4})\s*(\d{4})\b")
ADVISOR_LINE = re.compile(r"(?:Project\s+)?Advisor\s*:?\s*(.+)")
ADVISOR_FLOW = re.compile(r"(?:Project\s+Advisor|Advisor)\s*:\s*(.+?)(?:\s*\(|\s+Academic|\s+Committee|\s+The\s+Senior|$)")
COMMITTEE_LINE = re.compile(r"Project Committee\s*:?\s*(.+)")
KEYWORDS_LINE = re.compile(r"^Keywords?\s*[:\-–]?\s*(.+)$", re.IGNORECASE | re.MULTILINE)
TITLE_LABEL = re.compile(r"^(?:Project\s+)?[Tt]itle\s*:\s*(.*)$")
TITLE_FLOW = re.compile(r"Project\s+[Tt]itle\s*:\s*(.+?)\s+(?:Members|Academic|Authors|Project\s+Advisor|The\s+Senior)", re.IGNORECASE)
ABSTRACT_HEADING = re.compile(r"^\s*Abstract\s*:?\s*$", re.IGNORECASE | re.MULTILINE)
ABSTRACT_SECTION_END = re.compile(
    r"^(Keywords?\b|Acknowledg|Table of Contents|Chapter \d|References\b|List of)", re.IGNORECASE)


def page_lines(page) -> list[str]:
    text = (page.extract_text() or "").replace("​", "").replace("﻿", "")
    return [squish(line) for line in text.splitlines() if squish(line)]


def looks_like_toc(lines: list[str]) -> bool:
    joined = " ".join(lines[:6])
    return "Table of Contents" in joined or "Contents" == joined[:8]


STUDENT_BLOCK_MARKERS = re.compile(r"^(Submitted by|By|Authors?|Members)\s*:\s*", re.IGNORECASE)
STUDENT_BLOCK_END = re.compile(r"(Project Advisor|Project Committee|Academic Year|Semester|Approval Committee|The Senior Project commit)", re.IGNORECASE)
BARE_ID = re.compile(r"(?<!\d)(\d{7})(?!\d)")
ID_BEFORE_NAME = re.compile(r"^(\d{7})\s+(\S.*)$")
ID_AFTER_NAME = re.compile(r"^(\S.*?)\s*\(?\s*(\d{7})\s*\)?$")


def parse_students(lines: list[str]) -> list[tuple[str, str]]:
    """Parse `name ddd-dddd`, `name (ddddddd)`, and `ddddddd name` entries
    from Submitted-by / By / Authors blocks across layout generations."""
    students: list[tuple[str, str]] = []
    inside = False
    pending_name = ""
    for line in lines:
        if not inside:
            if STUDENT_BLOCK_MARKERS.search(line):
                inside = True
                pending_name = ""
                remainder = STUDENT_BLOCK_MARKERS.sub("", line, count=1)
                if remainder and not STUDENT_BLOCK_END.search(remainder):
                    entry = student_entry(remainder)
                    if entry:
                        students.append(entry)
                    else:
                        pending_name = remainder
            continue
        if STUDENT_BLOCK_END.search(line) or STUDENT_BLOCK_MARKERS.search(line):
            inside = False
            pending_name = ""
            continue
        entry = student_entry(line)
        if entry:
            students.append(entry)
            pending_name = ""
            continue
        bare = BARE_ID.fullmatch(line)
        if bare and pending_name:
            students.append((pending_name, bare.group(1)))
            pending_name = ""
        elif not bare:
            pending_name = line
    return students


def student_entry(line: str) -> tuple[str, str] | None:
    hyphen = STUDENT_ID.search(line)
    if hyphen:
        student_id = hyphen.group(1) + hyphen.group(2)
        name = squish(line[:hyphen.start()]).strip(" .,-:()")
        return (name, student_id) if name else None
    before = ID_BEFORE_NAME.match(line)
    if before:
        name = squish(before.group(2)).strip(" .,-:()")
        return (name, before.group(1)) if name else None
    after = ID_AFTER_NAME.match(line)
    if after:
        name = squish(after.group(1)).strip(" .,-:()")
        return (name, after.group(2)) if name else None
    return None



SOURCE_WEIGHTS = {"approval": 3, "cover": 2}


def choose_title(meta: Metadata, template_titles: set[str]) -> None:
    usable = [c for c in meta.title_candidates if norm_title(c["value"]) and norm_title(c["value"]) not in template_titles]
    dropped = [c for c in meta.title_candidates if c not in usable]

    # Agreement scoring: approval pages carry weight, covers slightly less, and
    # running headers add one point per page they repeat. This lets cover plus
    # headers outvote an approval-page typo (RANGOON vs YANGOON) while keeping
    # stale template values out entirely.
    scores: dict[str, int] = {}
    variants: dict[str, list[dict]] = {}
    for candidate in usable:
        normalized = norm_title(candidate["value"])
        source = candidate["source"].split("(")[0]
        weight = SOURCE_WEIGHTS.get(source)
        if weight is None:
            weight = candidate["source"].count("x") or 1
        scores[normalized] = scores.get(normalized, 0) + weight
        variants.setdefault(normalized, []).append(candidate)

    chosen = None
    if scores:
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_score = ranked[0][1]
        # Candidates within one point compete on informativeness: the longer
        # variant usually carries the subtitle that a short approval line or
        # header drops, while genuine conflicts rarely sit one point apart.
        winners = [normalized for normalized, score in ranked if top_score - score <= 1]
        best_normalized = max(winners, key=lambda normalized: len(normalized))
        best = None
        for source in ("cover", "approval", "header"):
            variant = next((c for c in variants[best_normalized] if c["source"].split("(")[0] == source), None)
            if variant:
                best = variant["value"]
                break
        chosen = best

    meta.canonical_title = chosen or ""
    seen = {norm_title(meta.canonical_title)} if chosen else set()
    for candidate in usable:
        normalized = norm_title(candidate["value"])
        if normalized not in seen:
            meta.aliases.append(candidate["value"])
            seen.add(normalized)
    for candidate in dropped:
        if norm_title(candidate["value"]) not in seen:
            meta.conflicts.append(f"template-residue title dropped: {candidate['value']} ({candidate['source']})")


TOC_LEADER = re.compile(r"\.{4,}| {6,}\.\.\.")
TOC_HEADING_LINE = re.compile(r"^(Table of Contents|Contents|List of Figures|List of Tables|ACKNOWLEDGEMENTS?)$", re.IGNORECASE)
TOC_ENTRY = re.compile(r"^(?:Chapter\s+)?\d+(?:\.\d+)*\s+\S.*?\s+\d+\s*$")


def toc_noise(line: str) -> bool:
    return bool(TOC_LEADER.search(line)) or bool(TOC_HEADING_LINE.match(line))


def extract_abstract(pages: list[list[str]]) -> str | None:
    """Collect the abstract starting at any `Abstract` heading. The abstract
    can begin on an approval page and continue across table-of-contents pages,
    so collection carries across pages while skipping TOC dot-leader noise."""
    body: list[str] = []
    started = False
    for lines in pages:
        for line in lines:
            if not started:
                if re.fullmatch(r"abstract\s*:?", line.strip(), re.IGNORECASE):
                    started = True
                    continue
                inline = re.match(r"^abstract\s*[:\-]?\s+(\S.*)$", line, re.IGNORECASE)
                if inline:
                    started = True
                    body.append(inline.group(1))
                continue
            if TOC_HEADING_LINE.match(line):
                if body:
                    return squish(" ".join(body))
                continue
            if toc_noise(line) or TOC_ENTRY.match(line):
                continue
            if ABSTRACT_SECTION_END.match(line):
                return squish(" ".join(body))
            body.append(line)
    if not (started and body):
        return None
    abstract = squish(" ".join(body))
    return re.sub(r"\s+((?:i{1,3}|iv|v{1,3}|\d{1,3}))$", "", abstract)


COVER_BOILERPLATE = re.compile(
    r"(assumption university|faculty of|department of|vincent mary|school of|"
    r"senior project report|senior project proposal|senior project [12]|^project$|^team\b|"
    r"submitted by|^advisor|^project advisor|^project committee|^committee\b|approval)", re.IGNORECASE)


def is_flow_layout(lines_list: list[list[str]]) -> bool:
    """Word-per-line extraction: the cover page itself splits every word.
    Later approval paragraphs can be word-split in otherwise normal files,
    so only the cover decides the document mode."""
    if not lines_list or not lines_list[0]:
        return False
    sample = lines_list[0]
    if len(sample) < 8:
        return False
    short = sum(1 for line in sample if len(line.split()) <= 2)
    return short / len(sample) > 0.7


TITLE_BOILERPLATE_TAIL = re.compile(
    r"\s*(Submitted (?:in|by|to)\b.*|In Partial Fulfil?ment.*|\d{7}\b.*)$", re.IGNORECASE)
LEADING_NOISE = re.compile(r"^(?:[ivx]+\s+)?(?:senior project(?: report| proposal)?|final report|proposal|report|[a-z]{2,4}\s?\d{4})\s+", re.IGNORECASE)


def clean_title_value(value: str) -> str:
    value = squish(value)
    value = re.sub(r"^\[?\s*\d{1,5}\]?\s+", "", value)  # "[1904] Title" bracket ids
    value = re.sub(r"^\d{7}\s+", "", value)  # bare student id glued to the title
    first_id = re.search(r"\s\d{7}\b", value)
    if first_id:
        value = value[:first_id.start()]
    value = TITLE_BOILERPLATE_TAIL.sub("", value)
    previous = None
    while previous != value:
        previous = value
        value = LEADING_NOISE.sub("", value)
    return value.strip(" .,-:")


TITLE_WORDS = re.compile(r"^(system|management|application|platform|web|analysis|design|project|senior|report|car|service|ordering|detection)$", re.IGNORECASE)


def trim_title_words(name: str) -> str:
    """Flow-captured names can swallow preceding title words; trim them."""
    tokens = name.split()
    while len(tokens) > 2 and TITLE_WORDS.match(tokens[0]):
        tokens.pop(0)
    return " ".join(tokens)


def flow_students(text: str) -> list[tuple[str, str]]:
    """Students from joined flow text: `Name 6218323,` and `6610918 Name,` forms."""
    students: list[tuple[str, str]] = []
    for match in re.finditer(r"([A-Z][A-Za-z .'-]{2,60}?)\s*\(?\s*(\d{7})\s*\)?", text):
        name = squish(match.group(1)).strip(" .,-:()")
        name = re.split(r"\s+by\s+", name)[-1]  # drop committee residue before a bare `by`
        name = trim_title_words(name)
        if name and len(name.split()) <= 5 and not COVER_BOILERPLATE.search(name):
            students.append((name, match.group(2)))
    for match in re.finditer(r"(\d{7})\s+([A-Z][A-Za-z .'-]{2,60}?)(?=,|\d{7}|Advisor|Committee|Academic|$)", text):
        name = squish(match.group(2)).strip(" .,-:()")
        name = re.sub(r"\s*\((?:CS|IT|CPE)[A-Z0-9 ]*\)\s*$", "", name).strip(" .,-:()")
        name = trim_title_words(name)
        if name and len(name.split()) <= 5 and not COVER_BOILERPLATE.search(name):
            students.append((name, match.group(1)))
    return students


def extract_metadata(path: Path) -> Metadata:
    project_id = re.search(r"(\d+)", path.stem).group(1)
    meta = Metadata(project_id=project_id, file=path.name)
    reader = PdfReader(str(path))
    meta.pages = len(reader.pages)
    pages = [page_lines(page) for page in reader.pages]
    flows = [squish(" ".join(lines)) for lines in pages]
    front = "\n".join("\n".join(p) for p in pages[:3])
    front_flow = " ".join(flows[:3])
    flow_mode = is_flow_layout(pages)

    period = PERIOD.search(front) or PERIOD.search(front_flow)
    if not period:
        period = PERIOD_PARENTHESES.search(front) or PERIOD_PARENTHESES.search(front_flow)
    if period:
        meta.semester = SEMESTER_NAMES[period.group(1)]
        meta.academic_year = int(period.group(2))

    code = COURSE_CODE.search(flows[0] if flows else "") or COURSE_CODE.search(front_flow)
    if code:
        meta.course_code = f"{code.group(1).upper()} {code.group(2)}"
    if re.search(r"PROPOSAL", front, re.IGNORECASE):
        meta.phase = "proposal"
    elif re.search(r"FINAL|REPORT", front, re.IGNORECASE):
        meta.phase = "final"

    candidates: list[dict] = []
    if flow_mode:
        match = TITLE_FLOW.search(front_flow)
        if match:
            candidates.append({"value": clean_title_value(match.group(1)), "source": "approval"})
        for flow in flows[:1]:
            cover = re.search(r"Senior Project Report\s+(.{5,200}?)(?:\s+\d{7}\s|\s+Advisor\s|\s+Team\b)", flow, re.IGNORECASE)
            if cover:
                candidates.append({"value": clean_title_value(cover.group(1)), "source": "cover"})
    else:
        # Old layout: title lines between the course/phase marker and labels.
        marker_index = None
        for index, line in enumerate(pages[0] if pages else []):
            if student_entry(line) or BARE_ID.search(line):
                continue
            if COURSE_CODE.search(line) or re.search(r"SENIOR PROJECT (PROPOSAL|REPORT)", line, re.IGNORECASE) or re.match(r"^Project\s*:", line, re.IGNORECASE):
                marker_index = index
                if re.match(r"^Project\s*:", line, re.IGNORECASE):
                    inline = squish(re.sub(r"^Project\s*:\s*", "", line, flags=re.IGNORECASE))
                    for following in pages[0][index + 1:index + 3]:
                        if inline:
                            break
                        if not (ADVISOR_LINE.search(following) or student_entry(following) or BARE_ID.search(following)):
                            inline = following
                    value = clean_title_value(inline)
                    if value and value.lower() != "project":
                        candidates.append({"value": value, "source": "cover"})
                break
        if marker_index is not None:
            title_lines = []
            for line in pages[0][marker_index + 1:]:
                if re.fullmatch(r"(SENIOR PROJECT [IV12 ]*|FINAL REPORT|PROPOSAL|by|Title)", line, re.IGNORECASE):
                    continue
                if ADVISOR_LINE.search(line) or COMMITTEE_LINE.search(line) or "Submitted by" in line or PERIOD.search(line) or re.match(r"^Team\b", line, re.IGNORECASE):
                    break
                title_lines.append(line)
            while title_lines and (len(title_lines[0]) <= 2 or title_lines[0].lower() in {"i", "ii", "iii"}):
                title_lines.pop(0)
            if title_lines:
                joined = clean_title_value(" ".join(title_lines))
                if joined:
                    candidates.append({"value": joined, "source": "cover"})
            # Newer layout: title sits above a bottom course line; collect the
            # non-boilerplate, non-person lines before the marker as well.
            pre_lines = []
            for line in pages[0][:marker_index]:
                if (len(line) <= 2 or COVER_BOILERPLATE.search(line) or student_entry(line)
                        or BARE_ID.search(line) or PERIOD.search(line) or COURSE_CODE.search(line)):
                    if pre_lines:
                        break
                    continue
                pre_lines.append(line)
            if pre_lines:
                joined = clean_title_value(" ".join(pre_lines))
                if joined and len(joined) > 6:
                    candidates.append({"value": joined, "source": "cover"})

        for lines in pages[1:3]:
            for index, line in enumerate(lines):
                label = TITLE_LABEL.match(line)
                if not label:
                    continue
                value = clean_title_value(label.group(1))
                if not value and index + 1 < len(lines):
                    value = clean_title_value(lines[index + 1])
                if value:
                    candidates.append({"value": value, "source": "approval"})

    header_counts: Counter[str] = Counter()
    for lines in pages[2:]:
        if not lines or looks_like_toc(lines):
            continue
        first = lines[0]
        if (len(first) > 6 and not STUDENT_ID.search(first) and not COURSE_CODE.fullmatch(first)
                and not first.lower().startswith("assumption") and not re.fullmatch(r"[ivxlc]+", first.lower())):
            header_counts[first] += 1
    for value, count in header_counts.items():
        if count >= 2:
            cleaned = clean_title_value(value)
            if cleaned:
                candidates.append({"value": cleaned, "source": f"header(x{count})"})
    meta.title_candidates = candidates

    advisor = None
    if flow_mode:
        match = ADVISOR_FLOW.search(front_flow)
        if match:
            advisor = re.split(r"\s+The\s+Senior", squish(match.group(1)))[0].rstrip(" .,:")
    else:
        advisor_matches = [squish(m.group(1)).rstrip(" .:") for m in ADVISOR_LINE.finditer(front)]
        advisor_matches = [a for a in advisor_matches if a.lower() not in {"", "none", "committee 1", "committee 2"} and not re.match(r"^\d", a) and squish(a).lower() not in PLACEHOLDER_NAMES]
        advisor = advisor_matches[0] if advisor_matches else None
    meta.advisor = advisor

    merged: dict[str, str] = {}
    parsed: list[tuple[str, str]] = []
    if flow_mode:
        parsed = flow_students(front_flow)
    else:
        person_block_lines = list(pages[0])
        for lines in pages[1:3]:
            person_block_lines.extend(lines)
        parsed = parse_students(person_block_lines)
    if not parsed and not flow_mode:
        # Some covers list names and IDs with no block label at all.
        parsed = [entry for line in person_block_lines for entry in [student_entry(line)] if entry]
    for name, student_id in parsed:
        merged.setdefault(student_id, name)
        if len(name) > len(merged[student_id]):
            merged[student_id] = name
    meta.students = [{"display_name": name, "student_id": sid} for sid, name in merged.items()]

    approval_text = " ".join(flows[1:3])
    committee_lines = [squish(m.group(1)) for m in COMMITTEE_LINE.finditer(front)]
    parenthesized = re.findall(r"\(([^)]+)\)", approval_text)
    committee = []
    for value in committee_lines + parenthesized + re.findall(r"Committee\s*\d?\s*:\s*([^,]+)", front_flow):
        value = squish(value).rstrip(" .,")
        if not value or STUDENT_ID.search(value) or BARE_ID.search(value):
            continue
        if "advisor" in value.lower() or "committee" in value.lower() or "member" in value.lower():
            continue
        if squish(value).lower() in PLACEHOLDER_NAMES:
            continue
        if value not in committee and (meta.advisor is None or norm_title(value) != norm_title(meta.advisor)):
            committee.append(value)
    meta.committee = committee

    meta.abstract = extract_abstract(pages)
    keywords: list[str] = []
    keyword_sources = [front_flow] if flow_mode else ["\n".join(lines) for lines in pages]
    for source_text in keyword_sources:
        for match in KEYWORDS_LINE.finditer(source_text):
            for part in re.split(r"[;,·]", match.group(1)):
                part = squish(part).strip(" .")
                if part and part.lower() not in {"keywords"} and len(part) <= 80:
                    keywords.append(part)
    seen = set()
    for keyword in keywords:
        normalized = keyword.lower()
        if normalized not in seen:
            meta.keywords.append(keyword)
            seen.add(normalized)
    return meta


# ------------------------------------------------------------- classification

def load_taxonomy_keys(path: Path) -> dict[str, set[str]]:
    keys: dict[str, set[str]] = {}
    for match in re.finditer(r"dimension:\s*(\w+),\s*key:\s*([\w_]+)", path.read_text()):
        keys.setdefault(match.group(1), set()).add(match.group(2))
    return keys


# Ordered rules: (facet, key, pattern). First match per facet-and-key wins;
# caps applied per facet after matching. Patterns are matched case-insensitively
# against title + abstract + keywords only, keeping classification conservative.
RULES: list[tuple[str, str, re.Pattern]] = [
    # category
    ("category", "ai_data", re.compile(r"\b(machine learning|deep learning|neural network|\bai\b|artificial intelligence|data mining|predictive model|classification model|recommendation|clustering|computer vision|opencv|tensorflow|yolo\b|\bcnn\b|\bllm\b|chatbot|mask detect\w*|detect(?:ing|s|ion)? (?:the )?faces|face mask detection)\b", re.I)),
    ("category", "game", re.compile(r"\b(game (design|development|engine|realism|mechanic)|gameplay|serious game|gamif)\w*\b", re.I)),
    ("category", "hardware_iot", re.compile(r"\b(arduino|raspberry pi|\biot\b|internet of things|embedded|microcontroller|sensor-based|wearable|wi-?fi)\w*\b", re.I)),
    ("category", "research", re.compile(r"\b(experiment|experimental study|comparative study|usability study|survey study|effect of|impact of|evaluation of|investigates|this (?:project|study) (?:investigat|analyz|propos))\b", re.I)),
    ("category", "software_application", re.compile(r"\b(application|management system|information system|website|web application|web-based|platform|portal|management|tracker|booking|schedul\w+|e-?commerce|marketplace|dashboard|digital interface)\w*\b", re.I)),
    # platform
    ("platform", "mobile", re.compile(r"\b(mobile[- ](?:app|application|phone|web|device app)|android|\bios\b|kotlin|swift|flutter|jetpack|react native)\w*\b", re.I)),
    ("platform", "game", re.compile(r"\b(unity|unreal|game engine|gameplay)\w*\b", re.I)),
    ("platform", "embedded_hardware", re.compile(r"\b(arduino|raspberry pi|embedded|microcontroller|wearable|sensor hardware)\w*\b", re.I)),
    ("platform", "desktop", re.compile(r"\b(desktop|windows application|wpf|winforms|java fx|standalone (?:program|application)|webcam)\w*\b", re.I)),
    ("platform", "web", re.compile(r"\b(web(?!cam)|website|web-based|web application|laravel|php\b|react|next\.?js|node|django|flask|wordpress|browser)\w*\b", re.I)),
    # domain
    ("domain", "healthcare", re.compile(r"\b(health|medical|patient|hospital|clinic|fitness|nutrition|wellness)\w*\b", re.I)),
    ("domain", "transportation", re.compile(r"\b(transport|traffic|parking|vehicle|transit|fleet|road)\w*\b", re.I)),
    ("domain", "e_commerce", re.compile(r"\b(e-?commerce|online (shop|store|marketplace)|shopping cart|store management)\w*\b", re.I)),
    ("domain", "finance", re.compile(r"\b(finance|financial|banking|insurance|stock|cryptocur)\w*\b", re.I)),
    ("domain", "security", re.compile(r"\b(security|surveillance|intrusion|vulnerability|encryption|authentication system)\w*\b", re.I)),
    ("domain", "entertainment", re.compile(r"\b(entertainment|music|movie|media|streaming|game|tourism|travel)\w*\b", re.I)),
    ("domain", "campus", re.compile(r"\b(campus|assumption university|\bau\b|canteen|dormitor|registrar|enrollment|scholarship|vincent mary school)\w*\b", re.I)),
    ("domain", "education", re.compile(r"\b(education|e-?learning|classroom|curriculum|teaching)\w*\b", re.I)),
    ("domain", "business", re.compile(r"\b(business|enterprise|inventory|erp|crm|workflow|logistics|supply chain|company|retail|restaurant|shop management|sales|r[eé]sum[eé])\w*\b", re.I)),
    # topic
    ("topic", "computer_vision", re.compile(r"\b(computer vision|image (processing|classification|recognition)|object detection|face (detection|recognition)|face mask|mask detection|detect(?:ing|s)? the faces|video analytic|opencv|yolo|\bcnn\b)\w*\b", re.I)),
    ("topic", "ocr", re.compile(r"\b(ocr|optical character|tesseract)\w*\b", re.I)),
    ("topic", "nlp", re.compile(r"\b(natural language|\bnlp\b|text classification|sentiment|topic model|language model|\bllm\b|chatbot)\w*\b", re.I)),
    ("topic", "gamification", re.compile(r"\bgamif\w*\b", re.I)),
    ("topic", "geolocation", re.compile(r"\b(geolocation|\bgps\b|location-based|beacon|map track)\w*\b", re.I)),
    ("topic", "recommender_system", re.compile(r"\brecommend\w*\b", re.I)),
    # technology
    ("technology", "react", re.compile(r"\breact(\s?native)?\b", re.I)),
    ("technology", "go", re.compile(r"\b(golang|go language)\b", re.I)),
    ("technology", "postgresql", re.compile(r"\bpostgre\w*\b", re.I)),
    ("technology", "opencv", re.compile(r"\bopencv\b", re.I)),
    ("technology", "unity", re.compile(r"\bunity\b", re.I)),
    ("technology", "python", re.compile(r"\bpython\b", re.I)),
    ("technology", "firebase", re.compile(r"\bfirebase\b", re.I)),
    ("technology", "nextjs", re.compile(r"\bnext\.?js\b", re.I)),
    ("technology", "nodejs", re.compile(r"\bnode\.js\b", re.I)),
    ("technology", "mongodb", re.compile(r"\bmongo\w*\b", re.I)),
    ("technology", "laravel", re.compile(r"\blaravel\b", re.I)),
    ("technology", "wordpress", re.compile(r"\bwordpress\b", re.I)),
    ("technology", "kotlin", re.compile(r"\bkotlin\b", re.I)),
    ("technology", "mysql", re.compile(r"\bmysql\b", re.I)),
    ("technology", "unreal_engine", re.compile(r"\bunreal engine\b", re.I)),
]

FACET_CAPS = {"category": 3, "platform": 3, "domain": 3, "topic": 3, "technology": 5}


def apply_domain_priorities(matched: dict[str, list[str]]) -> None:
    domains = matched.get("domain", [])
    # Campus is the university-scoped subset of education; keep the specific tag.
    if "campus" in domains and "education" in domains:
        domains.remove("education")
        matched["domain"] = domains
FACET_TO_COLUMNS = {
    "category": "categories", "platform": "platforms", "domain": "domains",
    "topic": "topics", "technology": "technologies",
}

# Terms that indicate richer taxonomy the repository does not carry yet; kept
# for the unmapped report so the vocabulary gap stays visible.
UNMAPPED_WATCH = re.compile(
    r"\b(next\.?js|node|laravel|mongodb|kotlin|tensorflow|keras|wordpress|graphql|n8n|gemini|sanity|unreal engine|raspberry pi|arduino|flutter|swift|django|flask|deep learning|machine learning|recommendation|sentiment|topic model|wearable|iot|data analytics|automation)\b", re.I)


def classify(meta: Metadata, taxonomy: dict[str, set[str]]) -> tuple[dict[str, list[str]], list[str]]:
    # Abstract-driven only: full-document text turns literature-review and
    # template mentions into false tags (see the corpus design note).
    text = " ".join([meta.canonical_title, meta.abstract or "", *meta.keywords])
    matched: dict[str, list[str]] = {}
    unmapped: list[str] = []
    for facet, key, pattern in RULES:
        if facet not in taxonomy or key not in taxonomy[facet]:
            continue
        if pattern.search(text) and key not in matched.get(facet, []):
            matched.setdefault(facet, []).append(key)
    for facet, keys in matched.items():
        matched[facet] = keys[: FACET_CAPS[facet]]
    apply_domain_priorities(matched)
    for term in UNMAPPED_WATCH.findall(text):
        normalized = squish(term).lower()
        if normalized not in unmapped:
            unmapped.append(normalized)
    return matched, unmapped


# ------------------------------------------------------------------- output

def json_field(values: list[dict | str]) -> str:
    return json.dumps(values, ensure_ascii=False)


def program_key_for(meta: Metadata) -> str:
    """IT-prefixed course codes belong to the Information Technology program."""
    return PROGRAM_KEY_IT if meta.course_code.upper().startswith("IT") else PROGRAM_KEY


def build_row(meta: Metadata, classification: dict[str, list[str]]) -> dict:
    def people(entries: list[str], role: str) -> list[dict]:
        result = []
        for name in entries:
            person = {"display_name": name}
            if role == "student" and False:
                pass
            result.append(person)
        return result

    row = {
        "import_key": f"sp-{meta.project_id}",
        "title": meta.canonical_title,
        "reference_code": meta.project_id,
        "abstract": meta.abstract or "",
        "academic_year": meta.academic_year or "",
        "semester": meta.semester,
        "program_key": program_key_for(meta),
        "major_key": "",
        "course_key": COURSE_KEY,
        "title_aliases": json_field(meta.aliases),
        "students": json.dumps(meta.students, ensure_ascii=False),
        "advisors": json.dumps([{"display_name": meta.advisor}] if meta.advisor else [], ensure_ascii=False),
        "co_advisors": json_field([]),
        "committee_members": json.dumps([{"display_name": name} for name in meta.committee], ensure_ascii=False),
    }
    for facet, column in FACET_TO_COLUMNS.items():
        row[column] = json_field(classification.get(facet, []))
    return row


HONORIFIC = re.compile(r"^(?:mr|mrs|ms|miss)\.?\s+", re.IGNORECASE)
ID_FRAGMENT = re.compile(
    r"[, ]+(?:(?:mr|mrs|ms|miss)\.?\s+)?(?:[A-Za-z'.\-]+\s+){0,3}\(?((?:\d{7}|\d{3}-\d{4}))\)?"
    r"(?:\s*\((?:CS|IT|CPE)[A-Z0-9 ]*\))?[, ]*$")


def strip_student_suffix(meta: Metadata) -> None:
    """Remove trailing student names, ids, honorifics, and course tags that
    unlabelled cover layouts let bleed into the title candidate. Name removal
    uses exact trailing-token equality; spelling variants are caught by the
    id-fragment pattern instead of fuzzy text matching."""
    for student in meta.students:
        student["display_name"] = HONORIFIC.sub("", student["display_name"].strip())
    title = meta.canonical_title
    changed = True
    while changed and title:
        changed = False
        fragment = ID_FRAGMENT.search(title)
        if fragment:
            title = title[:fragment.start()].rstrip(" .,-(")
            changed = True
            continue
        cleaned = title.rstrip(" .,-(")
        if cleaned != title:
            title = cleaned
            changed = True
            continue
        words = [word for word in title.split()]
        tails = {tuple(word.strip(" ,(").lower() for word in words[-take:])
                 for take in range(1, min(4, len(words)) + 1)}
        for student in meta.students:
            tokens = [token.strip(" ,(").lower() for token in student["display_name"].split()]
            for take in range(len(tokens), 1, -1) if len(tokens) > 1 else [1]:
                if len(words) - take < 2:
                    continue
                if tuple(tokens[-take:]) in tails:
                    words = words[:-take]
                    title = " ".join(words).rstrip(" .,-(")
                    tails = {tuple(word.strip(" ,(").lower() for word in words[-take:])
                             for take in range(1, min(4, len(words)) + 1)}
                    changed = True
                    break
            if changed:
                break
    meta.canonical_title = title


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdfs", type=Path, required=True)
    parser.add_argument("--taxonomy", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("output"))
    args = parser.parse_args()

    taxonomy = load_taxonomy_keys(args.taxonomy)
    if not taxonomy:
        print("taxonomy file yielded no keys", file=sys.stderr)
        return 2

    pdf_paths = sorted(args.pdfs.glob("*.pdf"))
    if not pdf_paths:
        print("no PDFs found", file=sys.stderr)
        return 2

    # Cross-file header frequency: a header candidate seen in many unrelated
    # reports is template residue regardless of the known list.
    header_counter: Counter[str] = Counter()
    metas: list[Metadata] = []
    for path in pdf_paths:
        meta = extract_metadata(path)
        metas.append(meta)
        for candidate in meta.title_candidates:
            if candidate["source"].startswith("header"):
                header_counter[norm_title(candidate["value"])] += 1
    template_titles = set(KNOWN_TEMPLATE_TITLES) | {
        title for title, count in header_counter.items() if count >= 4 and title
    }

    args.output.mkdir(parents=True, exist_ok=True)
    metadata_dir = args.output / "metadata"
    metadata_dir.mkdir(exist_ok=True)

    rows: list[dict] = []
    unmapped_terms: Counter[str] = Counter()
    report_lines: list[str] = ["# SP import extraction report", ""]
    excluded: list[str] = []

    for meta in metas:
        choose_title(meta, template_titles)
        strip_student_suffix(meta)
        classification, unmapped = classify(meta, taxonomy)
        for term in unmapped:
            unmapped_terms[term] += 1
        (metadata_dir / f"{meta.project_id}.json").write_text(
            json.dumps({**meta.to_json(), "classification": classification}, ensure_ascii=False, indent=1))

        # Only commit-blocking gaps exclude a row; missing publication
        # prerequisites surface as warnings in the import preview instead.
        blocking = []
        if not meta.canonical_title:
            blocking.append("no title")
        if not meta.abstract:
            blocking.append("no abstract")
        if not meta.academic_year or not meta.semester:
            blocking.append("no academic period")
        if blocking:
            excluded.append(f"{meta.project_id}: {', '.join(blocking)}")
        else:
            rows.append(build_row(meta, classification))
            warnings = []
            if not meta.students:
                warnings.append("no students")
            if not meta.advisor:
                warnings.append("no advisor")
            if not classification.get("category"):
                warnings.append("no category tag")
            if not classification.get("platform"):
                warnings.append("no platform tag")
            if warnings:
                report_lines.append(f"- {meta.project_id} warnings: {', '.join(warnings)}")
        if meta.conflicts:
            report_lines.append(f"- {meta.project_id}: " + "; ".join(meta.conflicts))

    with (args.output / "import.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(rows)

    report_lines += ["", f"- PDFs processed: {len(metas)}",
                     f"- rows emitted: {len(rows)}",
                     f"- rows excluded: {len(metas) - len(rows)}"]
    report_lines += ["", "## Excluded rows"] + ([f"- {line}" for line in excluded] or ["- none"])
    report_lines += ["", "## Unmapped vocabulary (repository taxonomy gap)"] + (
        [f"- {term}: {count} projects" for term, count in unmapped_terms.most_common()] or ["- none"])
    (args.output / "extraction-report.md").write_text("\n".join(report_lines) + "\n")

    print(f"processed {len(metas)} PDFs, emitted {len(rows)} rows to {args.output / 'import.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
