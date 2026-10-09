"""The agents' own quote check: the lanes' machine check (`opus_audit/quotes.check_quote`) on the live
page, run before an answer is recorded.

An agent that quotes a page is checked by a machine against the page the import fetches itself, so a
quote copied from a cached text or a search snippet can fail there (calibration teaser-2026-10-09: six
true Wikipedia quotes refused for a footnote marker the cache drops). This command runs exactly that
check, on the same reading (`Q.normalise`, `Q.page_source`) and the lanes' source rule
(`wc.answers.url_problem`: never an AI aggregator, a Wikipedia mirror, a blocked domain, this
project's site), for one quote and one URL:

    ./.venv/Scripts/python.exe scripts/remediation/quote_check.py --url URL --quote-file Q.txt
    ./.venv/Scripts/python.exe scripts/remediation/quote_check.py --url URL --quote "the words"

One request, with the lanes' User-Agent. It prints one JSON object - `ok`, `outcome` (`found`,
`not found`, `source refused`, `fetch failed`, ...) and, for a quote that is not found, `hint`: the
longest start of the quote the page does hold and what the page says next, so a quote copied
inexactly can be corrected from the page. Exit 0 when the quote is found, 1 when not, 2 for a
refused request.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[2]
for _path in (ROOT, ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import research_web  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402
from wc.answers import url_problem  # noqa: E402 - lane WC's source rule, by code

#: What a hint shows of the page after the part of the quote it holds.
HINT_CHARS = 120
SOURCE_REFUSED = "source refused"


class CheckError(ValueError):
    """The request is not one the check can run."""


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def hint(wanted: str, texts: Iterable[tuple[str, str]]) -> dict[str, Any]:
    """The longest start of `wanted` that a reading holds, and the page text after it."""
    best_length, best_after = 0, ""
    for _, haystack in texts:
        low, high = 0, len(wanted)
        while low < high:  # the longest prefix that occurs: occurrence is monotone in the length
            middle = (low + high + 1) // 2
            if wanted[:middle] in haystack:
                low = middle
            else:
                high = middle - 1
        if low > best_length:
            at = haystack.find(wanted[:low]) + low
            best_length, best_after = low, haystack[at : at + HINT_CHARS]
    return {
        "quote_found_up_to": wanted[:best_length],
        "page_continues_with": best_after,
        "quote_continues_with": wanted[best_length : best_length + HINT_CHARS],
    }


def self_check(
    url: str,
    quote: str,
    client: Any,
    pages: Path,
    *,
    now: Callable[[], str] = _now,
    errors: tuple[type[BaseException], ...] = (httpx.HTTPError,),
) -> dict[str, Any]:
    """The lanes' check of one quote on one page: fetch it once into `pages`, read it, look."""
    refused = url_problem(url)
    if refused is not None:
        return {"ok": False, "url": url, "outcome": f"{SOURCE_REFUSED}: {refused}", "detail": ""}
    Q.collect([url], pages, client, now=now, pace=0, errors=errors)
    library = Q.Library(ROOT, pages)
    result = Q.check_quote(
        {"source": url, "quote": quote}, {"change_key": "self-check", "evidence_files": []}, library
    )
    out: dict[str, Any] = {
        "ok": result.outcome == Q.FOUND,
        "url": url,
        "outcome": result.outcome,
        "detail": result.detail,
    }
    if result.outcome == Q.NOT_FOUND:
        out["hint"] = hint(Q.normalise(quote), library.url(url).texts)
    return out


def main(argv: Iterable[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--url", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--quote")
    source.add_argument("--quote-file", type=Path, help="the quote, UTF-8")
    args = parser.parse_args(list(argv) if argv is not None else None)
    quote = args.quote if args.quote is not None else args.quote_file.read_bytes().decode("utf-8")
    if not Q.normalise(quote):
        print("REFUSED: the quote is empty", file=sys.stderr)
        return 2
    with (
        tempfile.TemporaryDirectory() as tmp,
        Q.http_client(research_web.USER_AGENT) as client,
    ):
        result = self_check(args.url, quote, client, Path(tmp) / "pages")
    print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
