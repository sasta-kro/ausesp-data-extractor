#!/usr/bin/env python3
"""Check public accessibility of every discovered repository URL.

Collects distinct normalized URLs from output/extraction-evidence/repo-link-evidence/text-grep.json and
output/extraction-evidence/logo-and-link-records/*.json, then checks each with an unauthenticated
GET (redirects followed, one second pacing). github.com HTML pages are not
API-rate-limited at this scale. Writes output/extraction-evidence/repo-link-evidence/liveness.json.

Status semantics: public = final 200; not_found = final 404, meaning private
or deleted (indistinguishable from outside); unknown = anything else
(429/5xx/network/timeout). checked_at and final_url are recorded so renamed
repos resolve to their new home.

Usage: python3 steps/check_link_liveness.py
"""
from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36")


def collect(root: Path) -> set[str]:
    urls: set[str] = set()
    grep_file = root / "output" / "extraction-evidence" / "repo-link-evidence" / "text-grep.json"
    if grep_file.exists():
        for record in json.loads(grep_file.read_text()):
            if record.get("url"):
                urls.add(record["url"])
    records_dir = root / "output" / "extraction-evidence" / "logo-and-link-records"
    for record_file in sorted(records_dir.glob("*.json")):
        record = json.loads(record_file.read_text())
        for link in record.get("links", []):
            if link.get("url"):
                urls.add(link["url"].rstrip("/"))
    return urls


def check(url: str) -> dict:
    result = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-L", "--max-time", "20",
         "-w", "%{http_code} %{url_effective}", "-A", USER_AGENT, url],
        capture_output=True, text=True, timeout=30)
    parts = result.stdout.strip().rsplit(" ", 1)
    http_status = int(parts[0]) if parts and parts[0].isdigit() else 0
    final_url = parts[1] if len(parts) == 2 else url
    if http_status == 200:
        status = "public"
    elif http_status == 404:
        status = "not_found"
    else:
        status = "unknown"
    return {"url": url, "status": status, "http_status": http_status,
            "final_url": final_url,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    urls = sorted(collect(root))
    results = []
    for index, url in enumerate(urls):
        try:
            results.append(check(url))
        except Exception as exc:  # noqa: BLE001 - network errors become unknown
            results.append({"url": url, "status": "unknown", "http_status": 0,
                            "final_url": url,
                            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            "error": str(exc)[:120]})
        time.sleep(1.0)
        print(f"[{index + 1}/{len(urls)}] {url} -> {results[-1]['status']}")

    output = root / "output" / "extraction-evidence" / "repo-link-evidence" / "liveness.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    counts = {status: sum(1 for r in results if r["status"] == status)
              for status in ("public", "not_found", "unknown")}
    print(f"checked {len(results)} urls: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
