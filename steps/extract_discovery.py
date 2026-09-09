#!/usr/bin/env python3
"""Pull the final JSON array from an agent transcript JSONL into ground-truth/discovery/.

Usage: python3 steps/extract_discovery.py <output-file> <chunk-number>
Validates the array, drops placeholder records (empty title or non-numeric id),
and writes ground-truth/discovery/chunk-NN.json.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def main() -> int:
    source = Path(sys.argv[1])
    chunk = sys.argv[2]
    best = None
    for line in source.read_text().splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = entry.get("message") or entry
        if entry.get("type") == "assistant" or message.get("role") == "assistant":
            content = message.get("content")
            if isinstance(content, list):
                text = "".join(block.get("text", "") for block in content if isinstance(block, dict))
            else:
                text = content or ""
            text = text.strip()
            match = re.search(r"\[\s*\{", text)
            if not match:
                continue
            idx = match.start()
            candidate = re.sub(r"^```(?:json)?|```$", "", text[idx:], flags=re.MULTILINE).strip()
            try:
                records = json.loads(candidate)
            except json.JSONDecodeError:
                cut = candidate.rfind("}")
                if cut < 0:
                    continue
                try:
                    records = json.loads(candidate[: cut + 1])
                except json.JSONDecodeError:
                    continue
            if isinstance(records, list) and records and "canonical_title" in str(records[0]):
                best = records
    if not best:
        print(f"chunk {chunk}: no JSON array found")
        return 1
    records = best
    clean = [r for r in records if r.get("canonical_title") and str(r.get("id", "")).isdigit()]
    dropped = [r.get("id") for r in records if r not in clean]
    dest = Path("ground-truth/discovery") / f"chunk-{int(chunk):02d}.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(clean, ensure_ascii=False, indent=1))
    suffix = f" (dropped {dropped})" if dropped else ""
    print(f"chunk {chunk}: {len(clean)} records -> {dest}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
