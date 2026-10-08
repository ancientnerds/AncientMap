"""Contract shorts-v1's answer shapes: the writer's three variants, the hook rater's ratings, the
checker's wider verdict and the rewrite after a failed web verification.

The web judge's shape is the v1 one (`answers.parse_judge`): the verifier is unchanged, only its
prompt is (`prompts_shorts.judge_prompt`). Like v1's, every parser takes one JSON object and nothing
else, and refuses what is not exactly its shape with the reason - nothing is defaulted or repaired
(`run.check_answer` shows the reason to the agent; the import runs the parsers again).

* `parse_writer`: `{"variants": [3 x {card, basis, anchors, reserve, hook_type}]}`, or, for a thin
  description only, `{"card": null, "thin": true, "reason": "..."}` (C19, owner decision D3: enrich
  first, never pad). The three variants differ in their cards and in their first three words, so the
  rater has something to choose between.
* `parse_rater`: `{"ratings": [{variant, first5, hook}], "best": n}`; one rating per variant shown,
  the first five words copied exactly, the hook 1-5, `best` a variant with the highest rating.
* `parse_checker`: v1's claims, tone and site fields plus `name_leak`, `hook_ok`, `s1_no_place`,
  `payoff_ok`, `generic_ok`, `loop_ok` and `anchors_ok`. PASS needs every judgement field good -
  `name_leak` false, the others true - every claim supported and no reason.
* `parse_verify_writer`: the rewrite after a failed verification: one variant plus `repeats`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from teaser import answers as A
from teaser import contract as C
from teaser import shorts_v1 as SV

#: The hook rater's scale and the floor of the best opening (a lower best sends the site to a
#: rewrite round).
MIN_HOOK, MAX_HOOK = 1, 5
HOOK_FLOOR = 3
VARIANT_KEYS = frozenset({"card", "basis", "anchors", "reserve", "hook_type"})
WRITER_KEYS = frozenset({"variants"})
THIN_KEYS = frozenset({"card", "thin", "reason"})
RATER_KEYS = frozenset({"ratings", "best"})
RATING_KEYS = frozenset({"variant", "first5", "hook"})
#: The checker's judgement fields; `name_leak` is the one where false is good.
GOOD_WHEN_TRUE = (
    "this_site",
    "hook_ok",
    "s1_no_place",
    "payoff_ok",
    "generic_ok",
    "loop_ok",
    "tone_ok",
    "anchors_ok",
)
CHECKER_KEYS = frozenset({"claims", "name_leak", "verdict", "reasons", *GOOD_WHEN_TRUE})


@dataclass(frozen=True)
class Variant:
    """One card of a writer's answer with what the Short needs beside the text: the sentences it
    rests on, the photo anchors, the reserve and the declared hook type. `number` is its place in
    the answer (1-3), 0 for the single card of a rewrite."""

    number: int
    text: str
    card: str
    basis: tuple[str, ...]
    anchors: tuple[str, ...]
    reserve: tuple[str, ...] | None
    hook_type: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "written": self.text,
            "card": self.card,
            "basis": list(self.basis),
            "anchors": list(self.anchors),
            "reserve": None if self.reserve is None else list(self.reserve),
            "hook_type": self.hook_type,
        }


@dataclass(frozen=True)
class Thin:
    """A writer's decline of a thin description (C19); `reason` is in its own words. The contract
    proves the premise (`shorts_v1.thin_proof`), the shape does not."""

    reason: str


def _variant(data: Any, site: SV.ShortsBasis, number: int) -> Variant:
    if not isinstance(data, dict) or set(data) != VARIANT_KEYS:
        found = sorted(data) if isinstance(data, dict) else type(data).__name__
        raise A.AnswerError(f"variant {number} carries {found}, not {sorted(VARIANT_KEYS)}")
    return _read_variant(data, site, number, f"variant {number}")


def _read_variant(data: dict[str, Any], site: SV.ShortsBasis, number: int, what: str) -> Variant:
    written = A._string(data["card"], f"{what}'s card")
    basis = A._ids(data["basis"], site, f"{what}'s basis")
    if not basis:
        raise A.AnswerError(f"{what}'s basis names no sentence - every card rests on at least one")
    anchors = data["anchors"]
    if not isinstance(anchors, list) or not all(isinstance(a, str) and a.strip() for a in anchors):
        raise A.AnswerError(f"{what}'s anchors is not a list of non-empty strings")
    reserve = data["reserve"]
    if reserve is not None and (
        not isinstance(reserve, list) or not all(isinstance(r, str) for r in reserve)
    ):
        raise A.AnswerError(f"{what}'s reserve is neither null nor a list of strings")
    if data["hook_type"] not in SV.HOOK_TYPES:
        raise A.AnswerError(
            f"{what}'s hook_type {data['hook_type']!r} is not one of {SV.HOOK_TYPES}"
        )
    return Variant(
        number=number,
        text=written,
        card=C.final_card(written),
        basis=basis,
        anchors=tuple(anchors),
        reserve=None if reserve is None else tuple(reserve),
        hook_type=data["hook_type"],
    )


def parse_writer(text: str, site: SV.ShortsBasis) -> tuple[Variant, ...] | Thin:
    """The writer's answer: three distinct variants, or a thin decline."""
    data = A._object(text, WRITER_KEYS, THIN_KEYS)
    if set(data) == THIN_KEYS:
        if data["card"] is not None or data["thin"] is not True:
            raise A.AnswerError('a thin decline is exactly {"card": null, "thin": true, "reason"}')
        reason = A._string(data["reason"], "reason")
        try:
            SV.thin_proof(site)
        except ValueError as exc:
            raise A.AnswerError(str(exc)) from exc
        return Thin(reason)
    raw = data["variants"]
    if not isinstance(raw, list) or len(raw) != SV.VARIANTS:
        found = len(raw) if isinstance(raw, list) else type(raw).__name__
        raise A.AnswerError(f"variants has {found} entries, it has exactly {SV.VARIANTS}")
    variants = tuple(_variant(entry, site, number) for number, entry in enumerate(raw, start=1))
    if len({v.card for v in variants}) != len(variants):
        raise A.AnswerError("two variants are the same card")
    openings = [SV.opening(v.card, 3) for v in variants]
    if len(set(openings)) != len(openings):
        raise A.AnswerError("two variants open with the same three words; they must differ")
    return variants


@dataclass(frozen=True)
class Rewritten:
    """The rewrite after a failed verification: one variant and, per contradicted claim, the
    description sentence that states it (`None` where none does)."""

    variant: Variant
    repeats: tuple[str | None, ...]


def parse_verify_writer(text: str, site: SV.ShortsBasis, contradicted: int) -> Rewritten:
    """`{"card", "basis", "repeats", "anchors", "reserve", "hook_type"}`: v1's rewrite after a
    failed verification with the shorts-v1 fields; `repeats` is read as v1 reads it."""
    data = A._object(text, VARIANT_KEYS | {"repeats"})
    variant = _read_variant(data, site, 0, "the card")
    repeats = data["repeats"]
    if not isinstance(repeats, list) or len(repeats) != contradicted:
        found = len(repeats) if isinstance(repeats, list) else type(repeats).__name__
        raise A.AnswerError(
            f"repeats has {found} entries: it has one per contradicted claim, {contradicted}"
        )
    for number, entry in enumerate(repeats, start=1):
        if entry is not None and entry not in site.described_ids:
            raise A.AnswerError(
                f"repeats entry {number} ({entry!r}) is neither null nor the id of a sentence of "
                "the description"
            )
    return Rewritten(variant, tuple(repeats))


@dataclass(frozen=True)
class Rated:
    """The hook rater's answer: a rating per variant shown and the best."""

    ratings: tuple[tuple[int, str, int], ...]
    best: int

    @property
    def best_rating(self) -> int:
        return next(hook for number, _, hook in self.ratings if number == self.best)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ratings": [
                {"variant": number, "first5": first5, "hook": hook}
                for number, first5, hook in self.ratings
            ],
            "best": self.best,
        }


def first_five(card: str) -> str:
    """The first five words of a card as the rater copies them: the words as written."""
    return " ".join(card.split()[:5])


def parse_rater(text: str, shown: Sequence[tuple[int, str]]) -> Rated:
    """`shown` is `(variant number, final card)` of every variant the rater was asked about."""
    data = A._object(text, RATER_KEYS)
    raw = data["ratings"]
    if not isinstance(raw, list):
        raise A.AnswerError("ratings is not a list")
    cards = dict(shown)
    ratings: list[tuple[int, str, int]] = []
    for entry in raw:
        if not isinstance(entry, dict) or set(entry) != RATING_KEYS:
            raise A.AnswerError(f"a rating is not {sorted(RATING_KEYS)}")
        number, hook = entry["variant"], entry["hook"]
        if type(number) is not int or number not in cards:
            raise A.AnswerError(f"a rating names variant {number!r}, not one of {sorted(cards)}")
        if type(hook) is not int or not MIN_HOOK <= hook <= MAX_HOOK:
            raise A.AnswerError(
                f"variant {number}'s hook is not a whole number {MIN_HOOK}-{MAX_HOOK}"
            )
        first5 = A._string(entry["first5"], f"variant {number}'s first5")
        if first5 != first_five(cards[number]):
            raise A.AnswerError(
                f"variant {number}'s first5 is not its first five words: "
                f"{first_five(cards[number])!r}"
            )
        ratings.append((number, first5, hook))
    if sorted(number for number, _, _ in ratings) != sorted(cards):
        raise A.AnswerError(
            f"the ratings cover variants {sorted(n for n, _, _ in ratings)}, the "
            f"question shows {sorted(cards)}: one rating per variant"
        )
    best = data["best"]
    if type(best) is not int or best not in cards:
        raise A.AnswerError(f"best {best!r} is not one of the variants shown {sorted(cards)}")
    top = max(hook for _, _, hook in ratings)
    if next(hook for number, _, hook in ratings if number == best) != top:
        raise A.AnswerError(f"best is variant {best}, which does not have the highest hook ({top})")
    return Rated(tuple(sorted(ratings)), best)


@dataclass(frozen=True)
class Checked:
    """A shorts-v1 checker's answer, consistent with its own verdict. The v1 fields keep their
    shape (`claims`, `this_site`, `tone_ok`, `verdict`, `reasons`)."""

    claims: tuple[tuple[str, tuple[str, ...]], ...]
    flags: tuple[tuple[str, bool], ...]
    verdict: str
    reasons: tuple[str, ...]

    @property
    def tone_ok(self) -> bool:
        return dict(self.flags)["tone_ok"]

    @property
    def this_site(self) -> bool:
        return dict(self.flags)["this_site"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "claims": [{"claim": claim, "support": list(ids)} for claim, ids in self.claims],
            **dict(self.flags),
            "verdict": self.verdict,
            "reasons": list(self.reasons),
        }


def parse_checker(text: str, site: SV.ShortsBasis) -> Checked:
    """PASS is refused with an unsupported claim, a judgement field that is bad, or a reason; FAIL
    is refused without a reason. A checker that lists no claim has not read the card."""
    data = A._object(text, CHECKER_KEYS)
    raw_claims = data["claims"]
    if not isinstance(raw_claims, list) or not raw_claims:
        raise A.AnswerError("claims is not a non-empty list - every card makes at least one claim")
    claims: list[tuple[str, tuple[str, ...]]] = []
    for number, raw in enumerate(raw_claims, start=1):
        if not isinstance(raw, dict) or set(raw) != {"claim", "support"}:
            raise A.AnswerError(f"claim {number} is not {{'claim', 'support'}}")
        claims.append(
            (
                A._string(raw["claim"], f"claim {number}"),
                A._ids(raw["support"], site, f"claim {number}'s support"),
            )
        )
    flags = []
    for key in ("name_leak", *GOOD_WHEN_TRUE):
        if not isinstance(data[key], bool):
            raise A.AnswerError(f"{key} is not true or false")
        flags.append((key, data[key]))
    if data["verdict"] not in A.VERDICTS:
        raise A.AnswerError(f"verdict {data['verdict']!r} is not PASS or FAIL")
    raw_reasons = data["reasons"]
    if not isinstance(raw_reasons, list):
        raise A.AnswerError("reasons is not a list")
    reasons = tuple(A._string(reason, "a reason") for reason in raw_reasons)
    unsupported = [claim for claim, ids in claims if not ids]
    if data["verdict"] == A.PASSED:
        if unsupported:
            raise A.AnswerError(f"PASS with an unsupported claim: {unsupported[0]!r}")
        if data["name_leak"]:
            raise A.AnswerError("PASS with name_leak true")
        bad = [key for key in GOOD_WHEN_TRUE if not data[key]]
        if bad:
            raise A.AnswerError(f"PASS with {', '.join(bad)} false")
        if reasons:
            raise A.AnswerError("PASS with a reason - a card with a finding is a FAIL")
    elif not reasons:
        raise A.AnswerError("FAIL without a reason - the rewrite needs the finding")
    return Checked(tuple(claims), tuple(flags), data["verdict"], reasons)
