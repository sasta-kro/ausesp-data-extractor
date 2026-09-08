from pathlib import Path
import argparse
import csv
import fnmatch
import re
from collections import Counter

import pymupdf


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

# Only inspect the beginning of each report.
DEFAULT_SCAN_LIMIT = 15

# If the detected boundary starts at or below 35% of the page height,
# keep the whole physical page so we do not lose front matter above it.
DEFAULT_INCLUDE_PAGE_THRESHOLD = 0.35

# By default, process report PDFs only.
# The * after Report also catches names such as 26010_Report(1).pdf.
DEFAULT_INCLUDE_PATTERNS = ["*_Report*.pdf"]


# ---------------------------------------------------------------------------
# Boundary heading patterns
# ---------------------------------------------------------------------------

# Examples:
#   Chapter 1: Introduction
#   CHAPTER 1 INTRODUCTION
#   Chapter I: Introduction
#   Chapter One - Introduction
CHAPTER_1_FULL_PATTERN = re.compile(
    r"^\s*chapter\s+(?:1|i|one)\s*[\.\:\-\)]?\s*introduction\b",
    re.IGNORECASE,
)

# Examples:
#   Chapter 1
#   Chapter I
# followed by a separate line containing Introduction.
CHAPTER_1_ONLY_PATTERN = re.compile(
    r"^\s*chapter\s+(?:1|i|one)\s*[\.\:\-\)]?\s*$",
    re.IGNORECASE,
)

# Examples:
#   1. Introduction
#   1 Introduction
#   1.0 Introduction
NUMBERED_INTRO_PATTERN = re.compile(
    r"^\s*1(?:\.0)?\s*[\.\:\-\)]?\s*introduction\b",
    re.IGNORECASE,
)

# Example:
#   I. Introduction
ROMAN_INTRO_PATTERN = re.compile(
    r"^\s*i\s*[\.\:\-\)]\s*introduction\b",
    re.IGNORECASE,
)

# Fallback for older/non-chaptered reports such as 1912_Report.pdf:
#   Introduction
#   Introduction: Background
INTRODUCTION_ONLY_PATTERN = re.compile(
    r"^\s*introduction\b(?:\s*[:\-].*)?$",
    re.IGNORECASE,
)

# Evidence that real Chapter 1 content follows a heading.
SUBSECTION_PATTERN = re.compile(
    r"^\s*1\.\d+(?:\.\d+)*\b",
    re.IGNORECASE,
)

# Used to recognize standalone TOC/index page numbers.
PAGE_NUMBER_PATTERN = re.compile(
    r"^(?:\d+|[ivxlcdm]+|\d+\s*[-\u2013]\s*\d+)$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def normalize_line(line):
    """Collapse repeated whitespace and trim a line."""
    return " ".join(line.strip().split())


def glob_match(name, pattern):
    """Case-insensitive shell-style glob matching."""
    return fnmatch.fnmatch(name.casefold(), pattern.casefold())


def discover_pdfs(folder, include_patterns, ignore_patterns):
    """
    Find files directly inside folder.

    Include semantics:
      - If the user gives no --include args, DEFAULT_INCLUDE_PATTERNS are used.
      - If the user gives one or more --include args, they replace the defaults.

    Ignore semantics:
      - Every --ignore pattern is layered on top of the include patterns.
    """
    files = []

    for path in folder.iterdir():
        if not path.is_file():
            continue

        if not any(glob_match(path.name, p) for p in include_patterns):
            continue

        if any(glob_match(path.name, p) for p in ignore_patterns):
            continue

        files.append(path)

    return sorted(files, key=lambda p: p.name.casefold())


# ---------------------------------------------------------------------------
# PDF text + geometry extraction
# ---------------------------------------------------------------------------


def extract_lines(page):
    """
    Extract text lines while preserving their physical PDF coordinates.

    This matters because a TOC may store:

        Chapter 1: Introduction

    and its right-aligned page number as two separate text objects on the
    same visual row. Looking only at the text string can therefore create
    false positives.
    """
    output = []
    page_dict = page.get_text("dict", sort=True)

    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue

        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue

            text = normalize_line(
                "".join(span.get("text", "") for span in spans)
            )

            if not text:
                continue

            x0, y0, x1, y1 = line.get("bbox", (0, 0, 0, 0))

            output.append(
                {
                    "text": text,
                    "x0": x0,
                    "y0": y0,
                    "x1": x1,
                    "y1": y1,
                }
            )

    output.sort(key=lambda item: (item["y0"], item["x0"]))
    return output


def same_visual_row(a, b, tolerance=3.0):
    """Return True when two extracted lines are on approximately the same row."""
    a_center = (a["y0"] + a["y1"]) / 2
    b_center = (b["y0"] + b["y1"]) / 2
    return abs(a_center - b_center) <= tolerance


# ---------------------------------------------------------------------------
# Local TOC/index rejection
# ---------------------------------------------------------------------------


def row_has_right_page_number(lines, index, page_width):
    """
    Check whether a candidate row has a page number on its far right.

    This rejects TOC entries such as:

        Chapter 1: Introduction                         6

    even when PyMuPDF extracts the heading and the number as separate
    text objects.

    This is deliberately local. We do NOT reject an entire page merely
    because some part of it looks like a TOC/list page. That is important
    for reports where list material and the real Chapter 1 share a page.
    """
    candidate = lines[index]

    # Same text object contains dotted leaders + page number.
    if re.search(
        r"\.{2,}\s*(?:\d+|[ivxlcdm]+)\s*$",
        candidate["text"],
        re.IGNORECASE,
    ):
        return True

    # Same text object contains a trailing page number without dots.
    if re.search(
        r"\bintroduction\s+(?:\d+|[ivxlcdm]+)\s*$",
        candidate["text"],
        re.IGNORECASE,
    ):
        return True

    # Separate right-aligned text object on the same visual row.
    for other_index, other in enumerate(lines):
        if other_index == index:
            continue

        if not same_visual_row(candidate, other):
            continue

        if other["x0"] < page_width * 0.65:
            continue

        if PAGE_NUMBER_PATTERN.fullmatch(other["text"]):
            return True

    return False


def following_rows_look_indexed(lines, start_index, page_width, limit=8):
    """
    Check whether the rows immediately after a candidate mostly look like
    TOC/index entries with right-aligned page numbers.

    This is another local safeguard. It helps when the candidate's own
    page number is extracted strangely or is missing, while nearby TOC rows
    still expose the pattern.
    """
    row_indexes = []

    for index in range(start_index, min(len(lines), start_index + limit * 2)):
        item = lines[index]

        # Skip standalone page-number text objects. They belong to another
        # row and are checked through row_has_right_page_number().
        if PAGE_NUMBER_PATTERN.fullmatch(item["text"]):
            continue

        row_indexes.append(index)

        if len(row_indexes) >= limit:
            break

    if not row_indexes:
        return False

    indexed_count = sum(
        row_has_right_page_number(lines, index, page_width)
        for index in row_indexes
    )

    return (
        indexed_count >= 2
        and indexed_count >= len(row_indexes) * 0.40
    )


# ---------------------------------------------------------------------------
# Candidate validation
# ---------------------------------------------------------------------------


def following_text_looks_real(lines, start_index, page_width):
    """
    Validate that useful prose or real section content follows the heading.

    Real content commonly contains:
      - 1.1 Problem Statement
      - 1.1 Background
      - prose paragraphs

    A TOC/index instead tends to contain repeated right-aligned page numbers.
    """
    if following_rows_look_indexed(lines, start_index, page_width):
        return False

    texts = []

    for item in lines[start_index : start_index + 15]:
        if PAGE_NUMBER_PATTERN.fullmatch(item["text"]):
            continue
        texts.append(item["text"])

    # A heading at the very bottom of a page may have its body on the next
    # physical page. Do not reject that automatically.
    if not texts:
        return True

    # Strong evidence: a Chapter 1 subsection follows shortly afterward.
    if any(SUBSECTION_PATTERN.match(text) for text in texts[:6]):
        return True

    word_count = len(
        re.findall(r"\b[\w'-]+\b", " ".join(texts))
    )

    return word_count >= 20


def meaningful_words_before(lines, boundary_index, page_height):
    """
    Count meaningful words above the real boundary on the same physical page.

    If enough useful material appears above the boundary, keep that entire
    page even when the boundary itself starts before the normal percentage
    threshold.

    This handles cases such as:

        Objective
        <objective paragraph>
        Introduction
        <main report body>

    We prefer a little main-body leakage over losing that Objective section.
    """
    texts = []

    for item in lines[:boundary_index]:
        # Ignore extreme header/footer zones.
        if item["y0"] < page_height * 0.04:
            continue

        if item["y0"] > page_height * 0.94:
            continue

        if PAGE_NUMBER_PATTERN.fullmatch(item["text"]):
            continue

        texts.append(item["text"])

    return len(
        re.findall(r"\b[\w'-]+\b", " ".join(texts))
    )


# ---------------------------------------------------------------------------
# Boundary detection
# ---------------------------------------------------------------------------


def find_boundary_on_page(page):
    """
    Find the real beginning of the report body on one physical PDF page.

    Preferred boundary:
      - Chapter 1 / Chapter I / 1. Introduction

    Fallback boundary:
      - plain "Introduction" for older reports that do not use chapters

    Returns None if no reliable boundary is found.
    """
    lines = extract_lines(page)

    if not lines:
        return None

    page_width = page.rect.width
    page_height = page.rect.height

    for index, item in enumerate(lines):
        text = item["text"]

        boundary_type = None
        heading_text = text
        content_start_index = index + 1

        # ---------------------------------------------------------------
        # Chapter 1: Introduction
        # ---------------------------------------------------------------
        if CHAPTER_1_FULL_PATTERN.match(text):
            boundary_type = "CHAPTER_1"

        # ---------------------------------------------------------------
        # 1. Introduction / 1.0 Introduction
        # ---------------------------------------------------------------
        elif NUMBERED_INTRO_PATTERN.match(text):
            boundary_type = "CHAPTER_1"

        # ---------------------------------------------------------------
        # I. Introduction
        # ---------------------------------------------------------------
        elif ROMAN_INTRO_PATTERN.match(text):
            boundary_type = "CHAPTER_1"

        # ---------------------------------------------------------------
        # Chapter 1
        # Introduction
        # ---------------------------------------------------------------
        elif CHAPTER_1_ONLY_PATTERN.match(text):
            next_index = index + 1

            while (
                next_index < len(lines)
                and PAGE_NUMBER_PATTERN.fullmatch(lines[next_index]["text"])
            ):
                next_index += 1

            if next_index >= len(lines):
                continue

            next_text = lines[next_index]["text"]

            if not INTRODUCTION_ONLY_PATTERN.match(next_text):
                continue

            if row_has_right_page_number(lines, next_index, page_width):
                continue

            boundary_type = "CHAPTER_1"
            heading_text = f"{text} {next_text}"
            content_start_index = next_index + 1

        # ---------------------------------------------------------------
        # Fallback for non-chaptered reports:
        # Introduction
        # ---------------------------------------------------------------
        elif INTRODUCTION_ONLY_PATTERN.match(text):
            boundary_type = "INTRODUCTION"

        else:
            continue

        # Reject the candidate itself if it is a TOC/index row.
        if row_has_right_page_number(lines, index, page_width):
            continue

        # Reject a candidate followed by more TOC/index rows.
        if following_rows_look_indexed(
            lines,
            content_start_index,
            page_width,
        ):
            continue

        # Require real content after the candidate.
        if not following_text_looks_real(
            lines,
            content_start_index,
            page_width,
        ):
            continue

        preboundary_words = meaningful_words_before(
            lines,
            index,
            page_height,
        )

        return {
            "boundary_type": boundary_type,
            "heading": heading_text,
            "position_ratio": item["y0"] / page_height,
            "preboundary_words": preboundary_words,
        }

    return None


def find_boundary(doc, scan_limit):
    """
    Scan only the first N physical PDF pages.

    Also track how much extractable text exists so a failure can be reported as:
      - NO_TEXT_IN_SCAN
      - BOUNDARY_NOT_FOUND
    """
    pages_to_scan = min(scan_limit, doc.page_count)
    total_text_characters = 0

    for page_index in range(pages_to_scan):
        page = doc[page_index]

        page_text = page.get_text("text", sort=True)
        total_text_characters += len(page_text.strip())

        match = find_boundary_on_page(page)

        if match is not None:
            match["page_index"] = page_index
            match["total_text_characters"] = total_text_characters
            return match

    return {
        "page_index": None,
        "total_text_characters": total_text_characters,
    }


# ---------------------------------------------------------------------------
# PDF cutting
# ---------------------------------------------------------------------------


def empty_result(filename, total_pages, status):
    """Create a consistent result row for failures."""
    return {
        "filename": filename,
        "total_pages": total_pages,
        "boundary_type": "",
        "boundary_heading": "",
        "boundary_pdf_page": "",
        "boundary_start_percent": "",
        "boundary_page_included": "",
        "include_reason": "",
        "preboundary_words": "",
        "pages_saved": "",
        "status": status,
    }


def cut_frontmatter(
    input_pdf,
    output_pdf,
    scan_limit,
    include_page_threshold,
):
    """
    Create a shortened PDF containing the front matter.

    Boundary page policy:

    1. Boundary starts sufficiently far down the page:
       Keep the whole page.

    2. Significant useful text exists above the boundary on that page:
       Keep the whole page.

    3. Otherwise:
       Exclude the boundary page.

    This intentionally favors a small amount of Introduction/Chapter 1
    leakage over losing useful front matter.
    """
    doc = pymupdf.open(input_pdf)

    try:
        match = find_boundary(doc, scan_limit)

        if match["page_index"] is None:
            if match["total_text_characters"] < 40:
                status = "NO_TEXT_IN_SCAN"
            else:
                status = "BOUNDARY_NOT_FOUND"

            return empty_result(
                input_pdf.name,
                doc.page_count,
                status,
            )

        boundary_index = match["page_index"]
        position_ratio = match["position_ratio"]
        preboundary_words = match["preboundary_words"]

        start_percent = round(position_ratio * 100, 1)

        # ---------------------------------------------------------------
        # Decide whether to keep the physical boundary page.
        # ---------------------------------------------------------------
        if position_ratio >= include_page_threshold:
            include_boundary_page = True
            include_reason = "STARTS_AFTER_THRESHOLD"

        elif preboundary_words >= 20:
            include_boundary_page = True
            include_reason = "FRONTMATTER_ABOVE_BOUNDARY"

        else:
            include_boundary_page = False
            include_reason = "EXCLUDED_BOUNDARY_PAGE"

        if include_boundary_page:
            pages_to_keep = boundary_index + 1
        else:
            pages_to_keep = boundary_index

        if pages_to_keep <= 0:
            return {
                "filename": input_pdf.name,
                "total_pages": doc.page_count,
                "boundary_type": match["boundary_type"],
                "boundary_heading": match["heading"],
                "boundary_pdf_page": boundary_index + 1,
                "boundary_start_percent": start_percent,
                "boundary_page_included": "NO",
                "include_reason": "BOUNDARY_AT_START",
                "preboundary_words": preboundary_words,
                "pages_saved": 0,
                "status": "BOUNDARY_AT_START",
            }

        output_doc = pymupdf.open()

        try:
            output_doc.insert_pdf(
                doc,
                from_page=0,
                to_page=pages_to_keep - 1,
            )

            # Avoid stale output from a previous run.
            if output_pdf.exists():
                output_pdf.unlink()

            output_doc.save(
                output_pdf,
                garbage=4,
                deflate=True,
            )

        finally:
            output_doc.close()

        return {
            "filename": input_pdf.name,
            "total_pages": doc.page_count,
            "boundary_type": match["boundary_type"],
            "boundary_heading": match["heading"],
            "boundary_pdf_page": boundary_index + 1,
            "boundary_start_percent": start_percent,
            "boundary_page_included": (
                "YES" if include_boundary_page else "NO"
            ),
            "include_reason": include_reason,
            "preboundary_words": preboundary_words,
            "pages_saved": pages_to_keep,
            "status": "OK",
        }

    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Console output
# ---------------------------------------------------------------------------


def print_result(number, total, result):
    """Readable one-line result for each file."""
    prefix = f"[{number:03d}/{total:03d}]"
    status = result["status"]
    filename = result["filename"]

    if status == "OK":
        boundary_label = (
            "Chapter 1"
            if result["boundary_type"] == "CHAPTER_1"
            else "Introduction"
        )

        if result["boundary_page_included"] == "YES":
            action = "kept boundary page"
        else:
            action = "excluded boundary page"

        print(
            f"{prefix} OK       {filename} | "
            f"{boundary_label} p{result['boundary_pdf_page']} "
            f"@ {result['boundary_start_percent']}% | "
            f"{action} | saved {result['pages_saved']}"
        )

    elif status == "NO_TEXT_IN_SCAN":
        print(
            f"{prefix} NO-TEXT  {filename} | "
            "almost no extractable text in scanned pages"
        )

    elif status == "BOUNDARY_NOT_FOUND":
        print(
            f"{prefix} MISS     {filename} | "
            "text exists, but no supported Introduction boundary was found"
        )

    elif status == "BOUNDARY_AT_START":
        print(
            f"{prefix} START    {filename} | "
            "boundary is on the first page; nothing useful to cut before it"
        )

    else:
        print(f"{prefix} ERROR    {filename} | {status}")


def print_summary(results):
    counts = Counter(result["status"] for result in results)

    print()
    print("Summary")
    print(f"  OK:                 {counts.get('OK', 0)}")
    print(f"  Boundary not found: {counts.get('BOUNDARY_NOT_FOUND', 0)}")
    print(f"  No text in scan:    {counts.get('NO_TEXT_IN_SCAN', 0)}")
    print(f"  Boundary at start:  {counts.get('BOUNDARY_AT_START', 0)}")

    error_count = sum(
        count
        for status, count in counts.items()
        if status.startswith("ERROR:")
    )

    print(f"  Errors:             {error_count}")


# ---------------------------------------------------------------------------
# Command-line entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Extract senior-project report front matter while detecting "
            "Chapter 1 or a plain Introduction boundary."
        )
    )

    parser.add_argument(
        "input_folder",
        type=Path,
        help="Folder containing source PDFs",
    )

    parser.add_argument(
        "output_folder",
        type=Path,
        help="Folder for shortened PDFs",
    )

    parser.add_argument(
        "--scan-pages",
        type=int,
        default=DEFAULT_SCAN_LIMIT,
        help=(
            "Maximum number of physical pages to inspect. "
            f"Default: {DEFAULT_SCAN_LIMIT}"
        ),
    )

    parser.add_argument(
        "--include-if-after",
        type=float,
        default=DEFAULT_INCLUDE_PAGE_THRESHOLD,
        help=(
            "Keep the boundary page if the heading begins after this "
            "fraction of page height. Default: 0.35"
        ),
    )

    parser.add_argument(
        "--include",
        action="append",
        default=None,
        metavar="GLOB",
        help=(
            "File glob to include. Repeatable. If supplied, these patterns "
            "replace the default '*_Report*.pdf'. Quote globs in your shell."
        ),
    )

    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        metavar="GLOB",
        help=(
            "File glob to ignore after inclusion. Repeatable. "
            "Quote globs in your shell."
        ),
    )

    args = parser.parse_args()

    input_folder = args.input_folder
    output_folder = args.output_folder

    if not input_folder.exists():
        parser.error(f"Input folder does not exist: {input_folder}")

    if not input_folder.is_dir():
        parser.error(f"Input path is not a directory: {input_folder}")

    if args.scan_pages <= 0:
        parser.error("--scan-pages must be greater than 0")

    if not 0 <= args.include_if_after <= 1:
        parser.error("--include-if-after must be between 0 and 1")

    if input_folder.resolve() == output_folder.resolve():
        parser.error("Input and output folders must be different")

    include_patterns = (
        args.include
        if args.include
        else DEFAULT_INCLUDE_PATTERNS
    )

    ignore_patterns = args.ignore

    output_folder.mkdir(parents=True, exist_ok=True)

    pdf_files = discover_pdfs(
        input_folder,
        include_patterns,
        ignore_patterns,
    )

    print("Front-matter extractor")
    print(f"  Input:    {input_folder}")
    print(f"  Output:   {output_folder}")
    print(f"  Include:  {', '.join(include_patterns)}")
    print(
        f"  Ignore:   "
        f"{', '.join(ignore_patterns) if ignore_patterns else '(none)'}"
    )
    print(f"  Scan:     first {args.scan_pages} pages")
    print(f"  Found:    {len(pdf_files)} files")
    print()

    results = []

    for number, pdf_path in enumerate(pdf_files, start=1):
        output_path = output_folder / pdf_path.name

        try:
            result = cut_frontmatter(
                pdf_path,
                output_path,
                args.scan_pages,
                args.include_if_after,
            )

        except Exception as exc:
            result = empty_result(
                pdf_path.name,
                "",
                f"ERROR: {exc}",
            )

        results.append(result)
        print_result(number, len(pdf_files), result)

    csv_path = output_folder / "processing_report.csv"

    with open(csv_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "filename",
                "total_pages",
                "boundary_type",
                "boundary_heading",
                "boundary_pdf_page",
                "boundary_start_percent",
                "boundary_page_included",
                "include_reason",
                "preboundary_words",
                "pages_saved",
                "status",
            ],
        )

        writer.writeheader()
        writer.writerows(results)

    print_summary(results)
    print()
    print(f"CSV log: {csv_path}")


if __name__ == "__main__":
    main()
