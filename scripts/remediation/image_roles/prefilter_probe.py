"""D118 (owner, 2026-11-06): the prefilter tested at Opus before its tier is decided.

image-roles-v2 failed the prefilter on Sonnet low (photo agreement 0.9033 of 0.92, depicts-capable
recall 0.848 of 0.98; 44 of its 300 pictures wrong on one of the two), worse than Haiku in v1. The
owner's choice was "test Opus first (about five answers) or drop the prefilter". The probe asks
**the same five questions** - v2's exported prompts and picture bytes, byte for byte - of Opus as a
candidate-model trial (`roles.candidate_model`): the role stays registered on Sonnet, every answer is
stamped Opus and recorded with `--candidate-model`. Its measure is the one v2 was measured with,
against v2's own fixed gold, beside Sonnet's answers to the same questions; on top, the 44 cases
Sonnet failed are listed one by one with both answers.

The probe decides nothing by itself: it is the evidence for the tier move that a commit applies
(`roles.APPLIED_ESCALATIONS`, the move v2's verdict named) - or for the owner, if Opus fails too. A
role that is moved is calibrated again on the clean gold of D117 before its first answer.

    prefilter_probe.py export  --source image-roles-v2 --run-dir P --handoff H
    prefilter_probe.py brief   --run-dir P --handoff H --batch-id pre-0001
    run.py check-answer        --run-dir P --handoff H --stage image-prefilter --batch-id B ...
    opus_handoff.py validate   --dir H
    prefilter_probe.py measure --run-dir P --handoff H          -> P/PREFILTER.jsonl, P/PROBE.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _path in (_HERE.parents[3], _HERE.parents[1]):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import roles as RO  # noqa: E402
from served_image import state as ST  # noqa: E402

from image_roles import calibrate as CAL  # noqa: E402
from image_roles import prefilter as PF  # noqa: E402
from image_roles import stage as SG  # noqa: E402

CANDIDATE = "claude-opus-5-5"
SOURCE_FILE = "PROBE_SOURCE.json"
PROBE_FILE = "PROBE.json"


class ProbeError(ST.StateError):
    """The probe cannot take this step. Nothing is half-written."""


def _source(run: Path) -> Path:
    path = run / SOURCE_FILE
    if not path.is_file():
        raise ProbeError(f"{path} does not exist - run `export` first")
    return Path(json.loads(path.read_text(encoding="utf-8"))["source"])


def export(source: Path, run: Path, handoff: Path) -> dict[str, Any]:
    """The source calibration's prefilter questions and their picture bytes, unchanged, into a new
    handoff. Refused unless the source's questions are the ones its export recorded and every
    picture still has the bytes its question showed."""
    record = json.loads((source / PF.SPEC.export_file).read_text(encoding="utf-8"))
    if ST.file_sha256(source / PF.SPEC.questions_file) != record["questions_sha256"]:
        raise ProbeError(f"{source / PF.SPEC.questions_file} is not the file its export recorded")
    _, gold_at = CAL.fixed_gold(source)
    questions = list(SG.load_questions(source, PF.SPEC).values())
    old_handoff = Path(record["handoff"])
    pictures: dict[str, bytes] = {}
    for question in questions:
        for image in question.images:
            data = (old_handoff / image.path).read_bytes()
            if hashlib.sha256(data).hexdigest() != image.sha256:
                raise ProbeError(f"{old_handoff / image.path} is not the picture v2 showed")
            pictures[image.name] = data
    ST.write_text_once(
        run / SOURCE_FILE,
        ST.json_text(
            {
                "source": str(source),
                "source_questions_sha256": record["questions_sha256"],
                "source_gold_fixed_at": gold_at,
                "candidate_model": CANDIDATE,
                "decision": "D118",
            }
        ),
    )
    summary = SG.export(run, handoff, PF.SPEC, questions, pictures)
    if summary["questions_sha256"] != record["questions_sha256"]:
        raise ProbeError("the probe's questions are not the source's byte for byte")
    return summary


def brief(run: Path, handoff: Path, batch_id: str) -> str:
    return SG.brief(run, handoff, PF.SPEC, batch_id, candidate_model=CANDIDATE)


def failed_cases(
    cases: Sequence[Mapping[str, Any]], judged: Mapping[str, Mapping[str, Any]]
) -> list[str]:
    """The case ids a judge got wrong on either measure of `calibrate.measure_prefilter`: photo
    versus non-photo, or a depicts-capable picture that does not survive."""
    out = []
    for c in cases:
        if c["role"] != "image_prefilter":
            continue
        truth, row = c["truth"], judged[c["case_id"]]
        photo = (truth in CAL.PHOTO_KINDS) != (row["kind"] in CAL.PHOTO_KINDS)
        dropped = truth in PF.SURVIVING_KINDS and not row["survives"]
        if photo or dropped:
            out.append(c["case_id"])
    return out


def compare(
    cases: Sequence[Mapping[str, Any]],
    probe: Sequence[Mapping[str, Any]],
    before: Sequence[Mapping[str, Any]],
    cp: Callable[[int, int], tuple[float, float]],
) -> dict[str, Any]:
    """The probe's metrics beside the earlier model's on the same cases, and every case either got
    wrong with both answers."""
    mine = [c for c in cases if c["role"] == "image_prefilter"]
    now = {r["site_id"]: r for r in PF.judged(probe)}
    then = {r["site_id"]: r for r in PF.judged(before)}
    failed_now, failed_then = set(failed_cases(mine, now)), set(failed_cases(mine, then))
    truth = {c["case_id"]: c for c in mine}

    def row(case_id: str) -> dict[str, Any]:
        return {
            "case_id": case_id,
            "file": truth[case_id]["file"],
            "truth": truth[case_id]["truth"],
            "probe": {k: now[case_id][k] for k in ("kind", "usable", "survives")},
            "before": {k: then[case_id][k] for k in ("kind", "usable", "survives")},
        }

    return {
        "probe": CAL.measure_prefilter(mine, probe, cp),
        "before": CAL.measure_prefilter(mine, before, cp),
        "before_failed": len(failed_then),
        "probe_failed": len(failed_now),
        "fixed": len(failed_then - failed_now),
        "broken": len(failed_now - failed_then),
        "cases": [row(i) for i in sorted(failed_now | failed_then)],
    }


def measure(
    run: Path, handoff: Path, *, cp: Callable[[int, int], tuple[float, float]] | None = None
) -> dict[str, Any]:
    """Import the trial's answers (each stamped by the candidate) and write PROBE.json once."""
    source = _source(run)
    cases, _ = CAL.fixed_gold(source)
    SG.import_answers(run, handoff, PF.SPEC, candidate_model=CANDIDATE)
    probe = SG.read_results(run, PF.SPEC)
    before = SG.read_results(source, PF.SPEC)
    result = {
        "decision": "D118",
        "candidate_model": CANDIDATE,
        "source": source.name,
        "before_model": sorted({r["model"] for r in before}),
        "probe_model": sorted({r["model"] for r in probe}),
        "answers": len(probe),
        **compare(cases, probe, before, cp or CAL.clopper_pearson()),
    }
    ST.write_text_once(run / PROBE_FILE, ST.json_text(result))
    return {k: v for k, v in result.items() if k != "cases"}


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(prog="image_roles/prefilter_probe.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("export", "brief", "measure"):
        command = sub.add_parser(name)
        command.add_argument("--run-dir", required=True, type=Path)
        command.add_argument("--handoff", required=True, type=Path)
    sub.choices["export"].add_argument("--source", required=True, type=Path)
    sub.choices["brief"].add_argument("--batch-id", required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "export":
            payload: Any = export(args.source, args.run_dir, args.handoff)
        elif args.command == "brief":
            print(brief(args.run_dir, args.handoff, args.batch_id))
            return 0
        else:
            payload = measure(args.run_dir, args.handoff)
    except (ST.StateError, RO.RoleError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
