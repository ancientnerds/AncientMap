"""Phase 6 acceptance, sections 6-7: the strict parsers of a judge's answer, and the quote check.

An answer is one JSON object with exactly its keys (`load_object`: no code fence, no prose around it,
no key twice, no NaN) and a verdict of its stage:

* **stage 1** (`parse_stage1`): `CORRECT` rests on at least two quotes from at least two independent
  source families (`source_family`: one Wikipedia article, its Wikidata item and Commons are one
  family, `wikimedia`; otherwise the registrable domain); for the text fields every quote names the
  part of the served text it bears on, copied from it, and together they touch every sentence
  (`uncovered_sentences`). `WRONG` rests on at least one quote, proposes a right value that differs
  from the served one and names a class its row allows; where the row makes the class a matter of
  arithmetic - kilometres for F3, buckets for F5 - the class must be the one the arithmetic gives,
  and a value the row says is not wrong (under 1 km, the same bucket) is refused. `UNVERIFIABLE`
  rests on no quote and proposes nothing.
* **stage 2** (`parse_stage2`): `CONFIRMED` rests on at least one quote and may only name a *lower*
  class, with its reason; `REFUTED` may name the false-alarm pattern; `UNDECIDED` rests on nothing.
* **stage 3** (`parse_stage3`): `CONFIRMED` (quoted) or `REFUTED`.

**The quote check** (`check_quotes`) is the Opus re-verification's, unchanged
(`opus_audit/quotes.py`: NFC and whitespace runs only, the page as fetched and stored by the run). A
verdict counts only when every quote it gives is found; a verdict that gives none has none to fail.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit

from opus_audit import quotes as Q

from acceptance import questions as QN
from pipeline.normalizers.site_type import CANONICAL_TYPES, normalize_site_type
from pipeline.utils.geo import haversine_distance
from pipeline.utils.text import PERIOD_BUCKETS, categorize_period

CORRECT, WRONG, UNVERIFIABLE = "CORRECT", "WRONG", "UNVERIFIABLE"
CONFIRMED, REFUTED, UNDECIDED = "CONFIRMED", "REFUTED", "UNDECIDED"
STAGE1_KEYS = frozenset({"verdict", "quotes", "right_value", "severity", "reasoning"})
STAGE2_KEYS = frozenset(
    {"verdict", "quotes", "severity", "severity_reason", "pattern", "reasoning"}
)
STAGE3_KEYS = frozenset({"verdict", "quotes", "reasoning"})
QUOTE_KEYS = frozenset({"url", "quote"})
TEXT_QUOTE_KEYS = frozenset({"url", "quote", "claim"})
PATTERNS = range(1, 12)
#: F3's row: within 1 km is right; more than 5 km is severe.
RIGHT_KM, SEVERE_KM = 1.0, 5.0
BUCKETS = [name for name, _low, _high in PERIOD_BUCKETS]


class AnswerError(ValueError):
    """The answer is not in the shape its stage asks for: it does not count."""


@dataclass(frozen=True)
class Quote:
    url: str
    quote: str
    claim: str | None


@dataclass(frozen=True)
class Answer1:
    verdict: str
    quotes: tuple[Quote, ...]
    right_value: str | None
    severity: str | None
    reasoning: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Answer2:
    verdict: str
    quotes: tuple[Quote, ...]
    severity: str | None
    severity_reason: str | None
    pattern: int | None
    reasoning: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Answer3:
    verdict: str
    quotes: tuple[Quote, ...]
    reasoning: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ------------------------------------------------------------------------------ the JSON object
def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise AnswerError(f"key {key!r} twice")
        out[key] = value
    return out


def _no_constant(name: str) -> Any:
    raise AnswerError(f"{name} is not JSON")


def load_object(text: str, keys: frozenset[str]) -> dict[str, Any]:
    try:
        data = json.loads(text, object_pairs_hook=_unique, parse_constant=_no_constant)
    except json.JSONDecodeError as exc:
        raise AnswerError(f"not one JSON object: {exc}") from exc
    if not isinstance(data, dict):
        raise AnswerError(f"the answer is a JSON {type(data).__name__}, not an object")
    if set(data) != keys:
        raise AnswerError(f"keys {sorted(data)} are not {sorted(keys)}")
    return data


def _text(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AnswerError(f"{what} is not a non-empty string")
    return value


def _quotes(value: Any, keys: frozenset[str]) -> tuple[Quote, ...]:
    if not isinstance(value, list):
        raise AnswerError("quotes is not a list")
    out = []
    for item in value:
        if not isinstance(item, dict) or set(item) != keys:
            raise AnswerError(
                f"a quote carries {sorted(item) if isinstance(item, dict) else item!r}, not {sorted(keys)}"
            )
        url, quote = item["url"], item["quote"]
        if not isinstance(url, str) or url != url.strip() or not Q.is_url(url):
            raise AnswerError(f"quote url {url!r} is not an http(s) URL")
        if not isinstance(quote, str) or not Q.normalise(quote):
            raise AnswerError(f"an empty quote on {url}")
        claim = item.get("claim")
        if claim is not None and not isinstance(claim, str):
            raise AnswerError(f"the claim of a quote on {url} is not a string or null")
        out.append(Quote(url, quote, claim))
    return tuple(out)


def _null(data: dict[str, Any], keys: Sequence[str], verdict: str) -> None:
    for key in keys:
        if data[key] is not None:
            raise AnswerError(f"{verdict} leaves {key} null")


# ------------------------------------------------------------------------------ source families
WIKIMEDIA = (
    "wikipedia.org", "wikidata.org", "wikimedia.org", "wikisource.org", "wikivoyage.org",
    "wiktionary.org", "wikibooks.org", "wikiquote.org", "wikinews.org", "wikiversity.org",
    "mediawiki.org",
)  # fmt: skip
#: Second-level labels under a two-letter country code that a registrable domain sits below
#: (`english-heritage.org.uk`, `ntu.ac.uk`, `inah.gob.mx`).
SECOND_LEVEL = frozenset(
    {
        "ac",
        "co",
        "com",
        "edu",
        "go",
        "gob",
        "gouv",
        "gov",
        "govt",
        "gv",
        "mil",
        "ne",
        "net",
        "nic",
        "or",
        "org",
        "sch",
    }  # fmt: skip
)
_ARCHIVED = re.compile(r"/web/[^/]+/(https?://.+)")


def source_family(url: str) -> str:
    """The publisher a URL belongs to: Wikimedia as one, an archived copy as its original's, else
    the registrable domain."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    if host == "web.archive.org":
        archived = _ARCHIVED.fullmatch(parts.path)
        return source_family(archived.group(1)) if archived else "archive.org"
    if any(host == w or host.endswith("." + w) for w in WIKIMEDIA):
        return "wikimedia"
    labels = host.split(".")
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in SECOND_LEVEL:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


# ------------------------------------------------------------------------------ the text fields
def _sentences(text: str) -> list[tuple[int, int]]:
    """Sentence spans of a normalised text: an end is `.`, `!` or `?` (and its markers) before a
    space and a character that is neither lower case nor a digit - `c. 400` goes on."""
    spans, start = [], 0
    for match in re.finditer(r"[.!?](?:\[\d+\])* ", text):
        following = text[match.end() : match.end() + 1]
        if following.islower() or following.isdigit():
            continue
        spans.append((start, match.end() - 1))
        start = match.end()
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def uncovered_sentences(text: str, claims: Sequence[str]) -> list[str]:
    """The sentences of `text` that no claim overlaps (every occurrence of every claim counts)."""
    norm = Q.normalise(text)
    covered: list[tuple[int, int]] = []
    for claim in claims:
        wanted = Q.normalise(claim)
        at = norm.find(wanted)
        while wanted and at >= 0:
            covered.append((at, at + len(wanted)))
            at = norm.find(wanted, at + 1)
    return [norm[a:b] for a, b in _sentences(norm) if not any(s < b and a < e for s, e in covered)]


def _claims(field: str, value: str, quotes: tuple[Quote, ...]) -> None:
    for quote in quotes:
        if field not in QN.TEXT_FIELDS:
            if quote.claim is not None:
                raise AnswerError(
                    f"{field}: a quote's claim is null (only the text fields name one)"
                )
            continue
        if quote.claim is None or not Q.normalise(quote.claim):
            raise AnswerError(f"{field}: every quote names the claim it bears on")
        if Q.normalise(quote.claim) not in Q.normalise(value):
            raise AnswerError(f"claim {quote.claim!r} is not in the served text")


# ------------------------------------------------------------------------------ typed right values
_POINT = re.compile(r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*")


def _point(value: str) -> tuple[float, float]:
    match = _POINT.fullmatch(value)
    if not match:
        raise AnswerError(f'{value!r} is not a point "lat, lon"')
    lat, lon = float(match[1]), float(match[2])
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise AnswerError(f'{value!r} is not a point "lat, lon" on Earth')
    return lat, lon


def _year(value: str) -> int:
    if not re.fullmatch(r"-?\d+", value.strip()):
        raise AnswerError(f"{value!r} is not an integer year")
    return int(value)


def _right_value(field: str, value: str, right: str, severity: str) -> None:
    if Q.normalise(right) == Q.normalise(value):
        raise AnswerError("the right_value is the served value")
    if field == "coordinates":
        km = haversine_distance(*_point(value), *_point(right))
        if km < RIGHT_KM:
            raise AnswerError(f"{km:.2f} km from the served point: within 1 km is right (F3)")
        if km > SEVERE_KM and severity != "severe":
            raise AnswerError(f"{km:.1f} km from the served point: more than 5 km is severe")
    elif field == "site_type":
        if right not in CANONICAL_TYPES or normalize_site_type(right) != right:
            raise AnswerError(f"{right!r} is not a canonical type")
    elif field == "period_start":
        served = BUCKETS.index(str(categorize_period(_year(value))))
        proposed = BUCKETS.index(str(categorize_period(_year(right))))
        distance = abs(served - proposed)
        if distance == 0:
            raise AnswerError(f"{right} is in the served value's bucket: not wrong (pattern 1)")
        expected = "severe" if distance >= 2 else "moderate"
        if severity != expected:
            raise AnswerError(f"{distance} bucket(s) off is {expected}, not {severity}")
    elif field == "period_name" and right not in BUCKETS:
        raise AnswerError(f"{right!r} is not a bucket")


# ------------------------------------------------------------------------------ the parsers
def parse_stage1(text: str, field: str, value: str) -> Answer1:
    data = load_object(text, STAGE1_KEYS)
    verdict = data["verdict"]
    if verdict not in (CORRECT, WRONG, UNVERIFIABLE):
        raise AnswerError(f"verdict {verdict!r} is not CORRECT, WRONG or UNVERIFIABLE")
    reasoning = _text(data["reasoning"], "reasoning")
    quotes = _quotes(data["quotes"], TEXT_QUOTE_KEYS)
    _claims(field, value, quotes)
    if verdict == CORRECT:
        _null(data, ("right_value", "severity"), verdict)
        if len({source_family(q.url) for q in quotes}) < 2:
            raise AnswerError("CORRECT rests on at least two independent source families")
        if field in QN.TEXT_FIELDS:
            missing = uncovered_sentences(value, [str(q.claim) for q in quotes])
            if missing:
                raise AnswerError(f"sentences without a quoted claim: {missing}")
        return Answer1(verdict, quotes, None, None, reasoning)
    if verdict == WRONG:
        if not quotes:
            raise AnswerError("WRONG rests on at least one quote")
        right = _text(data["right_value"], "right_value")
        severity = data["severity"]
        allowed = QN.FIELD_BY_KEY[field].severities
        if severity not in allowed:
            raise AnswerError(f"severity {severity!r} is not one of {list(allowed)}")
        _right_value(field, value, right, severity)
        return Answer1(verdict, quotes, right, severity, reasoning)
    if quotes:
        raise AnswerError("UNVERIFIABLE rests on no quote: quotes is []")
    _null(data, ("right_value", "severity"), verdict)
    return Answer1(verdict, quotes, None, None, reasoning)


def parse_stage2(text: str, field: str, claimed: str) -> Answer2:
    data = load_object(text, STAGE2_KEYS)
    verdict = data["verdict"]
    if verdict not in (CONFIRMED, REFUTED, UNDECIDED):
        raise AnswerError(f"verdict {verdict!r} is not CONFIRMED, REFUTED or UNDECIDED")
    reasoning = _text(data["reasoning"], "reasoning")
    quotes = _quotes(data["quotes"], QUOTE_KEYS)
    if verdict == CONFIRMED:
        if not quotes:
            raise AnswerError("CONFIRMED rests on at least one quote")
        _null(data, ("pattern",), verdict)
        severity = data["severity"]
        if severity is None:
            _null(data, ("severity_reason",), verdict)
            return Answer2(verdict, quotes, None, None, None, reasoning)
        if severity not in QN.FIELD_BY_KEY[field].severities:
            raise AnswerError(f"severity {severity!r} is not a class of {field}")
        if QN.SEVERITIES.index(severity) >= QN.SEVERITIES.index(claimed):
            raise AnswerError(f"severity {severity!r} is not lower than the claimed {claimed!r}")
        reason = _text(data["severity_reason"], "severity_reason")
        return Answer2(verdict, quotes, severity, reason, None, reasoning)
    _null(data, ("severity", "severity_reason"), verdict)
    if verdict == UNDECIDED:
        if quotes:
            raise AnswerError("UNDECIDED rests on no quote: quotes is []")
        _null(data, ("pattern",), verdict)
        return Answer2(verdict, quotes, None, None, None, reasoning)
    pattern = data["pattern"]
    if pattern is not None and (
        isinstance(pattern, bool) or not isinstance(pattern, int) or pattern not in PATTERNS
    ):
        raise AnswerError(f"pattern {pattern!r} is not a false-alarm pattern 1-11")
    return Answer2(verdict, quotes, None, None, pattern, reasoning)


def parse_stage3(text: str) -> Answer3:
    data = load_object(text, STAGE3_KEYS)
    verdict = data["verdict"]
    if verdict not in (CONFIRMED, REFUTED):
        raise AnswerError(f"verdict {verdict!r} is not CONFIRMED or REFUTED")
    quotes = _quotes(data["quotes"], QUOTE_KEYS)
    if verdict == CONFIRMED and not quotes:
        raise AnswerError("CONFIRMED rests on at least one quote")
    return Answer3(verdict, quotes, _text(data["reasoning"], "reasoning"))


# ------------------------------------------------------------------------------ the quote check
@dataclass(frozen=True)
class QuoteCheck:
    counted: bool
    reason: str
    results: tuple[dict[str, Any], ...]


def check_quotes(label: str, quotes: Sequence[Quote], library: Q.Library) -> QuoteCheck:
    """Every quote against its stored page, by `opus_audit/quotes.check_quote`; no quote, no fail."""
    row = {"change_key": label, "evidence_files": []}
    results = tuple(
        Q.check_quote({"source": quote.url, "quote": quote.quote}, row, library) for quote in quotes
    )
    failed = [result.outcome for result in results if result.outcome != Q.FOUND]
    return QuoteCheck(not failed, failed[0] if failed else "", tuple(asdict(r) for r in results))
