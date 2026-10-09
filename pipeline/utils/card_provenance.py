# SPDX-License-Identifier: AGPL-3.0-only
"""A teaser card's provenance: `unified_sites.raw_data._card_provenance`, written by lane WB.

Owner decisions O2-O4 and O10 of 2026-09-26 (`output/remediation/FINISH_PLAN_2026-09-26.md`,
contract `docs/procedures/CARD_DESCRIPTIONS.md`): every curated card is a teaser of 160-190
characters that an Opus agent writes from the site's published description and a second, independent
Opus agent checks claim by claim against that description. The card is AI-generated text, so it is
marked as such wherever it is shown or narrated:

* `ai: 'generated'` - the SiteCard's `data-card-ai`, the AI footnote on the site page and the AI note
  in the shorts description (O10, "wie bisher");
* `text_sha256` - the card the provenance describes. A disclosure is a statement about one text: a
  card changed by any other path (an old card file imported at boot, an admin edit) is not the card
  this provenance describes, and nothing is claimed for it;
* `desc_sha256` - the description the card was written from and checked against. When the
  description changes afterwards the card is **stale**: still AI-generated (the mark stays), but no
  longer proven against the text the site shows, so it is not shorts-eligible until lane WB writes
  and checks it again;
* `check` - the independent checker's verdict (`PASS`, the only verdict lane WB writes), its stage,
  its agent, its time and the claims it mapped to the description's sentence ids (`S1`, `S2`, ... in
  the order `scripts/remediation/teaser/contract.description_sentences` numbers them) - or to a web
  fact (`W1`, ...), see `web_facts`;
* `verify` - the independent web verification of the card (owner O2: "natuerlich muessen sie
  inhaltlich stimmen"): `VERIFIED`, the only verdict lane WB writes - no claim contradicted by a
  page, at most `MAX_UNPROVEN_CLAIMS` claim without a proving quote and never the central one - with
  the verifier's stage, agent and time, the counts of its claims and of those it could not prove, and
  the sha256 of the text it judged (`text_sha256`: always the card's own - a verification of another
  text proves nothing about this one). The verifier is never the checker (nor, by the run's rule,
  anyone who wrote or checked the card);
* `web_facts` - `[]`, except for a card rewritten after a failed verification (checker stage
  `check-v`, verifier stage `verify2`) that corrects a contradicted claim with a fact the first
  verifier quoted from a page: each such quote (`W1`, ...: id, URL, quote) that a claim of `check`
  cites, and no other - the card's fact basis beyond its description.

Version 3 (contract `shorts-v1`, owner decisions D1-D6 of 2026-10-08) is the provenance of a nameless
Shorts card. It keeps every key of version 2 and adds `contract`, `models` (the answer stamp of the
model that wrote, rated, checked and verified the card - `rate` is `None` for the one card rewritten
after a failed verification, which is not rated), `hook` (the declared type, the rater's rating 1-5
and the variant 1-3 the card was; `None` and `None` for that same rewrite), `anchors` (the photo
phrases the Short cuts its stills on), `reserve` (the description sentences held back for the page, or
`reveal`, or `None`) and `shorts_ready`. `ai_system` is derived from the stamps in `models` at the
one place a provenance enters a write (`scripts/remediation/mechanical/teaser.py`, which holds the
strings): this module checks the shape only, since `pipeline/` cannot import the lane. Version 2
stays valid: the 2,830 cards written before are version 2, and their site pages are unchanged. The
shorts gate (`shorts_pin`) pins a version-3 card only: a card that names its site cannot be narrated.

The key is its own, beside `_description_provenance`, because the description's provenance is
replaced whole whenever a description is rewritten (Phase 4, lane WC), and a card outlives that. The
leading underscore keeps it out of the generic raw_data panel (`src/config/sourceFields.ts`).

One reading for every reader - the site API (`api/services/description_provenance.card_ai`), the
site page's SSR payload and the shorts export (`pipeline/video/shorts_export.py`) - so the three
cannot disagree. Stdlib only: the Lyra image ships `pipeline/` without `api/`.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

#: The raw_data key lane WB writes (`scripts/remediation/mechanical/teaser.py`).
CARD_PROVENANCE_KEY = "_card_provenance"
#: 2 since the web verification (2026-09-26): `verify` and `web_facts`. No version 1 was ever
#: written (read-only count 2026-09-26 21:00 UTC: 0 teaser provenances in production).
VERSION = 2
#: Version 3: contract `shorts-v1`, the nameless Shorts card. `build` writes version 2, `build_v3`
#: version 3; `validate` accepts both (`VERSIONS`).
VERSION_3 = 3
VERSIONS = (VERSION, VERSION_3)
KIND = "teaser"
LANE = "WB"
#: The AI mark: the card's words are written by an AI system (EU AI Act Art. 50).
AI_GENERATED = "generated"
#: The only verdict a written teaser carries: a card the checker failed is rewritten or cleared.
ACCEPTING_VERDICT = "PASS"
#: The checker stage of the one rewrite after a failed verification (`teaser/run.py`).
VERIFY_REWRITE_CHECK = "check-v"
#: The checker stages of lane WB (`scripts/remediation/teaser/run.py`).
CHECK_STAGES = frozenset({"check", "check1", "check2", VERIFY_REWRITE_CHECK})
#: The only verdict of the web verification a written teaser carries.
VERIFIED = "VERIFIED"
#: The verification of a card the checker accepted, and of its rewrite after a failed one.
FIRST_VERIFY, SECOND_VERIFY = "verify", "verify2"
#: A VERIFIED card has at most this many claims without a proving quote (UNVERIFIABLE, or a quote
#: the machine did not find on its page), and its central claim - what the site is - is never one.
#: The rule and its reasons: docs/procedures/CARD_DESCRIPTIONS.md, section 2.1.
MAX_UNPROVEN_CLAIMS = 1
#: The contract of a version-3 provenance (`scripts/remediation/teaser/shorts_v1.py`).
CONTRACT_SHORTS = "shorts-v1"
#: The stages a version-3 provenance names a model for.
MODEL_STAGES = ("write", "rate", "check", "verify")
#: The hook types a writer declares (`shorts_v1.HOOK_TYPES` is this tuple).
HOOK_TYPES = ("object", "act", "person", "number", "name_meaning", "absence")
#: The best rating of a hook (1-5) and the number of variants a writer answers (1-3).
MAX_RATING = 5
MAX_VARIANT = 3
MAX_ANCHORS = 3
REVEAL = "reveal"

_KEYS = frozenset(
    {
        "v",
        "kind",
        "lane",
        "ai",
        "ai_system",
        "run",
        "text_sha256",
        "desc_sha256",
        "check",
        "verify",
        "web_facts",
    }
)
_KEYS_V3 = _KEYS | {"contract", "models", "hook", "anchors", "reserve", "shorts_ready"}
_HOOK_KEYS = frozenset({"type", "rating", "variant"})
_RESERVE_ID = re.compile(r"S[1-9][0-9]*")
_CHECK_KEYS = frozenset({"verdict", "stage", "by", "at", "claims"})
_CLAIM_KEYS = frozenset({"claim", "support"})
_VERIFY_KEYS = frozenset({"verdict", "stage", "by", "at", "claims", "unproven", "text_sha256"})
_WEB_FACT_KEYS = frozenset({"id", "url", "quote"})
_SHA256 = re.compile(r"[0-9a-f]{64}")
#: A claim's support: a sentence of the description (`S3`) or a web fact (`W1`).
_SUPPORT_ID = re.compile(r"[SW][1-9][0-9]*")
_WEB_FACT_ID = re.compile(r"W[1-9][0-9]*")


def text_sha256(text: str) -> str:
    """The sha256 of a text's UTF-8 bytes, lowercase hex: the form both hashes use."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _need(condition: bool, why: str) -> None:
    if not condition:
        raise ValueError(f"{CARD_PROVENANCE_KEY}: {why}")


def _text(value: Any, what: str) -> None:
    _need(isinstance(value, str) and bool(value.strip()), f"{what} is not a non-empty string")


def validate(value: Any) -> dict[str, Any]:
    """`value` if it is a teaser card provenance in exactly its shape, else `ValueError`.

    Nothing is defaulted: a missing or extra key, another kind, lane, mark or version, a hash that is
    not a sha256, a check verdict other than PASS, a claim without a sentence id, a verification
    other than VERIFIED (beyond the unproven limit, by the checker, out of step with the check, or
    of another text than the card), or a web fact no claim cites (or a cited one missing) is
    refused, so a malformed provenance
    fails on every reader alike instead of reading as "nothing to disclose".
    """
    _need(isinstance(value, dict), f"is not a JSON object but {type(value).__name__}")
    version = value.get("v")
    _need(type(version) is int and version in VERSIONS, f"v is not one of {list(VERSIONS)}")
    keys = _KEYS if version == VERSION else _KEYS_V3
    _need(set(value) == keys, f"carries {sorted(value)}, not {sorted(keys)}")
    _need(value["kind"] == KIND, f"kind {value['kind']!r} is not {KIND!r}")
    _need(value["lane"] == LANE, f"lane {value['lane']!r} is not {LANE!r}")
    _need(value["ai"] == AI_GENERATED, f"ai {value['ai']!r} is not {AI_GENERATED!r}")
    _text(value["ai_system"], "ai_system")
    _text(value["run"], "run")
    for key in ("text_sha256", "desc_sha256"):
        _need(
            isinstance(value[key], str) and bool(_SHA256.fullmatch(value[key])),
            f"{key} is not a lowercase sha256",
        )
    check = value["check"]
    _need(isinstance(check, dict) and set(check) == _CHECK_KEYS, "check is not the check shape")
    _need(check["verdict"] == ACCEPTING_VERDICT, f"check.verdict {check['verdict']!r} is not PASS")
    _need(check["stage"] in CHECK_STAGES, f"check.stage {check['stage']!r} is no checker stage")
    _text(check["by"], "check.by")
    _text(check["at"], "check.at")
    claims = check["claims"]
    _need(isinstance(claims, list) and bool(claims), "check.claims is not a non-empty list")
    for claim in claims:
        _need(isinstance(claim, dict) and set(claim) == _CLAIM_KEYS, "a claim is not the shape")
        _text(claim["claim"], "a claim")
        support = claim["support"]
        _need(
            isinstance(support, list)
            and bool(support)
            and all(isinstance(s, str) and _SUPPORT_ID.fullmatch(s) for s in support),
            f"claim {claim['claim']!r} names no sentence id",
        )
    _web_facts(value["web_facts"], claims, check["stage"])
    _verify(value["verify"], check, value["text_sha256"])
    if version == VERSION_3:
        _shorts(value, check["stage"])
    return value


def _stamp_or_none(value: Any, what: str, *, allowed_none: bool) -> None:
    if value is None:
        _need(allowed_none, f"{what} is null")
        return
    _text(value, what)


def _shorts(value: Mapping[str, Any], check_stage: str) -> None:
    """The keys a version-3 provenance adds: the contract, the models of its four stages, the hook,
    the anchors, the reserve and `shorts_ready`. The one card that is not rated is the rewrite after
    a failed verification (checked at `check-v`): its `models.rate`, `hook.rating` and
    `hook.variant` are `None`, and only its."""
    _need(
        value["contract"] == CONTRACT_SHORTS,
        f"contract {value['contract']!r} is not {CONTRACT_SHORTS!r}",
    )
    unrated = check_stage == VERIFY_REWRITE_CHECK
    models = value["models"]
    _need(
        isinstance(models, dict) and set(models) == set(MODEL_STAGES),
        f"models is not {list(MODEL_STAGES)}",
    )
    for stage in MODEL_STAGES:
        _stamp_or_none(models[stage], f"models.{stage}", allowed_none=stage == "rate" and unrated)
    _need(
        (models["rate"] is None) == unrated,
        "models.rate is null exactly for the rewrite after a failed verification",
    )
    hook = value["hook"]
    _need(isinstance(hook, dict) and set(hook) == _HOOK_KEYS, "hook is not the hook shape")
    _need(hook["type"] in HOOK_TYPES, f"hook.type {hook['type']!r} is not one of {HOOK_TYPES}")
    for key, top in (("rating", MAX_RATING), ("variant", MAX_VARIANT)):
        if unrated:
            _need(hook[key] is None, f"hook.{key} of a rewrite after a failed verification is null")
        else:
            _need(
                type(hook[key]) is int and 1 <= hook[key] <= top,
                f"hook.{key} is not a whole number 1-{top}",
            )
    anchors = value["anchors"]
    _need(
        isinstance(anchors, list)
        and len(anchors) <= MAX_ANCHORS
        and all(isinstance(a, str) and bool(a.strip()) for a in anchors),
        f"anchors is not a list of at most {MAX_ANCHORS} non-empty strings",
    )
    reserve = value["reserve"]
    _need(
        reserve is None
        or (
            isinstance(reserve, list)
            and bool(reserve)
            and len(set(reserve)) == len(reserve)
            and all(
                isinstance(r, str) and (r == REVEAL or bool(_RESERVE_ID.fullmatch(r)))
                for r in reserve
            )
        ),
        f"reserve is neither null nor a list of sentence ids and {REVEAL!r}",
    )
    ready = value["shorts_ready"]
    _need(type(ready) is bool, "shorts_ready is not true or false")
    _need(
        not ready or (reserve is not None and bool(anchors)),
        "shorts_ready needs a reserve and at least one anchor",
    )


def _web_facts(facts: Any, claims: list[dict[str, Any]], stage: str) -> None:
    """The web facts: well formed, exactly those the claims cite, and only after a rewrite."""
    _need(isinstance(facts, list), "web_facts is not a list")
    ids: list[str] = []
    for fact in facts:
        _need(isinstance(fact, dict) and set(fact) == _WEB_FACT_KEYS, "a web fact is not the shape")
        _need(
            isinstance(fact["id"], str) and bool(_WEB_FACT_ID.fullmatch(fact["id"])),
            f"web fact id {fact['id']!r} is not W<n>",
        )
        _need(
            isinstance(fact["url"], str) and fact["url"].startswith(("https://", "http://")),
            f"web fact {fact['id']}'s url is not an http(s) URL",
        )
        _text(fact["quote"], f"web fact {fact['id']}'s quote")
        ids.append(fact["id"])
    _need(len(set(ids)) == len(ids), "web_facts names an id twice")
    cited = {s for claim in claims for s in claim["support"] if s.startswith("W")}
    _need(
        cited == set(ids),
        f"web_facts {sorted(ids)} are not exactly the web facts the claims cite {sorted(cited)}",
    )
    _need(
        not ids or stage == VERIFY_REWRITE_CHECK,
        f"web facts on a card checked at {stage!r}: only a rewrite after a failed verification "
        "rests on one",
    )


def _verify(verify: Any, check: Mapping[str, Any], card_sha256: str) -> None:
    """The web verification: VERIFIED, of the card this provenance hashes, within the unproven
    limit, by another agent than the checker, at the verification stage that follows the check's
    stage."""
    _need(
        isinstance(verify, dict) and set(verify) == _VERIFY_KEYS, "verify is not the verify shape"
    )
    _need(verify["verdict"] == VERIFIED, f"verify.verdict {verify['verdict']!r} is not VERIFIED")
    _need(
        verify["text_sha256"] == card_sha256,
        "verify.text_sha256 is not the card the provenance hashes: the verifier judged another text",
    )
    after_rewrite = check["stage"] == VERIFY_REWRITE_CHECK
    _need(
        verify["stage"] == (SECOND_VERIFY if after_rewrite else FIRST_VERIFY),
        f"verify.stage {verify['stage']!r} does not follow check.stage {check['stage']!r}",
    )
    _text(verify["by"], "verify.by")
    _text(verify["at"], "verify.at")
    _need(verify["by"] != check["by"], "the verifier is the checker")
    claims, unproven = verify["claims"], verify["unproven"]
    _need(type(claims) is int and claims >= 1, "verify.claims is not a positive count")
    _need(
        type(unproven) is int and 0 <= unproven <= min(MAX_UNPROVEN_CLAIMS, claims - 1),
        f"verify.unproven {unproven!r} is beyond the limit of a VERIFIED card",
    )


def card_provenance_of(raw_data: Any) -> dict[str, Any] | None:
    """The teaser provenance of a `raw_data` value (a dict, a JSON string or `None`).

    `None` only when there is none: no raw_data object, or no key. A key that is present is
    validated (`validate`): a malformed one raises instead of reading as "no provenance".
    """
    if isinstance(raw_data, str):
        raw_data = json.loads(raw_data)
    if not isinstance(raw_data, Mapping) or CARD_PROVENANCE_KEY not in raw_data:
        return None
    return validate(raw_data[CARD_PROVENANCE_KEY])


def build(
    *,
    run: str,
    ai_system: str,
    card: str,
    description: str,
    stage: str,
    checker: str,
    checked_at: str,
    claims: Sequence[Mapping[str, Any]],
    verify: Mapping[str, Any],
    web_facts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """The provenance of one checked and verified teaser card, validated: the one place its shape
    is built. `verify` carries `_VERIFY_KEYS` (its `text_sha256` the sha256 of the text the verifier
    judged, which `validate` holds to the card's), each web fact `_WEB_FACT_KEYS`."""
    return validate(
        {
            "v": VERSION,
            "kind": KIND,
            "lane": LANE,
            "ai": AI_GENERATED,
            "ai_system": ai_system,
            "run": run,
            "text_sha256": text_sha256(card),
            "desc_sha256": text_sha256(description),
            "check": {
                "verdict": ACCEPTING_VERDICT,
                "stage": stage,
                "by": checker,
                "at": checked_at,
                "claims": [
                    {"claim": claim["claim"], "support": list(claim["support"])} for claim in claims
                ],
            },
            "verify": {key: verify[key] for key in sorted(_VERIFY_KEYS)},
            "web_facts": [{key: fact[key] for key in sorted(_WEB_FACT_KEYS)} for fact in web_facts],
        }
    )


def build_v3(
    *,
    run: str,
    ai_system: str,
    card: str,
    description: str,
    stage: str,
    checker: str,
    checked_at: str,
    claims: Sequence[Mapping[str, Any]],
    verify: Mapping[str, Any],
    web_facts: Sequence[Mapping[str, Any]],
    models: Mapping[str, str | None],
    hook: Mapping[str, Any],
    anchors: Sequence[str],
    reserve: Sequence[str] | None,
    shorts_ready: bool,
) -> dict[str, Any]:
    """The version-3 provenance of one checked and verified shorts-v1 card, validated: `build`'s
    inputs plus the contract's. `ai_system` must be derived from `models` by the caller (the lane
    holds the strings)."""
    base = build(
        run=run,
        ai_system=ai_system,
        card=card,
        description=description,
        stage=stage,
        checker=checker,
        checked_at=checked_at,
        claims=claims,
        verify=verify,
        web_facts=web_facts,
    )
    return validate(
        {
            **base,
            "v": VERSION_3,
            "contract": CONTRACT_SHORTS,
            "models": {stage_name: models[stage_name] for stage_name in MODEL_STAGES},
            "hook": {key: hook[key] for key in sorted(_HOOK_KEYS)},
            "anchors": list(anchors),
            "reserve": None if reserve is None else list(reserve),
            "shorts_ready": shorts_ready,
        }
    )


def describes(provenance: Mapping[str, Any], card: str | None) -> bool:
    """Whether `card` is exactly the card the provenance hashes."""
    return card is not None and provenance["text_sha256"] == text_sha256(card)


def stale(provenance: Mapping[str, Any], description: str | None) -> bool:
    """Whether the description changed since the card was written and checked from it."""
    return description is None or provenance["desc_sha256"] != text_sha256(description)


def card_ai(provenance: Mapping[str, Any], card: str | None) -> str | None:
    """The AI mark of `card`: `generated` while it is the card the provenance hashes, else `None`.

    A stale card keeps its mark: its words are still an AI system's, whatever the description does.
    """
    return AI_GENERATED if describes(provenance, card) else None


def shorts_pin(provenance: Mapping[str, Any], description: str | None) -> str | None:
    """The card hash the shorts gate (S13) may narrate: the provenance's own `text_sha256` of a
    version-3 card that is `shorts_ready` while the description is the one the card was checked
    against. `None` for a stale card - a short narrates only a card proven against the text the
    site shows - and for a version-2 card, which names its site and cannot be a Short (owner
    decision D1, 2026-10-08)."""
    if stale(provenance, description):
        return None
    if provenance["v"] != VERSION_3 or not provenance["shorts_ready"]:
        return None
    return provenance["text_sha256"]
