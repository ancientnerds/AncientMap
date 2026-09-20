"""Logged HTTP GET helper for the Phase-3 pilot.

One call = one line in fetch_log.jsonl, so COST.md can report a measured fetch count
instead of an estimate. Saves the response body under evidence/ so every claim in
PILOT.md can be re-read from the bytes that were actually fetched.

Usage:
    python http_get.py <stage> <label> <url> [outfile]

stage  = finder | reviewer
label  = short tag, e.g. "Satsurblia/wikidata"
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVID = HERE / "evidence"
LOG = HERE / "fetch_log.jsonl"

UA = "AncientMap-Phase3-Pilot/1.0 (https://github.com/ancientnerds; martin@example.invalid)"
"""Wikimedia asks for a descriptive UA; the address is not used for anything but politeness."""


def fetch(url: str, timeout: int = 40) -> tuple[int, bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - https only
            return resp.status, resp.read(), resp.geturl()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), url
    except Exception as exc:  # noqa: BLE001 - a failed fetch is recorded, never swallowed
        return -1, str(exc).encode("utf-8", "replace"), url


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    stage, label, url = sys.argv[1], sys.argv[2], sys.argv[3]
    slug = urllib.parse.quote(label, safe="")
    status, body, final = fetch(url)
    EVID.mkdir(parents=True, exist_ok=True)
    out = EVID / f"{slug}.txt"
    out.write_bytes(body)
    entry = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "stage": stage,
        "label": label,
        "url": url,
        "final_url": final,
        "http": status,
        "bytes": len(body),
        "file": str(out.relative_to(HERE)),
    }
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"{status} {len(body)} bytes -> {entry['file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
