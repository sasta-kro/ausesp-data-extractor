#!/usr/bin/env python3
"""Square-normalize a project logo with background-aware padding.

The fill rule (decided 2026-09-12 after sample review): sample the exact
dominant color along the image border and pad the shorter dimension with that
color so the logo's own canvas extends naturally; no rounding or snapping to
white. Logos whose border is mostly transparent pad with transparency.

Modes:
  --logo <path> [--out <path>] [--max-side N]   one logo -> square PNG
  --all [--max-side N]                          every output/enrichment/logos/*.png
                                                 (replaces in place after verification)
  --demo <id>                                   3-panel comparison sheet for review

Usage: python3 steps/normalize_logo.py --demo 2141
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
LOGOS = ROOT / "output" / "enrichment" / "logos"
PAPER = (251, 247, 240)   # app page background #fbf7f0
TILE = (244, 242, 247)    # app logo tile background #f4f2f7


def edge_background(image: Image.Image) -> tuple[int, int, int, int] | None:
    """Exact dominant border color; None means pad with transparency."""
    w, h = image.size
    edge = [image.getpixel((x, 0)) for x in range(0, w, max(1, w // 60))]
    edge += [image.getpixel((x, h - 1)) for x in range(0, w, max(1, w // 60))]
    edge += [image.getpixel((0, y)) for y in range(0, h, max(1, h // 60))]
    edge += [image.getpixel((w - 1, y)) for y in range(0, h, max(1, h // 60))]
    opaque = [p[:3] for p in edge if p[3] > 240]
    if len(opaque) < len(edge) // 2:
        return None
    (r, g, b), _ = Counter(opaque).most_common(1)[0]
    return (r, g, b, 255)


def square(image: Image.Image, max_side: int,
           background: tuple[int, int, int, int] | None) -> Image.Image:
    """Logo centered on a square canvas of side min(longest edge, max_side),
    never upscaled beyond its own longest edge, padded with the background."""
    side = min(max(image.width, image.height), max_side)
    fitted = image.copy()
    fitted.thumbnail((side, side), Image.LANCZOS)
    canvas = Image.new("RGBA", (side, side),
                       background if background is not None else (0, 0, 0, 0))
    canvas.paste(fitted, ((side - fitted.width) // 2, (side - fitted.height) // 2), fitted)
    return canvas


def normalize(path: Path, out: Path, max_side: int) -> tuple[int, int, int] | None:
    image = Image.open(path).convert("RGBA")
    background = edge_background(image)
    square(image, max_side, background).save(out)
    return background[:3] if background else None


def demo(pid: str) -> None:
    source = LOGOS / f"{pid}.png"
    image = Image.open(source).convert("RGBA")
    background = edge_background(image)
    side = 300
    cell, pad = 360, 16

    def on_tile(content: Image.Image) -> Image.Image:
        tile = Image.new("RGBA", (side, side), TILE + (255,))
        tile.paste(content, ((side - content.width) // 2,
                             (side - content.height) // 2), content)
        return tile

    fitted = image.copy()
    fitted.thumbnail((side, side), Image.LANCZOS)
    on_page = Image.alpha_composite(
        Image.new("RGBA", (side, side), PAPER + (255,)),
        square(image, side, background)).convert("RGBA")
    panels = [
        ("original (as extracted)", on_tile(fitted)),
        ("bg-aware square (final rule)", on_tile(square(image, side, background))),
        ("same on page background", on_page),
    ]
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
        small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 15)
    except OSError:
        font = small = ImageFont.load_default()
    sheet = Image.new("RGB", (cell * 3 + pad * 4, 360 + 40 + pad * 2), PAPER)
    draw = ImageDraw.Draw(sheet)
    fill = background[:3] if background else "transparent"
    draw.text((pad, 10), f"Logo {pid}   {image.width}x{image.height}   fill={fill}",
              fill=(33, 26, 26), font=font)
    for index, (label, img) in enumerate(panels):
        x = pad + index * (cell + pad)
        sheet.paste(img.convert("RGB"), (x + (cell - side) // 2, pad + 26))
        draw.text((x + 10, pad + 26 + side + 10), label, fill=(33, 26, 26), font=small)
    out = ROOT / ".tmp-enrichment" / "pad-demo" / f"{pid}-comparison.png"
    out.parent.mkdir(exist_ok=True)
    sheet.save(out)
    print(f"{pid}: fill={fill} -> {out}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logo", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--demo")
    parser.add_argument("--max-side", type=int, default=1024)
    args = parser.parse_args()

    if args.demo:
        demo(args.demo)
        return 0
    if args.all:
        for path in sorted(LOGOS.glob("*.png")):
            fill = normalize(path, path, args.max_side)
            print(f"{path.stem}: fill={fill}")
        return 0
    if args.logo:
        out = args.out or args.logo
        fill = normalize(args.logo, out, args.max_side)
        print(f"fill={fill} -> {out}")
        return 0
    parser.error("choose --logo, --all, or --demo")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
