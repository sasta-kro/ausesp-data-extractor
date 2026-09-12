from pathlib import Path
import argparse
import csv
import fnmatch
import hashlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections import Counter


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

# Source files handled by the preparation step.
DEFAULT_INCLUDE_PATTERNS = [
    "*_Report*.pdf",
    "*_Report*.zip",
]

# Ignore obviously non-report PDFs when a report ZIP contains several PDFs.
DEFAULT_MEMBER_IGNORE_PATTERNS = [
    "*slide*.pdf",
    "*slides*.pdf",
    "*poster*.pdf",
    "*presentation*.pdf",
    "*external*exposure*.pdf",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def glob_match(name, pattern):
    return fnmatch.fnmatch(name.casefold(), pattern.casefold())


def matches_any(name, patterns):
    return any(glob_match(name, pattern) for pattern in patterns)


def discover_sources(folder, include_patterns, ignore_patterns):
    files = []

    for path in folder.iterdir():
        if not path.is_file():
            continue

        if not matches_any(path.name, include_patterns):
            continue

        if matches_any(path.name, ignore_patterns):
            continue

        files.append(path)

    return sorted(files, key=lambda p: p.name.casefold())


def sha256(path):
    digest = hashlib.sha256()

    with open(path, "rb") as file:
        while True:
            chunk = file.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)

    return digest.hexdigest()


def next_available_path(path):
    """
    Return path if unused, otherwise append __2, __3, ... before suffix.
    """
    if not path.exists():
        return path

    counter = 2

    while True:
        candidate = path.with_name(
            f"{path.stem}__{counter}{path.suffix}"
        )

        if not candidate.exists():
            return candidate

        counter += 1


def copy_without_overwriting(source, target):
    """
    Copy source into staging.

    If target already exists with identical bytes, reuse it.
    If target exists with different bytes, create a numbered filename.
    """
    if target.exists():
        if sha256(source) == sha256(target):
            return target, "DUPLICATE_REUSED"

        target = next_available_path(target)

    shutil.copy2(source, target)
    return target, "COPIED"


def clean_member_name(name):
    """Return only the basename of a ZIP member for safe staging."""
    return Path(name.replace("\\", "/")).name


def usable_zip_members(zip_file, member_ignore_patterns):
    """
    Return candidate PDF and DOCX members from a ZIP without extracting it.
    """
    pdf_members = []
    docx_members = []

    for info in zip_file.infolist():
        if info.is_dir():
            continue

        normalized = info.filename.replace("\\", "/")

        if normalized.startswith("__MACOSX/"):
            continue

        base_name = clean_member_name(normalized)

        if not base_name:
            continue

        lower = base_name.casefold()

        if lower.endswith(".pdf"):
            if matches_any(base_name, member_ignore_patterns):
                continue
            pdf_members.append(info)

        elif lower.endswith(".docx"):
            docx_members.append(info)

    return pdf_members, docx_members


def choose_pdf_member(pdf_members):
    """
    Conservatively choose one PDF from a report ZIP.

    Rules:
      1. Exactly one PDF -> choose it.
      2. Multiple PDFs, but exactly one filename contains 'report' -> choose it.
      3. Otherwise -> ambiguous; do not guess.
    """
    if len(pdf_members) == 1:
        return pdf_members[0], "ONLY_PDF"

    report_named = [
        member
        for member in pdf_members
        if "report" in clean_member_name(member.filename).casefold()
    ]

    if len(report_named) == 1:
        return report_named[0], "UNIQUE_REPORT_NAMED_PDF"

    return None, "AMBIGUOUS"


def extract_zip_member_to_path(zip_file, member, target):
    """
    Stream one selected ZIP member directly to target.

    We do not extract arbitrary archive paths, which avoids path traversal
    issues and avoids unpacking unnecessary files.
    """
    if target.exists():
        target = next_available_path(target)

    with zip_file.open(member, "r") as source:
        with open(target, "wb") as output:
            shutil.copyfileobj(source, output)

    return target


# ---------------------------------------------------------------------------
# Preparation
# ---------------------------------------------------------------------------


def prepare_direct_pdf(source, staging_folder):
    target = staging_folder / source.name
    staged_path, copy_status = copy_without_overwriting(source, target)

    return {
        "source": source.name,
        "source_type": "PDF",
        "staged_file": staged_path.name,
        "details": copy_status,
        "status": "READY",
    }


def prepare_zip(source, staging_folder, member_ignore_patterns):
    try:
        with zipfile.ZipFile(source, "r") as archive:
            pdf_members, docx_members = usable_zip_members(
                archive,
                member_ignore_patterns,
            )

            selected, selection_reason = choose_pdf_member(pdf_members)

            if selected is None:
                if not pdf_members and docx_members:
                    return {
                        "source": source.name,
                        "source_type": "ZIP",
                        "staged_file": "",
                        "details": (
                            f"0 PDF candidates; {len(docx_members)} DOCX candidate(s)"
                        ),
                        "status": "DOCX_ONLY",
                    }

                if not pdf_members:
                    return {
                        "source": source.name,
                        "source_type": "ZIP",
                        "staged_file": "",
                        "details": "No usable PDF found in archive",
                        "status": "NO_PDF_IN_ZIP",
                    }

                names = "; ".join(
                    clean_member_name(member.filename)
                    for member in pdf_members[:8]
                )

                if len(pdf_members) > 8:
                    names += "; ..."

                return {
                    "source": source.name,
                    "source_type": "ZIP",
                    "staged_file": "",
                    "details": (
                        f"{len(pdf_members)} PDF candidates: {names}"
                    ),
                    "status": "AMBIGUOUS_ZIP",
                }

            # Normalize the staged name from the archive name.
            # Example:
            #   1616_Report.zip -> 1616_Report.pdf
            target = staging_folder / f"{source.stem}.pdf"
            staged_path = extract_zip_member_to_path(
                archive,
                selected,
                target,
            )

            return {
                "source": source.name,
                "source_type": "ZIP",
                "staged_file": staged_path.name,
                "details": (
                    f"{selection_reason}; member="
                    f"{clean_member_name(selected.filename)}"
                ),
                "status": "READY",
            }

    except zipfile.BadZipFile:
        return {
            "source": source.name,
            "source_type": "ZIP",
            "staged_file": "",
            "details": "Archive is not a valid ZIP file",
            "status": "BAD_ZIP",
        }

    except RuntimeError as exc:
        # Often raised for encrypted ZIP members.
        return {
            "source": source.name,
            "source_type": "ZIP",
            "staged_file": "",
            "details": str(exc),
            "status": "ZIP_ERROR",
        }


def prepare_source(source, staging_folder, member_ignore_patterns):
    suffix = source.suffix.casefold()

    if suffix == ".pdf":
        return prepare_direct_pdf(source, staging_folder)

    if suffix == ".zip":
        return prepare_zip(
            source,
            staging_folder,
            member_ignore_patterns,
        )

    return {
        "source": source.name,
        "source_type": suffix.lstrip(".").upper(),
        "staged_file": "",
        "details": "Unsupported source type",
        "status": "UNSUPPORTED",
    }


# ---------------------------------------------------------------------------
# Console output
# ---------------------------------------------------------------------------


def print_result(number, total, result):
    prefix = f"[{number:03d}/{total:03d}]"
    status = result["status"]

    if status == "READY":
        print(
            f"{prefix} READY    {result['source']} -> "
            f"{result['staged_file']}"
        )

    elif status == "DOCX_ONLY":
        print(
            f"{prefix} DOCX     {result['source']} | "
            f"{result['details']}"
        )

    elif status == "AMBIGUOUS_ZIP":
        print(
            f"{prefix} AMBIG    {result['source']} | "
            f"multiple possible report PDFs"
        )

    else:
        print(
            f"{prefix} {status:<8} {result['source']} | "
            f"{result['details']}"
        )


def print_summary(results):
    counts = Counter(result["status"] for result in results)

    print()
    print("Preparation summary")

    for status in [
        "READY",
        "DOCX_ONLY",
        "AMBIGUOUS_ZIP",
        "NO_PDF_IN_ZIP",
        "BAD_ZIP",
        "ZIP_ERROR",
        "UNSUPPORTED",
    ]:
        print(f"  {status:<15} {counts.get(status, 0)}")


# ---------------------------------------------------------------------------
# Optional slicer invocation
# ---------------------------------------------------------------------------


def run_slicer(slicer_path, staging_folder, output_folder):
    """Call trim_frontmatter.py using the current Python interpreter."""
    command = [
        sys.executable,
        str(slicer_path),
        str(staging_folder),
        str(output_folder),
    ]

    print()
    print("Running slicer")
    print("  " + " ".join(command))
    print()

    completed = subprocess.run(command)

    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Prepare senior-project report files by staging direct PDFs and "
            "extracting report PDFs from ZIP archives."
        )
    )

    parser.add_argument(
        "source_folder",
        type=Path,
        help="Folder containing raw PDFs and ZIP archives",
    )

    parser.add_argument(
        "staging_folder",
        type=Path,
        help="Folder where normalized report PDFs will be staged",
    )

    parser.add_argument(
        "--include",
        action="append",
        default=None,
        metavar="GLOB",
        help=(
            "Source glob to include. Repeatable. If supplied, replaces the "
            "defaults '*_Report*.pdf' and '*_Report*.zip'."
        ),
    )

    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        metavar="GLOB",
        help="Source glob to ignore after inclusion. Repeatable.",
    )

    parser.add_argument(
        "--member-ignore",
        action="append",
        default=[],
        metavar="GLOB",
        help=(
            "Additional PDF-member glob to ignore inside ZIP archives. "
            "Repeatable and added on top of built-in slide/poster ignores."
        ),
    )

    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete the staging folder before preparing files",
    )

    parser.add_argument(
        "--run-slicer",
        type=Path,
        metavar="OUTPUT_FOLDER",
        help=(
            "After preparation, run trim_frontmatter.py automatically and "
            "write sliced PDFs to this folder."
        ),
    )

    parser.add_argument(
        "--slicer",
        type=Path,
        default=Path(__file__).with_name("trim_frontmatter.py"),
        help=(
            "Path to trim_frontmatter.py when using --run-slicer. "
            "Default: trim_frontmatter.py next to this script."
        ),
    )

    args = parser.parse_args()

    source_folder = args.source_folder
    staging_folder = args.staging_folder

    if not source_folder.exists():
        parser.error(f"Source folder does not exist: {source_folder}")

    if not source_folder.is_dir():
        parser.error(f"Source path is not a directory: {source_folder}")

    if source_folder.resolve() == staging_folder.resolve():
        parser.error("Source and staging folders must be different")

    include_patterns = (
        args.include
        if args.include
        else DEFAULT_INCLUDE_PATTERNS
    )

    member_ignore_patterns = (
        DEFAULT_MEMBER_IGNORE_PATTERNS
        + args.member_ignore
    )

    if args.clean and staging_folder.exists():
        shutil.rmtree(staging_folder)

    staging_folder.mkdir(parents=True, exist_ok=True)

    sources = discover_sources(
        source_folder,
        include_patterns,
        args.ignore,
    )

    print("Report preparation")
    print(f"  Source:   {source_folder}")
    print(f"  Staging:  {staging_folder}")
    print(f"  Include:  {', '.join(include_patterns)}")
    print(
        f"  Ignore:   "
        f"{', '.join(args.ignore) if args.ignore else '(none)'}"
    )
    print(f"  Found:    {len(sources)} source files")
    print()

    results = []

    for number, source in enumerate(sources, start=1):
        try:
            result = prepare_source(
                source,
                staging_folder,
                member_ignore_patterns,
            )

        except Exception as exc:
            result = {
                "source": source.name,
                "source_type": source.suffix.lstrip(".").upper(),
                "staged_file": "",
                "details": str(exc),
                "status": "ERROR",
            }

        results.append(result)
        print_result(number, len(sources), result)

    csv_path = staging_folder / "preparation_report.csv"

    with open(csv_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "source",
                "source_type",
                "staged_file",
                "details",
                "status",
            ],
        )

        writer.writeheader()
        writer.writerows(results)

    print_summary(results)
    print()
    print(f"CSV log: {csv_path}")

    if args.run_slicer is not None:
        slicer_path = args.slicer

        if not slicer_path.exists():
            parser.error(f"Slicer script does not exist: {slicer_path}")

        run_slicer(
            slicer_path,
            staging_folder,
            args.run_slicer,
        )


if __name__ == "__main__":
    main()
