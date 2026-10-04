"""Dossier export for the Claude write (spec 2.8). Runs in the API container.

    ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_dossier list
    ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_dossier export <id> [--texts cited|all] > dossier.json.gz

`export` writes gzip'd JSON (contract C3) to stdout. Runs without a 'dossier'
manifest (the full-pipeline runs since the corpus started, e.g. 95fa3798)
export too, from their per-stage artifacts, with `"legacy": true`.
Exit codes: 0 ok, 1 no or incomplete dossier, 2 bad request id.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import uuid
from collections import Counter
from typing import Any, BinaryIO, TextIO

from sqlalchemy import text

from pipeline.database import get_session
from pipeline.lyra.dossier_manifest import (
    DOSSIER_VERSION,
    cited_source_ids,
    moderated_source_ids,
)
from pipeline.lyra.training_corpus import best_archive_rows_in, classify_archive_row

EXPORT_VERSION = 1
TEXTS_MODES = ("cited", "all")

_LIST_SQL = text("""
    SELECT id::text AS id, question, status, is_batch, created_at, completed_at, result_json
    FROM research_requests
    WHERE status = 'researched'
    ORDER BY completed_at ASC
""")
_REQUEST_SQL = text("""
    SELECT id::text AS id, question, status, is_batch, user_id, created_at, completed_at,
           llm_calls, total_tokens, duration_ms
    FROM research_requests
    WHERE id = :id
""")
_ARTIFACTS_SQL = text("""
    SELECT DISTINCT ON (kind, ref) kind, ref, payload
    FROM research_artifacts
    WHERE request_id = :id AND kind = ANY(:kinds)
    ORDER BY kind, ref, created_at DESC, id DESC
""")
# The kinds the export ships (specialist_analyses is corpus material, not writer input).
_DOSSIER_REQUIRED = (
    "moderated",
    "synthesis",
    "debate",
    "angle_findings",
    "citation_registry",
    "image_candidate_pool",
)
_LEGACY_REQUIRED = (
    "moderated",
    "synthesis",
    "debate",
    "angle_findings",
    "citation_registry",
    "paper_final",
)
_EXPORT_KINDS = ["dossier", *_DOSSIER_REQUIRED, "paper_final"]
_SOURCE_KEYS = (
    "id",
    "url",
    "title",
    "domain",
    "reliability_tier",
    "doi",
    "authors",
    "venue",
    "date",
    "license",
    "source_api",
)


class DossierExportError(RuntimeError):
    """The request has no dossier, or its dossier is incomplete."""


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def list_researched(session: Any) -> list[dict]:
    """Researched rows with their dossier summary, oldest first (the writing queue)."""
    rows = session.execute(_LIST_SQL).fetchall()
    return [
        {
            "id": row.id,
            "question": row.question,
            "status": row.status,
            "is_batch": bool(row.is_batch),
            "created_at": _iso(row.created_at),
            "completed_at": _iso(row.completed_at),
            "dossier": json.loads(row.result_json)["dossier"],
        }
        for row in rows
    ]


def _export_source(source: dict, archive: dict | None) -> dict:
    entry = {key: source[key] for key in _SOURCE_KEYS}
    entry["archive"] = (
        None
        if archive is None
        else {
            "content_type": archive["content_type"],
            "text_chars": archive["text_chars"],
            "fetched_at": _iso(archive["fetched_at"]),
            "tdm_opt_out": archive["tdm_opt_out"],
        }
    )
    return entry


def _legacy_manifest(
    row: Any, parts: dict, angles: list[dict], images: dict, archive: dict[str, dict]
) -> dict:
    """What a manifest would say for a run that predates the DossierHandler."""
    moderated = parts["moderated"][""]
    cited = moderated_source_ids(moderated)
    classes = Counter(classify_archive_row(archive.get(source_id)) for source_id in cited)
    return {
        "version": DOSSIER_VERSION,
        "legacy": True,
        "request_id": row.id,
        "question": row.question,
        "created_at": None,
        "angle_ids": [angle["id"] for angle in angles],
        "counts": {
            "angles": len(angles),
            "findings": sum(len(angle["findings"]) for angle in angles),
            "sources": len(parts["citation_registry"][""]["sources"]),
            "final_claims": len(moderated.get("final_claims") or []),
            "revised_claims": len(moderated.get("revised_claims") or []),
            "speculative_claims": len(moderated.get("speculative_claims") or []),
            "images": sum(len(pool) for pool in images.values()),
        },
        "kinds": sorted(parts),
        "archive": {
            "cited_sources": len(cited),
            "full_text": classes["full_text"],
            "abstract_only": classes["abstract_only"],
            "missing": classes["missing"],
            "tdm_reserved": classes["tdm_reserved"],
            "failures": [],
            "duration_s": 0.0,
            "timed_out": False,
        },
        "research": {
            "llm_calls": row.llm_calls,
            "total_tokens": row.total_tokens,
            "duration_s": round(row.duration_ms / 1000, 1) if row.duration_ms is not None else None,
        },
    }


def build_export(session: Any, request_id: str, *, texts: str) -> dict:
    """The export bundle of one request (contract C3). texts: 'cited' or 'all'."""
    if texts not in TEXTS_MODES:
        raise ValueError(f"texts must be 'cited' or 'all', got {texts!r}")
    row = session.execute(_REQUEST_SQL, {"id": request_id}).fetchone()
    if row is None:
        raise DossierExportError(f"research request {request_id} does not exist")
    parts: dict[str, dict[str, Any]] = {}
    for artifact in session.execute(
        _ARTIFACTS_SQL, {"id": request_id, "kinds": _EXPORT_KINDS}
    ).fetchall():
        parts.setdefault(artifact.kind, {})[artifact.ref] = artifact.payload

    legacy = "dossier" not in parts
    required = _LEGACY_REQUIRED if legacy else _DOSSIER_REQUIRED
    missing = [kind for kind in required if kind not in parts]
    if missing:
        label = (
            "has no dossier and its per-stage artifacts are incomplete"
            if legacy
            else "has an incomplete dossier"
        )
        raise DossierExportError(f"{request_id} {label}: missing {missing}")

    angle_rows = parts["angle_findings"]
    angle_ids = sorted(angle_rows) if legacy else parts["dossier"][""]["angle_ids"]
    absent = [angle_id for angle_id in angle_ids if angle_id not in angle_rows]
    if absent:
        raise DossierExportError(f"{request_id}: angle_findings rows missing for {absent}")
    angles = [
        {key: angle_rows[angle_id][key] for key in ("id", "topic", "description", "findings")}
        for angle_id in angle_ids
    ]
    if legacy:
        if "image_candidate_pool" not in parts["paper_final"][""]:
            raise DossierExportError(f"{request_id}: paper_final carries no image_candidate_pool")
        images = parts["paper_final"][""]["image_candidate_pool"]
    else:
        images = parts["image_candidate_pool"][""]

    moderated = parts["moderated"][""]
    registry = parts["citation_registry"][""]
    source_ids = [source["id"] for source in registry["sources"]]
    archive = best_archive_rows_in(session, source_ids, with_text=False)
    manifest = (
        _legacy_manifest(row, parts, angles, images, archive) if legacy else parts["dossier"][""]
    )
    text_ids = cited_source_ids(moderated, angles) if texts == "cited" else source_ids
    text_rows = best_archive_rows_in(session, text_ids, with_text=True)
    return {
        "version": EXPORT_VERSION,
        "texts_mode": texts,
        "request": {
            "id": row.id,
            "question": row.question,
            "status": row.status,
            "is_batch": bool(row.is_batch),
            "user_id": row.user_id,
            "created_at": _iso(row.created_at),
            "completed_at": _iso(row.completed_at),
        },
        "manifest": manifest,
        "moderated": moderated,
        "synthesis": parts["synthesis"][""],
        "debate": parts["debate"][""],
        "angles": angles,
        "sources": [
            _export_source(source, archive.get(source["id"])) for source in registry["sources"]
        ],
        "texts": {
            source_id: entry["full_text"]
            for source_id, entry in text_rows.items()
            if entry["full_text"] and not entry["tdm_opt_out"]
        },
        "images": images,
    }


def main(
    argv: list[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stdout_bytes: BinaryIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.lyra.theo_dossier",
        description="Theo dossiers for the Claude write.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="researched rows with their dossier summary (JSON)")
    export = commands.add_parser("export", help="gzip'd JSON export bundle on stdout")
    export.add_argument("request_id")
    export.add_argument("--texts", choices=TEXTS_MODES, default="cited")
    args = parser.parse_args(argv)

    if args.command == "list":
        with get_session() as session:
            rows = list_researched(session)
        (stdout or sys.stdout).write(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
        return 0

    try:
        # Canonical lowercase: research_requests.id is a uuid column and matches
        # any spelling, but research_artifacts.request_id is TEXT and matches
        # only this one.
        request_id = str(uuid.UUID(args.request_id))
    except ValueError:
        print(f"not a request id: {args.request_id!r}", file=sys.stderr)
        return 2
    try:
        with get_session() as session:
            bundle = build_export(session, request_id, texts=args.texts)
    except DossierExportError as exc:
        print(f"dossier export failed: {exc}", file=sys.stderr)
        return 1
    data = gzip.compress(json.dumps(bundle, ensure_ascii=False).encode("utf-8"), mtime=0)
    (stdout_bytes or sys.stdout.buffer).write(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
