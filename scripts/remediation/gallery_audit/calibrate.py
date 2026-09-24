"""S7 - calibration C1: thresholds sealed before the first call, then the admission of each trigger.

Order, enforced rather than promised
------------------------------------
1. ``seal``     writes ``THRESHOLDS.json`` from the constant below and appends its sha256 to
                ``SEAL.jsonl``. It refuses when the run directory already holds a verdict ledger:
                a threshold written after data exists is not a threshold.
2. ``jobs``     writes the C1 ``JOBS.jsonl`` - and refuses unless the seal is in place and the
                file on disk still hashes to it.
3. the vision round through the Opus handoff (owner order 2026-09-23): `vision.py export --jobs
   .../JOBS.jsonl --run-dir <this dir> --handoff H`, the orchestrator's Opus agents answer,
   `opus_handoff.py validate --dir H`, then `vision.py import` with the same arguments - a
   production operation of 939 questions. The thresholds name the model (`vision.MODEL`), so a
   directory sealed for another model (`calibration-2026-09-23/`, the pilot's DeepSeek transport)
   admits nothing of an Opus ledger, and the Opus calibration is sealed in a directory of its own.
4. ``evaluate`` refuses a thresholds file whose sha256 is not the sealed one, and a ledger line
   judged before the seal; then measures, and writes ``ADMISSION.json``, which `decide.py` reads.
   The eye labels are named explicitly (``--eye-labels`` a file of this repository, or
   ``--no-eye-labels``): a mistyped path is an error, never "no eye labels".

No threshold changes after its data is seen; a trigger that fails is dropped, not re-tuned.

What ties an admission to its calibration
-----------------------------------------
``ADMISSION.json`` is a pure function of its inputs - the sealed thresholds, the jobs, the ledger
and the eye labels, each named with its sha256 - and carries no time of its own, so its own sha256
names exactly what was measured. `decide.py` never trusts the file: `verify_admission` re-derives
it from the run directory and refuses it unless the two are byte-identical and T0 passed. A
hand-edited admission, one measured on other labels or another ledger, or one written before the
last verdict, switches nothing on. Every vision-planned row cites the admission's sha256.

The three sets (`labels.py`): (i) the 200 pilot tiles, (ii) the 652 labelled rows, (iii) the gold
galleries - all 42 rows of Agri Bavnehoj, Langdale and Xcaret, of which 25 are named. The strict
question is asked of all 50 tier-A pilot tiles, so its precision and recall are measurable against
W8's eye labels whatever the first pass said.

Counts are reported with Clopper-Pearson intervals (the project's own implementation,
`output/remediation/gold_standard/compare_fnr.py::clopper_pearson`), never as bare rates.

Usage:
    calibrate.py seal --run-dir DIR
    calibrate.py jobs --run-dir DIR --hero-moves PLAN.jsonl [--snapshot DIR] [--cache DIR] [--t10 F]
    calibrate.py evaluate --run-dir DIR (--eye-labels LABELS.jsonl | --no-eye-labels)
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
_REMEDIATION = ROOT / "scripts" / "remediation"
if str(_REMEDIATION) not in sys.path:
    sys.path.insert(0, str(_REMEDIATION))

from gallery_audit import labels, vision, worklist  # noqa: E402

OUTPUT = ROOT / "output" / "remediation" / "gallery_audit"
COMPARE_FNR = ROOT / "output" / "remediation" / "gold_standard" / "compare_fnr.py"

THRESHOLDS: dict[str, Any] = {
    "version": "c1-v1",
    "source": "output/remediation/logs/design_texts_images_2026-09-22.json, entry 7, pilot_and_thresholds",
    "T0": {"rule": "every C1 job has an in-vocabulary verdict, else STOP and admit nothing"},
    "T-kind": {
        "rule": "image_kind writes (K1, K2) only if both hold",
        "pilot_agreement_min": 0.90,
        "non_photo_precision_min": 0.90,
    },
    "T-X1": {
        "rule": "other_site exclusions (X1) only if all hold",
        "foreign_rows_resolved_min": 60,
        "precision_min": 0.85,
        "recall_min": 0.70,
        "gold_foreign_flagged": "all",
        "gold_correct_flagged_max": 1,
    },
    "T-X2": {"rule": "kind people exclusions (X2)", "precision_min": 0.85, "flags_min": 10},
    "T-X3": {"rule": "kind other exclusions (X3)", "precision_min": 0.85, "flags_min": 10},
    "T-strict": {
        "rule": "HERO_PROMPT (K2, H1) only if both hold on the tier-A pilot tiles the eye labels judged",
        "tier": "A",
        "tiles": 50,
        "precision_min": 0.90,
        "recall_min": 0.60,
        "owner_spot_check": "at least 36 of 40 agree (non-blocking; a failure reverses the hero moves)",
    },
    "definitions": {
        "non_photo_kinds": ["map_or_document", "painting_or_artwork"],
        "non_photo_labels": list(labels.NON_PHOTO),
        "foreign_label": labels.FOREIGN,
        "not_this_site_labels": list(labels.NOT_THIS_SITE),
        "gold_foreign": sorted(g.image_id for g in labels.GOLD_ROWS if g.foreign),
        "gold_correct": sorted(g.image_id for g in labels.GOLD_ROWS if not g.foreign),
        "gold_sites": list(labels.GOLD_SITE_IDS),
        "gallery_prompt_sha256": vision.prompt_sha256(vision.GALLERY_PROMPT),
        "hero_prompt_sha256": vision.prompt_sha256(vision.HERO_PROMPT),
        "model": vision.MODEL,
        "interval": "Clopper-Pearson 95 %",
    },
    "early_gate": {
        "after_sites": 300,
        "blind_tiles": {"excluded": 30, "judged_and_kept": 30},
        "pass": "at most 3 exclusions wrong AND at most 3 kept tiles show another place",
    },
    "final_acceptance": {
        "seed": 20260923,
        "excluded_rows": {"n": 100, "correct_min": 90},
        "judged_kept_rows": {"n": 100, "other_place_max": 5},
        "tier_d_zero_call_rows": {"n": 50, "foreign_max": 3},
        "served_heroes": {"n": 50, "shows_archaeology_min": 45},
        "gold": "every gold-foreign row excluded, no gold-correct row excluded, all 3 served heroes strict-confirmed",
        "journal_two_way_deviations_max": 0,
    },
}

#: JSON lines, and not `*.log`: the repository ignores every `*.log`, and the seal is evidence.
SEAL_LOG = "SEAL.jsonl"
THRESHOLDS_FILE = "THRESHOLDS.json"
JOBS_FILE = "JOBS.jsonl"
LEDGER_FILE = "VERDICTS.jsonl"
ADMISSION_FILE = "ADMISSION.json"
C1 = "C1"


class CalibrationError(RuntimeError):
    """Calibration cannot be trusted as asked. Never answered with a partial admission."""


def _clopper_pearson() -> Callable[[int, int], tuple[float, float]]:
    spec = importlib.util.spec_from_file_location("compare_fnr", COMPARE_FNR)
    if spec is None or spec.loader is None:
        raise CalibrationError(f"{COMPARE_FNR} cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.clopper_pearson  # type: ignore[no-any-return]


def thresholds_text(thresholds: Mapping[str, Any] = THRESHOLDS) -> str:
    return json.dumps(thresholds, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------------------ the seal
def seal(run_dir: Path, *, now: Callable[[], str] = _now) -> str:
    """Write THRESHOLDS.json and log its sha256 - before any verdict exists in `run_dir`."""
    if (run_dir / LEDGER_FILE).exists():
        raise CalibrationError(
            f"{run_dir / LEDGER_FILE} exists - thresholds are sealed before the first call, not after"
        )
    text = thresholds_text()
    digest = _sha(text)
    path = run_dir / THRESHOLDS_FILE
    if path.exists() and path.read_text(encoding="utf-8") != text:
        raise CalibrationError(
            f"{path} already holds other thresholds - a sealed file is never rewritten"
        )
    run_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    with open(run_dir / SEAL_LOG, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps({"thresholds_sha256": digest, "sealed_at": now()}, sort_keys=True) + "\n"
        )
    return digest


def sealed(run_dir: Path) -> tuple[dict[str, Any], str, str]:
    """(thresholds, sha256, sealed_at) - refusing a file that is not the one the log sealed."""
    log = run_dir / SEAL_LOG
    path = run_dir / THRESHOLDS_FILE
    if not log.is_file() or not path.is_file():
        raise CalibrationError(
            f"{run_dir} is not sealed - run `calibrate.py seal` before anything else"
        )
    entries = [
        json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if len({e["thresholds_sha256"] for e in entries}) != 1:
        raise CalibrationError(f"{log} records more than one thresholds hash")
    text = path.read_text(encoding="utf-8")
    digest = _sha(text)
    if digest != entries[0]["thresholds_sha256"]:
        raise CalibrationError(
            f"{path} hashes to {digest[:16]}, the seal says {entries[0]['thresholds_sha256'][:16]} - "
            "the thresholds changed after they were sealed"
        )
    return json.loads(text), digest, str(entries[0]["sealed_at"])


# ------------------------------------------------------------------------------ the jobs
def c1_jobs(
    state: worklist.State, tiles: Sequence[labels.PilotTile], labelled: Sequence[labels.LabelledRow]
) -> list[vision.Job]:
    """The gallery question on (i), (ii) and every row of the gold galleries (iii), once per image,
    plus the hero question on every tier-A pilot tile."""
    wanted: list[int] = []
    for image_id in [t.image_id for t in tiles] + [r.image_id for r in labelled]:
        if image_id not in wanted:
            wanted.append(image_id)
    for site_id in labels.GOLD_SITE_IDS:
        for row in state.by_site[site_id]:
            if int(row["id"]) not in wanted:
                wanted.append(int(row["id"]))
    jobs = [worklist.job_for(state, state.row(image_id), vision.GALLERY, C1) for image_id in wanted]
    jobs += [
        worklist.job_for(state, state.row(t.image_id), vision.HERO, C1)
        for t in tiles
        if t.tier == "A"
    ]
    return jobs


# ------------------------------------------------------------------------------ measuring
def _rate(k: int, n: int, ci: Callable[[int, int], tuple[float, float]]) -> dict[str, Any]:
    lo, hi = ci(k, n)
    return {
        "k": k,
        "n": n,
        "rate": None if n == 0 else round(k / n, 4),
        "ci95": [round(lo, 4), round(hi, 4)],
    }


def evaluate(
    thresholds: Mapping[str, Any],
    jobs: Sequence[vision.Job],
    ledger: Sequence[vision.LedgerLine],
    tiles: Sequence[labels.PilotTile],
    labelled: Sequence[labels.LabelledRow],
    eye: Mapping[int, labels.EyeLabel] | None,
    ci: Callable[[int, int], tuple[float, float]],
) -> dict[str, Any]:
    """Every metric the thresholds name, and the admission each one gives."""
    gallery = vision.verdicts_by_image(ledger, vision.GALLERY_PROMPT_ID)
    hero = vision.verdicts_by_image(ledger, vision.HERO_PROMPT_ID)
    have = {(image_id, vision.GALLERY_PROMPT_ID) for image_id in gallery} | {
        (image_id, vision.HERO_PROMPT_ID) for image_id in hero
    }
    missing = [job.key() for job in jobs if job.key() not in have]
    metrics: dict[str, Any] = {
        "T0": {"jobs": len(jobs), "without_verdict": len(missing), "first_missing": missing[:5]}
    }
    admitted = dict.fromkeys(("kind", "strict", "x1", "x2", "x3"), False)
    if missing:
        metrics["T0"]["pass"] = False
        return {"metrics": metrics, "admitted": admitted}
    metrics["T0"]["pass"] = True

    t_kind, t_x1, t_x2, t_x3, t_strict = (
        thresholds[k] for k in ("T-kind", "T-X1", "T-X2", "T-X3", "T-strict")
    )
    non_photo_kinds = set(thresholds["definitions"]["non_photo_kinds"])
    gold_foreign = set(thresholds["definitions"]["gold_foreign"])
    gold_correct = set(thresholds["definitions"]["gold_correct"])

    agree = sum(1 for t in tiles if gallery[t.image_id].verdict["kind"] == t.pilot_kind)
    called_non_photo = [
        r for r in labelled if gallery[r.image_id].verdict["kind"] in non_photo_kinds
    ]
    kind_agreement = _rate(agree, len(tiles), ci)
    non_photo_precision = _rate(
        sum(1 for r in called_non_photo if r.non_photo), len(called_non_photo), ci
    )
    metrics["T-kind"] = {
        "pilot_agreement": kind_agreement,
        "non_photo_precision": non_photo_precision,
    }
    admitted["kind"] = bool(
        kind_agreement["n"]
        and kind_agreement["k"] / kind_agreement["n"] >= t_kind["pilot_agreement_min"]
        and non_photo_precision["n"]
        and non_photo_precision["k"] / non_photo_precision["n"] >= t_kind["non_photo_precision_min"]
    )
    if eye:
        judged = [t for t in tiles if t.image_id in eye and eye[t.image_id].human_kind is not None]
        metrics["T-kind"]["eye_agreement (reported, not a threshold)"] = _rate(
            sum(
                1
                for t in judged
                if gallery[t.image_id].verdict["kind"] == eye[t.image_id].human_kind
            ),
            len(judged),
            ci,
        )

    foreign = [r for r in labelled if r.foreign]
    flagged = [r for r in labelled if gallery[r.image_id].verdict["other_site"] is True]
    precision = _rate(sum(1 for r in flagged if r.foreign), len(flagged), ci)
    recall = _rate(
        sum(1 for r in foreign if gallery[r.image_id].verdict["other_site"] is True),
        len(foreign),
        ci,
    )
    gold_foreign_flagged = sum(1 for i in gold_foreign if gallery[i].verdict["other_site"] is True)
    gold_correct_flagged = sum(1 for i in gold_correct if gallery[i].verdict["other_site"] is True)
    metrics["T-X1"] = {
        "foreign_rows_resolved": len(foreign),
        "precision": precision,
        "recall": recall,
        "gold_foreign_flagged": {"k": gold_foreign_flagged, "n": len(gold_foreign)},
        "gold_correct_flagged": {"k": gold_correct_flagged, "n": len(gold_correct)},
    }
    admitted["x1"] = bool(
        len(foreign) >= t_x1["foreign_rows_resolved_min"]
        and precision["n"]
        and precision["k"] / precision["n"] >= t_x1["precision_min"]
        and recall["n"]
        and recall["k"] / recall["n"] >= t_x1["recall_min"]
        and gold_foreign_flagged == len(gold_foreign)
        and gold_correct_flagged <= t_x1["gold_correct_flagged_max"]
    )

    judged_rows = [(r.image_id, r.not_this_site) for r in labelled]
    judged_rows += [(i, True) for i in sorted(gold_foreign)] + [
        (i, False) for i in sorted(gold_correct)
    ]
    for key, kind, threshold in (("x2", "people", t_x2), ("x3", "other", t_x3)):
        hits = [bad for image_id, bad in judged_rows if gallery[image_id].verdict["kind"] == kind]
        rate = _rate(sum(hits), len(hits), ci)
        metrics[f"T-{key.upper()}"] = {"precision": rate}
        admitted[key] = bool(
            rate["n"] >= threshold["flags_min"]
            and rate["k"] / rate["n"] >= threshold["precision_min"]
        )

    tier_a = [t for t in tiles if t.tier == t_strict["tier"]]
    labelled_a = [
        t
        for t in tier_a
        if eye and t.image_id in eye and eye[t.image_id].shows_archaeology is not None
    ]
    if len(labelled_a) < t_strict["tiles"]:
        metrics["T-strict"] = {
            "evaluable": False,
            "why": f"{len(labelled_a)} of {t_strict['tiles']} tier-A tiles carry an eye label for shows_archaeology",
        }
    else:
        says_yes = [t for t in labelled_a if hero[t.image_id].verdict["shows_archaeology"] is True]
        truly = [t for t in labelled_a if eye and eye[t.image_id].shows_archaeology is True]
        s_precision = _rate(
            sum(1 for t in says_yes if eye and eye[t.image_id].shows_archaeology), len(says_yes), ci
        )
        s_recall = _rate(
            sum(1 for t in truly if hero[t.image_id].verdict["shows_archaeology"] is True),
            len(truly),
            ci,
        )
        metrics["T-strict"] = {"evaluable": True, "precision": s_precision, "recall": s_recall}
        admitted["strict"] = bool(
            s_precision["n"]
            and s_precision["k"] / s_precision["n"] >= t_strict["precision_min"]
            and s_recall["n"]
            and s_recall["k"] / s_recall["n"] >= t_strict["recall_min"]
        )
    return {"metrics": metrics, "admitted": admitted}


def _repo_path(path: Path) -> str:
    """A path as ADMISSION.json records it: relative to the repository, so the admission can be
    re-derived from any checkout. A file outside the repository cannot be re-read there."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise CalibrationError(
            f"{path} is not a file of this repository - the eye labels an admission rests on "
            "must be re-readable wherever the admission is checked"
        ) from exc


def admission_record(run_dir: Path, eye_labels: str | None) -> dict[str, Any]:
    """What `evaluate` measures, with the sha256 of every input it measured on.

    `eye_labels` is a repository-relative path (`_repo_path`) or None for an explicit run without
    eye labels. Nothing in the record depends on when it was made, so the same inputs give the
    same bytes.
    """
    thresholds, digest, sealed_at = sealed(run_dir)
    ledger_path = run_dir / LEDGER_FILE
    if not ledger_path.is_file():
        raise CalibrationError(f"{ledger_path} does not exist - run the C1 vision run first")
    jobs = vision.read_jobs(run_dir / JOBS_FILE)
    ledger = vision.Ledger(ledger_path).lines
    early = [e for e in ledger if str(e.line["judged_at"]) < sealed_at]
    if early:
        raise CalibrationError(
            f"{len(early)} verdict(s) were judged before the seal at {sealed_at}"
        )
    tiles = labels.pilot_tiles()
    labelled = labels.load_labelled()
    eye = None
    eye_sha = None
    if eye_labels is not None:
        eye_path = ROOT / eye_labels
        if not eye_path.is_file():
            raise CalibrationError(
                f"{eye_path} does not exist - name the eye labels W8 wrote, or --no-eye-labels"
            )
        eye = labels.load_eye_labels(eye_path, tiles)
        eye_sha = _sha(eye_path.read_text(encoding="utf-8"))
    result = evaluate(thresholds, jobs, ledger, tiles, labelled, eye, _clopper_pearson())
    return {
        "thresholds_sha256": digest,
        "sealed_at": sealed_at,
        "jobs_sha256": _sha((run_dir / JOBS_FILE).read_text(encoding="utf-8")),
        "ledger_sha256": _sha(ledger_path.read_text(encoding="utf-8")),
        "ledger_lines": len(ledger),
        "eye_labels": eye_labels,
        "eye_labels_sha256": eye_sha,
        **result,
    }


def admission_text(record: Mapping[str, Any]) -> str:
    return json.dumps(record, indent=1, sort_keys=True) + "\n"


def command_evaluate(run_dir: Path, eye_path: Path | None) -> dict[str, Any]:
    """Measure and write ADMISSION.json. `eye_path` None is the explicit --no-eye-labels."""
    record = admission_record(run_dir, None if eye_path is None else _repo_path(eye_path))
    (run_dir / ADMISSION_FILE).write_text(admission_text(record), encoding="utf-8", newline="\n")
    return record


def verify_admission(run_dir: Path) -> tuple[dict[str, Any], str]:
    """ADMISSION.json as `decide.py` may trust it, and its sha256.

    The file is re-derived from the run directory - the sealed thresholds, the jobs, the ledger and
    the eye labels it names - and refused unless the re-derivation is byte-identical and T0 passed.
    """
    path = run_dir / ADMISSION_FILE
    if not path.is_file():
        raise CalibrationError(f"{path} does not exist - run `calibrate.py evaluate` first")
    text = path.read_text(encoding="utf-8")
    stored = json.loads(text)
    again = admission_record(run_dir, stored.get("eye_labels"))
    if admission_text(again) != text:
        differing = sorted(k for k in set(stored) | set(again) if stored.get(k) != again.get(k))
        raise CalibrationError(
            f"{path} is not what the sealed calibration in {run_dir} measures (differs in "
            f"{differing}) - an admission is re-derived, never trusted"
        )
    if again["metrics"]["T0"]["pass"] is not True:
        raise CalibrationError(
            f"{path}: T0 failed ({again['metrics']['T0']['without_verdict']} job(s) without a "
            "verdict) - calibration admits nothing"
        )
    return again, _sha(text)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("seal", "jobs", "evaluate"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--run-dir", required=True)
        if name == "jobs":
            cmd.add_argument("--snapshot", default=str(worklist.DEFAULT_SNAPSHOT))
            cmd.add_argument("--cache", default=str(worklist.DEFAULT_CACHE))
            cmd.add_argument("--t10", default=str(worklist.DEFAULT_T10))
            cmd.add_argument("--hero-moves", default=str(worklist.DEFAULT_HERO_MOVES))
        if name == "evaluate":
            eye = cmd.add_mutually_exclusive_group(required=True)
            eye.add_argument(
                "--eye-labels", help=f"W8's blinded tile labels (normally {labels.B4_LABELS})"
            )
            eye.add_argument(
                "--no-eye-labels",
                action="store_true",
                help="evaluate without eye labels: T-strict is then not evaluable (K2, H1 off)",
            )
    args = parser.parse_args(list(argv) if argv is not None else None)
    run_dir = Path(args.run_dir)
    if args.command == "seal":
        print(f"sealed {run_dir / THRESHOLDS_FILE}: sha256 {seal(run_dir)}")
        return 0
    if args.command == "jobs":
        sealed(run_dir)
        if (run_dir / LEDGER_FILE).exists():
            raise CalibrationError(
                f"{run_dir / LEDGER_FILE} exists - the C1 job list is fixed before the first call"
            )
        state = worklist.build_state(
            Path(args.snapshot), Path(args.cache), Path(args.hero_moves), Path(args.t10)
        )
        jobs = c1_jobs(state, labels.pilot_tiles(), labels.load_labelled())
        print(
            f"{len(jobs)} C1 jobs -> {run_dir / JOBS_FILE} (sha256 {vision.write_jobs(run_dir / JOBS_FILE, jobs)})"
        )
        return 0
    admission = command_evaluate(run_dir, None if args.no_eye_labels else Path(args.eye_labels))
    print(json.dumps({k: admission[k] for k in ("admitted", "metrics")}, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
