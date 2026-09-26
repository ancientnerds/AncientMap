"""Lane WC's answers: the strict parsers of a check answer and a judge answer, and the quote check.

**A check answer** (`parse_check`) is one JSON object `{site_id, sentences}` (`acceptance.answers.
load_object`: no code fence, no key twice, no NaN) naming exactly the asked sentences in order, each
`{n, verdict, remove, reason, quotes, note}`:

* `KEEP` - 1-4 quotes, no piece to remove, no reason;
* `KEEP_TRIMMED` - 1-4 quotes and the piece to remove, which `phase4/wc4.trim` must accept (an exact
  substring once, no protected token, a clean sentence left);
* `DROP` - reason `contradicted` with 1-4 quotes, or `unsupported` with none.

Every quote is `{url, title, quote}`: an http(s) URL without whitespace or `utm_` tracking, not a
host `phase4/licences.deny_family` refuses (this project's own site, the AI aggregators, the
Wikipedia mirrors, the blocked domains); a title of 1-300 characters; a quote of 20-500 characters
after the quote check's own normalisation. Every note is 1-600 characters.

**The quote check** (`check_quotes`) is the Opus re-verification's, unchanged
(`opus_audit/quotes.py`, through `acceptance.answers.check_quotes`), on pages fetched once each into
a page store (`cli.py`: the import's own under the run, `check-answer`'s under the batch) - with two
additions. A page that is not a Wikipedia page and shares a run of 25 words with the checked
description is a copy of our own text (`licences.is_mirror`, the Phase-4 mirror rule), and a quote on
it does not count. And the quote's title, which the citation list publishes, must stand in the page's
text (its heading, whitespace and case aside): a title the page does not carry does not count
either, so no invented or garbled title reaches a citation. The fetcher is
`requests` with the User-Agent `AncientMapRemediation/1.0 (research)` (no personal data in any
request): measured on 2026-09-26, httpx with that User-Agent is answered 403 by en/de.wikipedia.org,
britannica.com and whc.unesco.org, which answer requests 200 (`FETCH_MEASURED`).

**A judge answer** (`parse_judge`) is `{site_id, kept, dropped, coherent, note}`: one verdict per kept
sentence (`SUPPORTED`, `UNSUPPORTED`, `WRONG` - a quote needed) and per dropped one (`DROP_OK`,
`DROP_WRONG` - a quote needed), quotes `{url, quote}`.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import requests

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

import research_web  # noqa: E402
from acceptance.answers import AnswerError, Quote, check_quotes, load_object  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402
from phase4 import licences, wc4  # noqa: E402 - Phase 4's deny list and mirror rule; lane WC

__all__ = ["AnswerError"]

#: The User-Agent of every WC request: the lanes' one (`research_web`), no personal data.
USER_AGENT = research_web.USER_AGENT
#: What the fetcher was chosen on (2026-09-26, one GET each with the User-Agent above): httpx 0.28.1
#: vs requests 2.32.5. Only requests passes where it matters; neither passes the 403 hosts, which the
#: question names so the agents quote elsewhere.
FETCH_MEASURED = {
    "https://en.wikipedia.org/wiki/Stonehenge": ("httpx 403", "requests 200"),
    "https://de.wikipedia.org/wiki/Stonehenge": ("httpx 403", "requests 200"),
    "https://www.britannica.com/topic/Stonehenge": ("httpx 403", "requests 200"),
    "https://whc.unesco.org/en/list/373/": ("httpx 403", "requests 200"),
    "https://www.worldhistory.org/stonehenge/": ("httpx 200", "requests 200"),
    "https://historicengland.org.uk/listing/the-list/list-entry/1012397": (
        "httpx 403",
        "requests 403",
    ),
    "https://canmore.org.uk/site/3104": ("httpx 403", "requests 403"),
}

CHECK_KEYS = frozenset({"site_id", "sentences"})
SENTENCE_KEYS = frozenset({"n", "verdict", "remove", "reason", "quotes", "note"})
QUOTE_KEYS = frozenset({"url", "title", "quote"})
JUDGE_KEYS = frozenset({"site_id", "kept", "dropped", "coherent", "note"})
JUDGE_KEPT_KEYS = frozenset({"k", "verdict", "quotes", "note"})
JUDGE_DROPPED_KEYS = frozenset({"d", "verdict", "quotes", "note"})
JUDGE_QUOTE_KEYS = frozenset({"url", "quote"})
KEPT_VERDICTS = ("SUPPORTED", "UNSUPPORTED", "WRONG")
DROPPED_VERDICTS = ("DROP_OK", "DROP_WRONG")
MAX_QUOTES = 4
MIN_QUOTE_CHARS = 20
MAX_QUOTE_CHARS = 500
MAX_TITLE_CHARS = 300
MAX_NOTE_CHARS = 600
#: A mirror of our own text: why a quote on it does not count (the Phase-4 mirror rule).
MIRROR = "mirror of this description"
#: The quote was found, its title was not: the citation would publish a title the page lacks.
TITLE_NOT_ON_PAGE = "title not on page"
DENIED = "denied source"


# ------------------------------------------------------------------------------ the fetcher
class Client:
    """What `opus_audit/quotes.collect` needs of a client - `get(url)` with `status_code`, `url`,
    `headers` and `content` - over `requests`, every GET bounded by the quote check's timeout."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def get(self, url: str) -> requests.Response:
        return self.session.get(url, timeout=Q.TIMEOUT_SECONDS, allow_redirects=True)

    def close(self) -> None:
        self.session.close()


#: The errors a failed fetch raises: `collect` records them as the page's failure.
FETCH_ERRORS = (requests.RequestException,)


# ------------------------------------------------------------------------------ the shapes
def _text(value: Any, what: str, *, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AnswerError(f"{what} is not a non-empty string")
    if len(value) > limit:
        raise AnswerError(f"{what} is {len(value)} characters, at most {limit}")
    return value


def url_problem(url: str) -> str | None:
    """Why a quote's URL is refused before anything is fetched, or `None`."""
    if not isinstance(url, str) or url != url.strip() or any(c.isspace() for c in url):
        return f"{url!r} is not a URL without whitespace"
    if not Q.is_url(url):
        return f"{url!r} is not an http(s) URL"
    try:
        family = licences.deny_family(url)
    except ValueError as exc:
        return str(exc)
    if family is not None:
        return f"{url} is a {family} host: never a source"
    if any(key.lower().startswith("utm_") for key, _ in parse_qsl(urlsplit(url).query)):
        return f"{url} carries utm_ tracking parameters: give the page's own URL"
    return None


@dataclass(frozen=True)
class SentenceAnswer:
    """One sentence of a check answer, as the agent gave it."""

    n: int
    verdict: wc4.Verdict
    remove: str | None
    reason: wc4.DropReason | None
    quotes: tuple[wc4.Quote, ...]
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "verdict": self.verdict.value,
            "remove": self.remove,
            "reason": None if self.reason is None else self.reason.value,
            "quotes": [quote.to_dict() for quote in self.quotes],
            "note": self.note,
        }


def _check_quotes(value: Any, where: str) -> tuple[wc4.Quote, ...]:
    if not isinstance(value, list):
        raise AnswerError(f"{where}: quotes is not a list")
    if len(value) > MAX_QUOTES:
        raise AnswerError(f"{where}: {len(value)} quotes, at most {MAX_QUOTES}")
    out: list[wc4.Quote] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != QUOTE_KEYS:
            keys = sorted(item) if isinstance(item, dict) else item
            raise AnswerError(f"{where}: a quote carries {keys!r}, not {sorted(QUOTE_KEYS)}")
        problem = url_problem(item["url"])
        if problem is not None:
            raise AnswerError(f"{where}: {problem}")
        title = _text(item["title"], f"{where}: a title", limit=MAX_TITLE_CHARS)
        if not isinstance(item["quote"], str):
            raise AnswerError(f"{where}: a quote is not a string")
        length = len(Q.normalise(item["quote"]))
        if not MIN_QUOTE_CHARS <= length <= MAX_QUOTE_CHARS:
            raise AnswerError(
                f"{where}: a quote of {length} characters; {MIN_QUOTE_CHARS}-{MAX_QUOTE_CHARS}"
            )
        out.append(wc4.Quote(url=item["url"], title=title.strip(), quote=item["quote"]))
    return tuple(out)


def parse_sentence(item: Any, sentence: str) -> SentenceAnswer:
    """One sentence's answer against the sentence it answers; `AnswerError` names the problem."""
    if not isinstance(item, dict) or set(item) != SENTENCE_KEYS:
        keys = sorted(item) if isinstance(item, dict) else item
        raise AnswerError(f"a sentence answer carries {keys!r}, not {sorted(SENTENCE_KEYS)}")
    n = item["n"]
    where = f"S{n}"
    try:
        verdict = wc4.Verdict(item["verdict"])
    except ValueError:
        raise AnswerError(
            f"{where}: verdict {item['verdict']!r} is not KEEP, KEEP_TRIMMED or DROP"
        ) from None
    quotes = _check_quotes(item["quotes"], where)
    note = _text(item["note"], f"{where}: note", limit=MAX_NOTE_CHARS)
    remove, reason = item["remove"], item["reason"]
    if verdict is wc4.Verdict.DROP:
        if remove is not None:
            raise AnswerError(f"{where}: a DROP removes nothing (remove is null)")
        if reason not in [r.value for r in wc4.AGENT_REASONS]:
            raise AnswerError(f"{where}: a DROP's reason is 'contradicted' or 'unsupported'")
        drop = wc4.DropReason(reason)
        if (drop is wc4.DropReason.CONTRADICTED) != bool(quotes):
            raise AnswerError(
                f"{where}: 'contradicted' gives the contradicting quote, 'unsupported' none"
            )
        return SentenceAnswer(n, verdict, None, drop, quotes, note)
    if reason is not None:
        raise AnswerError(f"{where}: a kept sentence has no reason (reason is null)")
    if not quotes:
        raise AnswerError(f"{where}: a kept sentence rests on at least one quote")
    if verdict is wc4.Verdict.KEEP:
        if remove is not None:
            raise AnswerError(
                f"{where}: KEEP removes nothing (remove is null); a cut is KEEP_TRIMMED"
            )
        return SentenceAnswer(n, verdict, None, None, quotes, note)
    if not isinstance(remove, str):
        raise AnswerError(f"{where}: KEEP_TRIMMED names the piece to remove")
    try:
        wc4.trim(sentence, remove)
    except wc4.WcError as exc:
        raise AnswerError(f"{where}: {exc}") from None
    return SentenceAnswer(n, verdict, remove, None, quotes, note)


def parse_check(
    text: str, *, site_id: str, sentences: Sequence[str], asked: Sequence[int]
) -> tuple[SentenceAnswer, ...]:
    """A check answer: the site it names, and exactly the asked sentences, in order."""
    data = load_object(text, CHECK_KEYS)
    if data["site_id"] != site_id:
        raise AnswerError(f"the answer names site {data['site_id']!r}, the question {site_id}")
    items = data["sentences"]
    if not isinstance(items, list):
        raise AnswerError("sentences is not a list")
    numbers = [item.get("n") if isinstance(item, dict) else None for item in items]
    if any(isinstance(n, bool) or not isinstance(n, int) for n in numbers):
        raise AnswerError(f"every sentence answer names its number n as an integer: {numbers}")
    if numbers != list(asked):
        raise AnswerError(f"the answer covers sentences {numbers}, the question asks {list(asked)}")
    return tuple(parse_sentence(item, sentences[item["n"] - 1]) for item in items)


# ------------------------------------------------------------------------------ the quote check
@dataclass(frozen=True)
class QuoteOutcome:
    """One quote as the check found it: counted or not, the check's outcome and detail."""

    quote: wc4.Quote
    verified: bool
    outcome: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.quote.to_dict(),
            "verified": self.verified,
            "outcome": self.outcome,
            "detail": self.detail,
        }


def is_wikipedia(url: str) -> bool:
    return licences.is_wikipedia_host(licences.host_of(url))


def title_on_page(title: str, page: Q.Source) -> bool:
    """Does the page's text carry the title (normalised as the quotes are, case aside)?"""
    wanted = Q.normalise(title).casefold()
    return any(wanted in text.casefold() for _, text in page.texts)


def quote_outcomes(
    label: str, quotes: Sequence[wc4.Quote], library: Q.Library, *, checked: str
) -> tuple[QuoteOutcome, ...]:
    """Every quote against its stored page (`acceptance.answers.check_quotes`, i.e. the Opus
    re-verification's check), then the mirror rule - a found quote on a non-Wikipedia page that
    shares a run of 25 words with the checked description (`checked`, read without its markers,
    as its reader and a scraper see it) does not count - and the title rule: a found quote whose
    title the page's text does not carry does not count."""
    check = check_quotes(label, [Quote(q.url, q.quote, None) for q in quotes], library)
    served = wc4.strip_markers(checked)
    out: list[QuoteOutcome] = []
    for quote, result in zip(quotes, check.results, strict=True):
        if result["outcome"] != Q.FOUND:
            out.append(QuoteOutcome(quote, False, result["outcome"], result["detail"]))
            continue
        page = library.url(quote.url)
        if not is_wikipedia(quote.url) and any(
            licences.is_mirror(text, served) for _, text in page.texts
        ):
            out.append(QuoteOutcome(quote, False, MIRROR, "shares 25 words with our text"))
        elif not title_on_page(quote.title, page):
            out.append(
                QuoteOutcome(quote, False, TITLE_NOT_ON_PAGE, f"{quote.title!r} is not on the page")
            )
        else:
            out.append(QuoteOutcome(quote, True, Q.FOUND, result["detail"]))
    return tuple(out)


# ------------------------------------------------------------------------------ the judge
@dataclass(frozen=True)
class JudgeItem:
    number: int
    verdict: str
    quotes: tuple[Quote, ...]
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "verdict": self.verdict,
            "quotes": [{"url": q.url, "quote": q.quote} for q in self.quotes],
            "note": self.note,
        }


@dataclass(frozen=True)
class JudgeAnswer:
    kept: tuple[JudgeItem, ...]
    dropped: tuple[JudgeItem, ...]
    coherent: bool
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kept": [item.to_dict() for item in self.kept],
            "dropped": [item.to_dict() for item in self.dropped],
            "coherent": self.coherent,
            "note": self.note,
        }


def _judge_items(
    value: Any, *, key: str, keys: frozenset[str], verdicts: Sequence[str], count: int, needs: str
) -> tuple[JudgeItem, ...]:
    if not isinstance(value, list):
        raise AnswerError(f"{key} is not a list")
    numbers = [item.get(key[0]) if isinstance(item, dict) else None for item in value]
    if numbers != list(range(1, count + 1)):
        raise AnswerError(f"{key} covers {numbers}, the question has 1..{count}")
    out: list[JudgeItem] = []
    for item in value:
        if set(item) != keys:
            raise AnswerError(f"a {key} item carries {sorted(item)}, not {sorted(keys)}")
        where = f"{key[0].upper()}{item[key[0]]}"
        if item["verdict"] not in verdicts:
            raise AnswerError(f"{where}: verdict {item['verdict']!r} is not one of {verdicts}")
        if not isinstance(item["quotes"], list) or len(item["quotes"]) > MAX_QUOTES:
            raise AnswerError(f"{where}: quotes is a list of at most {MAX_QUOTES}")
        quotes: list[Quote] = []
        for quote in item["quotes"]:
            if not isinstance(quote, dict) or set(quote) != JUDGE_QUOTE_KEYS:
                raise AnswerError(f"{where}: a quote is {{url, quote}}")
            problem = url_problem(quote["url"])
            if problem is not None:
                raise AnswerError(f"{where}: {problem}")
            if not isinstance(quote["quote"], str) or not (
                MIN_QUOTE_CHARS <= len(Q.normalise(quote["quote"])) <= MAX_QUOTE_CHARS
            ):
                raise AnswerError(f"{where}: a quote of {MIN_QUOTE_CHARS}-{MAX_QUOTE_CHARS} chars")
            quotes.append(Quote(quote["url"], quote["quote"], None))
        if item["verdict"] == needs and not quotes:
            raise AnswerError(f"{where}: {needs} rests on at least one quote")
        note = _text(item["note"], f"{where}: note", limit=MAX_NOTE_CHARS)
        out.append(JudgeItem(item[key[0]], item["verdict"], tuple(quotes), note))
    return tuple(out)


def parse_judge(text: str, *, site_id: str, kept: int, dropped: int) -> JudgeAnswer:
    """A judge answer about a site with `kept` kept and `dropped` dropped sentences."""
    data = load_object(text, JUDGE_KEYS)
    if data["site_id"] != site_id:
        raise AnswerError(f"the answer names site {data['site_id']!r}, the question {site_id}")
    if not isinstance(data["coherent"], bool):
        raise AnswerError("coherent is true or false")
    return JudgeAnswer(
        kept=_judge_items(
            data["kept"],
            key="kept",
            keys=JUDGE_KEPT_KEYS,
            verdicts=KEPT_VERDICTS,
            count=kept,
            needs="WRONG",
        ),
        dropped=_judge_items(
            data["dropped"],
            key="dropped",
            keys=JUDGE_DROPPED_KEYS,
            verdicts=DROPPED_VERDICTS,
            count=dropped,
            needs="DROP_WRONG",
        ),
        coherent=data["coherent"],
        note=_text(data["note"], "note", limit=MAX_NOTE_CHARS),
    )
