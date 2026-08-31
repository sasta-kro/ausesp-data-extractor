from pathlib import Path
import argparse
import csv
import re

import fitz  # PyMuPDF


# We intentionally inspect only the beginning of each report.
DEFAULT_SCAN_LIMIT = 15


CHAPTER_1_PATTERNS = [
    # Chapter 1: Introduction
    # CHAPTER 1 INTRODUCTION
    # Chapter I: Introduction
    re.compile(
        r"^\s*chapter\s+(?:1|i|one)\b.*$",
        re.IGNORECASE,
    ),

    # 1. Introduction
    # 1 Introduction
    # 1.Introduction
    re.compile(
        r"^\s*1\s*[\.\:\-\)]?\s*introduction\b.*$",
        re.IGNORECASE,
    ),

    # I. Introduction
    re.compile(
        r"^\s*i\s*[\.\:\-\)]\s*introduction\b.*$",
        re.IGNORECASE,
    ),
]


def normalize_line(line):
    return " ".join(line.strip().split())


def looks_like_table_of_contents(text):
    """
    Prevents us from mistaking:
        Chapter 1: Introduction ........ 8

    inside the TOC for the real Chapter 1 page.
    """

    lower = text.lower()

    if re.search(r"table\s+of\s+contents?", lower):
        return True

    if re.search(r"table\s+of\s+content\b", lower):
        return True

    # A TOC often mentions many different chapters on the same page.
    chapters = re.findall(
        r"\bchapter\s+([1-9]|i{1,3}|iv|v|vi{0,3}|ix|x)\b",
        lower,
    )

    if len(set(chapters)) >= 3:
        return True

    # Lots of dotted leader lines are also a strong TOC signal.
    dotted_lines = len(
        re.findall(r"\.{3,}.*\d+\s*$", text, re.MULTILINE)
    )

    if dotted_lines >= 4:
        return True

    return False


def page_has_real_chapter_1(page):
    text = page.get_text("text", sort=True)

    if not text.strip():
        return False

    lines = [
        normalize_line(line)
        for line in text.splitlines()
        if normalize_line(line)
    ]

    # Chapter headings should occur near the top of the page.
    top_lines = lines[:20]

    found_heading = False

    for line_number, line in enumerate(top_lines):
        for pattern in CHAPTER_1_PATTERNS:
            if pattern.match(line):
                # Don't accept something buried well down the page.
                if line_number <= 10:
                    found_heading = True
                    break

        if found_heading:
            break

    if not found_heading:
        return False

    # The TOC itself contains "Chapter 1", so exclude TOC-like pages.
    if looks_like_table_of_contents(text):
        return False

    return True


def find_chapter_1(doc, scan_limit):
    pages_to_scan = min(scan_limit, doc.page_count)

    for page_index in range(pages_to_scan):
        page = doc[page_index]

        if page_has_real_chapter_1(page):
            return page_index

    return None


def cut_frontmatter(input_pdf, output_pdf, scan_limit):
    doc = fitz.open(input_pdf)

    chapter_1_index = find_chapter_1(doc, scan_limit)

    if chapter_1_index is None:
        result = {
            "filename": input_pdf.name,
            "total_pages": doc.page_count,
            "chapter1_pdf_page": "",
            "pages_saved": "",
            "status": "NOT_FOUND",
        }

        doc.close()
        return result

    # chapter_1_index is zero-based.
    # Example:
    # index 7 = physical PDF page 8.
    #
    # We want everything BEFORE Chapter 1,
    # so copy pages indexes 0 through 6.
    pages_to_keep = chapter_1_index

    if pages_to_keep <= 0:
        result = {
            "filename": input_pdf.name,
            "total_pages": doc.page_count,
            "chapter1_pdf_page": chapter_1_index + 1,
            "pages_saved": 0,
            "status": "CHAPTER_1_AT_START",
        }

        doc.close()
        return result

    output_doc = fitz.open()

    output_doc.insert_pdf(
        doc,
        from_page=0,
        to_page=chapter_1_index - 1,
    )

    output_doc.save(
        output_pdf,
        garbage=4,
        deflate=True,
    )

    result = {
        "filename": input_pdf.name,
        "total_pages": doc.page_count,
        "chapter1_pdf_page": chapter_1_index + 1,
        "pages_saved": pages_to_keep,
        "status": "OK",
    }

    output_doc.close()
    doc.close()

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Extract report front matter before Chapter 1."
    )

    parser.add_argument(
        "input_folder",
        type=Path,
        help="Folder containing the original PDFs",
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
        help="Maximum number of pages to inspect. Default: 15",
    )

    args = parser.parse_args()

    input_folder = args.input_folder
    output_folder = args.output_folder

    output_folder.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(input_folder.glob("*.pdf"))

    print(f"Found {len(pdf_files)} PDF files")
    print()

    results = []

    for number, pdf_path in enumerate(pdf_files, start=1):
        output_path = output_folder / pdf_path.name

        try:
            result = cut_frontmatter(
                pdf_path,
                output_path,
                args.scan_pages,
            )

            results.append(result)

            if result["status"] == "OK":
                print(
                    f"[{number}/{len(pdf_files)}] "
                    f"{pdf_path.name}: "
                    f"Chapter 1 = PDF page "
                    f"{result['chapter1_pdf_page']}, "
                    f"saved first {result['pages_saved']} pages"
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
                f"{pdf_path.name}: ERROR: {exc}"
            )

            results.append({
                "filename": pdf_path.name,
                "total_pages": "",
                "chapter1_pdf_page": "",
                "pages_saved": "",
                "status": f"ERROR: {exc}",
            })

    # Save an audit log so questionable files are easy to find.
    csv_path = output_folder / "processing_report.csv"

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "filename",
                "total_pages",
                "chapter1_pdf_page",
                "pages_saved",
                "status",
            ],
        )

        writer.writeheader()
        writer.writerows(results)

    print()
    print(f"Finished.")
    print(f"Log: {csv_path}")


if __name__ == "__main__":
    main()
