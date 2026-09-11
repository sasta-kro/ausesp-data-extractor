#!/usr/bin/env python3
"""Crop a logo out of a staged PDF page, or pass through a DOCX media image.

Modes:
  --pdf <file> --page N --box X0,Y0,X1,Y1   crop fractions of the page (0.0-1.0,
                                            origin top-left) rendered at 300 DPI
  --image <file> --box X0,Y0,X1,Y1          crop fractions of a plain image file
  --media <file>                            copy a staged media image instead

The crop auto-trims near-uniform borders and is rejected if what remains is
smaller than 40 px on either side, so a wrong box fails loudly instead of
producing a sliver. Prints the output size; on success the PNG is written to
--out.

Usage: python3 steps/crop_logo.py --pdf <path> --page N --box 0.30,0.10,0.70,0.25 --out <path>
       python3 steps/crop_logo.py --media <path> --out <path>
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pymupdf
from PIL import Image

MIN_SIDE = 40


def autocrop(image: Image.Image) -> Image.Image:
    """Trim near-uniform borders, tolerating JPEG-ish noise."""
    grayscale = image.convert("L")
    threshold = grayscale.point(lambda px: 0 if px > 242 else 255)
    bbox = threshold.getbbox()
    if bbox is None:
        return image
    pad = max(2, int(0.02 * max(image.size)))
    left = max(0, bbox[0] - pad)
    top = max(0, bbox[1] - pad)
    right = min(image.width, bbox[2] + pad)
    bottom = min(image.height, bbox[3] + pad)
    return image.crop((left, top, right, bottom))


def blank_fraction(image: Image.Image) -> float:
    grayscale = image.convert("L")
    histogram = grayscale.histogram()
    near_white = sum(histogram[243:])
    return near_white / (image.width * image.height)


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--page", type=int)
    parser.add_argument("--box", help="crop fractions x0,y0,x1,y1 (top-left origin)")
    parser.add_argument("--media", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if args.media is not None:
        image = Image.open(args.media)
        image.load()
        if image.mode in ("P", "CMYK"):
            image = image.convert("RGBA" if "transparency" in image.info else "RGB")
        image.save(args.out)
        print(f"OK media copy {image.width}x{image.height} -> {args.out}")
        return 0

    if args.image is not None and args.box is not None:
        try:
            fractions = [float(v) for v in args.box.split(",")]
            if len(fractions) != 4 or not all(0.0 <= f <= 1.0 for f in fractions):
                raise ValueError
            if fractions[0] >= fractions[2] or fractions[1] >= fractions[3]:
                raise ValueError
        except ValueError:
            print("FAIL box must be four fractions 0.0-1.0 as x0,y0,x1,y1 with x0<x1, y0<y1")
            return 1
        image = Image.open(args.image)
        image.load()
        crop = image.crop((int(fractions[0] * image.width), int(fractions[1] * image.height),
                           int(fractions[2] * image.width), int(fractions[3] * image.height)))
        trimmed = autocrop(crop)
        if min(trimmed.size) < MIN_SIDE:
            print(f"FAIL cropped result too small ({trimmed.width}x{trimmed.height}); widen the box")
            return 1
        if blank_fraction(trimmed) > 0.995:
            print("FAIL cropped region is essentially blank; the box probably misses the logo")
            return 1
        trimmed.save(args.out)
        print(f"OK crop {trimmed.width}x{trimmed.height} -> {args.out}")
        return 0

    if args.pdf is None or args.page is None or args.box is None:
        parser.error("--pdf, --page, and --box are required unless --media or --image is used")
    try:
        fractions = [float(v) for v in args.box.split(",")]
        if len(fractions) != 4 or not all(0.0 <= f <= 1.0 for f in fractions):
            raise ValueError
        if fractions[0] >= fractions[2] or fractions[1] >= fractions[3]:
            raise ValueError
    except ValueError:
        print("FAIL box must be four fractions 0.0-1.0 as x0,y0,x1,y1 with x0<x1, y0<y1")
        return 1

    try:
        doc = pymupdf.open(args.pdf)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL cannot open {args.pdf}: {exc}")
        return 1
    with doc:
        if not 1 <= args.page <= doc.page_count:
            print(f"FAIL page {args.page} out of range (1-{doc.page_count})")
            return 1
        page = doc[args.page - 1]
        full = page.rect
        clip = pymupdf.Rect(full.x0 + fractions[0] * full.width,
                            full.y0 + fractions[1] * full.height,
                            full.x0 + fractions[2] * full.width,
                            full.y0 + fractions[3] * full.height)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(300 / 72, 300 / 72), clip=clip, alpha=True)

    temp = args.out.with_suffix(".tmp.png")
    pix.save(temp)
    image = Image.open(temp)
    image.load()
    trimmed = autocrop(image)
    if min(trimmed.size) < MIN_SIDE:
        temp.unlink(missing_ok=True)
        print(f"FAIL cropped result too small "
              f"({trimmed.width}x{trimmed.height}, minimum side {MIN_SIDE}); widen the box")
        return 1
    if blank_fraction(trimmed) > 0.995:
        temp.unlink(missing_ok=True)
        print("FAIL cropped region is essentially blank; the box probably misses the logo")
        return 1
    trimmed.save(args.out)
    temp.unlink(missing_ok=True)
    print(f"OK crop {trimmed.width}x{trimmed.height} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
