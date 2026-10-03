"""`paper publish`, `paper correct`, `paper register-video`: the clients of theo_publish.

Every call goes through remote.run_module (ssh + docker exec in ancient_nerds_api); the input
travels on stdin, credentials stay on the VPS. The input shapes are stream A's C4-C6, exactly:

    --dry-run|--apply            {version, request_id, writer, result}            (bundle.json)
    --correct [--dry-run]        {version, request_id, writer, corrections_append,
                                  report? + evidence? | report? + rewrite? |
                                  result? + dossier_request_id?}
    --register-video [--dry-run] {version, request_id, writer, youtube_id, title, published_at,
                                  evidence_timestamps, poster?}

theo_publish prints one JSON outcome (stream A's C8) and exits 0 ok, 1 a gate failed, 2
unusable input, 3 the row changed between read and write (nothing committed), 4 committed but
the re-read differs (side effects not run). Every write is preceded by its dry run; a write
mode that answers without JSON, times out or exits 4 is `RemoteOutcomeUnknown`: read the
journal before running it again. For an --apply and a --correct the error names the one
adoption procedure (`unknown_outcome_steps`): the newest theo_paper_publications row carries
the sha256 of the bytes theo_publish read, which publish_outcome.json (`bundle_sha256`) and
every corrections/<stamp>.json (`body_sha256`) record before the write; a committed publish or
republish is adopted by copying bundle.json to published_bundle.json by hand, never by
running the write again. The images a result references are uploaded (and verified
byte for byte) before the dry run, because the gate checks that they exist on the VPS; so is a
video's poster (owner decision 13), after a dry run without it has shown the video is new.

published_bundle.json is written only by a successful apply (a publish or a republish: a byte
copy of the bundle.json it sent). It is the published baseline a text correction is compared
with; bundle.json stays the scratch output of `paper bundle`. The studio never fills
`result.corrections`: theo_publish keeps the published log on a republish and appends
`corrections_append` (stream A's C5, owner question Q3).

A rewrite workspace (`paper pull TARGET --dossier-from RUN`, owner decisions 17 and 18) is
published only through `paper correct TARGET --republish`: its first republish also sends
`dossier_request_id` = RUN, so theo_publish stores RUN's dossier summary with TARGET and closes
the fresh run (stream A's C5). `paper publish` refuses such a workspace.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from pipeline.lyra.theo_citations import validate_paper_artifact
from pipeline.lyra.theo_publishing import EVIDENCE_ID_RE, YOUTUBE_ID_RE, poster_web_path
from pipeline.studio import config, remote
from pipeline.studio.errors import StudioError
from pipeline.studio.paper.bundle import WRITER, require_fresh_check, upload_names
from pipeline.studio.paper.numbering import build_paper
from pipeline.studio.paper.workspace import (
    PaperWorkspace,
    dossier_request_id,
    published_slug,
    read_json,
    read_meta,
    write_json,
)

MODULE = "pipeline.lyra.theo_publish"
DRY_RUN_TIMEOUT_S = 300
APPLY_TIMEOUT_S = 600
CORRECT_TIMEOUT_S = 600
VIDEO_TIMEOUT_S = 120
ENTRY_KEYS = frozenset({"text", "evidence_id"})


def outcome_of(result: remote.RemoteResult, *, write: bool) -> dict[str, Any]:
    """The JSON outcome; none from a write mode means the write may or may not have happened."""
    error: type[StudioError] = remote.RemoteOutcomeUnknown if write else remote.RemoteError
    unknown = (
        "; the write may have committed: read theo_paper_publications before running it again"
        if write
        else ""
    )
    try:
        outcome = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise error(
            f"theo_publish printed no JSON outcome (exit {result.returncode}): "
            f"{result.stderr[-800:]}{unknown}"
        ) from exc
    if not isinstance(outcome, dict) or "ok" not in outcome:
        raise error(f"theo_publish outcome has no 'ok': {outcome!r}{unknown}")
    return outcome


def _run(args: list[str], payload: bytes, timeout: int) -> tuple[int, dict[str, Any]]:
    """(exit code, outcome) of one theo_publish call."""
    result = remote.run_module(MODULE, args, stdin=payload, timeout=timeout)
    return result.returncode, outcome_of(result, write="--dry-run" not in args)


def require_ok(step: str, code: int, outcome: dict[str, Any]) -> None:
    """Map theo_publish's exit codes to what the operator has to do next.

    Exit 2-4 print {ok: false, error}; exit 0 and 1 print the PublishOutcome with its gates
    (stream A's C8)."""
    if code == 0 and outcome["ok"]:
        return
    if code == 2:
        raise StudioError(f"{step}: theo_publish refused the input: {outcome['error']}")
    if code == 3:
        raise StudioError(
            f"{step}: the row changed underneath; nothing was committed; re-run after `paper check`"
        )
    if code == 4:
        raise remote.RemoteOutcomeUnknown(
            f"{step}: committed but the re-read differs: inspect research_requests and "
            "theo_paper_publications; its side effects (IndexNow, Qdrant, the owner notice) did "
            "not run; do not run it again"
        )
    if code in (0, 1):
        failing = sorted(name for name, gate in outcome["gates"].items() if not gate["passed"])
        raise StudioError(f"{step} refused: failing gates {failing}: {outcome}")
    raise remote.RemoteOutcomeUnknown(f"{step}: theo_publish exited {code}: {outcome}")


def journal_query(request_id: str) -> str:
    """The read-only command that prints the newest theo_paper_publications row of a paper."""
    sql = (
        "SELECT id, action, slug, bundle_sha256, side_effects FROM theo_paper_publications "
        f"WHERE request_id = '{request_id}' ORDER BY id DESC LIMIT 1"
    )
    return (
        f'ssh {remote.SSH_HOST} "docker exec ancient_nerds_db psql -U ancient_map '
        f'-d ancient_map -c \\"{sql}\\""'
    )


def unknown_outcome_steps(
    request_id: str, sha256: str, *, sent_bundle: bool, first_publish: bool
) -> str:
    """The one adoption procedure after a write whose outcome is unknown (a timeout, exit 4,
    no JSON, an unexpected exit). theo_publish journals every committed write with the sha256
    of the exact bytes it read (theo_paper_publications.bundle_sha256, stream A; dry runs are
    not journalled), and the studio records that hash before the write (publish_outcome.json
    `bundle_sha256`, corrections/<stamp>.json `body_sha256`), so the newest journal row tells
    whether this write committed. `sent_bundle`: the write sent bundle.json's result (a
    publish or a --republish), whose published baseline is then copied by hand;
    `first_publish`: the episode needs the slug the row recorded."""
    steps = [
        f"read the newest journal row (read-only) first: {journal_query(request_id)}",
        f"if its bundle_sha256 is {sha256}, the write committed: never run it again",
    ]
    if sent_bundle:
        steps.append(
            "copy bundle.json (the bundle this write sent) byte for byte to "
            "published_bundle.json by hand, before any new `paper bundle`"
        )
    if first_publish:
        steps.append("`episode init --paper` then takes the row's slug as `--paper-slug`")
    steps.append(
        "side_effects NULL means IndexNow, Qdrant and the owner notice did not run: the "
        "nightly reindex covers Qdrant, report the missing notice to the owner"
    )
    steps.append(
        "if the newest row carries another sha256, nothing committed: run it again from the dry run"
    )
    return "; ".join(steps)


def _call(
    record: dict[str, Any],
    key: str,
    args: list[str],
    payload: bytes,
    timeout: int,
    path: Path,
    *,
    unknown: str | None = None,
) -> dict[str, Any]:
    """Run one call, journal it in `record` (written to `path`), then require success.

    `unknown` (a write only: `unknown_outcome_steps`) is added to a RemoteOutcomeUnknown, so
    the operator reads how to adopt a write that did commit instead of running it again."""
    try:
        code, record[key] = _run(args, payload, timeout)
        record[f"{key}_exit_code"] = code
        write_json(path, record)
        require_ok(f"theo_publish {' '.join(args)}", code, record[key])
    except remote.RemoteOutcomeUnknown as exc:
        if unknown is None:
            raise
        raise remote.RemoteOutcomeUnknown(f"{exc}. {unknown}") from exc
    return record[key]


def _upload_selected(ws: PaperWorkspace, names: list[str]) -> None:
    files = [ws.images_dir / "selected" / name for name in names]
    missing = [p.name for p in files if not p.exists()]
    if missing:
        raise StudioError(f"selected images missing locally: {missing}")
    remote.upload_research_images(ws.request_id, files)


def _fresh_bundle(ws: PaperWorkspace) -> tuple[bytes, dict[str, Any]]:
    raw = ws.require(ws.bundle, f"run `python -m pipeline.studio paper bundle {ws.request_id}`")
    payload = raw.read_bytes()
    bundle = json.loads(payload)
    if bundle["result"]["report"] != build_paper(ws).markdown:
        raise StudioError("bundle.json is stale (the paper changed); run `paper bundle` again")
    return payload, bundle


def _archive_outcome(ws: PaperWorkspace) -> None:
    """Keep the earlier record beside the new one: publish_outcome.<its at, colons removed>.json."""
    earlier = read_json(ws.publish_outcome, "")
    ws.publish_outcome.rename(ws.root / f"publish_outcome.{earlier['at'].replace(':', '')}.json")


def publish(ws: PaperWorkspace, *, dry_run: bool) -> dict[str, Any]:
    """Upload, dry-run, apply. A successful apply leaves published_bundle.json, a byte copy
    of the bundle it sent.

    A dry run that finds the row public (exit 0 or 1: A's status gate always carries
    `is_public`) stops with `paper correct` before its gate failures are reported, because a
    public paper changes only through a correction; that stop leaves publish_outcome.json
    untouched (the slug of a successful apply, or the bundle_sha256 of an apply whose outcome
    was unknown, which its adoption needs) and names the recorded slug when there is one; a
    row the founder route unpublished since (not public: slug and published_at are NULL again)
    is published again, and the earlier record is kept as publish_outcome.<at>.json (stream A
    keeps its corrections, videos and evidence ids through the `retention` gate). A rewrite
    workspace (dossier_from.json) is sent with `paper correct --republish` instead."""
    if ws.dossier_from.exists():
        raise StudioError(
            f"papers/{ws.request_id} rewrites the public paper {ws.request_id} from the dossier "
            f"of {dossier_request_id(ws)}: send it with "
            f"`python -m pipeline.studio paper correct {ws.request_id} --republish`"
        )
    earlier = published_slug(ws.publish_outcome)
    payload, bundle = _fresh_bundle(ws)
    _upload_selected(ws, upload_names(bundle["result"]))
    record: dict[str, Any] = {
        "bundle_sha256": hashlib.sha256(payload).hexdigest(),
        "at": datetime.now(UTC).isoformat(),
        "dry_run": None,
        "apply": None,
    }
    code, checked = _run(["--dry-run"], payload, DRY_RUN_TIMEOUT_S)
    record["dry_run"], record["dry_run_exit_code"] = checked, code
    status_known = code in (0, 1)  # A's status gate reports is_public in every gate outcome
    public = status_known and checked["gates"]["status"]["is_public"] is True
    if public:
        # publish_outcome.json stays as it is: a successful apply's record names the slug,
        # and the record of an apply whose outcome was unknown keeps the bundle_sha256 the
        # adoption procedure (unknown_outcome_steps) matches with the journal.
        if earlier is not None:
            raise StudioError(
                f"already published as /research/{earlier}: change it with `paper correct`"
            )
        raise StudioError(
            "the paper is already public: change it with `paper correct` (after an apply "
            "whose outcome was unknown, adopt it as that error said)"
        )
    if earlier is not None:
        if not status_known:
            require_ok("theo_publish --dry-run", code, checked)  # exit 2-4: always raises
        _archive_outcome(ws)
    write_json(ws.publish_outcome, record)
    require_ok("theo_publish --dry-run", code, checked)
    if dry_run:
        return record
    steps = unknown_outcome_steps(
        ws.request_id, record["bundle_sha256"], sent_bundle=True, first_publish=True
    )
    _call(record, "apply", ["--apply"], payload, APPLY_TIMEOUT_S, ws.publish_outcome, unknown=steps)
    ws.published_bundle.write_bytes(payload)
    return record


def correction_entries(items: Any, on: date | None = None) -> list[dict[str, Any]]:
    """[{text, evidence_id?}] -> corrections_append entries, all dated `on` (default: today UTC)."""
    if not isinstance(items, list) or not items:
        raise StudioError("a correction needs at least one entry [{text, evidence_id?}]")
    day = (on or datetime.now(UTC).date()).isoformat()
    entries: list[dict[str, Any]] = []
    for n, item in enumerate(items, start=1):
        if not isinstance(item, dict) or "text" not in item or not set(item) <= ENTRY_KEYS:
            raise StudioError(f"correction {n}: keys must be text and optionally evidence_id")
        if not isinstance(item["text"], str) or not item["text"].strip():
            raise StudioError(f"correction {n}: a correction needs its text")
        entry: dict[str, Any] = {"date": day, "text": item["text"]}
        evidence_id = item.get("evidence_id")
        if evidence_id is not None:
            if not isinstance(evidence_id, str) or not EVIDENCE_ID_RE.fullmatch(evidence_id):
                raise StudioError(f"correction {n}: {evidence_id!r} is not an evidence id (ev-NN)")
            entry["evidence_id"] = evidence_id
        entries.append(entry)
    return entries


def _published_bundle(ws: PaperWorkspace) -> dict[str, Any]:
    if not ws.published_bundle.exists():
        raise StudioError(
            "no published bundle in this workspace (published_bundle.json is written by a "
            "successful `paper publish` or `paper correct --republish`)"
        )
    return json.loads(ws.published_bundle.read_text(encoding="utf-8"))


def correct(
    ws: PaperWorkspace,
    entries: list[dict[str, Any]],
    *,
    with_report: bool = False,
    republish: bool = False,
    report: str | None = None,
    rewrite: bool = False,
) -> dict[str, Any]:
    """Append corrections to a published paper (stream A's C5); at most one of the modes.

    - neither: only the corrections log grows;
    - with_report: the re-checked paper's report and evidence replace the published ones. A
      correction cannot change the images, the title or the card description (theo_publish
      keeps the stored ones), so the image set, title and card description must equal the
      published baseline's (published_bundle.json; the images are on the VPS already); a
      changed title or card is a --republish;
    - republish: the checked workspace's bundle.json `result` replaces the published result
      (a full rewrite of a public paper, e.g. one of the legacy M3 papers); its apply makes
      that bundle the new published_bundle.json. In a rewrite workspace (dossier_from.json,
      owner decisions 17 and 18) the first republish, the one before any published_bundle.json
      exists, also sends `dossier_request_id` = the fresh run: theo_publish stores that run's
      dossier with this paper and closes the run (stream A's C5), so a later republish of the
      same workspace sends none;
    - report: the full markdown (`# Title` ... `## References`) of a paper that has no studio
      workspace check (a legacy M3 paper, starting from the `content` field of
      GET /api/v1/research/{slug}); evidence stays untouched. `rewrite` (only here) marks a
      full Claude rewrite: theo_publish then stores this correction's writer, so the page
      shows the Claude disclosure line, and sends the `paper_published` owner notice of a
      republish (side effect `notify`, owner decisions 18 and 21); a small fix such as the
      Roswell date goes without it and sends no notice.
    Every mode dry-runs first and applies only when the dry run passes. Every record in
    corrections/ carries `body_sha256`, the sha256 of the exact bytes sent: theo_publish
    journals that hash (theo_paper_publications.bundle_sha256), so a write whose outcome is
    unknown can be matched to its journal row (`unknown_outcome_steps`).
    """
    if sum([with_report, republish, report is not None]) > 1:
        raise StudioError("choose one of --with-report, --republish, --report-file")
    if rewrite and report is None:
        raise StudioError(
            "--rewrite goes with --report-file: it marks the full rewrite of a paper "
            "without a studio workspace check (a studio rewrite is --republish)"
        )
    payload: dict[str, Any] = {
        "version": 1,
        "request_id": ws.request_id,
        "writer": WRITER,
        "corrections_append": entries,
    }
    sent_bundle: bytes | None = None
    if with_report:
        published = _published_bundle(ws)
        _check, built = require_fresh_check(ws)
        now = sorted(e["web_path"] for e in built.probative_images)
        before = sorted(e["web_path"] for e in published["result"]["probative_images"])
        if now != before:
            raise StudioError(
                "a correction cannot change the images; the image set differs from the "
                "published bundle"
            )
        meta = read_meta(ws)
        if (
            meta["title"].strip() != published["result"]["title"]
            or meta["card_description"].strip() != published["result"]["card_description"]
        ):
            raise StudioError(
                "a correction cannot change the title or card description; use --republish"
            )
        payload["report"] = built.markdown
        payload["evidence"] = read_json(ws.evidence, "")
    elif republish:
        sent_bundle, bundle = _fresh_bundle(ws)
        _upload_selected(ws, upload_names(bundle["result"]))
        payload["result"] = bundle["result"]
        if ws.dossier_from.exists() and not ws.published_bundle.exists():
            payload["dossier_request_id"] = dossier_request_id(ws)
    elif report is not None:
        audit = validate_paper_artifact(report)
        if not audit["passed"]:
            raise StudioError(f"the report fails validate_paper_artifact: {audit['issues']}")
        payload["report"] = report
        if rewrite:
            payload["rewrite"] = True
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = ws.root / "corrections" / f"{stamp}.json"
    record: dict[str, Any] = {
        "payload": payload,
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "dry_run": None,
        "apply": None,
    }
    _call(record, "dry_run", ["--correct", "--dry-run"], body, CORRECT_TIMEOUT_S, path)
    steps = unknown_outcome_steps(
        ws.request_id,
        record["body_sha256"],
        sent_bundle=sent_bundle is not None,
        first_publish=False,
    )
    _call(record, "apply", ["--correct"], body, CORRECT_TIMEOUT_S, path, unknown=steps)
    if sent_bundle is not None:
        ws.published_bundle.write_bytes(sent_bundle)
    return record


def video_payload(
    request_id: str,
    youtube_id: str,
    title: str,
    published_at: str,
    evidence_timestamps: dict[str, int],
    *,
    with_poster: bool = False,
) -> dict[str, Any]:
    """The --register-video input (stream A's C6), validated as theo_publish validates it.

    `with_poster` adds `poster`, our own studio thumbnail at the one web path
    theo_publishing.poster_web_path gives it (owner decision 13); upload it first. The title
    is the one the video was uploaded with, so it obeys YouTube's rule (package.check_title).
    """
    from pipeline.studio.package import check_title

    config.check_request_id(request_id)
    if not YOUTUBE_ID_RE.fullmatch(youtube_id):
        raise StudioError(f"{youtube_id!r} is not a YouTube video id")
    try:
        stamp = datetime.fromisoformat(published_at)
    except ValueError as exc:
        raise StudioError("published_at must be ISO 8601 with a timezone") from exc
    if stamp.tzinfo is None:
        raise StudioError("published_at must carry a timezone (e.g. 2026-10-01T18:00:00+00:00)")
    if not isinstance(evidence_timestamps, dict):
        raise StudioError("evidence timestamps must be a JSON object {ev-NN: seconds}")
    bad = {
        k: v
        for k, v in evidence_timestamps.items()
        if not EVIDENCE_ID_RE.fullmatch(k) or isinstance(v, bool) or not isinstance(v, int) or v < 0
    }
    if bad:
        raise StudioError(f"evidence timestamps must map ev-NN to whole seconds >= 0: {bad}")
    check_title(title)
    payload: dict[str, Any] = {
        "version": 1,
        "request_id": request_id,
        "writer": WRITER,
        "youtube_id": youtube_id,
        "title": title,
        "published_at": published_at,
        "evidence_timestamps": evidence_timestamps,
    }
    if with_poster:
        payload["poster"] = poster_web_path(request_id, youtube_id)
    return payload


def register_video(payload: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    """One --register-video call (dry run or apply); raises unless it passed."""
    args = ["--register-video", "--dry-run"] if dry_run else ["--register-video"]
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    code, outcome = _run(args, body, VIDEO_TIMEOUT_S)
    require_ok(f"theo_publish {' '.join(args)}", code, outcome)
    return outcome


def check_poster(jpeg: Path) -> None:
    """A poster is an existing JPEG file."""
    from PIL import Image, UnidentifiedImageError

    if not jpeg.is_file():
        raise StudioError(f"poster {jpeg} does not exist")
    try:
        with Image.open(jpeg) as img:
            kind = img.format
    except UnidentifiedImageError as exc:
        raise StudioError(f"poster {jpeg} is not an image") from exc
    if kind != "JPEG":
        raise StudioError(f"poster {jpeg} is {kind}, not a JPEG")


def upload_poster(request_id: str, youtube_id: str, jpeg: Path) -> None:
    """Upload `jpeg` under the name poster_web_path gives it (research-images/<request_id>/
    video_<youtube_id>.jpg), verified byte for byte by remote.upload_research_images."""
    check_poster(jpeg)
    name = PurePosixPath(poster_web_path(request_id, youtube_id)).name
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / name
        shutil.copyfile(jpeg, copy)
        remote.upload_research_images(request_id, [copy])


def prepare_video(
    request_id: str,
    youtube_id: str,
    title: str,
    published_at: str,
    evidence_timestamps: dict[str, int],
    poster: Path | None,
) -> dict[str, Any]:
    """The dry-run-proven --register-video payload, its poster on the VPS (owner decision 13).

    1. a dry run without the poster: status, evidence_refs and duplicate pass, so the upload
       that follows can never replace the poster of a video the paper already shows;
    2. with a poster: the JPEG, uploaded as video_<youtube_id>.jpg and verified;
    3. a dry run with the poster (theo_publish's `images` gate finds the file).
    The caller applies the returned payload with `register_video(payload, dry_run=False)`;
    `episode register-youtube` writes the ledger in between. The payload and the poster file
    are checked before the first production call.
    """
    bare = video_payload(request_id, youtube_id, title, published_at, evidence_timestamps)
    if poster is not None:
        check_poster(poster)
    register_video(bare, dry_run=True)
    if poster is None:
        return bare
    upload_poster(request_id, youtube_id, poster)
    full = video_payload(
        request_id, youtube_id, title, published_at, evidence_timestamps, with_poster=True
    )
    register_video(full, dry_run=True)
    return full
