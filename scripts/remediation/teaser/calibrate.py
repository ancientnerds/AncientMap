"""Calibration of the card lane's roles (owner decision D6, 2026-10-08; plan `cards.md` 3.4).

Before a role gives its first answer of lane WB it re-answers cases that were judged already, and is
measured against them. The thresholds are **sealed before any answer exists**; a role that fails moves
up one tier (Haiku to Sonnet to Opus, `roles.escalation`) and is calibrated again in a directory of its
own. Nothing here calls a model: the answers come from the orchestrator's agents through
`opus_handoff.py answer --role`, exactly as in a run.

The cases are the lane's own record - the Opus-era runs `output/remediation/teaser/runs/wb-*`
(never an answer by MiniMax: a record is ground truth only if its stamp is not MiniMax's, or, when it
carries none, if it was given before the MiniMax cutover of 2026-10-03; master plan X6), the live
cards of the production export and a file of vetted shorts-v1 cards (`--base-cards`).

    seal      THRESHOLDS.json (the table below, the sha256 of every prompt-bearing module and of the
              role registry), its sha256 logged in SEAL.jsonl. Refused once any case, answer or
              verdict exists in the directory.
    jobs      the fixed cases (JOBS.jsonl) drawn with the sealed seed from the recorded runs, the
              export and the base cards; fixed by its sha256 in SEAL.jsonl; never rewritten. Refused
              unless the seal is in place and the modules still hash to it.
    export    every case of one ROLE into a handoff directory, shuffled and under opaque keys (batches
              of 15, of 5 for a web role), to be answered by agents of that role. A role never sees
              which kind of case it is asked: the keys, the batch ids and the stage name
              (`calibration`) say nothing, and the case a key stands for is written in JOBS.jsonl
              alone.
    evaluate  one role: every set measured against the sealed thresholds, VERDICT-<role>.json written
              once. A failing role carries its `tier_move` (`run.py escalate` applies it).
    release   a verdict that failed and is held at the top tier (Opus has no tier above): who decided
              it should stand, why, and the sha256 of the verdict, the sealed thresholds, the role's
              registry entry and the evidence, into RELEASE-<role>.json, once.
    standing  how a role's verdict stands: passed, or released (a release that still rests on what
              it was made on). Refused otherwise - this is what a gate asks.

    T=scripts/remediation/teaser/calibrate.py     D=output/remediation/calibration/teaser-<id>
    $T seal --run-dir $D
    $T jobs --run-dir $D --runs output/remediation/teaser/runs/wb-ws-2026-09-27-01 ... \\
        --export output/remediation/teaser/runs/<run>/EXPORT.jsonl --base-cards BASE.jsonl
    $T export --run-dir $D --role fact_checker --handoff output/remediation/handoff/cal-<id>-...
    $T agents --run-dir $D --role fact_checker             one workflow job per batch: role, fixed
        model id, effort, brief, how many may run at once (JSON)
    $T evaluate --run-dir $D --role fact_checker           (web_verifier: fetches the cited pages)
    $T evaluate --run-dir $D --role card_writer --writer-run output/remediation/teaser/runs/<pilot>
    $T release --run-dir $D --role hook_rater --decided-by TEXT --reason TEXT --evidence FILE ...
    $T standing --run-dir $D --role hook_rater

`BASE.jsonl` is one JSON object per line: `site_id, name, country, description, alt_names,
pool_images, image_titles, card, anchors` and `"sample": true` on the eleven cards of the design's
pilot samples. It holds at least as many cards as the sealed `checker_defects` set and exactly the
sealed number of samples; every card passes `shorts_v1.problems_shorts` - the file's author vets it.
"""

from __future__ import annotations

import argparse
import difflib
import functools
import hashlib
import json
import math
import random
import re
import sys
import unicodedata
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT, ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import calibrate_claude as CC  # noqa: E402 - the evidence a release rests on
import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
import web_rules as WR  # noqa: E402 - how an agent uses the Wikipedia cache and the web
from image_roles.wiki_cache import WikiCache  # noqa: E402
from mechanical.plan import PlanError, parse_tagged_export  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402
from phase3.run import read_jsonl  # noqa: E402
from phase4 import verify4 as V  # noqa: E402 - the brand fonts' measurement of a card

from teaser import answers as A  # noqa: E402
from teaser import answers_shorts as AS  # noqa: E402
from teaser import contract as C  # noqa: E402
from teaser import prompts as P  # noqa: E402
from teaser import prompts_shorts as PS  # noqa: E402
from teaser import run as R  # noqa: E402
from teaser import shorts_v1 as SV  # noqa: E402

CALIBRATION_ROOT = ROOT / "output" / "remediation" / "calibration"
SEAL_LOG = "SEAL.jsonl"
THRESHOLDS_FILE = "THRESHOLDS.json"
JOBS_FILE = "JOBS.jsonl"
HANDOFFS_FILE = "HANDOFFS.json"
VERDICT_FILE = "VERDICT-{role}.json"
#: `release`: the decision to let a verdict stand that failed and is held at the top tier.
RELEASE_FILE = "RELEASE-{role}.json"
#: The first day MiniMax answered lane WB (owner decision of 2026-10-03). A recorded answer that
#: carries no model stamp and was given on or after it is not ground truth.
MINIMAX_CUTOVER = "2026-10-03"
BATCH_SIZE = 15
WEB_BATCH_SIZE = 5
#: The stage every calibration question is exported and answered under: it names no set.
STAGE = "calibration"
#: A fresh claim covers a recorded one of the same card when at least this share of the recorded
#: claim's content words stand in the fresh claim, or the two read this close (difflib ratio). Many
#: recorded claims may be covered by one fresh claim (an agent that lists a compound claim once).
CLAIM_MATCH = 0.6
#: Words that carry no claim: dropped before the content words of two claims are compared.
STOP_WORDS = frozenset(
    "the and was were are for with from that this its has had have been which into near also "
    "his her their there than then when who whom whose".split()
)

#: The recorded contradictions of the web verifier's sample that are disputed or hair-splitting, not
#: plain errors of the card (Opus diagnosis of calibration teaser-2026-10-09, 2026-10-09): they stay
#: in the sample and are reported, but do not count in the denominator of `caught_min`. Site id ->
#: why. A key that is not the site id of a contradicted case of the draw is refused by the evaluation.
DISPUTED_CONTRADICTIONS: dict[str, str] = {
    "5be3cff9-8b07-4cfc-b667-933e2d0ae302": "Undavalli Caves: the 4th-5th century date is disputed "
    "(the ASI dates the earliest phase to the 7th century); Wikipedia and Live History India agree "
    "with the card",
    "3f512971-679b-4f40-8f5e-1467424ce605": "Dolmen de Viera: the discoverers' surname (Fuentes "
    "against Viera Fuentes) - a naming convention, not a wrong fact",
    "9e723832-0a2b-43f9-90d1-3743b61b91ed": "Lot's Cave: April 606 (UNESCO, Wikipedia) against "
    "605 or 607 (the excavator) - the sources differ by one year",
    "93dd77da-64ad-4947-96b3-8ead4d6c98c1": "Mormont: 'burial pits' against the excavators' "
    "'deposit pits' for the same 245 pits",
    "b7cc5073-ffca-4cd3-a168-3062908d4959": "Beacon Hill, West Sussex: the tense of 'lie' about a "
    "mound the sources say was ploughed out - a reading of the card, not a wrong fact",
}

#: The sealed table of plan `cards.md` 3.4, as amended by the diagnosis of calibration
#: teaser-2026-10-09 (the claim measure is a coverage; the disputed contradictions are out of the
#: `caught_min` denominator). Every number is a threshold fixed before the first answer; the counts
#: are the sizes of the fixed sample. `modules` is added at the seal.
THRESHOLDS: dict[str, Any] = {
    "version": "teaser-calibration-v1",
    "source": "output/remediation/final-2026-10-08/plans/cards.md section 3.4",
    "seed": 20261009,
    "roles": {
        "fact_checker": {
            "sets": {
                "checker_agreement": {
                    "pass_cases": 30,
                    "fail_cases": 15,
                    "verdict_agreement_min": 0.90,
                    "claim_coverage_min": 0.80,
                    "claim_agreement_min": 0.90,
                    "false_pass_max": 0,
                },
                "checker_fail_again": {"cases": 30, "fail_min": 27},
                "checker_defects": {"cases": 30, "caught_min": 27},
                "checker_good": {"cases": 30, "pass_min": 27},
            }
        },
        "web_verifier": {
            "sets": {
                "verifier_contradicted": {
                    "cases": 20,
                    "caught_min": 18,
                    "disputed": DISPUTED_CONTRADICTIONS,
                },
                "verifier_verified": {
                    "cases": 20,
                    "falsely_contradicted_max": 2,
                    "claim_coverage_min": 0.80,
                    "claim_agreement_min": 0.90,
                    "false_sources_max": 0,
                },
            }
        },
        "hook_rater": {
            "sets": {
                "hook_pairs": {
                    "strong": 11,
                    "weak": 13,
                    "ordered_right_min": 1.0,
                    "reference_within_one_min": 0.80,
                }
            }
        },
        "card_writer": {"sets": {"writer_pilot": {"sites": 40, "clean_first_min": 0.80}}},
        "adversarial": {
            "sets": {
                "adversarial_contradicted": {"cases": 25},
                "adversarial_clean": {"cases": 25},
                "adversarial_agreement": {"agreement_min": 0.90},
            }
        },
    },
}
#: The set whose answers (by the pilot judge, Opus xhigh) are the hook rater's reference.
HOOK_REFERENCE = "hook_reference"
#: Which role answers which set of cases, and with which prompt.
SET_ROLE: dict[str, str] = {
    "checker_agreement": "fact_checker",
    "checker_fail_again": "fact_checker",
    "checker_defects": "fact_checker",
    "checker_good": "fact_checker",
    "verifier_contradicted": "web_verifier",
    "verifier_verified": "web_verifier",
    "hook_pairs": "hook_rater",
    HOOK_REFERENCE: "pilot_judge",
    "adversarial_contradicted": "adversarial",
    "adversarial_clean": "adversarial",
}
WEB_SETS = frozenset(
    {"verifier_contradicted", "verifier_verified", "adversarial_contradicted", "adversarial_clean"}
)
#: The files the prompts and answer shapes of the calibrated roles live in: a seal binds a
#: calibration to their exact bytes, as a run pins its prompts by sha256.
MODULES = (
    "scripts/remediation/roles.py",
    "scripts/remediation/teaser/contract.py",
    "scripts/remediation/teaser/prompts.py",
    "scripts/remediation/teaser/answers.py",
    "scripts/remediation/teaser/shorts_v1.py",
    "scripts/remediation/teaser/prompts_shorts.py",
    "scripts/remediation/teaser/answers_shorts.py",
    # the code the questions are built and the answers judged with (a change moves the measure)
    "scripts/remediation/teaser/run.py",
    "scripts/remediation/teaser/calibrate.py",
    "scripts/remediation/opus_audit/quotes.py",
    "scripts/remediation/wc/answers.py",  # the source rule `prove_claims` applies (url_problem)
    "scripts/remediation/phase4/licences.py",  # `wc.answers.url_problem` -> `deny_family`
    "pipeline/utils/card_provenance.py",  # MAX_UNPROVEN_CLAIMS: VERIFIED against UNPROVEN
    "scripts/remediation/image_roles/wiki_cache.py",  # the WIKI_MAP the web agents read
    "scripts/remediation/web_rules.py",
    "scripts/remediation/quote_check.py",
    "scripts/remediation/opus_handoff.py",
)


class CalibrationError(RuntimeError):
    """The calibration cannot take this step. Nothing is guessed and nothing is half-written."""


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _text(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def module_hashes(root: Path = ROOT, names: Iterable[str] | None = None) -> dict[str, str]:
    """The sha256 of each module's bytes in the checkout `root` - those of `MODULES` unless the
    caller names others (a seal checks the modules it was sealed with)."""
    wanted = MODULES if names is None else names
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sorted(wanted)}


# ------------------------------------------------------------------------------ the seal
def seal(
    run_dir: Path,
    *,
    thresholds: Mapping[str, Any] = THRESHOLDS,
    now: Callable[[], str] = _now,
    root: Path = ROOT,
) -> str:
    """Write THRESHOLDS.json and log its sha256 - before any case, answer or verdict exists in
    `run_dir`. The registry entries of the calibrated roles are sealed with it."""
    present = [p for p in (JOBS_FILE, HANDOFFS_FILE) if (run_dir / p).exists()]
    present += [p.name for p in run_dir.glob("VERDICT-*.json")] if run_dir.exists() else []
    if present:
        raise CalibrationError(
            f"{run_dir} holds {present}: thresholds are sealed before the first case, not after"
        )
    sealed = {
        **thresholds,
        "modules": module_hashes(root),
        "registry": {
            name: {
                "model": RO.role(name).model,
                "effort": RO.role(name).effort,
                "sha256": RO.role_sha256(name),
            }
            for name in (*thresholds["roles"], RO.role("pilot_judge").name)
        },
    }
    text = _text(sealed)
    path = run_dir / THRESHOLDS_FILE
    if path.exists() and path.read_text(encoding="utf-8") != text:
        raise CalibrationError(f"{path} holds other thresholds - a sealed file is never rewritten")
    run_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    digest = _sha(text)
    with (run_dir / SEAL_LOG).open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"thresholds_sha256": digest, "sealed_at": now()}) + "\n")
    return digest


SEALED_KEY, FIXED_KEY = "thresholds_sha256", "jobs_sha256"


def _seal_log(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / SEAL_LOG
    if not path.is_file():
        raise CalibrationError(f"{run_dir} is not sealed - run `calibrate.py seal` first")
    entries = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
    for entry in entries:
        if (SEALED_KEY in entry) == (FIXED_KEY in entry):
            raise CalibrationError(f"{path}: a line that is neither the seal nor the fixed cases")
    return entries


def integrity(run_dir: Path) -> tuple[dict[str, Any], str]:
    """The sealed thresholds and their sha256 - refusing only a file that is not the one the log
    sealed. For a step that reads no prompt and judges no answer (`void_answers` moves a file aside),
    so that it can serve a calibration sealed with an older checkout of the modules."""
    entries = [e for e in _seal_log(run_dir) if SEALED_KEY in e]
    if len({e[SEALED_KEY] for e in entries}) != 1:
        raise CalibrationError(f"{run_dir / SEAL_LOG} records more than one thresholds hash")
    path = run_dir / THRESHOLDS_FILE
    text = path.read_text(encoding="utf-8")
    if _sha(text) != entries[0][SEALED_KEY]:
        raise CalibrationError(f"{path} changed after it was sealed")
    return json.loads(text), _sha(text)


def sealed(run_dir: Path, *, root: Path = ROOT) -> tuple[dict[str, Any], str]:
    """The sealed thresholds and their sha256 - refusing a file that is not the one the log sealed
    and a calibration whose prompts, answer shapes, quote check or role registry changed after the
    seal (the modules the seal recorded are hashed in `root`)."""
    thresholds, digest = integrity(run_dir)
    sealed_with = module_hashes(root, thresholds["modules"])
    moved = [n for n, recorded in thresholds["modules"].items() if sealed_with[n] != recorded]
    if moved:
        raise CalibrationError(
            f"{moved} changed after the seal: the prompts the cases are asked with are not the ones "
            "sealed - seal a new calibration"
        )
    for name, entry in thresholds["registry"].items():
        if RO.role_sha256(name) != entry["sha256"]:
            raise CalibrationError(f"the registry entry of role {name} changed after the seal")
    return thresholds, digest


# ------------------------------------------------------------------------------ the cases
def ground_truth(record: Mapping[str, Any]) -> bool:
    """Whether a recorded answer may judge a role: never MiniMax's, and an unstamped one only from
    before the MiniMax cutover."""
    model = record.get("model")
    if model is not None:
        return bool(model != OH.MINIMAX_MODEL)
    return str(record["answered_at"]) < MINIMAX_CUTOVER


@functools.cache
def _sites(run: Path) -> dict[str, dict[str, Any]]:
    return {row["site_id"]: row for row in read_jsonl(run / "SITES.jsonl")}


def _site(run: Path, site_id: str) -> dict[str, Any]:
    return _sites(run)[site_id]


def _case(
    set_name: str, number: int, prompt_kind: str, site: Mapping[str, Any], **extra: Any
) -> dict[str, Any]:
    return {
        "number": number,
        "set": set_name,
        "role": SET_ROLE[set_name],
        "prompt_kind": prompt_kind,
        "site_id": site["site_id"],
        "name": site["name"],
        "country": site["country"],
        "description": site["description"],
        "alt_names": list(site["alt_names"]),
        **extra,
    }


def recorded_checks(runs: Sequence[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The ground-truth check records of the runs' first three rounds: `(PASS, FAIL)` in a fixed
    order, each with its site's basis inputs and the card it judged."""
    passes: list[dict[str, Any]] = []
    fails: list[dict[str, Any]] = []
    for run in runs:
        records = R.stage_records(run)
        for stage in ("check", "check1", "check2"):
            for site_id, record in sorted(records[stage].items()):
                if not ground_truth(record):
                    continue
                item = {
                    "run": run.name,
                    "stage": stage,
                    "record": record,
                    "site": _site(run, site_id),
                }
                (passes if record["verdict"] == A.PASSED else fails).append(item)
    return passes, fails


def recorded_verifications(
    runs: Sequence[Path],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The ground-truth first verifications with their check: `(VERIFIED, CONTRADICTED with a
    proven contradiction)`."""
    verified: list[dict[str, Any]] = []
    contradicted: list[dict[str, Any]] = []
    for run in runs:
        records = R.stage_records(run)
        for site_id, record in sorted(records[R.FIRST_VERIFY].items()):
            check = records["check"].get(site_id)
            if check is None or not ground_truth(record) or not ground_truth(check):
                continue
            if check["card"] != record["card"]:
                continue
            item = {
                "run": run.name,
                "record": record,
                "check": check,
                "site": _site(run, site_id),
            }
            if record["verdict"] == R.VERIFIED:
                verified.append(item)
            elif any(c["verdict"] == R.CONTRADICTED and c["proven"] for c in record["claims"]):
                contradicted.append(item)
    return verified, contradicted


def _draw(pool: Sequence[Any], count: int, rng: random.Random, what: str) -> list[Any]:
    if len(pool) < count:
        raise CalibrationError(f"{what}: {len(pool)} recorded case(s), {count} sealed")
    return rng.sample(list(pool), count)


def _checker_job(set_name: str, number: int, item: Mapping[str, Any]) -> dict[str, Any]:
    record = item["record"]
    return _case(
        set_name,
        number,
        "checker_v1",
        item["site"],
        card=record["card"],
        recorded={
            "run": item["run"],
            "stage": item["stage"],
            "verdict": record["verdict"],
            "claims": record["claims"],
            "reasons": record["reasons"],
        },
    )


def _verifier_job(set_name: str, number: int, item: Mapping[str, Any]) -> dict[str, Any]:
    record = item["record"]
    return _case(
        set_name,
        number,
        "judge_v1",
        item["site"],
        card=record["card"],
        # the fewest claims the verifier may list: as many as the check that accepted the card
        # listed, as `run.import_stage` holds a production verifier to (`claims_floor`)
        floor=len(item["check"]["claims"]),
        recorded={
            "run": item["run"],
            "verdict": record["verdict"],
            "claims": [
                {k: c[k] for k in ("claim", "verdict", "url", "quote", "proven")}
                for c in record["claims"]
            ],
        },
    )


def _adversarial_job(
    set_name: str, number: int, item: Mapping[str, Any], *, withhold: bool
) -> dict[str, Any]:
    """The reviewer's case: the card, the checker's claim map and the verifier's evidence. For a card
    the web contradicted the contradicted claims are left out of the evidence - a reviewer is asked
    about what a verifier missed, not what it found."""
    record = item["record"]
    claims = [
        {k: c[k] for k in ("claim", "verdict", "url", "quote", "proven", "quote_outcome")}
        for c in record["claims"]
        if not (withhold and c["verdict"] == R.CONTRADICTED)
    ]
    return _case(
        set_name,
        number,
        "adversarial",
        item["site"],
        card=record["card"],
        check={"claims": item["check"]["claims"]},
        verify={"claims": claims},
        expected="FAIL" if withhold else "PASS",
    )


def _base_basis(row: Mapping[str, Any]) -> SV.ShortsBasis:
    return SV.shorts_basis(
        site_id=row["site_id"],
        name=row["name"],
        country=row["country"],
        description=row["description"],
        alt_names=row["alt_names"],
        pool_images=row["pool_images"],
        image_titles=row["image_titles"],
    )


def read_base_cards(path: Path, fit: C.Fit | None = None) -> list[dict[str, Any]]:
    """The vetted shorts-v1 cards of `--base-cards`, each checked against the mechanical contract."""
    rows = read_jsonl(path)
    for row in rows:
        site = _base_basis(row)
        found = (
            []
            if fit is None
            else SV.problems_shorts(
                C.final_card(row["card"]), site, row["anchors"], ["reveal"], fit, basis=[]
            )
        )
        found = [p for p in found if not p.startswith("reserve")]
        if found:
            raise CalibrationError(
                f"{path}: the card of {row['name']!r} breaks the contract: {found}"
            )
    return rows


def weak_openers(export: Path, count: int, rng: random.Random) -> list[dict[str, Any]]:
    """Live cards that open with a place word (the March shape the contract replaces): from a
    production export of `run.py select`."""
    parsed, _at = parse_tagged_export(export.read_text(encoding="utf-8"), ("site",))
    pool = [
        row
        for row in sorted(parsed["site"], key=lambda r: str(r["site_id"]))
        if row["card"] and SV.first_word(row["card"]) in SV.LOCATION_PREPOSITIONS
    ]
    return [
        {
            "site_id": row["site_id"],
            "name": row["name"],
            "country": row["country"],
            "description": row["description"] or "",
            "alt_names": list(row["alt_names"]),
            "card": row["card"],
        }
        for row in _draw(pool, count, rng, "live cards that open with a place word")
    ]


def build_jobs(
    thresholds: Mapping[str, Any],
    *,
    runs: Sequence[Path],
    export: Path,
    base_cards: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """The fixed cases, drawn with the sealed seed. Pure over its inputs."""
    rng = random.Random(thresholds["seed"])  # noqa: S311 - a sealed, seeded draw
    roles = thresholds["roles"]
    jobs: list[dict[str, Any]] = []

    passes, fails = recorded_checks(runs)
    spec = roles["fact_checker"]["sets"]
    agree, again = spec["checker_agreement"], spec["checker_fail_again"]
    drawn_pass = _draw(passes, agree["pass_cases"], rng, "recorded checker PASS")
    drawn_fail = _draw(fails, agree["fail_cases"] + again["cases"], rng, "recorded checker FAIL")
    both = [*drawn_pass, *drawn_fail[: agree["fail_cases"]]]
    jobs += [_checker_job("checker_agreement", n, i) for n, i in enumerate(both, start=1)]
    jobs += [
        _checker_job("checker_fail_again", n, i)
        for n, i in enumerate(drawn_fail[agree["fail_cases"] :], start=1)
    ]

    needed = spec["checker_defects"]["cases"]
    if len(base_cards) < needed or spec["checker_good"]["cases"] > len(base_cards):
        raise CalibrationError(f"base cards: {len(base_cards)} vetted card(s), {needed} sealed")
    base = _draw(sorted(base_cards, key=lambda r: r["site_id"]), needed, rng, "base cards")
    for number, row in enumerate(base, start=1):
        site = _base_basis(row)
        kind, flawed = SV.canary_card(C.final_card(row["card"]), site, number)
        jobs.append(
            _case(
                "checker_defects",
                number,
                "checker_shorts",
                row,
                card=flawed,
                pool_images=row["pool_images"],
                image_titles=row["image_titles"],
                anchors=row["anchors"],
                recorded={"defect": kind, "verdict": "FAIL"},
            )
        )
        jobs.append(
            _case(
                "checker_good",
                number,
                "checker_shorts",
                row,
                card=C.final_card(row["card"]),
                pool_images=row["pool_images"],
                image_titles=row["image_titles"],
                anchors=row["anchors"],
                recorded={"verdict": "PASS"},
            )
        )

    verified, contradicted = recorded_verifications(runs)
    web = roles["web_verifier"]["sets"]
    jobs += [
        _verifier_job("verifier_contradicted", n, i)
        for n, i in enumerate(
            _draw(
                contradicted, web["verifier_contradicted"]["cases"], rng, "recorded contradictions"
            ),
            start=1,
        )
    ]
    jobs += [
        _verifier_job("verifier_verified", n, i)
        for n, i in enumerate(
            _draw(verified, web["verifier_verified"]["cases"], rng, "recorded VERIFIED cards"),
            start=1,
        )
    ]

    hooks = roles["hook_rater"]["sets"]["hook_pairs"]
    strong = [r for r in base_cards if r.get("sample")]
    if len(strong) != hooks["strong"]:
        raise CalibrationError(
            f"base cards: {len(strong)} card(s) marked sample, {hooks['strong']} sealed"
        )
    openers = [("strong", row) for row in sorted(strong, key=lambda r: r["site_id"])]
    openers += [("weak", row) for row in weak_openers(export, hooks["weak"], rng)]
    for number, (grade, row) in enumerate(openers, start=1):
        for set_name in ("hook_pairs", HOOK_REFERENCE):
            jobs.append(
                _case(set_name, number, "rate", row, card=C.final_card(row["card"]), grade=grade)
            )

    adv = roles["adversarial"]["sets"]
    jobs += [
        _adversarial_job("adversarial_contradicted", n, i, withhold=True)
        for n, i in enumerate(
            _draw(contradicted, adv["adversarial_contradicted"]["cases"], rng, "contradictions"),
            start=1,
        )
    ]
    jobs += [
        _adversarial_job("adversarial_clean", n, i, withhold=False)
        for n, i in enumerate(
            _draw(verified, adv["adversarial_clean"]["cases"], rng, "clean cards"), start=1
        )
    ]
    return opaque_keys(jobs, thresholds["seed"])


def opaque_keys(jobs: Sequence[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    """The cases with a key each that says nothing: a random version-4 UUID, drawn with the sealed
    seed - the shape of a site id. The case a key stands for is written in JOBS.jsonl alone."""
    rng = random.Random(f"{seed}/keys")  # noqa: S311 - a sealed, seeded draw
    keyed = []
    for job in sorted(jobs, key=lambda j: (j["set"], j["number"])):
        key = str(uuid.UUID(int=rng.getrandbits(128), version=4))
        keyed.append({"key": key, **job})
    if len({j["key"] for j in keyed}) != len(keyed):
        raise CalibrationError("two cases drew the same key")
    return keyed


def jobs_text(jobs: Iterable[Mapping[str, Any]]) -> str:
    return "".join(json.dumps(j, ensure_ascii=False, sort_keys=True) + "\n" for j in jobs)


def fix_jobs(
    run_dir: Path, jobs: Sequence[Mapping[str, Any]], *, now: Callable[[], str] = _now
) -> str:
    """Write the cases (JOBS.jsonl) and log their sha256 - after the seal, before the first answer,
    once. The same cases again change nothing; others are refused."""
    sealed(run_dir)
    if (run_dir / HANDOFFS_FILE).exists():
        raise CalibrationError(f"{run_dir / HANDOFFS_FILE} exists: the cases are fixed first")
    text = jobs_text(jobs)
    digest = _sha(text)
    fixed = {e[FIXED_KEY] for e in _seal_log(run_dir) if FIXED_KEY in e}
    if fixed - {digest}:
        raise CalibrationError("the cases were fixed already: a fixed sample is never rewritten")
    (run_dir / JOBS_FILE).write_text(text, encoding="utf-8", newline="\n")
    if not fixed:
        with (run_dir / SEAL_LOG).open("a", encoding="utf-8", newline="\n") as handle:
            line = {FIXED_KEY: digest, "jobs": len(jobs), "fixed_at": now()}
            handle.write(json.dumps(line) + "\n")
    return digest


def sealed_jobs(run_dir: Path) -> list[dict[str, Any]]:
    """The fixed cases exactly as they were fixed."""
    sealed(run_dir)
    fixed = sorted({e[FIXED_KEY] for e in _seal_log(run_dir) if FIXED_KEY in e})
    path = run_dir / JOBS_FILE
    if len(fixed) != 1 or not path.is_file() or _sha(path.read_text("utf-8")) != fixed[0]:
        raise CalibrationError(f"{path} is not the sample the seal log fixed: run `jobs` once")
    return read_jsonl(path)


# ------------------------------------------------------------------------------ the questions
def job_basis(job: Mapping[str, Any]) -> C.Basis:
    if job["prompt_kind"] in ("checker_shorts", "rate"):
        return SV.shorts_basis(
            site_id=job["site_id"],
            name=job["name"],
            country=job["country"],
            description=job["description"],
            alt_names=job["alt_names"],
            pool_images=job.get("pool_images", 0),
            image_titles=job.get("image_titles", []),
        )
    return C.basis(
        site_id=job["site_id"],
        name=job["name"],
        country=job["country"],
        description=job["description"],
        alt_names=job["alt_names"],
    )


def job_prompt(job: Mapping[str, Any]) -> str:
    """The exact question of one case, as the lane would ask it."""
    kind = job["prompt_kind"]
    basis = job_basis(job)
    if kind == "checker_v1":
        return P.checker_prompt(basis, job["card"])
    if kind == "checker_shorts":
        assert isinstance(basis, SV.ShortsBasis)
        return PS.checker_prompt(basis, job["card"], job["anchors"])
    if kind == "judge_v1":
        return P.judge_prompt(job["name"], job["country"], job["card"])
    if kind == "rate":
        return PS.rate_prompt(job["name"], job["country"], [(1, job["card"])])
    return PS.adversarial_prompt(basis, job["card"], job["check"], job["verify"])


def _handoffs(run_dir: Path) -> dict[str, Any]:
    """The roles exported so far and where; nothing before the first export."""
    path = run_dir / HANDOFFS_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def export_batches(
    jobs: Sequence[Mapping[str, Any]], size: int, rng: random.Random
) -> list[list[Mapping[str, Any]]]:
    """The cases in a random order, dealt to batches of at most `size`; two cases of one site are
    never in one batch (a good card and its flawed twin would show a checker which is which)."""
    order = list(jobs)
    rng.shuffle(order)
    twins = max(Counter(job["site_id"] for job in order).values())
    count = max(-(-len(order) // size), twins)
    batches: list[list[Mapping[str, Any]]] = [[] for _ in range(count)]
    for index, job in enumerate(order):
        for step in range(count):
            batch = batches[(index + step) % count]
            if len(batch) < size and all(other["site_id"] != job["site_id"] for other in batch):
                batch.append(job)
                break
        else:
            raise CalibrationError(
                f"the cases cannot be dealt to batches of {size} without a site twice in one"
            )
    return batches


def wiki_map(group: Sequence[Mapping[str, Any]], cache: WikiCache) -> str:
    """The batch's `WIKI_MAP.jsonl`: for each question, in the batch's own (shuffled) order, its label
    and the pages of the shared cache for its site. A web agent finds the cache through this map
    because a label is an opaque key. It carries nothing but label and pages - no site id, no set,
    no number - so it tells no more about a case than the question does."""
    lines = []
    for job in group:
        pages = [
            {"lang": lang, "title": row["title"], "file": row["file"].replace("\\", "/")}
            for lang, row in sorted(cache.pages.get(job["site_id"], {}).items())
        ]
        lines.append(json.dumps({"label": job["key"], "pages": pages}, ensure_ascii=False))
    return "".join(line + "\n" for line in lines)


def export_role(
    run_dir: Path, role: str, handoff: Path, *, wiki_cache: Path | None = None
) -> dict[str, Any]:
    """Every case of one role into a handoff directory of its own, to be answered by that role.
    The cases of all the role's sets are shuffled together under their opaque keys and one neutral
    stage name: the role is not told which kind of case a question is (a seeded flaw, a recorded
    failure, a good card), so that a threshold met by the role proves reading, not label-reading.
    A web role gets, beside each batch's manifest, the map from its labels to the cache's pages."""
    thresholds, _ = sealed(run_dir)
    jobs = [j for j in sealed_jobs(run_dir) if j["role"] == role]
    if not jobs:
        raise CalibrationError(f"no case of role {role!r}")
    record_path = run_dir / HANDOFFS_FILE
    exported = _handoffs(run_dir)
    if role in exported:
        raise CalibrationError(f"role {role} is exported already: a role is asked once")
    if handoff.exists() and any(handoff.iterdir()):
        raise CalibrationError(f"{handoff} is not empty: a role gets a directory of its own")
    web = any(j["set"] in WEB_SETS for j in jobs)
    size = WEB_BATCH_SIZE if web else BATCH_SIZE
    cache = WikiCache(wiki_cache or ROOT / R.WIKI_CACHE) if web else None
    rng = random.Random(f"{thresholds['seed']}/{role}/deal")  # noqa: S311 - a sealed, seeded draw
    batches = {}
    for number, group in enumerate(export_batches(jobs, size, rng), start=1):
        batch = f"{role.replace('_', '-')}-{number:03d}"
        batches[batch] = [j["key"] for j in group]
        for job in group:
            OH.export(
                handoff,
                batch_id=batch,
                stage=STAGE,
                label=job["key"],
                field="calibration",
                prompt=job_prompt(job),
            )
        if cache is not None:
            (handoff / batch / WIKI_MAP).write_text(
                wiki_map(group, cache), encoding="utf-8", newline="\n"
            )
    exported[role] = {"handoff": str(handoff), "batches": batches}
    record_path.write_text(_text(exported), encoding="utf-8", newline="\n")
    return {
        "role": role,
        "cases": len(jobs),
        "batches": {batch: len(keys) for batch, keys in batches.items()},
    }


# ------------------------------------------------------------------------------ the agents
BRIEF = """You are agent {batch} of calibration {calibration}, answering as the role **{role}**: your \
model is **{model}**, effort {effort}. If your own system prompt names another model, stop now and \
say so - an answer stamped with any other model is refused when the calibration is evaluated.

This batch needs an agent that has answered no other batch of this calibration: if you have, stop \
now and say so.

Read ONLY your prompt files: {handoff}/{batch}/MANIFEST.jsonl lists them, one JSON line per \
question with its "label" and its "prompt_path" (relative to {handoff}). Open no other file of the \
repository{web_files} - no other batch, nothing else under output/ or docs/, no database, no git \
history.

Skip every question whose "answer_path" (in the manifest, relative to {handoff}) exists already: an \
earlier agent of this batch recorded it, and an answer is written once.

For each other question:
1. Read {handoff}/<prompt_path>.
2. Answer exactly as the prompt asks: only the JSON object it specifies.
3. Write your answer to a new UTF-8 file of your own: {scratch}/<label>.json
4. Check it (nothing is recorded by this). The check reads your answer with the parser the \
evaluation reads it with and prints "ok": true, or the problems - an answer that is not in the \
shape the prompt asks for, and, for a web question, one that lists fewer claims than the card \
makes (the floor: list every claim, each fact on its own):
   {check}
   Fix the shape until it prints "ok": true - never your finding.
5. Record it - an answer is written once, and the recorder runs the same check first and refuses an \
answer that fails it:
   ./.venv/Scripts/python.exe scripts/remediation/opus_handoff.py answer --dir {handoff} \
--batch-id {batch} --stage {stage} --label <label> --answered-by cal-{batch} --role {role} \
--model {model} --text-file {scratch}/<label>.json --check "{check}"
{web_note}
When every question of the batch is recorded, report how many answers you recorded.
"""

#: What a calibration web brief says of the Wikipedia cache. The label of a question is opaque (a
#: random UUID that names no site and no set), so the cache is reached through a map of the batch,
#: not through the label (production's brief says the label is the site id; here it is not).
CAL_WIKI_LOOKUP = (
    "the labels of this calibration are opaque keys and name no site: {handoff}/{batch}/"
    "WIKI_MAP.jsonl has one JSON line per question of your batch - its label and the pages of the "
    "shared cache for that question's site ({{lang, title, file}}; the file is relative to {cache}; "
    "the list is empty when the site has no cached page); the page file is JSON with "
    "resolved_title, revid and text."
)
CAL_WEB_NOTE = (
    "\nWEB RESEARCH. The site's Wikipedia text is in the shared cache: "
    + CAL_WIKI_LOOKUP
    + " "
    + WR.VERIFIER_RULE
    + " "
    + WR.QUOTE_RULE
)
WIKI_MAP = "WIKI_MAP.jsonl"


def agent_jobs(run_dir: Path, role: str) -> list[dict[str, Any]]:
    """The workflow-ready jobs of one exported role: for each batch the agent that answers it - role,
    the model id and effort the seal fixed for the role, the brief it is given and how many such
    agents may run at the same time. A workflow starts one fresh agent per job, waits for them, and
    `evaluate` reads the answers."""
    thresholds, _ = sealed(run_dir)
    exported = _handoffs(run_dir).get(role)
    if exported is None:
        raise CalibrationError(f"role {role} was never exported")
    fixed = thresholds["registry"][role]
    web = any(j["set"] in WEB_SETS for j in sealed_jobs(run_dir) if j["role"] == role)
    handoff = Path(exported["handoff"])
    shown = _shown(handoff)
    return [
        {
            "batch_id": batch,
            "role": role,
            "model": fixed["model"],
            "effort": fixed["effort"],
            "cases": len(keys),
            "max_parallel": R.MAX_PARALLEL_WEB if web else None,
            "brief": BRIEF.format(
                batch=batch,
                calibration=run_dir.name,
                role=role,
                model=fixed["model"],
                effort=fixed["effort"],
                handoff=shown,
                scratch=f"{shown}-scratch/{batch}",
                stage=STAGE,
                check=check_command(run_dir, batch, f"{shown}-scratch/{batch}"),
                web_files=" except the Wikipedia cache named below" if web else "",
                web_note=(
                    CAL_WEB_NOTE.format(handoff=shown, batch=batch, cache=R.WIKI_CACHE)
                    if web
                    else ""
                ),
            ),
        }
        for batch, keys in sorted(exported["batches"].items())
    ]


def check_command(run_dir: Path, batch: str, scratch: str) -> str:
    """The command an agent checks one answer with before it records it (`check_answer`)."""
    return (
        "./.venv/Scripts/python.exe scripts/remediation/teaser/calibrate.py check-answer "
        f"--run-dir {_shown(run_dir)} --batch-id {batch} --label <label> "
        f"--text-file {scratch}/<label>.json"
    )


def _shown(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


# ------------------------------------------------------------------------------ the answers
def _answers(
    run_dir: Path, role: str, thresholds: Mapping[str, Any]
) -> dict[str, dict[str, tuple[dict[str, Any], OH.Answer]]]:
    """The recorded answers of one role: `set -> key -> (case, answer)`, each given in the role by
    the model the seal fixed for it. The sets are told apart here, from the sealed cases, never in
    the questions."""
    exported = _handoffs(run_dir).get(role)
    if exported is None:
        raise CalibrationError(f"role {role} was never exported")
    handoff = Path(exported["handoff"])
    check = OH.validate(handoff)
    if not check.ok:
        raise CalibrationError(
            f"{handoff}: {len(check.missing)} missing, {len(check.stale)} stale, "
            f"{len(check.malformed)} malformed - every case is answered first"
        )
    model = thresholds["registry"][role]["model"]
    cases = {j["key"]: j for j in sealed_jobs(run_dir) if j["role"] == role}
    found: dict[str, dict[str, tuple[dict[str, Any], OH.Answer]]] = {}
    for batch, keys in exported["batches"].items():
        for key in keys:
            case = cases[key]
            answer = OH.read_answer(
                handoff, batch_id=batch, stage=STAGE, label=key, prompt=job_prompt(case)
            )
            if RO.role_of(answer.answered_by) != role:
                raise CalibrationError(
                    f"{key}: {answer.answered_by!r} did not answer as role {role}"
                )
            if answer.model != OH.ANSWER_MODELS[model]:
                raise CalibrationError(
                    f"{key}: role {role} is sealed to {model}, the answer is stamped {answer.model!r}"
                )
            found.setdefault(case["set"], {})[key] = (case, answer)
    return found


def parse_case(case: Mapping[str, Any], text: str) -> Any:
    """One answer parsed as its case's prompt asks - the single reading of an answer: `evaluate`
    measures with it and `check-answer` tells the agent with it, so an answer that passes the one
    parses in the other. Raises `A.AnswerError` for a shape that does not parse and, for a web
    question (`judge_v1`), for fewer claims than the card makes (`run.claims_floor`, as production's
    import holds a verifier to). Returns: the checker's `to_dict()` for a checker-shaped answer
    (v1's, shorts-v1's, the adversary's), the claims (`A.Judged`) for a web judge, the rating for a
    hook rater."""
    kind = case["prompt_kind"]
    if kind == "judge_v1":
        claims = A.parse_judge(text)
        short = R.claims_floor(len(claims), case["floor"])
        if short is not None:
            raise A.AnswerError(short)
        return claims
    if kind == "rate":
        return AS.parse_rater(text, [(1, case["card"])])
    basis = job_basis(case)
    if kind == "checker_shorts":
        assert isinstance(basis, SV.ShortsBasis)
        return AS.parse_checker(text, basis).to_dict()
    return A.parse_checker(text, basis).to_dict()


def check_answer(run_dir: Path, batch_id: str, label: str, text: str) -> dict[str, Any]:
    """The shape of one answer to one question of a calibration batch, read exactly as `evaluate`
    reads it. Nothing is recorded. `{"ok": bool, "problems": [...]}`; for a web question also the
    `floor` of claims and how many the answer lists."""
    thresholds, _ = sealed(run_dir)  # the prompts the question was asked with are the sealed ones
    handoffs = _handoffs(run_dir)
    held = [r for r, e in handoffs.items() if label in e["batches"].get(batch_id, [])]
    if not held:
        raise CalibrationError(f"{batch_id}/{label} is no question of {run_dir}")
    role = held[0]
    case = next(j for j in sealed_jobs(run_dir) if j["key"] == label)
    result: dict[str, Any] = {"ok": True, "problems": []}
    try:
        parsed = parse_case(case, text)
    except A.AnswerError as exc:
        result.update(ok=False, problems=[str(exc)])
        parsed = None
    if case["prompt_kind"] == "judge_v1":
        try:
            listed: int | None = len(A.parse_judge(text))
        except A.AnswerError:
            listed = None
        result.update(floor=case["floor"], listed=listed)
    elif parsed is not None and case["prompt_kind"] != "rate":
        result["verdict"] = parsed["verdict"]
    result["role"] = role
    result["model"] = thresholds["registry"][role]["model"]
    return result


def _checks(
    answers: Mapping[str, tuple[dict[str, Any], OH.Answer]],
) -> dict[str, dict[str, Any]]:
    """Every checker-shaped answer (v1's or shorts-v1's shape) parsed: its verdict and claims."""
    out: dict[str, dict[str, Any]] = {}
    for key, (case, answer) in answers.items():
        try:
            out[key] = parse_case(case, answer.text)
        except A.AnswerError as exc:
            raise CalibrationError(f"{key}: malformed answer ({exc})") from exc
    return out


def _verdicts(
    answers: Mapping[str, tuple[dict[str, Any], OH.Answer]],
) -> dict[str, str]:
    """PASS or FAIL of every checker-shaped answer."""
    return {key: str(check["verdict"]) for key, check in _checks(answers).items()}


def _met(measured: float, floor: float) -> bool:
    return measured >= floor


def evaluate_fact_checker(
    answers: Mapping[str, Mapping[str, tuple[dict[str, Any], OH.Answer]]],
    spec: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    checked = _checks(answers["checker_agreement"])
    agree = {k: str(c["verdict"]) for k, c in checked.items()}
    cases = {k: c for k, (c, _) in answers["checker_agreement"].items()}
    same = sum(1 for k, v in agree.items() if v == cases[k]["recorded"]["verdict"])
    claim_cover = ClaimCoverage()
    for key, check in checked.items():
        claim_cover += claim_coverage(
            _supported(cases[key]["recorded"]["claims"]), _supported(check["claims"])
        )
    false_pass = [
        k
        for k, v in agree.items()
        if v == A.PASSED
        and cases[k]["recorded"]["verdict"] == A.FAILED
        and any(not c["support"] for c in cases[k]["recorded"]["claims"])
    ]
    rule = spec["checker_agreement"]
    out["checker_agreement"] = {
        "cases": len(agree),
        "verdict_agreement": round(same / len(agree), 4),
        **claim_cover.to_dict(),
        "false_pass": sorted(false_pass),
        "passed": _met(same / len(agree), rule["verdict_agreement_min"])
        and _met(claim_cover.coverage, rule["claim_coverage_min"])
        and _met(claim_cover.agreement, rule["claim_agreement_min"])
        and len(false_pass) <= rule["false_pass_max"],
    }
    again = _verdicts(answers["checker_fail_again"])
    failed = sum(1 for v in again.values() if v == A.FAILED)
    out["checker_fail_again"] = {
        "cases": len(again),
        "failed_again": failed,
        "passed": failed >= spec["checker_fail_again"]["fail_min"],
    }
    defects = _verdicts(answers["checker_defects"])
    caught = sum(1 for v in defects.values() if v == A.FAILED)
    missed = Counter(
        answers["checker_defects"][k][0]["recorded"]["defect"]
        for k, v in defects.items()
        if v != A.FAILED
    )
    out["checker_defects"] = {
        "cases": len(defects),
        "caught": caught,
        "missed_by_defect": dict(sorted(missed.items())),
        "passed": caught >= spec["checker_defects"]["caught_min"],
    }
    good = _verdicts(answers["checker_good"])
    passed = sum(1 for v in good.values() if v == A.PASSED)
    out["checker_good"] = {
        "cases": len(good),
        "passed_cards": passed,
        "passed": passed >= spec["checker_good"]["pass_min"],
    }
    return out


def _supported(claims: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    """A checker's claims as `claim_agreement` compares them: a claim is SUPPORTED when it names a
    sentence of the basis, UNSUPPORTED when it names none."""
    return [
        {"claim": c["claim"], "verdict": "SUPPORTED" if c["support"] else "UNSUPPORTED"}
        for c in claims
    ]


@dataclass(frozen=True)
class ClaimCoverage:
    """How a fresh claim list stands to a recorded one: `recorded` claims, how many of them a fresh
    claim `covered`, and how many of the covered ones the covering claim `agreed` with in verdict.
    Counts add up over cases."""

    recorded: int = 0
    covered: int = 0
    agreed: int = 0

    def __add__(self, other: ClaimCoverage) -> ClaimCoverage:
        return ClaimCoverage(
            self.recorded + other.recorded, self.covered + other.covered, self.agreed + other.agreed
        )

    @property
    def coverage(self) -> float:
        """The share of recorded claims some fresh claim covers (`not found by the agent`)."""
        return self.covered / self.recorded if self.recorded else 0.0

    @property
    def agreement(self) -> float:
        """The share of covered claims whose covering claim has the recorded verdict."""
        return self.agreed / self.covered if self.covered else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "claims_recorded": self.recorded,
            "claims_covered": self.covered,
            "claim_coverage": round(self.coverage, 4),
            "claim_agreement": round(self.agreement, 4),
        }


def _content_words(claim: str) -> frozenset[str]:
    """The words that carry a claim: letters and digits, case folded, no stop word, no word of one
    or two letters (a digit string of any length stays)."""
    words = re.findall(r"\w+", unicodedata.normalize("NFC", claim).casefold())
    return frozenset(w for w in words if w not in STOP_WORDS and (len(w) > 2 or w.isdigit()))


def _cover(recorded: str, fresh: str) -> tuple[float, float]:
    """`(recall, ratio)`: the share of the recorded claim's content words that the fresh claim holds,
    and the two claims' difflib ratio. A fresh claim covers the recorded one when either reaches
    `CLAIM_MATCH`."""
    words = _content_words(recorded)
    recall = len(words & _content_words(fresh)) / len(words) if words else 0.0
    ratio = difflib.SequenceMatcher(None, recorded.casefold(), fresh.casefold()).ratio()
    return recall, ratio


def claim_coverage(
    recorded: Sequence[Mapping[str, Any]], fresh: Sequence[Mapping[str, Any]]
) -> ClaimCoverage:
    """Each recorded claim is covered when a fresh claim's wording covers it (`_cover`); one fresh
    claim may cover several recorded ones, and a compound claim of the fresh list is no loss. The
    claim agrees when the verdict of its best covering claim (most words, then closest wording) is
    the recorded one. The old one-to-one pairing by wording counted a card the agent listed as three
    claims against five recorded ones as two disagreements, and could not reach 0.54 although every
    paired verdict agreed (calibration teaser-2026-10-09)."""
    covered = agreed = 0
    for claim in recorded:
        scored = [(_cover(claim["claim"], f["claim"]), f) for f in fresh]
        covering = [(score, f) for score, f in scored if max(score) >= CLAIM_MATCH]
        if not covering:
            continue
        covered += 1
        _, best = max(covering, key=lambda item: item[0])
        agreed += int(best["verdict"] == claim["verdict"])
    return ClaimCoverage(len(recorded), covered, agreed)


_DASHES = re.compile("[\u2010-\u2015\u2212]")
_NUMBER_GLUE = re.compile(r"(?<=\d)\s*([.,-])\s*(?=\d)")
#: Stand-ins for the `.`, `,` and `-` between two digits (private-use characters, so they survive
#: the "letters and digits only" filter and are no punctuation of the text).
_GLUE = {".": "\ue001", ",": "\ue002", "-": "\ue003"}


def _loose(text: str) -> str:
    """A text as a reader compares it: decomposed, accents and marks dropped, case folded, dash
    variants one dash, letters and digits only - but a `.`, `,` or `-` between two digits stays, so a
    changed number (3.5 against 35, 10-15 against 1015) is a different text. A quote that the strict
    check misses and this one finds is on the page - it differs in typography, a quotation mark, a
    dash, a line break - and was not made up."""
    decomposed = unicodedata.normalize("NFKD", Q.normalise(text)).casefold()
    glued = _NUMBER_GLUE.sub(lambda m: _GLUE[m.group(1)], _DASHES.sub("-", decomposed))
    return "".join(ch for ch in glued if ch.isalnum() or ch in _GLUE.values())


#: How a verifier's quote stands (`quote_standing`).
FOUND, MACHINE_MISS, FABRICATED, REFUSED, UNREADABLE = (
    "found",
    "not found by machine",
    "fabricated",
    "source refused",
    "page unreadable",
)


def quote_standing(claim: Mapping[str, Any], library: Q.Library) -> str | None:
    """Where a SUPPORTED or CONTRADICTED claim's quote stands after `prove_claims`: `FOUND`; `REFUSED`
    (the page is no source: an aggregator, a mirror, this project's site); `UNREADABLE` (the page
    was not fetched or could not be read - no finding about the quote); `MACHINE_MISS` (the strict
    check did not find it, the page holds it up to typography: the machine's miss); `FABRICATED` (not
    on the page even loosely: the agent wrote what the page does not say). `None` for a claim
    without a quote."""
    outcome = claim["quote_outcome"]
    if outcome is None:
        return None
    if outcome == Q.FOUND:
        return FOUND
    if str(outcome).startswith(R.SOURCE_REFUSED):
        return REFUSED
    if outcome != Q.NOT_FOUND:
        return UNREADABLE
    wanted = _loose(claim["quote"])
    page = library.url(claim["url"])
    if wanted and any(wanted in _loose(text) for _, text in page.texts):
        return MACHINE_MISS
    return FABRICATED


def evaluate_web_verifier(
    run_dir: Path,
    answers: Mapping[str, Mapping[str, tuple[dict[str, Any], OH.Answer]]],
    spec: Mapping[str, Mapping[str, Any]],
    client: httpx.Client | None,
) -> dict[str, Any]:
    """The verifier's answers with their quotes checked by machine (`run.prove_claims`) and the
    card's verification derived as a run derives it (`run.card_verification`).

    Each answer is read as `check-answer` reads it, with the claims floor of production's import
    (`parse_case`). The recorded contradictions the sealed table calls disputed are reported and
    left out of the `caught_min` denominator (the minimum scales with the cases that count). The
    claim measure is a coverage (`claim_coverage`) and the card-level verdict is reported beside
    it. A quote not found is told apart: `not_found_by_machine` (on the page up to typography) is
    reported; only `fabricated` and a refused source are false sources."""
    parsed: dict[str, tuple[dict[str, Any], tuple[A.Judged, ...]]] = {}
    for set_name in ROLE_SETS["web_verifier"]:
        for key, (case, answer) in answers[set_name].items():
            try:
                parsed[key] = (case, parse_case(case, answer.text))
            except A.AnswerError as exc:
                raise CalibrationError(f"{key}: malformed answer ({exc})") from exc
    urls = R.cited_pages(j for _, claims in parsed.values() for j in claims)
    library, failing = R.fetch_pages(run_dir, urls, client, Q.PACE_SECONDS if client is None else 0)
    results: dict[str, tuple[str, list[dict[str, Any]]]] = {}
    for key, (case, claims) in parsed.items():
        proven = R.prove_claims(case["site_id"], claims, library)
        results[key] = (R.card_verification(proven), proven)
    rule_c, rule_v = spec["verifier_contradicted"], spec["verifier_verified"]
    contradicted = [k for k in results if parsed[k][0]["set"] == "verifier_contradicted"]
    drawn = {parsed[k][0]["site_id"] for k in contradicted}
    if stray := sorted(set(rule_c["disputed"]) - drawn):
        raise CalibrationError(
            f"the sealed table calls {stray} disputed, but they are no site id of the contradicted set"
        )
    disputed = {k: rule_c["disputed"][parsed[k][0]["site_id"]] for k in contradicted
                if parsed[k][0]["site_id"] in rule_c["disputed"]}  # fmt: skip
    counted = [k for k in contradicted if k not in disputed]
    caught = [k for k in counted if results[k][0] == R.CONTRADICTED]
    required = math.ceil(rule_c["caught_min"] * len(counted) / rule_c["cases"])
    verified = [k for k in results if parsed[k][0]["set"] == "verifier_verified"]
    falsely = [k for k in verified if results[k][0] == R.CONTRADICTED]
    claim_cover = ClaimCoverage()
    for key in verified:
        claim_cover += claim_coverage(parsed[key][0]["recorded"]["claims"], results[key][1])
    standing: dict[str, list[str]] = {MACHINE_MISS: [], FABRICATED: [], REFUSED: [], UNREADABLE: []}
    for key, (_, proven) in sorted(results.items()):
        for claim in proven:
            if claim["verdict"] not in ("SUPPORTED", "CONTRADICTED"):
                continue
            how = quote_standing(claim, library)
            if how in standing:
                standing[how].append(f"{key}: {claim['url']}")
    false_sources = [*standing[FABRICATED], *standing[REFUSED]]
    card_agreement = sum(1 for k in verified if results[k][0] == R.VERIFIED)
    return {
        "verifier_contradicted": {
            "cases": len(contradicted),
            "counted": len(counted),
            "caught": len(caught),
            "caught_required": required,
            "missed": [f"{k}: {parsed[k][0]['name']}" for k in counted if k not in caught],
            "disputed": {
                k: {
                    "name": parsed[k][0]["name"],
                    "reason": why,
                    "fresh_verdict": results[k][0],
                }
                for k, why in sorted(disputed.items())
            },
            "passed": len(caught) >= required,
        },
        "verifier_verified": {
            "cases": len(verified),
            "falsely_contradicted": sorted(falsely),
            **claim_cover.to_dict(),
            "card_verdict_agreement": round(card_agreement / len(verified), 4) if verified else 0.0,
            "false_sources": false_sources,
            "not_found_by_machine": standing[MACHINE_MISS],
            "unreadable_pages": standing[UNREADABLE],
            "transient_failures": failing,
            "passed": len(falsely) <= rule_v["falsely_contradicted_max"]
            and claim_cover.coverage >= rule_v["claim_coverage_min"]
            and claim_cover.agreement >= rule_v["claim_agreement_min"]
            and len(false_sources) <= rule_v["false_sources_max"],
        },
    }


def hook_ratings(
    answers: Mapping[str, tuple[dict[str, Any], OH.Answer]],
) -> dict[str, int]:
    out: dict[str, int] = {}
    for key, (case, answer) in answers.items():
        try:
            out[key] = parse_case(case, answer.text).best_rating
        except A.AnswerError as exc:
            raise CalibrationError(f"{key}: malformed answer ({exc})") from exc
    return out


def evaluate_hook_rater(
    answers: Mapping[str, Mapping[str, tuple[dict[str, Any], OH.Answer]]],
    spec: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    rule = spec["hook_pairs"]
    fresh = hook_ratings(answers["hook_pairs"])
    reference = hook_ratings(answers[HOOK_REFERENCE])
    grades = {k: c["grade"] for k, (c, _) in answers["hook_pairs"].items()}
    judged = {answers[HOOK_REFERENCE][k][0]["site_id"]: hook for k, hook in reference.items()}
    sites = {k: c["site_id"] for k, (c, _) in answers["hook_pairs"].items()}
    strong = [fresh[k] for k, g in grades.items() if g == "strong"]
    weak = [fresh[k] for k, g in grades.items() if g == "weak"]
    pairs = [(s, w) for s in strong for w in weak]
    right = sum(1 for s, w in pairs if s > w)
    within = sum(1 for key, hook in fresh.items() if abs(hook - judged[sites[key]]) <= 1)
    ordered = right / len(pairs) if pairs else 0.0
    close = within / len(fresh)
    return {
        "hook_pairs": {
            "strong": len(strong),
            "weak": len(weak),
            "pairs_ordered_right": round(ordered, 4),
            "within_one_of_reference": round(close, 4),
            "passed": ordered >= rule["ordered_right_min"]
            and close >= rule["reference_within_one_min"],
        }
    }


def evaluate_adversarial(
    answers: Mapping[str, Mapping[str, tuple[dict[str, Any], OH.Answer]]],
    spec: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    right = total = 0
    detail: dict[str, Any] = {}
    for set_name in ("adversarial_contradicted", "adversarial_clean"):
        verdicts = _verdicts(answers[set_name])
        expected = {k: c["expected"] for k, (c, _) in answers[set_name].items()}
        hit = sum(1 for k, v in verdicts.items() if v == expected[k])
        right, total = right + hit, total + len(verdicts)
        detail[set_name] = {"cases": len(verdicts), "right": hit}
    agreement = right / total if total else 0.0
    detail["adversarial_agreement"] = {
        "agreement": round(agreement, 4),
        "passed": agreement >= spec["adversarial_agreement"]["agreement_min"],
    }
    return detail


def evaluate_card_writer(
    writer_run: Path, spec: Mapping[str, Mapping[str, Any]], thresholds: Mapping[str, Any]
) -> dict[str, Any]:
    """The writer's pilot: the share of first answers (stage `write`) that came out mechanically
    clean - not thin, all three variants without a problem - over the pilot's sites."""
    rule = spec["writer_pilot"]
    if R.contract_of(writer_run) != R.SHORTS:
        raise CalibrationError(f"{writer_run} is not a shorts-v1 run")
    rows = R.stage_records(writer_run)["write"]
    if len(rows) < rule["sites"]:
        raise CalibrationError(f"{writer_run}: {len(rows)} first answer(s), {rule['sites']} sealed")
    model = thresholds["registry"]["card_writer"]["model"]
    wrong = [r["site_id"] for r in rows.values() if r["model"] != OH.ANSWER_MODELS[model]]
    if wrong:
        raise CalibrationError(f"{len(wrong)} first answer(s) are not stamped {model}")
    asked = [r for r in rows.values() if not r["thin"]]
    clean = sum(1 for r in asked if all(not v["problems"] for v in r["variants"]))
    share = clean / len(asked) if asked else 0.0
    return {
        "writer_pilot": {
            "sites": len(rows),
            "thin_declined": len(rows) - len(asked),
            "clean_first": clean,
            "clean_first_share": round(share, 4),
            "passed": share >= rule["clean_first_min"],
        }
    }


ROLE_SETS = {
    "fact_checker": ("checker_agreement", "checker_fail_again", "checker_defects", "checker_good"),
    "web_verifier": ("verifier_contradicted", "verifier_verified"),
    "hook_rater": ("hook_pairs", HOOK_REFERENCE),
    "adversarial": ("adversarial_contradicted", "adversarial_clean"),
}


def evaluate(
    run_dir: Path,
    role: str,
    *,
    writer_run: Path | None = None,
    client: httpx.Client | None = None,
    now: Callable[[], str] = _now,
) -> dict[str, Any]:
    """Measure one role against the sealed thresholds and write `VERDICT-<role>.json`, once. A
    failing role carries its tier move (`roles.escalation`), or, at the top tier, a hold."""
    thresholds, digest = sealed(run_dir)
    path = run_dir / VERDICT_FILE.format(role=role)
    if path.exists():
        raise CalibrationError(f"{path} exists: a verdict is written once")
    spec = thresholds["roles"][role]["sets"]
    if role == "card_writer":
        if writer_run is None:
            raise CalibrationError(
                "the writer's calibration is measured on a pilot run: --writer-run"
            )
        sets = evaluate_card_writer(_resolve(writer_run), spec, thresholds)
    else:
        answers = _answers(run_dir, role, thresholds)
        if role == "hook_rater":  # the reference is the pilot judge's, on the same cards
            answers |= _answers(run_dir, "pilot_judge", thresholds)
        if role == "fact_checker":
            sets = evaluate_fact_checker(answers, spec)
        elif role == "web_verifier":
            sets = evaluate_web_verifier(run_dir, answers, spec, client)
        elif role == "hook_rater":
            sets = evaluate_hook_rater(answers, spec)
        else:
            sets = evaluate_adversarial(answers, spec)
    failed = [name for name, result in sets.items() if result.get("passed") is False]
    verdict: dict[str, Any] = {
        "calibration_id": run_dir.name,
        "role": role,
        "model": thresholds["registry"][role]["model"],
        "effort": thresholds["registry"][role]["effort"],
        "sets": sets,
        "passed": not failed,
        "tier_move": None,
        "thresholds_sha256": digest,
        "decided_at": now(),
    }
    if failed:
        try:
            verdict["tier_move"] = RO.escalation(
                role, calibration_id=run_dir.name, reason="failed: " + ", ".join(failed)
            )
        except RO.RoleError as exc:
            verdict["held"] = f"{exc}: the owner decides"
    path.write_text(_text(verdict), encoding="utf-8", newline="\n")
    return verdict


def _need_standing_record(run_dir: Path, role: str) -> tuple[dict[str, Any], Path, str]:
    """The role's verdict, its file and the sealed thresholds' sha256 - for a verdict that rests on
    the seal of `run_dir` and a role that is registered as it was sealed. Module bytes are not
    asked: they were checked when the verdict was made (`evaluate` reads `sealed`), and a later
    change to them moves the next calibration's seal, not this verdict."""
    thresholds, digest = integrity(run_dir)
    path = run_dir / VERDICT_FILE.format(role=role)
    if not path.is_file():
        raise CalibrationError(f"role {role} has no verdict in {run_dir}: {path} is missing")
    entry = thresholds["registry"].get(role)
    if entry is None:
        raise CalibrationError(f"role {role} is not in the registry sealed in {run_dir}")
    if RO.role_sha256(role) != entry["sha256"]:
        raise CalibrationError(f"the registry entry of role {role} changed after the seal")
    verdict = json.loads(path.read_text(encoding="utf-8"))
    if verdict["role"] != role:
        raise CalibrationError(f"{path} is the verdict of role {verdict['role']}, not {role}")
    if verdict["thresholds_sha256"] != digest:
        raise CalibrationError(f"{path} does not rest on the thresholds sealed in {run_dir}")
    return verdict, path, digest


def release_role(
    run_dir: Path,
    role: str,
    *,
    decided_by: str,
    reason: str,
    evidence: Sequence[Path],
    now: Callable[[], str] = _now,
) -> dict[str, Any]:
    """Let a verdict stand that failed and is held at the top tier, written once to
    `RELEASE-<role>.json`: `evaluate` says "the owner decides" where Opus has no tier above, and
    this is that decision on record, with the sha256 of what it rests on.

    Refused: an unsealed directory; no verdict, one of another role, one that does not rest on the
    sealed thresholds, or of a role registered otherwise than sealed; a verdict that passed; one with
    a tier move (the role moves up, it is not released); a failed one that is not held; an empty
    `decided_by` or `reason`; no evidence, a path that is not a file, a file named twice; a release
    written already."""
    if not decided_by.strip():
        raise CalibrationError("decided by is empty: a release names who decided it")
    if not reason.strip():
        raise CalibrationError("reason is empty: a release names why the verdict stands")
    verdict, path, digest = _need_standing_record(run_dir, role)
    if verdict["passed"]:
        raise CalibrationError(f"role {role} passed: there is nothing to release")
    if verdict["tier_move"] is not None:
        raise CalibrationError(
            f"role {role} carries a tier move: the role moves up a tier, it is not released"
        )
    if not verdict.get("held"):
        raise CalibrationError(
            f"role {role} failed but is not held at the top tier: only a held verdict is released"
        )
    release_path = run_dir / RELEASE_FILE.format(role=role)
    if release_path.exists():
        raise CalibrationError(f"{release_path} exists: a release is written once")
    try:
        items = CC.evidence_records(evidence)
    except CC.CalibrationError as exc:
        raise CalibrationError(str(exc)) from exc
    record = {
        "calibration_id": run_dir.name,
        "role": role,
        "verdict_sha256": CC.sha256_file(path),
        "thresholds_sha256": digest,
        "role_sha256": RO.role_sha256(role),
        "decided_by": decided_by,
        "reason": reason,
        "evidence": items,
        "decided_at": now(),
    }
    release_path.write_text(_text(record), encoding="utf-8", newline="\n")
    return record


def standing(run_dir: Path, role: str) -> dict[str, str]:
    """How the verdict of `role` in `run_dir` stands: `passed`, or `released` (naming who decided)
    when it failed at the top tier and its release still rests on the verdict, the sealed thresholds,
    the role's registry entry and the evidence files it was made on - or `CalibrationError`. A
    failed verdict with a tier move, a held one without a release and a role without a verdict do
    not stand."""
    verdict, path, digest = _need_standing_record(run_dir, role)
    line = {"role": role, "calibration_id": run_dir.name}
    if verdict["passed"]:
        return {**line, "standing": CC.PASSED}
    release_path = run_dir / RELEASE_FILE.format(role=role)
    if verdict["tier_move"] is not None or not verdict.get("held") or not release_path.is_file():
        raise CalibrationError(
            f"role {role} has no passing verdict and no release in {run_dir}: calibrate it "
            "again (a tier move) or release the held verdict"
        )
    record = json.loads(release_path.read_text(encoding="utf-8"))
    moved = f"the release of {role} ({release_path})"
    if record["verdict_sha256"] != CC.sha256_file(path):
        raise CalibrationError(f"{moved}: the verdict changed after the release")
    if record["thresholds_sha256"] != digest or record["role_sha256"] != RO.role_sha256(role):
        raise CalibrationError(f"{moved}: the thresholds or the role changed after the release")
    if record["calibration_id"] != run_dir.name or record["role"] != role:
        raise CalibrationError(f"{moved}: it names another calibration or role")
    if not record["evidence"]:
        raise CalibrationError(f"{moved}: it rests on no evidence")
    try:
        CC.verify_evidence(record["evidence"], moved)
    except CC.CalibrationError as exc:
        raise CalibrationError(str(exc)) from exc
    return {**line, "standing": CC.RELEASED, "decided_by": record["decided_by"]}


VOID_FILE = "VOID.jsonl"


def void_answers(
    run_dir: Path,
    role: str,
    labels: Sequence[str],
    reason: str,
    *,
    now: Callable[[], str] = _now,
) -> list[dict[str, Any]]:
    """Set aside the recorded answers to some questions of a role, so that new agents answer them:
    each named answer file moves to `<handoff>-void/<batch>/...` (same relative path), a line per
    answer goes to `VOID.jsonl` (who answered, the answer's sha256, why). The prompts, the manifest,
    the sealed table, the cases and every other answer stay as they are - the seal is not touched,
    so the voided questions are asked again under the thresholds sealed before the first answer.
    The seal is checked for integrity only (`integrity`): nothing here reads a prompt or judges an
    answer, so a calibration sealed with an older checkout of the modules can be repaired from a
    newer one.

    Refused, with nothing moved: no reason; a label that is no question of this role; a question
    with no recorded answer; an answer recorded in another role; a void file already there (an
    answer is voided once)."""
    integrity(run_dir)
    if not reason.strip():
        raise CalibrationError("a void needs its reason: say why the answers are set aside")
    exported = _handoffs(run_dir).get(role)
    if exported is None:
        raise CalibrationError(f"role {role} was never exported")
    if not labels or len(set(labels)) != len(labels):
        raise CalibrationError("name each label to void once, at least one")
    handoff = Path(exported["handoff"])
    batch_of = {key: batch for batch, keys in exported["batches"].items() for key in keys}
    voided_to = handoff.with_name(handoff.name + "-void")
    moves = []
    for label in labels:
        if label not in batch_of:
            raise CalibrationError(f"{label} is no question of role {role}")
        line = OH.read_manifest(handoff, batch_of[label])[(STAGE, label)]
        source = handoff / line["answer_path"]
        if not source.is_file():
            raise CalibrationError(f"{label} has no recorded answer to void")
        stored = json.loads(source.read_text(encoding="utf-8"))
        named = RO.role_of(stored["answered_by"])
        if named != role:
            raise CalibrationError(
                f"{label}: the answer was given by {stored['answered_by']!r}, not in role {role} "
                "- it is not this role's to void"
            )
        target = voided_to / line["answer_path"]
        if target.exists():
            raise CalibrationError(f"{target} exists: an answer is voided once")
        moves.append((label, batch_of[label], source, target, stored))
    voided = []
    for label, batch, source, target, stored in moves:
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        source.replace(target)
        voided.append(
            {
                "voided_at": now(),
                "role": role,
                "batch": batch,
                "label": label,
                "answered_by": stored["answered_by"],
                "answer_sha256": digest,
                "moved_to": _shown(target),
                "reason": reason,
            }
        )
    with (run_dir / VOID_FILE).open("a", encoding="utf-8", newline="\n") as handle:
        for line_ in voided:
            handle.write(json.dumps(line_, ensure_ascii=False, sort_keys=True) + "\n")
    return voided


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


# ------------------------------------------------------------------------------ the CLI
def main(argv: Iterable[str] | None = None) -> int:
    """0: done (and a verdict passed). 1: the verdict is a fail. 2: refused."""
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in (
        "seal", "jobs", "export", "agents", "evaluate", "check-answer", "void", "release", "standing",
    ):  # fmt: skip
        command = sub.add_parser(name)
        command.add_argument("--run-dir", required=True, type=Path)
    check = sub.choices["check-answer"]
    check.add_argument("--batch-id", required=True)
    check.add_argument("--label", required=True)
    check.add_argument("--text-file", required=True, type=Path)
    void = sub.choices["void"]
    void.add_argument("--role", required=True, choices=sorted(set(SET_ROLE.values())))
    void.add_argument("--labels", required=True, help="comma-separated question keys")
    void.add_argument("--reason", required=True)
    jobs = sub.choices["jobs"]
    jobs.add_argument("--runs", required=True, nargs="+", type=Path)
    jobs.add_argument("--export", required=True, type=Path)
    jobs.add_argument("--base-cards", required=True, type=Path)
    export = sub.choices["export"]
    export.add_argument("--role", required=True, choices=sorted(set(SET_ROLE.values())))
    export.add_argument("--handoff", required=True, type=Path)
    sub.choices["agents"].add_argument(
        "--role", required=True, choices=sorted(set(SET_ROLE.values()))
    )
    for name in ("release", "standing"):
        sub.choices[name].add_argument("--role", required=True, choices=sorted(RO.ROLES))
    release_cli = sub.choices["release"]
    release_cli.add_argument("--decided-by", required=True)
    release_cli.add_argument("--reason", required=True)
    release_cli.add_argument("--evidence", required=True, nargs="+", type=Path)
    ev = sub.choices["evaluate"]
    ev.add_argument("--role", required=True, choices=sorted(THRESHOLDS["roles"]))
    ev.add_argument("--writer-run", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    run_dir = _resolve(args.run_dir)
    try:
        if args.command == "seal":
            payload: Any = {"thresholds_sha256": seal(run_dir)}
        elif args.command == "jobs":
            thresholds, _ = sealed(run_dir)
            runs = [_resolve(r) for r in args.runs]
            made = build_jobs(
                thresholds,
                runs=runs,
                export=_resolve(args.export),
                base_cards=read_base_cards(_resolve(args.base_cards), fit=V.card_fit),
            )
            payload = {"cases": len(made), "jobs_sha256": fix_jobs(run_dir, made)}
        elif args.command == "export":
            payload = export_role(run_dir, args.role, _resolve(args.handoff))
        elif args.command == "agents":
            payload = agent_jobs(run_dir, args.role)
        elif args.command == "check-answer":
            payload = check_answer(
                run_dir, args.batch_id, args.label, args.text_file.read_bytes().decode("utf-8")
            )
        elif args.command == "void":
            payload = void_answers(
                run_dir, args.role, [x.strip() for x in args.labels.split(",")], args.reason
            )
        elif args.command == "release":
            payload = release_role(
                run_dir,
                args.role,
                decided_by=args.decided_by,
                reason=args.reason,
                evidence=args.evidence,
            )
        elif args.command == "standing":
            payload = standing(run_dir, args.role)
        else:
            payload = evaluate(run_dir, args.role, writer_run=args.writer_run)
    except (CalibrationError, RO.RoleError, OH.HandoffError, R.RunError, PlanError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))
    failed = (args.command == "evaluate" and not payload["passed"]) or (
        args.command == "check-answer" and not payload["ok"]
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
