"""The calibration of the image roles (D6, map `plans/images.md` section 4): sealed first, then measured.

Every Claude role of the picture research passes a calibration against already-judged cases before its
first answer of the lane. The thresholds are numbers written down **before** any case is chosen or
answered (`THRESHOLDS`, sealed in `THRESHOLDS.json` with the sha256 of each role's registry entry); a
role that fails moves up one tier (Haiku to Sonnet to Opus, `roles.escalation`) and is calibrated
again. Intervals are Clopper-Pearson (`gold_standard/compare_fnr.py`), never bare rates. The order is
enforced, not promised:

    seal       THRESHOLDS.json + SEAL.jsonl; refused once a gold sample or an answer exists
    gold       the cases: GOLD.jsonl (with the truth) and JOBS.jsonl (without), their sha256 sealed
    export     one role's questions - the production prompts, `stage.Spec` of the role - for the cases
    ...        the orchestrator's agents answer; `run.py`-style brief/check/import in this directory
    evaluate   the metrics per role against the sealed thresholds -> VERDICT_<role>.json

**The roles and what they are measured on** (the proposal of the map; the orchestrator seals it):

* `image_prefilter` (Haiku low) on 300 pictures stratified by kind, truth = Opus's C1 kind
  (`gallery_audit/calibration-2026-09-25-opus`): photo versus non-photo agreement >= 0.92, and recall
  of what Opus would call depicts-capable (a kind that can show a site) >= 0.98. Failing: Sonnet low.
* `image_depicts` (Sonnet medium): sensitivity >= 0.90 on 150 owner-linked heroes (the 2025 hand-links,
  not the 47 and not the 192 first heroes); false-`depicts` rate <= 3 % and precision >= 0.95 over the
  hard negatives (the 64 `fremde_staette` rows, the 12 gold-foreign rows, 60 of the Claude `other_site`
  verdicts) and the adjudicated pool candidates; **every** foreign row not `depicts`. Failing: Sonnet
  high, then Opus medium.
* `pilot_judge` (Opus xhigh) **adjudicates** 150 candidates of the MiniMax pool (50 per MiniMax verdict
  class) with web evidence: that adjudication is the pilot-judge gold, not a measured role.
* `adversarial` (Opus high, the hero re-check): agreement >= 0.95 with the adjudication and the labelled
  cases on whether a candidate called `depicts` really depicts the site.
* `web_verifier` (Sonnet high, the identity researcher): >= 0.90 correct over 5 known wrong links and
  20 known good ones, and **all five** wrong links flagged.

The label noise is real (the Opus C1 calibration of 2026-09-25 scored 0.515 precision against the
652 labels), so a threshold is on false-`depicts`, and a disagreement is adjudicated, not scored
against a raw label.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _path in (_HERE.parents[3], _HERE.parents[1]):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import roles as RO  # noqa: E402
from candidate_search import judge as CJ  # noqa: E402
from identity import common as IC  # noqa: E402
from served_image import state as ST  # noqa: E402

from image_roles import depicts as DP  # noqa: E402
from image_roles import hero_recheck as HR  # noqa: E402
from image_roles import identity as ID  # noqa: E402
from image_roles import prefilter as PF  # noqa: E402
from image_roles import stage as SG  # noqa: E402

#: The project's own interval (gitignored run data of the main checkout, a worktree has none).
COMPARE_FNR = Path("output") / "remediation" / "gold_standard" / "compare_fnr.py"
THRESHOLDS_FILE = "THRESHOLDS.json"
SEAL_LOG = "SEAL.jsonl"
GOLD_FILE = "GOLD.jsonl"
JOBS_FILE = "JOBS.jsonl"
VERDICTS_DIR = "verdicts"

#: What the map proposes; sealed before the first case is chosen. A number moves only by a new seal.
THRESHOLDS: dict[str, Any] = {
    "version": "image-roles-v1",
    "source": "output/remediation/final-2026-10-08/plans/images.md, section 4",
    "interval": "Clopper-Pearson, 95 %",
    "seed": 20261008,
    "roles": {
        "image_prefilter": {
            "kind_cases": 300,
            "photo_agreement_min": 0.92,
            "depicts_capable_recall_min": 0.98,
        },
        "image_depicts": {
            "positives": 150,
            "foreign_labelled": 64,
            "foreign_gold": 12,
            "claude_other_site": 60,
            "sensitivity_min": 0.90,
            "false_depicts_max": 0.03,
            "precision_min": 0.95,
            "every_foreign_not_depicts": True,
        },
        "pilot_judge": {"adjudicated": 150, "per_class": 50},
        "adversarial": {"agreement_min": 0.95},
        "web_verifier": {
            "wrong_links": 5,
            "good_links": 20,
            "correct_min": 0.90,
            "every_wrong_flagged": True,
        },
    },
}

#: Photo-like kinds for the prefilter's photo versus non-photo agreement.
PHOTO_KINDS = ("site_photo", "artifact")

#: The depicts role in a calibration directory: the same prompt, parser and role as `DP.SPEC`, a stage
#: name of its own so that `run.py import` records its answers without the lane's `VERDICTS.jsonl`.
DEPICTS_CAL_SPEC = replace(
    DP.SPEC,
    name="image-depicts-calibration",
    questions_file="QUESTIONS_DEPICTS_CAL.jsonl",
    export_file="EXPORT_DEPICTS_CAL.json",
    result_file="DEPICTS_CAL.jsonl",
)
ADJUDICATE_SPEC = replace(
    DP.SPEC,
    name="image-adjudicate",
    role="pilot_judge",
    questions_file="QUESTIONS_ADJUDICATE.jsonl",
    export_file="EXPORT_ADJUDICATE.json",
    result_file="ADJUDICATE.jsonl",
    what="adjudicate each candidate with web evidence (the pilot-judge gold)",
    web=True,
)
RECHECK_SPEC = HR.spec_for_round(1)
ROLE_SPECS: dict[str, SG.Spec] = {
    "image_prefilter": PF.SPEC,
    "image_depicts": DEPICTS_CAL_SPEC,
    "pilot_judge": ADJUDICATE_SPEC,
    "adversarial": RECHECK_SPEC,
    "web_verifier": ID.VERIFY_SPEC,
}


class CalibrationError(ST.StateError):
    """The calibration cannot take this step. Nothing is half-written."""


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clopper_pearson() -> Callable[[int, int], tuple[float, float]]:
    path = IC.main_checkout() / COMPARE_FNR
    spec = importlib.util.spec_from_file_location("compare_fnr", path)
    if spec is None or spec.loader is None or not path.is_file():
        raise CalibrationError(f"{path} cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.clopper_pearson  # type: ignore[no-any-return]


# ------------------------------------------------------------------------------------- the seal
def thresholds_text() -> str:
    """The sealed document: the thresholds and the registry entry of every calibrated role."""
    document = {
        **THRESHOLDS,
        "role_registry": {
            name: {
                "model": RO.role(name).model,
                "effort": RO.role(name).effort,
                "role_sha256": RO.role_sha256(name),
            }
            for name in THRESHOLDS["roles"]
        },
        "roles_sha256": RO.registry_sha256(),
    }
    return json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def seal(directory: Path, *, now: Callable[[], str] = _now) -> str:
    """Write THRESHOLDS.json and log its sha256 - before any case is chosen or answered."""
    if (directory / GOLD_FILE).exists():
        raise CalibrationError(f"{directory / GOLD_FILE} exists - thresholds are sealed first")
    text = thresholds_text()
    path = directory / THRESHOLDS_FILE
    if path.exists() and path.read_text(encoding="utf-8") != text:
        raise CalibrationError(f"{path} already holds other thresholds - a seal is never rewritten")
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    if (directory / SEAL_LOG).is_file() and any(
        e.get("thresholds_sha256") == _sha(text) for e in _log(directory)
    ):
        return _sha(text)  # the same seal again changes nothing
    with open(directory / SEAL_LOG, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps({"thresholds_sha256": _sha(text), "sealed_at": now()}, sort_keys=True) + "\n"
        )
    return _sha(text)


def _log(directory: Path) -> list[dict[str, Any]]:
    path = directory / SEAL_LOG
    if not path.is_file():
        raise CalibrationError(f"{directory} is not sealed - run `calibrate.py seal` first")
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def sealed(directory: Path) -> tuple[dict[str, Any], str, str]:
    """`(thresholds, sha256, sealed_at)`, refusing a file the log did not seal and roles that moved."""
    entries = [e for e in _log(directory) if "thresholds_sha256" in e]
    path = directory / THRESHOLDS_FILE
    if len(entries) != 1 or not path.is_file():
        raise CalibrationError(f"{directory} does not hold exactly one seal of its thresholds")
    text = path.read_text(encoding="utf-8")
    if _sha(text) != entries[0]["thresholds_sha256"]:
        raise CalibrationError(f"{path} changed after it was sealed")
    document = json.loads(text)
    for name, entry in document["role_registry"].items():
        if RO.role_sha256(name) != entry["role_sha256"]:
            raise CalibrationError(
                f"the registry entry of role {name} changed after the seal: seal a new directory"
            )
    return document, _sha(text), str(entries[0]["sealed_at"])


# ------------------------------------------------------------------------------------- the gold
def gold_text(cases: Sequence[Mapping[str, Any]], *, truth: bool) -> str:
    rows = [dict(c) if truth else {k: v for k, v in c.items() if k != "truth"} for c in cases]
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)


def fix_gold(
    directory: Path, cases: Sequence[Mapping[str, Any]], *, now: Callable[[], str] = _now
) -> str:
    """Write GOLD.jsonl (with the truth) and JOBS.jsonl (without), log the sample's sha256.

    After the seal and before the first answer; once. The same sample again changes nothing, another
    sample is refused: a fixed sample is never rewritten."""
    sealed(directory)
    ids = [c["case_id"] for c in cases]
    if len(set(ids)) != len(ids) or not cases:
        raise CalibrationError("a calibration sample has at least one case and no case twice")
    text = gold_text(cases, truth=True)
    digest = _sha(text)
    fixed = {e["gold_sha256"] for e in _log(directory) if "gold_sha256" in e}
    if fixed - {digest}:
        raise CalibrationError("a fixed sample is never rewritten: seal a new directory")
    (directory / GOLD_FILE).write_text(text, encoding="utf-8", newline="\n")
    (directory / JOBS_FILE).write_text(
        gold_text(cases, truth=False), encoding="utf-8", newline="\n"
    )
    if not fixed:
        with open(directory / SEAL_LOG, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(
                json.dumps(
                    {"gold_sha256": digest, "cases": len(cases), "fixed_at": now()}, sort_keys=True
                )
                + "\n"
            )
    return digest


def fixed_gold(directory: Path) -> tuple[list[dict[str, Any]], str]:
    """`(cases, fixed_at)`, refusing a GOLD.jsonl that is not the one the log fixed."""
    entries = [e for e in _log(directory) if "gold_sha256" in e]
    path = directory / GOLD_FILE
    if len(entries) != 1 or not path.is_file():
        raise CalibrationError(f"{directory} has no fixed sample: run `gold` first")
    text = path.read_text(encoding="utf-8")
    if _sha(text) != entries[0]["gold_sha256"]:
        raise CalibrationError(f"{path} changed after it was fixed")
    return [json.loads(line) for line in text.splitlines() if line.strip()], str(
        entries[0]["fixed_at"]
    )


def stratified(
    items: Sequence[Mapping[str, Any]], key: str, n: int, seed: int
) -> list[Mapping[str, Any]]:
    """`n` items stratified by `item[key]`: an equal share per class, the shortfall of a small class
    given to the larger ones; deterministic for a seed."""
    rng = random.Random(seed)  # noqa: S311 - a reproducible sample, not a secret
    by_class: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in items:
        by_class[str(item[key])].append(item)
    for rows in by_class.values():
        rows.sort(key=lambda r: json.dumps(r, sort_keys=True))
        rng.shuffle(rows)
    take = dict.fromkeys(by_class, 0)
    remaining = min(n, len(items))
    open_classes = sorted(by_class)
    while remaining and open_classes:
        share = max(1, remaining // len(open_classes))
        for cls in list(open_classes):
            grant = min(share, len(by_class[cls]) - take[cls], remaining)
            take[cls] += grant
            remaining -= grant
            if take[cls] == len(by_class[cls]):
                open_classes.remove(cls)
            if not remaining:
                break
    return [row for cls in sorted(by_class) for row in by_class[cls][: take[cls]]]


def sample(items: Sequence[Mapping[str, Any]], n: int, seed: int) -> list[Mapping[str, Any]]:
    """`n` items drawn without replacement, deterministic; fewer only when there are fewer."""
    ordered = sorted(items, key=lambda r: json.dumps(r, sort_keys=True))
    return random.Random(seed).sample(ordered, min(n, len(ordered)))  # noqa: S311 - reproducible


# ---- the case builders: pure functions of records the caller has loaded
def kind_cases(
    jobs: Sequence[Mapping[str, Any]],
    verdicts: Sequence[Mapping[str, Any]],
    path_of: Callable[[Mapping[str, Any]], str],
    *,
    n: int,
    seed: int,
) -> list[dict[str, Any]]:
    """The prefilter's gold: Opus's C1 kind of a gallery picture, stratified by kind. A verdict with
    an error or without a kind is no gold."""
    kinds = {
        int(v["image_id"]): v["parsed"]["kind"]
        for v in verdicts
        if not v.get("error") and (v.get("parsed") or {}).get("kind") in PF.KINDS
    }
    pool = [
        {**job, "kind": kinds[int(job["image_id"])]}
        for job in jobs
        if int(job["image_id"]) in kinds
    ]
    return [
        {
            "case_id": f"kind-{job['image_id']}",
            "role": "image_prefilter",
            "group": "kind",
            "site": {"site_id": job["site_id"], "name": job["site_name"]},
            "file": str(job["filename"]),
            "path": path_of(job),
            "truth": job["kind"],
        }
        for job in stratified(pool, "kind", n, seed)
    ]


def depicts_case(
    group: str, site: Mapping[str, Any], file: str, path: str, truth: str | None, *, case_id: str
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "role": "image_depicts",
        "group": group,
        "site": dict(site),
        "file": file,
        "path": path,
        "truth": truth,
    }


def adversarial_cases(
    depicts: Sequence[Mapping[str, Any]], *, per_group: int, seed: int
) -> list[dict[str, Any]]:
    """The re-check's cases: candidates a judge called `depicts`, with the truth the labels or the
    adjudication give. Positives and hard negatives of the depicts role are re-asked as picks."""
    out = []
    for group in ("positive", "foreign", "hard_negative", "adjudicated"):
        rows = [c for c in depicts if c["group"] == group]
        for case in sample(rows, per_group, seed):
            out.append({**case, "case_id": f"rck-{case['case_id']}", "role": "adversarial"})
    return out


def identity_cases(
    gold: Sequence[Mapping[str, Any]], population: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """The identity researcher's cases: sites whose link is known wrong or known good
    (`{site_id, label: wrong|good}`), as verify questions."""
    out = []
    for item in gold:
        site = population.get(str(item["site_id"]))
        if site is None:
            raise CalibrationError(f"{item['site_id']}: not in the population")
        if item["label"] not in ("wrong", "good"):
            raise CalibrationError(f"{item['site_id']}: label {item['label']!r} is not wrong/good")
        out.append(
            {
                "case_id": f"id-{item['site_id']}",
                "role": "web_verifier",
                "group": f"identity_{item['label']}",
                "site": {**site, "flags": item.get("flags") or ["calibration case"]},
                "file": "",
                "path": "",
                "truth": item["label"],
            }
        )
    return out


def _site_context(
    site: Mapping[str, Any],
    context: Mapping[str, Mapping[str, Any]],
    lead: Callable[[str], str | None],
) -> dict[str, Any]:
    """A case's site as the production prompt reads it: the read's facts, the description head and
    the lead of the English article."""
    sid = str(site["id"])
    return {
        "site_id": sid,
        "name": site["name"],
        "country": site.get("country"),
        "site_type": site.get("site_type"),
        "lat": site["lat"],
        "lon": site["lon"],
        "description": (context.get(sid) or {}).get("description") or None,
        "wikipedia_lead": lead(sid),
    }


def build_gold(
    *,
    state: ST.State,
    context: Mapping[str, Mapping[str, Any]],
    lead: Callable[[str], str | None],
    path_of: Callable[[str, str], str],
    c1_jobs: Sequence[Mapping[str, Any]],
    c1_verdicts: Sequence[Mapping[str, Any]],
    labelled: Sequence[Mapping[str, Any]],
    gold_rows: Sequence[Any],
    owner_links: Mapping[str, Mapping[str, Any]],
    excluded_images: Collection[int],
    served_checks: Sequence[Mapping[str, Any]],
    served_replaces: Sequence[Mapping[str, Any]],
    pool_candidates: Sequence[Mapping[str, Any]],
    pool_verdicts: Sequence[Mapping[str, Any]],
    pool_path: Callable[[Mapping[str, Any]], str],
    identity_gold: Sequence[Mapping[str, Any]],
    population: Mapping[str, Mapping[str, Any]],
    thresholds: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """The whole sample of the calibration, deterministic for the sealed seed.

    `state` is a fresh production read (its rows carry `filename`); `path_of(site_id, filename)` is
    the offsite picture of a gallery row. `excluded_images` are the 47 re-checked heroes and the 192
    candidate-search heroes: they are no gold, being the lane's own subjects. The caller loaded every
    other input; this function only chooses and labels."""
    from gallery_audit import labels as LB
    from served_image import recheck as RC

    seed = int(thresholds["seed"])
    roles = thresholds["roles"]
    rows = {int(r["id"]): r for sid in state.site_ids() for r in state.rows.get(sid, ())}
    cases: list[dict[str, Any]] = []

    def gallery_case(role_group: str, image_id: int, truth: str, prefix: str) -> dict[str, Any]:
        row = rows[image_id]
        site = state.sites[str(row["site_id"])]
        return depicts_case(
            role_group,
            _site_context(site, context, lead),
            str(row["filename"]),
            path_of(str(row["site_id"]), str(row["filename"])),
            truth,
            case_id=f"{prefix}-{image_id}",
        )

    # ---- the prefilter: Opus's C1 kind, stratified
    cases += kind_cases(
        c1_jobs,
        c1_verdicts,
        lambda job: path_of(str(job["site_id"]), str(job["filename"])),
        n=roles["image_prefilter"]["kind_cases"],
        seed=seed,
    )
    # ---- the depicts role: owner-linked heroes are the positives
    linked = [
        r
        for r in rows.values()
        if r.get("is_hero")
        and not r.get("is_excluded")
        and int(r["id"]) not in excluded_images
        and (claim := (owner_links.get(str(r["site_id"])) or {}).get("image"))
        and ST.file_of_row(r) == ST.file_of_url(claim)
    ]
    for r in sample(linked, roles["image_depicts"]["positives"], seed):
        cases.append(gallery_case("positive", int(r["id"]), "depicts", "pos"))
    for g in gold_rows:
        if not g.foreign and int(g.image_id) in rows:
            cases.append(gallery_case("positive_gold", int(g.image_id), "depicts", "gpos"))
    # ---- the hard negatives
    foreign = [
        line for line in labelled if LB.FOREIGN in line["labels"] and int(line["image_id"]) in rows
    ]
    for line in foreign[: roles["image_depicts"]["foreign_labelled"]]:
        cases.append(gallery_case("foreign", int(line["image_id"]), "not_depicts", "frn"))
    for g in gold_rows:
        if g.foreign and int(g.image_id) in rows:
            cases.append(gallery_case("foreign_gold", int(g.image_id), "not_depicts", "gfrn"))
    judged = RC.judged_gallery_rows(served_checks, served_replaces)
    claude_other = [
        {"image_id": i}
        for i, v in judged.items()
        if v["verdict"] == RC.OTHER_SITE and i not in excluded_images and i in rows
    ]
    for item in sample(claude_other, roles["image_depicts"]["claude_other_site"], seed):
        cases.append(gallery_case("hard_negative", int(item["image_id"]), "not_depicts", "cos"))
    # ---- the MiniMax pool, adjudicated by the pilot judge (Opus xhigh): no truth yet
    by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    candidates = {
        (str(s["site_id"]), str(c["file"])): (s, c)
        for s in pool_candidates
        for c in s["candidates"]
    }
    for v in pool_verdicts:
        key = (str(v["site_id"]), str(v["file"]))
        if key in candidates and Path(pool_path(candidates[key][1])).is_file():
            by_class[str(v["verdict"])].append({"site_id": key[0], "file": key[1]})
    adjudicated = [
        item
        for cls in sorted(by_class)
        for item in sample(by_class[cls], roles["pilot_judge"]["per_class"], seed)
    ]
    for item in adjudicated:
        site, candidate = candidates[(item["site_id"], item["file"])]
        info = population.get(item["site_id"]) or {
            "site_id": item["site_id"],
            "name": site["name"],
            "country": site.get("country"),
            "lat": 0.0,
            "lon": 0.0,
        }
        case = depicts_case(
            "adjudicated",
            {**info, "wikipedia_lead": lead(item["site_id"])},
            item["file"],
            pool_path(candidate),
            None,
            case_id=f"adj-{hashlib.sha256((item['site_id'] + item['file']).encode()).hexdigest()[:12]}",
        )
        case["why"] = str(candidate.get("why") or "a Commons picture search")
        cases.append(case)
    # ---- the hero re-check: the labelled and adjudicated cases asked again as picks
    depicts_cases = [c for c in cases if c["role"] == "image_depicts"]
    cases += adversarial_cases(
        depicts_cases, per_group=roles["pilot_judge"]["per_class"], seed=seed
    )
    # ---- the identity researcher
    cases += identity_cases(identity_gold, population)
    return cases


# ---------------------------------------------------------------------------------- the questions
def questions_for(
    role: str, cases: Sequence[Mapping[str, Any]], read: Callable[[Mapping[str, Any]], bytes]
) -> tuple[list[SG.Question], dict[str, bytes]]:
    """The production questions of `role` over its cases (the very prompts the lane will use)."""
    mine = [c for c in cases if c["role"] == role]
    if not mine:
        raise CalibrationError(f"the sample holds no case for role {role}")
    if role == "image_prefilter":
        flat = [{"site_id": c["case_id"], "file": c["file"], "path": c["path"]} for c in mine]
        return PF.build_questions(flat, read)
    if role in ("image_depicts", "pilot_judge"):
        by_site: dict[str, dict[str, Any]] = {}
        for c in mine:
            site = by_site.setdefault(str(c["site"]["site_id"]), {**c["site"], "candidates": []})
            site["candidates"].append(
                {"file": c["file"], "path": c["path"], "why": c.get("why") or "a Commons picture"}
            )
        questions, pictures, _ = DP.build_questions(list(by_site.values()), read)
        return questions, pictures
    if role == "adversarial":
        # a question is labelled by its site: the case id stands in for it, so that two cases of
        # one real site are two questions
        picks = [
            {
                **c["site"],
                "site_id": c["case_id"],
                "file": c["file"],
                "path": c["path"],
                "note": c.get("note") or "a judge called it depicts",
                "answered_by": "image_depicts:calibration",
            }
            for c in mine
        ]
        return HR.build_questions(picks, read, round_number=1)
    if role == "web_verifier":
        return ID.build_questions([c["site"] for c in mine], mode="verify", cache=None), {}
    raise CalibrationError(f"role {role} has no calibration questions")


# -------------------------------------------------------------------------------------- measuring
def interval(k: int, n: int, cp: Callable[[int, int], tuple[float, float]]) -> dict[str, Any]:
    low, high = cp(k, n)
    return {
        "k": k,
        "n": n,
        "rate": round(k / n, 4) if n else None,
        "ci95": [round(low, 4), round(high, 4)],
    }


def measure_prefilter(
    cases: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    cp: Callable[[int, int], tuple[float, float]],
) -> dict[str, Any]:
    """Photo versus non-photo agreement and the recall of depicts-capable pictures."""
    truth = {c["case_id"]: c["truth"] for c in cases if c["role"] == "image_prefilter"}
    judged = {r["site_id"]: r for r in PF.judged(results)}
    missing = sorted(set(truth) - set(judged))
    if missing:
        raise CalibrationError(f"{len(missing)} prefilter case(s) unanswered (first {missing[0]})")
    agree = sum((truth[i] in PHOTO_KINDS) == (judged[i]["kind"] in PHOTO_KINDS) for i in truth)
    capable = [i for i, kind in truth.items() if kind in PF.SURVIVING_KINDS]
    kept = sum(judged[i]["survives"] for i in capable)
    return {
        "photo_agreement": interval(agree, len(truth), cp),
        "depicts_capable_recall": interval(kept, len(capable), cp),
        "kind_confusion": dict(Counter(f"{truth[i]}->{judged[i]['kind']}" for i in truth)),
    }


def _verdicts_of(results: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """`{(site id, file): its verdict row}` from depicts-shaped results."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for result in results:
        files = {i["label"]: i["file"] for i in result["meta"]["items"]}
        for label, entry in result["candidates"].items():
            out[(str(result["meta"]["site_id"]), files[label])] = entry
    return out


def adjudicated_truth(
    cases: Sequence[Mapping[str, Any]], adjudication: Sequence[Mapping[str, Any]]
) -> dict[str, str]:
    """`{case id: depicts | not_depicts}` for the adjudicated cases, from the pilot judge's answers."""
    by_key = _verdicts_of(adjudication)
    out = {}
    for c in cases:
        if c["group"] != "adjudicated":
            continue
        entry = by_key.get((str(c["site"]["site_id"]), c["file"]))
        if entry is None:
            raise CalibrationError(f"{c['case_id']}: the pilot judge has not adjudicated it")
        out[c["case_id"]] = "depicts" if entry["verdict"] == CJ.DEPICTS else "not_depicts"
    return out


def measure_depicts(
    cases: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    adjudication: Sequence[Mapping[str, Any]],
    cp: Callable[[int, int], tuple[float, float]],
) -> dict[str, Any]:
    """Sensitivity on the owner-linked heroes, the false-depicts rate and the precision over the
    hard negatives and the adjudicated candidates, and the foreign rows called depicts."""
    mine = [c for c in cases if c["role"] == "image_depicts"]
    verdicts = _verdicts_of(results)
    truth = {c["case_id"]: c["truth"] for c in mine if c["truth"]} | adjudicated_truth(
        mine, adjudication
    )
    called: dict[str, bool] = {}
    for c in mine:
        entry = verdicts.get((str(c["site"]["site_id"]), c["file"]))
        if entry is None:
            raise CalibrationError(f"{c['case_id']}: unanswered")
        called[c["case_id"]] = entry["verdict"] == CJ.DEPICTS
    positives = [i for i, t in truth.items() if t == "depicts"]
    negatives = [i for i, t in truth.items() if t == "not_depicts"]
    owner = [c["case_id"] for c in mine if c["group"] == "positive"]
    foreign = [c["case_id"] for c in mine if c["group"] in ("foreign", "foreign_gold")]
    false_depicts = sum(called[i] for i in negatives)
    true_depicts = sum(called[i] for i in positives)
    precision_n = true_depicts + false_depicts
    return {
        "sensitivity": interval(sum(called[i] for i in owner), len(owner), cp),
        "false_depicts": interval(false_depicts, len(negatives), cp),
        "precision": interval(true_depicts, precision_n, cp),
        "foreign_called_depicts": sorted(i for i in foreign if called[i]),
        "foreign_rows": len(foreign),
    }


def measure_adversarial(
    cases: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    adjudication: Sequence[Mapping[str, Any]],
    cp: Callable[[int, int], tuple[float, float]],
) -> dict[str, Any]:
    """Agreement of the re-check's depicts / not-depicts with the labelled truth or the adjudication."""
    mine = [c for c in cases if c["role"] == "adversarial"]
    by_file = {
        (r["meta"]["site_id"], r["meta"]["file"]): r["verdict"] for r in results
    }  # site = case
    adjudicated = adjudicated_truth(
        [{**c, "group": "adjudicated"} for c in mine if c["truth"] is None], adjudication
    )
    agree = n = 0
    for c in mine:
        verdict = by_file.get((c["case_id"], c["file"]))
        if verdict is None:
            raise CalibrationError(f"{c['case_id']}: unanswered")
        truth = c["truth"] or adjudicated[c["case_id"]]
        n += 1
        agree += (verdict == CJ.DEPICTS) == (truth == "depicts")
    return {"agreement": interval(agree, n, cp)}


def measure_identity(
    cases: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    cp: Callable[[int, int], tuple[float, float]],
) -> dict[str, Any]:
    """Correct = a wrong link is flagged (a `wrong` status on the item or the article), a good one is
    confirmed."""
    mine = [c for c in cases if c["role"] == "web_verifier"]
    answers = ID.identity_rows(results)
    correct = 0
    unflagged = []
    for c in mine:
        verdict = answers.get(str(c["site"]["site_id"]))
        if verdict is None:
            raise CalibrationError(f"{c['case_id']}: unanswered")
        flagged = "wrong" in (verdict["qid_status"], verdict["enwiki_status"])
        ok = (
            flagged
            if c["truth"] == "wrong"
            else not flagged and "unknown" not in (verdict["qid_status"], verdict["enwiki_status"])
        )
        correct += ok
        if c["truth"] == "wrong" and not flagged:
            unflagged.append(c["case_id"])
    return {"correct": interval(correct, len(mine), cp), "wrong_not_flagged": unflagged}


def decide(role: str, thresholds: Mapping[str, Any], metrics: Mapping[str, Any]) -> list[str]:
    """The failures of one role against its sealed thresholds; empty means it passed."""
    if role not in MEASURED:
        raise CalibrationError(f"role {role} is not measured")
    t = thresholds["roles"][role]
    failures: list[str] = []

    def below(name: str, floor: float) -> None:
        value = metrics[name]["rate"]
        if value is None or value < floor:
            failures.append(f"{name} {value} is below {floor}")

    if role == "image_prefilter":
        below("photo_agreement", t["photo_agreement_min"])
        below("depicts_capable_recall", t["depicts_capable_recall_min"])
    elif role == "image_depicts":
        below("sensitivity", t["sensitivity_min"])
        below("precision", t["precision_min"])
        rate = metrics["false_depicts"]["rate"]
        if rate is None or rate > t["false_depicts_max"]:
            failures.append(f"false_depicts {rate} is above {t['false_depicts_max']}")
        if t["every_foreign_not_depicts"] and metrics["foreign_called_depicts"]:
            failures.append(
                f"{len(metrics['foreign_called_depicts'])} foreign row(s) called depicts"
            )
    elif role == "adversarial":
        below("agreement", t["agreement_min"])
    elif role == "web_verifier":
        below("correct", t["correct_min"])
        if t["every_wrong_flagged"] and metrics["wrong_not_flagged"]:
            failures.append(f"{len(metrics['wrong_not_flagged'])} wrong link(s) not flagged")
    else:
        raise CalibrationError(f"role {role} is not measured")
    return failures


MEASURED = ("image_prefilter", "image_depicts", "adversarial", "web_verifier")


def evaluate(
    directory: Path,
    role: str,
    *,
    now: Callable[[], str] = _now,
    cp: Callable[[int, int], tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """Measure one role against the sealed thresholds and write `verdicts/<role>.json` (once).

    Refused: a role that is not measured, a directory whose thresholds or sample changed, an answer
    judged before the sample was fixed. A failing role carries its tier move (`roles.escalation`), or
    - at Opus - the hold: the owner decides."""
    thresholds, _, _ = sealed(directory)
    if role not in MEASURED:
        raise CalibrationError(f"role {role} is not measured (the pilot judge is the gold)")
    cases, fixed_at = fixed_gold(directory)
    spec = ROLE_SPECS[role]
    results = SG.read_results(directory, spec)
    for row in results:
        if row["answered_at"] < fixed_at:
            raise CalibrationError(
                f"{row['batch_id']}/{row['label']}: judged before the sample was fixed"
            )
    cp = cp or clopper_pearson()
    adjudication = (
        SG.read_results(directory, ADJUDICATE_SPEC)
        if role in ("image_depicts", "adversarial")
        and (directory / ADJUDICATE_SPEC.result_file).is_file()
        else []
    )
    if role == "image_prefilter":
        metrics = measure_prefilter(cases, results, cp)
    elif role == "image_depicts":
        metrics = measure_depicts(cases, results, adjudication, cp)
    elif role == "adversarial":
        metrics = measure_adversarial(cases, results, adjudication, cp)
    else:
        metrics = measure_identity(cases, results, cp)
    failures = decide(role, thresholds, metrics)
    verdict: dict[str, Any] = {
        "role": role,
        "model": RO.role(role).model,
        "effort": RO.role(role).effort,
        "passed": not failures,
        "failures": failures,
        "metrics": metrics,
        "decided_at": now(),
        "tier_move": None,
    }
    if failures:
        try:
            verdict["tier_move"] = RO.escalation(
                role, calibration_id=directory.name, reason="; ".join(failures)
            )
        except RO.RoleError as exc:
            verdict["held"] = f"{exc}: the owner decides"
    path = directory / VERDICTS_DIR / f"{role}.json"
    if path.exists():
        raise CalibrationError(f"{path} exists - a verdict is written once")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(verdict, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return verdict


# ----------------------------------------------------------------------------------------- the CLI
def cmd_export(directory: Path, role: str, handoff: Path) -> dict[str, Any]:
    from pipeline.video.shorts_select import vlm_bytes

    sealed(directory)
    cases, _ = fixed_gold(directory)
    spec = ROLE_SPECS[role]
    questions, pictures = questions_for(role, cases, lambda c: vlm_bytes(Path(str(c["path"]))))
    return SG.export(directory, handoff, spec, questions, pictures)


DESCRIPTIONS_SQL = """SELECT row_to_json(t) FROM (
  SELECT u.id::text AS site_id, left(coalesce(u.description, ''), 900) AS description
    FROM unified_sites u WHERE u.source_id = 'ancient_nerds' ORDER BY u.id
) t;"""


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise CalibrationError(f"{path} does not exist")
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def cmd_gold(directory: Path, args: argparse.Namespace) -> dict[str, Any]:
    """Choose the sample from the files and production (read-only) and fix it."""
    from candidate_search import pool as PL
    from gallery_audit import labels as LB
    from gallery_audit import persist_verdicts as pv
    from gallery_audit.vision import Images
    from import_hero import plan as IH

    from image_roles.wiki_cache import WikiCache

    thresholds, _, _ = sealed(directory)
    state = ST.load_read(args.read)
    images = Images()
    context = {str(r["site_id"]): r for r in pv.read_rows(DESCRIPTIONS_SQL)}
    cache = WikiCache(args.wiki_cache)
    excluded: set[int] = set()
    for path in args.exclude_heroes or ():
        excluded |= {int(r["image_id"]) for r in _jsonl(path)}
    population = {str(r["site_id"]): r for r in _jsonl(args.population)}
    gold = [
        {"site_id": r["site_id"], "label": r["label"], "flags": r.get("flags")}
        for r in _jsonl(args.identity_gold)
    ]
    cases = build_gold(
        state=state,
        context=context,
        lead=lambda sid: cache.lead(sid),
        path_of=lambda sid, filename: str(images.path_for(sid, filename)),
        c1_jobs=_jsonl(args.c1_dir / "JOBS.jsonl"),
        c1_verdicts=_jsonl(args.c1_dir / "VERDICTS.jsonl"),
        labelled=_jsonl(args.labels),
        gold_rows=LB.GOLD_ROWS,
        owner_links=IH.join_import(state, IH.read_import(args.import_geojson)),
        excluded_images=excluded,
        served_checks=_jsonl(args.served_run / "CHECK.jsonl"),
        served_replaces=_jsonl(args.served_run / "REPLACE.jsonl"),
        pool_candidates=_jsonl(args.pool_run / "CANDIDATES.jsonl"),
        pool_verdicts=_jsonl(args.pool_run / "VERDICTS.jsonl"),
        pool_path=lambda c: str(PL.picture_path(args.pool_run, c)),
        identity_gold=gold,
        population=population,
        thresholds=thresholds,
    )
    digest = fix_gold(directory, cases)
    return {
        "gold_sha256": digest,
        "cases": len(cases),
        "by_group": dict(Counter(c["group"] for c in cases)),
        "by_role": dict(Counter(c["role"] for c in cases)),
    }


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(prog="image_roles/calibrate.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("seal", "gold", "export", "evaluate"):
        command = sub.add_parser(name)
        command.add_argument("--dir", required=True, type=Path)
    gold = sub.choices["gold"]
    gold.add_argument("--read", required=True, type=Path, help="a fresh production READ.json")
    gold.add_argument("--c1-dir", required=True, type=Path, help="gallery_audit/calibration-*-opus")
    gold.add_argument("--labels", required=True, type=Path, help="gallery_labels_652.jsonl")
    gold.add_argument("--import-geojson", required=True, type=Path, help="the 2025 import")
    gold.add_argument("--served-run", required=True, type=Path, help="served-image-2026-09-30")
    gold.add_argument("--pool-run", required=True, type=Path, help="candidates-2026-10-06")
    gold.add_argument("--population", required=True, type=Path, help="POPULATION.jsonl")
    gold.add_argument("--identity-gold", required=True, type=Path, help="site_id, label wrong|good")
    gold.add_argument("--wiki-cache", required=True, type=Path)
    gold.add_argument("--exclude-heroes", type=Path, nargs="*", help="OTHER_SITE_HEROES.jsonl")
    export = sub.choices["export"]
    export.add_argument("--role", required=True, choices=sorted(ROLE_SPECS))
    export.add_argument("--handoff", required=True, type=Path)
    sub.choices["evaluate"].add_argument("--role", required=True, choices=MEASURED)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "seal":
            payload: Any = {"thresholds_sha256": seal(args.dir)}
        elif args.command == "gold":
            payload = cmd_gold(args.dir, args)
        elif args.command == "export":
            payload = cmd_export(args.dir, args.role, args.handoff)
        else:
            payload = evaluate(args.dir, args.role)
    except (ST.StateError, RO.RoleError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))
    return 0 if args.command != "evaluate" or payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
