"""Lane WB's answer shapes: the strict JSON a writer, a checker and the pilot judge return.

`check-answer` (run.py) runs these parsers on an answer before the agent records it, and the import
runs them again: an answer is either exactly its shape or refused with the reason - nothing is
defaulted, repaired or guessed. The text is one JSON object and nothing else (no fence, no prose).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from teaser import contract as C

PASSED = "PASS"
FAILED = "FAIL"
VERDICTS = (PASSED, FAILED)
JUDGE_VERDICTS = ("SUPPORTED", "CONTRADICTED", "UNVERIFIABLE")
#: A quote shorter than this proves nothing: `the`, a date, a name alone are on any page.
MIN_QUOTE_CHARS = 20


class AnswerError(ValueError):
    """The answer is not its stage's shape; the reason is shown to the agent that wrote it."""


def _object(text: str, keys: frozenset[str]) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped.startswith("{"):
        raise AnswerError("the answer must be one JSON object and nothing else (no prose, no ```)")
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise AnswerError(f"not JSON: {exc}") from exc
    if not isinstance(data, dict) or set(data) != keys:
        found = sorted(data) if isinstance(data, dict) else type(data).__name__
        raise AnswerError(f"the object carries {found}, it must carry exactly {sorted(keys)}")
    return data


def _string(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AnswerError(f"{what} is not a non-empty string")
    return value


def _ids(value: Any, site: C.Basis, what: str) -> tuple[str, ...]:
    try:
        return C.sentence_ids(value, site, what)
    except ValueError as exc:
        raise AnswerError(str(exc)) from exc


@dataclass(frozen=True)
class Written:
    """A writer's answer: the text as written, the final card, and the sentences it rests on."""

    text: str
    card: str
    basis: tuple[str, ...]


def parse_writer(text: str, site: C.Basis) -> Written:
    """`{"card": str, "basis": [sentence ids, at least one]}`; the card is made final here."""
    data = _object(text, frozenset({"card", "basis"}))
    written = _string(data["card"], "card")
    basis = _ids(data["basis"], site, "basis")
    if not basis:
        raise AnswerError("basis names no sentence - every card rests on at least one")
    return Written(text=written, card=C.final_card(written), basis=basis)


@dataclass(frozen=True)
class Checked:
    """A checker's answer, consistent with its own verdict."""

    claims: tuple[tuple[str, tuple[str, ...]], ...]
    tone_ok: bool
    this_site: bool
    verdict: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "claims": [{"claim": claim, "support": list(ids)} for claim, ids in self.claims],
            "tone_ok": self.tone_ok,
            "this_site": self.this_site,
            "verdict": self.verdict,
            "reasons": list(self.reasons),
        }


def parse_checker(text: str, site: C.Basis) -> Checked:
    """`{"claims": [...], "tone_ok": bool, "this_site": bool, "verdict": PASS|FAIL, "reasons": [...]}`.

    PASS is refused unless every claim names a supporting sentence, tone_ok and this_site are true
    and no reason is given; FAIL is refused without a reason. A checker that lists no claim has not
    read the card.
    """
    data = _object(text, frozenset({"claims", "tone_ok", "this_site", "verdict", "reasons"}))
    raw_claims = data["claims"]
    if not isinstance(raw_claims, list) or not raw_claims:
        raise AnswerError("claims is not a non-empty list - every card makes at least one claim")
    claims: list[tuple[str, tuple[str, ...]]] = []
    for number, raw in enumerate(raw_claims, start=1):
        if not isinstance(raw, dict) or set(raw) != {"claim", "support"}:
            raise AnswerError(f"claim {number} is not {{'claim', 'support'}}")
        claims.append(
            (
                _string(raw["claim"], f"claim {number}"),
                _ids(raw["support"], site, f"claim {number}'s support"),
            )
        )
    for key in ("tone_ok", "this_site"):
        if not isinstance(data[key], bool):
            raise AnswerError(f"{key} is not true or false")
    if data["verdict"] not in VERDICTS:
        raise AnswerError(f"verdict {data['verdict']!r} is not PASS or FAIL")
    raw_reasons = data["reasons"]
    if not isinstance(raw_reasons, list):
        raise AnswerError("reasons is not a list")
    reasons = tuple(_string(reason, "a reason") for reason in raw_reasons)
    unsupported = [claim for claim, ids in claims if not ids]
    if data["verdict"] == PASSED:
        if unsupported:
            raise AnswerError(f"PASS with an unsupported claim: {unsupported[0]!r}")
        if not (data["tone_ok"] and data["this_site"]):
            raise AnswerError("PASS with tone_ok or this_site false")
        if reasons:
            raise AnswerError("PASS with a reason - a card with a finding is a FAIL")
    elif not reasons:
        raise AnswerError("FAIL without a reason - the rewrite needs the finding")
    return Checked(
        claims=tuple(claims),
        tone_ok=data["tone_ok"],
        this_site=data["this_site"],
        verdict=data["verdict"],
        reasons=reasons,
    )


@dataclass(frozen=True)
class Judged:
    """One claim of the pilot judge: its verdict and, unless UNVERIFIABLE, the page and quote."""

    claim: str
    verdict: str
    url: str | None
    quote: str | None


def parse_judge(text: str) -> tuple[Judged, ...]:
    """`{"claims": [{"claim", "verdict", "url", "quote"}, ...]}`, each verdict in its shape."""
    data = _object(text, frozenset({"claims"}))
    raw_claims = data["claims"]
    if not isinstance(raw_claims, list) or not raw_claims:
        raise AnswerError("claims is not a non-empty list")
    judged: list[Judged] = []
    for number, raw in enumerate(raw_claims, start=1):
        keys = {"claim", "verdict", "url", "quote"}
        if not isinstance(raw, dict) or set(raw) != keys:
            raise AnswerError(f"claim {number} is not {sorted(keys)}")
        claim = _string(raw["claim"], f"claim {number}")
        verdict = raw["verdict"]
        if verdict not in JUDGE_VERDICTS:
            raise AnswerError(f"claim {number}: verdict {verdict!r} is not one of {JUDGE_VERDICTS}")
        if verdict == "UNVERIFIABLE":
            if raw["url"] is not None or raw["quote"] is not None:
                raise AnswerError(f"claim {number}: UNVERIFIABLE carries no url and no quote")
            judged.append(Judged(claim, verdict, None, None))
            continue
        url = _string(raw["url"], f"claim {number}'s url")
        if not url.startswith(("https://", "http://")):
            raise AnswerError(f"claim {number}: the url is not an http(s) URL")
        quote = _string(raw["quote"], f"claim {number}'s quote")
        if len(quote.strip()) < MIN_QUOTE_CHARS:
            raise AnswerError(
                f"claim {number}: the quote is {len(quote.strip())} characters, at least "
                f"{MIN_QUOTE_CHARS}"
            )
        judged.append(Judged(claim, verdict, url, quote))
    return tuple(judged)
