from pathlib import Path
import argparse
import csv
import re

import pymupdf


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# We only inspect the beginning of each report.
#
# The reports we have looked at so far typically begin Chapter 1 somewhere
# around physical PDF pages 4-10. Scanning 15 gives us some extra room while
# avoiding unnecessary processing of the whole report.
DEFAULT_SCAN_LIMIT = 15


# If Chapter 1 begins after this fraction of the physical page height,
# keep the WHOLE page.
#
# Example:
#
#     0.35 = 35% down the page
#
# So:
#
#     Chapter 1 at 10% down the page
#         -> page is mostly Chapter 1
#         -> EXCLUDE the page
#
#     Chapter 1 at 70% down the page
#         -> page contains useful front matter before Chapter 1
#         -> INCLUDE the whole page
#
# This is intentional. We prefer a small amount of Chapter 1 leaking into
# the shortened PDF rather than losing useful front matter such as:
#
#     - List of Figures
#     - List of Tables
#     - Abbreviations
#     - Acknowledgements
#
DEFAULT_INCLUDE_PAGE_THRESHOLD = 0.35


# ---------------------------------------------------------------------------
# Chapter 1 heading patterns
# ---------------------------------------------------------------------------

# Full forms:
#
#     Chapter 1: Introduction
#     Chapter 1 Introduction
#     CHAPTER 1: INTRODUCTION
#     Chapter I: Introduction
#     Chapter One: Introduction
#
CHAPTER_1_FULL_PATTERN = re.compile(
    r"^\s*chapter\s+(?:1|i|one)"
    r"\s*[\.\:\-\)]?\s*"
    r"introduction\b",
    re.IGNORECASE,
)


# A Chapter heading by itself:
#
#     Chapter 1
#
# followed on the next line by:
#
#     Introduction
#
CHAPTER_1_ONLY_PATTERN = re.compile(
    r"^\s*chapter\s+(?:1|i|one)"
    r"\s*[\.\:\-\)]?\s*$",
    re.IGNORECASE,
)


# Numbered forms:
#
#     1. Introduction
#     1 Introduction
#     1.Introduction
#     1: Introduction
#
NUMBERED_INTRO_PATTERN = re.compile(
    r"^\s*1\s*[\.\:\-\)]?\s*introduction\b",
    re.IGNORECASE,
)


# Roman numeral form:
#
#     I. Introduction
#
ROMAN_INTRO_PATTERN = re.compile(
    r"^\s*i\s*[\.\:\-\)]\s*introduction\b",
    re.IGNORECASE,
)


# Used when Chapter 1 and Introduction are split across two lines.
INTRODUCTION_ONLY_PATTERN = re.compile(
    r"^\s*introduction\b",
    re.IGNORECASE,
)


# Common subsection formats that usually appear shortly after the real
# Chapter 1 heading:
#
#     1.1 Problem Statement
#     1.1 Background
#     1.2 Scope
#
SUBSECTION_PATTERN = re.compile(
    r"^\s*1\.\d+(?:\.\d+)*\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------

def normalize_line(line):
    """
    Collapse repeated whitespace and remove whitespace from the beginning
    and end of a line.

    Example:

        "   Chapter   1:   Introduction  "

    becomes:

        "Chapter 1: Introduction"
    """

    return " ".join(line.strip().split())


def extract_lines_with_positions(page):
    """
    Extract text line-by-line while preserving the vertical position of
    each line on the physical PDF page.

    We need the vertical position because it lets us distinguish:

        Chapter 1 near the TOP of a page
            -> exclude that page

    from:

        List of Tables
        List of Figures
        ...
        Chapter 1 near the BOTTOM
            -> keep that page

    Returns a list like:

        [
            {
                "text": "Chapter 1: Introduction",
                "y0": 512.4,
                "y1": 529.2,
            },
            ...
        ]
    """

    page_dict = page.get_text("dict", sort=True)

    extracted_lines = []

    for block in page_dict.get("blocks", []):
        # Type 0 means a text block.
        if block.get("type") != 0:
            continue

        for line in block.get("lines", []):
            spans = line.get("spans", [])

            if not spans:
                continue

            # Combine all spans belonging to this visual line.
            text = "".join(
                span.get("text", "")
                for span in spans
            )

            text = normalize_line(text)

            if not text:
                continue

            bbox = line.get("bbox")

            if bbox:
                y0 = bbox[1]
                y1 = bbox[3]
            else:
                # Very unlikely fallback.
                y0 = 0
                y1 = 0

            extracted_lines.append({
                "text": text,
                "y0": y0,
                "y1": y1,
            })

    # Although sort=True normally handles reading order, explicitly sorting
    # by vertical position makes the behavior easier to reason about.
    extracted_lines.sort(
        key=lambda item: (item["y0"], item["y1"])
    )

    return extracted_lines


# ---------------------------------------------------------------------------
# TOC detection
# ---------------------------------------------------------------------------

def looks_like_toc_entry(line):
    """
    Decide whether ONE LINE looks like a Table of Contents entry.

    This is intentionally different from asking whether the WHOLE PAGE is
    a table of contents.

    That distinction is important because reports such as 26030 can have:

        List of Figures
        List of Tables
        Chapter 1: Introduction

    all on the same physical PDF page.

    Examples considered TOC-like:

        Chapter 1: Introduction ............ 6
        Chapter 1: Introduction             6
        1.1 Problem Statement .............. 8
    """

    line = normalize_line(line)

    # Dotted leader followed by a page number:
    #
    #     Chapter 1: Introduction ........ 6
    #
    if re.search(r"\.{2,}\s*\d+\s*$", line):
        return True

    # Chapter entry ending in a standalone page number:
    #
    #     Chapter 1: Introduction 6
    #
    if re.search(
        r"\bintroduction\s+\d+\s*$",
        line,
        re.IGNORECASE,
    ):
        return True

    # Generic numbered subsection with dotted leader:
    #
    #     1.1 Problem Statement ........ 8
    #
    if re.search(
        r"^\s*\d+(?:\.\d+)+.*\.{2,}\s*\d+\s*$",
        line,
    ):
        return True

    return False


def nearby_text_looks_like_real_content(lines, start_index):
    """
    Inspect the text immediately AFTER a possible Chapter 1 heading.

    A real chapter usually has things such as:

        1.1 Background
        1.1 Problem Statement

    and/or actual paragraph text.

    A TOC usually contains many short entries ending with page numbers.

    This function provides another safeguard against mistaking a TOC entry
    for the real chapter.
    """

    following = lines[start_index:start_index + 15]

    if not following:
        # A heading at the very bottom of the physical page may legitimately
        # have its content starting on the next page.
        #
        # We do not automatically reject it.
        return True

    texts = [item["text"] for item in following]

    # Strong evidence: a Chapter 1 subsection follows the heading.
    for text in texts[:6]:
        if SUBSECTION_PATTERN.match(text):
            return True

    # Count TOC-looking lines.
    toc_like_count = sum(
        1
        for text in texts
        if looks_like_toc_entry(text)
    )

    # Count words in the nearby content.
    combined_text = " ".join(texts)

    word_count = len(
        re.findall(r"\b[\w'-]+\b", combined_text)
    )

    # If most nearby lines look like TOC entries, this is probably not the
    # real chapter.
    if following and toc_like_count >= max(3, len(following) // 2):
        return False

    # Real chapter prose normally gives us plenty of words.
    if word_count >= 20:
        return True

    # Not enough evidence.
    return False


# ---------------------------------------------------------------------------
# Chapter 1 detection
# ---------------------------------------------------------------------------

def find_chapter_1_on_page(page):
    """
    Look for the REAL Chapter 1 heading on one PDF page.

    Returns None if no reliable heading is found.

    Otherwise returns a dictionary containing:

        {
            "y": vertical coordinate,
            "position_ratio": fraction down the page,
            "heading": detected heading text,
            "line_index": index of heading
        }

    position_ratio examples:

        0.10 -> about 10% down the page
        0.50 -> halfway down the page
        0.80 -> about 80% down the page
    """

    lines = extract_lines_with_positions(page)

    if not lines:
        return None

    page_height = page.rect.height

    if page_height <= 0:
        return None

    for index, item in enumerate(lines):
        line = item["text"]

        heading_text = None
        content_start_index = index + 1

        # ---------------------------------------------------------------
        # Case 1:
        #
        #     Chapter 1: Introduction
        #
        # ---------------------------------------------------------------

        if CHAPTER_1_FULL_PATTERN.match(line):
            heading_text = line

            # Reject:
            #
            #     Chapter 1: Introduction ........ 6
            #
            if looks_like_toc_entry(line):
                continue

        # ---------------------------------------------------------------
        # Case 2:
        #
        #     1. Introduction
        #
        # ---------------------------------------------------------------

        elif NUMBERED_INTRO_PATTERN.match(line):
            heading_text = line

            if looks_like_toc_entry(line):
                continue

        # ---------------------------------------------------------------
        # Case 3:
        #
        #     I. Introduction
        #
        # ---------------------------------------------------------------

        elif ROMAN_INTRO_PATTERN.match(line):
            heading_text = line

            if looks_like_toc_entry(line):
                continue

        # ---------------------------------------------------------------
        # Case 4:
        #
        #     Chapter 1
        #     Introduction
        #
        # ---------------------------------------------------------------

        elif CHAPTER_1_ONLY_PATTERN.match(line):
            if index + 1 >= len(lines):
                continue

            next_line = lines[index + 1]["text"]

            if not INTRODUCTION_ONLY_PATTERN.match(next_line):
                continue

            # Reject something such as:
            #
            #     Chapter 1
            #     Introduction ........ 6
            #
            if looks_like_toc_entry(next_line):
                continue

            heading_text = f"{line} {next_line}"

            # Actual content starts after both heading lines.
            content_start_index = index + 2

        else:
            continue

        # ---------------------------------------------------------------
        # Check what comes after the possible heading.
        # ---------------------------------------------------------------

        if not nearby_text_looks_like_real_content(
            lines,
            content_start_index,
        ):
            continue

        y = item["y0"]

        position_ratio = y / page_height

        return {
            "y": y,
            "position_ratio": position_ratio,
            "heading": heading_text,
            "line_index": index,
        }

    return None


def find_chapter_1(doc, scan_limit):
    """
    Scan only the first N physical PDF pages.

    Returns:

        {
            "page_index": zero-based physical page index,
            "position_ratio": where the heading begins,
            "heading": matched heading text,
        }

    or None.
    """

    pages_to_scan = min(
        scan_limit,
        doc.page_count,
    )

    for page_index in range(pages_to_scan):
        page = doc[page_index]

        match = find_chapter_1_on_page(page)

        if match is not None:
            return {
                "page_index": page_index,
                "position_ratio": match["position_ratio"],
                "heading": match["heading"],
            }

    return None


# ---------------------------------------------------------------------------
# PDF cutting
# ---------------------------------------------------------------------------

def cut_frontmatter(
    input_pdf,
    output_pdf,
    scan_limit,
    include_page_threshold,
):
    """
    Detect Chapter 1 and create a shortened PDF containing the front matter.

    There are two cases.

    CASE A
    ------

    Chapter 1 starts near the top:

        [ Chapter 1 ]
        lots of chapter content
        ...

    We EXCLUDE that physical page.

    CASE B
    ------

    Useful front matter appears first:

        List of Figures
        List of Tables
        ...

        [ Chapter 1 ]

    We INCLUDE that whole physical page.

    This intentionally allows a small amount of Chapter 1 to leak into the
    output rather than throwing away useful front matter.
    """

    doc = pymupdf.open(input_pdf)

    try:
        chapter_match = find_chapter_1(
            doc,
            scan_limit,
        )

        if chapter_match is None:
            return {
                "filename": input_pdf.name,
                "total_pages": doc.page_count,
                "chapter1_pdf_page": "",
                "chapter1_start_percent": "",
                "chapter1_page_included": "",
                "pages_saved": "",
                "status": "NOT_FOUND",
            }

        chapter_1_index = chapter_match["page_index"]
        position_ratio = chapter_match["position_ratio"]

        # Convert to a nicer percentage for logging.
        start_percent = round(position_ratio * 100, 1)

        # ---------------------------------------------------------------
        # Decide whether to keep the physical page containing Chapter 1.
        # ---------------------------------------------------------------

        include_chapter_page = (
            position_ratio >= include_page_threshold
        )

        if include_chapter_page:
            # Example:
            #
            # Chapter 1 is physical page 7
            # zero-based index = 6
            #
            # Keep indexes:
            #
            #     0 through 6
            #
            # = physical pages 1 through 7.
            #
            pages_to_keep = chapter_1_index + 1

        else:
            # Chapter 1 starts near the top.
            #
            # Keep everything BEFORE the Chapter 1 page.
            #
            # Example:
            #
            # Chapter 1 is physical page 7
            # zero-based index = 6
            #
            # Keep indexes:
            #
            #     0 through 5
            #
            # = physical pages 1 through 6.
            #
            pages_to_keep = chapter_1_index

        # Chapter 1 appears on the first physical page.
        if pages_to_keep <= 0:
            return {
                "filename": input_pdf.name,
                "total_pages": doc.page_count,
                "chapter1_pdf_page": chapter_1_index + 1,
                "chapter1_start_percent": start_percent,
                "chapter1_page_included": "NO",
                "pages_saved": 0,
                "status": "CHAPTER_1_AT_START",
            }

        output_doc = pymupdf.open()

        try:
            output_doc.insert_pdf(
                doc,
                from_page=0,
                to_page=pages_to_keep - 1,
            )

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
            "chapter1_pdf_page": chapter_1_index + 1,
            "chapter1_start_percent": start_percent,
            "chapter1_page_included": (
                "YES"
                if include_chapter_page
                else "NO"
            ),
            "pages_saved": pages_to_keep,
            "status": "OK",
        }

    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Command-line program
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Extract senior-project report front matter while "
            "automatically detecting the start of Chapter 1."
        )
    )

    parser.add_argument(
        "input_folder",
        type=Path,
        help="Folder containing the original PDF reports",
    )

    parser.add_argument(
        "output_folder",
        type=Path,
        help="Folder where shortened PDFs will be written",
    )

    parser.add_argument(
        "--scan-pages",
        type=int,
        default=DEFAULT_SCAN_LIMIT,
        help=(
            "Maximum number of physical PDF pages to inspect "
            f"for Chapter 1. Default: {DEFAULT_SCAN_LIMIT}"
        ),
    )

    parser.add_argument(
        "--include-if-after",
        type=float,
        default=DEFAULT_INCLUDE_PAGE_THRESHOLD,
        help=(
            "Keep the physical Chapter 1 page when the heading "
            "begins after this fraction of the page height. "
            f"Default: {DEFAULT_INCLUDE_PAGE_THRESHOLD} "
            "(35%% down the page)."
        ),
    )

    args = parser.parse_args()

    input_folder = args.input_folder
    output_folder = args.output_folder

    # ---------------------------------------------------------------
    # Basic argument validation
    # ---------------------------------------------------------------

    if not input_folder.exists():
        parser.error(
            f"Input folder does not exist: {input_folder}"
        )

    if not input_folder.is_dir():
        parser.error(
            f"Input path is not a directory: {input_folder}"
        )

    if args.scan_pages <= 0:
        parser.error(
            "--scan-pages must be greater than 0"
        )

    if not 0 <= args.include_if_after <= 1:
        parser.error(
            "--include-if-after must be between 0 and 1"
        )

    output_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Only PDFs directly inside the input directory are processed.
    pdf_files = sorted(
        input_folder.glob("*.pdf")
    )

    print(
        f"Found {len(pdf_files)} PDF files"
    )
    print()

    results = []

    # ---------------------------------------------------------------
    # Process PDFs
    # ---------------------------------------------------------------

    for number, pdf_path in enumerate(
        pdf_files,
        start=1,
    ):
        output_path = output_folder / pdf_path.name

        try:
            result = cut_frontmatter(
                pdf_path,
                output_path,
                args.scan_pages,
                args.include_if_after,
            )

            results.append(result)

            if result["status"] == "OK":
                included = (
                    result["chapter1_page_included"] == "YES"
                )

                page_action = (
                    "included Chapter 1 page"
                    if included
                    else "excluded Chapter 1 page"
                )

                print(
                    f"[{number}/{len(pdf_files)}] "
                    f"{pdf_path.name}: "
                    f"Chapter 1 = PDF page "
                    f"{result['chapter1_pdf_page']}, "
                    f"starts at "
                    f"{result['chapter1_start_percent']}%, "
                    f"{page_action}, "
                    f"saved first "
                    f"{result['pages_saved']} pages"
                )

            else:
                print(
                    f"[{number}/{len(pdf_files)}] "
                    f"{pdf_path.name}: "
                    f"{result['status']}"
                )

        except Exception as exc:
            print(
                f"[{number}/{len(pdf_files)}] "
                f"{pdf_path.name}: "
                f"ERROR: {exc}"
            )

            results.append({
                "filename": pdf_path.name,
                "total_pages": "",
                "chapter1_pdf_page": "",
                "chapter1_start_percent": "",
                "chapter1_page_included": "",
                "pages_saved": "",
                "status": f"ERROR: {exc}",
            })

    # ---------------------------------------------------------------
    # Write audit CSV
    # ---------------------------------------------------------------

    csv_path = (
        output_folder
        / "processing_report.csv"
    )

    with open(
        csv_path,
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "filename",
                "total_pages",
                "chapter1_pdf_page",
                "chapter1_start_percent",
                "chapter1_page_included",
                "pages_saved",
                "status",
            ],
        )

        writer.writeheader()
        writer.writerows(results)

    print()
    print("Finished.")
    print(f"Log: {csv_path}")


if __name__ == "__main__":
    main()
