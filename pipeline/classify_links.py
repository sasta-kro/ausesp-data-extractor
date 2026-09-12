#!/usr/bin/env python3
"""Write the hand-reviewed URL classification for discovered repository links.

Each discovered URL is classified as:
  project_repo          the project team's own repository (owner matches a
                        student name, or the repo name matches the project)
  third_party_reference a cited library, tool, or tutorial repository
  dropped               a scrape artifact (mangled URL), excluded entirely

Output: output/extraction-evidence/repo-link-evidence/link-kinds.json ({url: {"kind": ..., "note": ...}}).
Hand-curated 2026-09-11 by cross-checking owners against ground-truth student
names and repo names against ground-truth titles.

Usage: python3 pipeline/classify_links.py
"""
from __future__ import annotations

import json
from pathlib import Path

PROJECT_REPOS = {
    # owner matches a ground-truth student name
    "https://github.com/chawanvtp/sakpha-android": "owner = Chawan Vattanalap (student)",
    "https://github.com/aretisd/sakpha-": "owner = Artisd Chanyawadee (student)",
    "https://github.com/morgancsit/lba-frontend": "owner = Morgan Kieffer (student)",
    "https://github.com/morgancsit/sp1-longtailbookingdapp": "owner = Morgan Kieffer (student)",
    "https://github.com/williampoch/sp1": "owner = William Sivutha Poch (student)",
    "https://github.com/williampoch/sp1website": "owner = William Sivutha Poch (student)",
    "https://github.com/williampoch/aspectbasedsentimentanalysis": "owner = William Sivutha Poch (student)",
    "https://github.com/serhii-bielik/cs4200-sp2-advising": "owner = Serhii Bielik (student)",
    "https://github.com/rohitks1997/cinemo": "owner = Rohit Kumar Setthachok (student)",
    "https://github.com/singekkasith/senior-project-i": "owner = Ekkasith Singmaneechai (student)",
    "https://github.com/taechasit1001/au_seniorproject_1": "owner = Taechasit Sarasitt (student)",
    "https://github.com/thuyein96/internal-developer-tool-orchestronic": "owner = Thu Yein (student)",
    "https://github.com/garrukzijian/cvcoach": "owner = Zijian Zhou (student)",
    # repo name matches the ground-truth project title
    "https://github.com/pandalabos/smarthomefinal": "repo name matches Smart Home Interface",
    "https://github.com/kusk24/augo": "repo name matches AUGo campus AR app",
    "https://gitlab.com/islabac/smartdigest/concept-predictor-api": "ISL lab GitLab hosting project work",
    # uncertain but plausible product repo
    "https://github.com/jg-fisher/dinoai": "owner not matched to a student; DinoAI plausibly the product name",
}

DROPPED = {
    # docs.github.com/en/actions mangled by the host-only regex
    "https://github.com/en/actions",
}


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    grep = json.loads((root / "output" / "extraction-evidence" / "repo-link-evidence" / "text-grep.json").read_text())
    urls = sorted({g["url"] for g in grep if g.get("url")})
    kinds = {}
    for url in urls:
        if url in DROPPED:
            kinds[url] = {"kind": "dropped", "note": "scrape artifact of a docs URL"}
        elif url in PROJECT_REPOS:
            note = PROJECT_REPOS[url]
            kinds[url] = {"kind": "project_repo",
                          "note": note, "uncertain": "plausibly" in note}
        else:
            kinds[url] = {"kind": "third_party_reference",
                          "note": "cited library, tool, or tutorial repository"}
    output = root / "output" / "extraction-evidence" / "repo-link-evidence" / "link-kinds.json"
    output.write_text(json.dumps(kinds, ensure_ascii=False, indent=1))
    project = sum(1 for v in kinds.values() if v["kind"] == "project_repo")
    print(f"classified {len(kinds)} urls: {project} project_repo, "
          f"{len(kinds) - project - len(DROPPED)} third_party_reference, {len(DROPPED)} dropped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
