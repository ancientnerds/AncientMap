"""Publish, correct and video-link Claude-written Theo papers (spec 2.6, 2.7). API image.

Run from a local Claude session over ssh, so production credentials never
leave the VPS:

    ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_publish --dry-run < bundle.json
    ... --apply < bundle.json
    ... --correct [--dry-run] < correction.json   (a log entry, a text correction, or a full republish via
                                                     `result`, optionally from a fresh run's `dossier_request_id`)
    ... --register-video [--dry-run] < video.json   (an optional `poster`: our own thumbnail, uploaded first)

Prints a PublishOutcome as JSON (contract C8). Exit codes: 0 ok, 1 a gate
failed, 2 unusable input, 3 the row changed between read and write (nothing
committed), 4 committed but the re-read row differs (side effects not run).

Sending the same bytes again is a no-op: the outcome answers
`already_applied: true` with the journal id of the write that already
committed, and nothing is written twice. So a retry after a timeout or an
exit 4 can simply be re-run, and a driver that sends twice cannot append a
second copy of a correction to the page.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from typing import BinaryIO, TextIO

from pipeline.database import get_session
from pipeline.lyra.theo_publishing import (
    PublishConflictError,
    PublishInputError,
    PublishVerificationError,
    correct_paper,
    publish_paper,
    register_video,
)

EXIT_OK = 0
EXIT_GATES = 1
EXIT_INPUT = 2
EXIT_CONFLICT = 3
EXIT_UNVERIFIED = 4

#: action -> (required top-level keys, optional top-level keys) (contracts C4-C6)
ENVELOPES: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "publish": (frozenset({"version", "request_id", "writer", "result"}), frozenset()),
    "correct": (
        frozenset({"version", "request_id", "writer", "corrections_append"}),
        frozenset({"report", "evidence", "result", "rewrite", "dossier_request_id"}),
    ),
    "register_video": (
        frozenset(
            {
                "version",
                "request_id",
                "writer",
                "youtube_id",
                "title",
                "published_at",
                "evidence_timestamps",
            }
        ),
        frozenset({"poster"}),
    ),
}


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.lyra.theo_publish",
        description="Publish, correct or video-link a Claude-written Theo paper (input on stdin).",
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true", help="publish the bundle")
    modes.add_argument(
        "--correct", action="store_true", help="apply a correction to a public paper"
    )
    modes.add_argument("--register-video", action="store_true", help="append a YouTube video")
    parser.add_argument("--dry-run", action="store_true", help="run every gate, write nothing")
    args = parser.parse_args(argv)
    if args.apply and args.dry_run:
        parser.error("--apply and --dry-run exclude each other")
    if not (args.apply or args.correct or args.register_video or args.dry_run):
        parser.error("choose one of --dry-run, --apply, --correct, --register-video")
    if args.correct:
        args.action = "correct"
    elif args.register_video:
        args.action = "register_video"
    else:
        args.action = "publish"
    return args


def _is_canonical_uuid(value: object) -> bool:
    """The one id spelling C4 accepts: str(uuid.UUID(value)) == value (lowercase, hyphenated)."""
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except ValueError:
        return False


def _check_envelope(payload: object, action: str) -> dict:
    """The top-level keys and ids of the input; value types are the gates' business."""
    if not isinstance(payload, dict):
        raise PublishInputError("the input must be a JSON object")
    required, optional = ENVELOPES[action]
    missing = sorted(required - set(payload))
    unknown = sorted(set(payload) - required - optional)
    if missing:
        raise PublishInputError(f"missing keys: {missing}")
    if unknown:
        raise PublishInputError(f"unknown keys: {unknown}")
    # type() too: True == 1 and 1.0 == 1 in Python.
    if type(payload["version"]) is not int or payload["version"] != 1:
        raise PublishInputError(f"unsupported version {payload['version']!r} (expected 1)")
    # One spelling only (C4): the image paths, the slug suffix and the journal use
    # the id as given, and theo_dossier exports under the canonical lowercase form.
    rid = payload["request_id"]
    if not _is_canonical_uuid(rid):
        raise PublishInputError(f"request_id is not a canonical lowercase UUID: {rid!r}")
    if "result" in payload and not isinstance(payload["result"], dict):
        raise PublishInputError("result must be a JSON object")
    if action == "correct" and "result" in payload and {"report", "evidence"} & set(payload):
        raise PublishInputError("result (a full republish) excludes report and evidence")
    # `rewrite` marks a text correction as a Claude rewrite (C5, from `paper correct
    # --report-file FILE --rewrite`): only JSON true, only with `report` and without
    # `evidence`, never with `result` (a full republish sets the writer anyway).
    if "rewrite" in payload and (
        payload["rewrite"] is not True
        or "report" not in payload
        or "evidence" in payload
        or "result" in payload
    ):
        raise PublishInputError(
            "rewrite needs report without evidence, excludes result and can only be true"
        )
    # `dossier_request_id` names the fresh Theo run a full republish was written
    # from (C5, owner decisions 17 and 18): only with `result`, spelled like request_id.
    if "dossier_request_id" in payload and not (
        "result" in payload and _is_canonical_uuid(payload["dossier_request_id"])
    ):
        raise PublishInputError("dossier_request_id needs result and a canonical lowercase UUID")
    return payload


def _refuse_constant(name: str) -> None:
    """json.loads' parse_constant: NaN and Infinity are not JSON and Postgres jsonb refuses
    them, so they would fail only after the commit (exit 4) or as an uncaught DataError."""
    raise PublishInputError(
        f"the input carries {name}, which is not JSON (Postgres jsonb refuses it)"
    )


def _error(out: TextIO, message: str, code: int) -> int:
    out.write(json.dumps({"ok": False, "error": message}) + "\n")
    return code


def main(
    argv: list[str] | None = None, *, stdin: BinaryIO | None = None, stdout: TextIO | None = None
) -> int:
    args = _parse(argv)
    out = stdout or sys.stdout
    raw = (stdin or sys.stdin.buffer).read()
    try:
        payload = _check_envelope(
            json.loads(raw.decode("utf-8"), parse_constant=_refuse_constant), args.action
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _error(out, f"the input is not UTF-8 JSON: {exc}", EXIT_INPUT)
    except PublishInputError as exc:
        return _error(out, str(exc), EXIT_INPUT)
    bundle_sha256 = hashlib.sha256(raw).hexdigest()
    request_id = payload["request_id"]
    try:
        with get_session() as session:
            if args.action == "publish":
                outcome = publish_paper(
                    session,
                    request_id,
                    payload["result"],
                    writer=payload["writer"],
                    dry_run=args.dry_run,
                    bundle_sha256=bundle_sha256,
                )
            elif args.action == "correct":
                outcome = correct_paper(
                    session, request_id, payload, bundle_sha256=bundle_sha256, dry_run=args.dry_run
                )
            else:
                outcome = register_video(
                    session, request_id, payload, bundle_sha256=bundle_sha256, dry_run=args.dry_run
                )
    except PublishInputError as exc:
        return _error(out, str(exc), EXIT_INPUT)
    except PublishConflictError as exc:
        return _error(out, str(exc), EXIT_CONFLICT)
    except PublishVerificationError as exc:
        return _error(out, str(exc), EXIT_UNVERIFIED)
    out.write(json.dumps(outcome.to_dict(), ensure_ascii=False, indent=2) + "\n")
    return EXIT_OK if outcome.ok else EXIT_GATES


if __name__ == "__main__":
    raise SystemExit(main())
