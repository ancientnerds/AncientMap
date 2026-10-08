"""What the identity questions' answers share: the exact JSON shape helpers and the quote check.

An answer is one JSON object with exactly the keys its prompt names, strict JSON (`json.loads`; an
agent that wraps it in prose fixes it with `check-answer`). A **quote** is `{"url": <the page>,
"quote": <text copied word for word from it>}`: `url`, because the calibration's spot check reads
`quote["url"]` (`mcode_driver._sources`). The machine fetches every cited page (`opus_audit/quotes`,
the one quote check, nothing fuzzier) and a cell counts only when **every** one of its quotes is found.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _root in (str(_HERE.parents[3]), str(_HERE.parents[1])):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from opus_audit import quotes as Q  # noqa: E402

from identity.rounds import AnswerError  # noqa: E402

CONTROL = frozenset(chr(c) for c in (*range(32), 127))


def load_object(
    text: str, keys: frozenset[str] | set[str], what: str = "the answer"
) -> dict[str, Any]:
    """The answer text as one JSON object with exactly `keys`."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AnswerError(f"not JSON: {exc}") from exc
    return exact(data, keys, what)


def exact(data: Any, keys: frozenset[str] | set[str], what: str) -> dict[str, Any]:
    if not isinstance(data, dict) or set(data) != set(keys):
        got = sorted(data) if isinstance(data, dict) else type(data).__name__
        raise AnswerError(f"{what} carries {got}, not {sorted(keys)}")
    return data


def text_of(value: Any, what: str, *, max_chars: int | None = None) -> str:
    """A trimmed, non-empty string without a control character."""
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise AnswerError(f"{what} is not a trimmed, non-empty string")
    if any(c in CONTROL for c in value):
        raise AnswerError(f"{what} carries a control character")
    if max_chars is not None and len(value) > max_chars:
        raise AnswerError(f"{what} is longer than {max_chars} characters")
    return value


def quotes_of(value: Any, what: str, *, minimum: int = 0) -> tuple[dict[str, str], ...]:
    """A list of `{url, quote}`: each a public http(s) page the machine fetches, each a text."""
    if not isinstance(value, list):
        raise AnswerError(f"{what}: quotes is not a list")
    out = []
    for q in value:
        if not isinstance(q, dict) or set(q) != {"url", "quote"}:
            raise AnswerError(f"{what}: a quote is not {{url, quote}}: {q!r}")
        if not all(isinstance(q[k], str) and q[k].strip() for k in ("url", "quote")):
            raise AnswerError(f"{what}: a quote needs a url and a text")
        if not Q.is_url(q["url"]):
            raise AnswerError(f"{what}: a quote's url must be the URL of the page: {q['url']!r}")
        refused = Q.not_fetchable(q["url"])
        if refused:
            raise AnswerError(f"{what}: {q['url']} is never fetched here ({refused})")
        out.append({"url": q["url"], "quote": q["quote"]})
    if len(out) < minimum:
        raise AnswerError(f"{what}: needs at least {minimum} quote(s), has {len(out)}")
    return tuple(out)


def check_quotes(
    quotes: Sequence[Mapping[str, str]], site_id: str, library: Q.Library
) -> tuple[bool, list[dict[str, str]], str]:
    """`(every quote found, each quote with its outcome, the first failure)`. No quotes: all found
    (nothing to check); a cell that must carry a quote says so in its parse."""
    if not quotes:
        return True, [], ""
    check = Q.check_verdict(
        {"quotes": [{"source": q["url"], "quote": q["quote"]} for q in quotes]},
        {"change_key": site_id, "evidence_files": []},
        library,
    )
    noted = [
        {"url": r.source, "quote": r.quote, "outcome": r.outcome, "detail": r.detail}
        for r in check.quotes
    ]
    failed = next((r for r in check.quotes if r.outcome != Q.FOUND), None)
    reason = "" if failed is None else f"{failed.outcome}: {failed.source}"
    return check.counted, noted, reason


def cites(quotes: Sequence[Mapping[str, str]], url: str) -> bool:
    """Whether a quote cites exactly `url` (canonicalised the way the fetch keys pages)."""
    return any(Q.canonical_url(q["url"])[0] == Q.canonical_url(url)[0] for q in quotes)


def urls_of(*groups: Sequence[Mapping[str, str]]) -> set[str]:
    return {q["url"] for group in groups for q in group}
