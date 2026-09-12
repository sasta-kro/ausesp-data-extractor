#!/usr/bin/env python3
"""Merge SP1/SP2 evidence into a per-project course classification.

Evidence layers, strongest first:
  1. Explicit statements re-read under contradiction (reread-*.json)
  2. Explicit cover statements (output/sp-course/<id>.json)
  3. Explicit Word-doc statements (mechanical textutil harvest, hardcoded below
     from .tmp-enrichment/docx-course-lines.json)
  4. Dictionary inference from the printed code (dominant explicit mapping)
  5. Unspecified

Outputs .tmp-enrichment/course-final.json: {id: {"course": "sp1"|"sp2"|"unspecified",
"basis": "explicit"|"reread"|"docx"|"inferred:<code>"|"none", "evidence": ...}}.

Usage: python3 steps/apply_course_classification.py
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

DOCX_EXPLICIT = {
    "1627": "sp1", "1726": "sp1", "1902": "sp2", "1906": "sp2", "1908": "sp1",
    "1909": "sp2", "1914": "sp1", "2001": "sp2", "2005": "sp2", "2008": "sp1",
    "2017": "sp1", "2018": "sp2",
}

CODE_RE = re.compile(r"(?:IT|CS|SC|TS|ITX|CSX)\s*-?\s*\d{3,4}")


# The worse side of each duplicate pair (culled this pass). Their evidence is
# excluded from the dictionary so known-bad documents cannot pollute mappings.
CULLED = {"1711", "2003", "1906", "1827", "26009", "2145"}


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    base = root / ".tmp-enrichment"

    gt = {}
    for f in (root / "ground-truth" / "batches").glob("*.json"):
        data = json.loads(f.read_text())
        for r in (data.values() if isinstance(data, dict) else data):
            gt[r["id"]] = r

    # dictionary from explicit sightings (agent covers + docx), excluding
    # superseded rereads handled below
    rereads = {}
    for f in (base / "slideonly").glob("reread-*.json"):
        r = json.loads(f.read_text())
        if r.get("explicit"):
            rereads[r["id"]] = r

    dic = defaultdict(lambda: defaultdict(int))
    covers = {}
    for f in (root / "output" / "sp-course").glob("*.json"):
        r = json.loads(f.read_text())
        covers[r["id"]] = r
        if r.get("explicit") and r["id"] not in rereads and r["id"] not in CULLED:
            for code in CODE_RE.findall((r.get("course_code_printed") or "").upper()):
                dic[re.sub(r"\s+", "", code)][r["explicit"]] += 1
    for pid, sp in DOCX_EXPLICIT.items():
        if pid not in rereads and pid not in CULLED:
            lines = json.loads((base / "docx-course-lines.json").read_text()).get(pid, [])
            for line in lines:
                for code in CODE_RE.findall(line.upper()):
                    dic[re.sub(r"\s+", "", code)][sp] += 1

    dictionary = {}
    for code, counts in dic.items():
        sp1, sp2 = counts.get("sp1", 0), counts.get("sp2", 0)
        if sp1 and not sp2:
            dictionary[code] = "sp1"
        elif sp2 and not sp1:
            dictionary[code] = "sp2"
        # conflicted codes stay out of the dictionary; inference never uses them

    final = {}
    for pid in sorted(gt):
        if pid in rereads:
            final[pid] = {"course": rereads[pid]["explicit"], "basis": "reread",
                          "evidence": "; ".join(rereads[pid].get("course_lines", [])[:3])}
            continue
        if pid in DOCX_EXPLICIT:
            final[pid] = {"course": DOCX_EXPLICIT[pid], "basis": "docx",
                          "evidence": "word-document explicit statement"}
            continue
        cover = covers.get(pid)
        if cover and cover.get("explicit"):
            final[pid] = {"course": cover["explicit"], "basis": "explicit",
                          "evidence": cover.get("evidence")}
            continue
        codes = []
        for source in ((cover or {}).get("course_code_printed"),
                       gt[pid].get("course_code")):
            if source:
                codes += [re.sub(r"\s+", "", c) for c in CODE_RE.findall(source.upper())]
        mapped = {dictionary[c] for c in codes if c in dictionary}
        # infer only when every mapped code agrees; mixed-code documents are
        # genuinely ambiguous and stay unspecified
        inferred = mapped.pop() if len(mapped) == 1 else None
        if inferred:
            used = ", ".join(c for c in codes if c in dictionary)
            final[pid] = {"course": inferred, "basis": f"inferred:{used}",
                          "evidence": "codes mapped unanimously from corpus dictionary"}
        else:
            final[pid] = {"course": "unspecified", "basis": "none",
                          "evidence": "; ".join(filter(None, [(cover or {}).get("course_code_printed"),
                                                               gt[pid].get("course_code")])) or None}

    (base / "course-final.json").write_text(json.dumps(final, ensure_ascii=False, indent=1))
    counts = defaultdict(int)
    for v in final.values():
        counts[v["course"]] += 1
    print(f"classified {len(final)} projects: {dict(counts)}")
    unspecified = [p for p, v in final.items() if v["course"] == "unspecified"]
    print("unspecified:", unspecified)
    inferred = [f"{p}({v['basis']})" for p, v in final.items() if v["basis"].startswith("inferred")]
    print(f"inferred ({len(inferred)}):", ", ".join(inferred))
    conflicted_codes = sorted(set(re.sub(r"\s+", "", c) for c in dic
                                  for c0 in [c] if dic[c].get("sp1") and dic[c].get("sp2")))
    print("codes excluded from dictionary (conflicted):", conflicted_codes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
