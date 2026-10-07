#!/usr/bin/env python3
"""paper24_seed: build a paper workspace from research done in this session.

The owner's 24 topics do not need a Theo run. The server's publish gate
(`theo_publishing.publish_paper`) asks for a row with status `researched` or
`completed`, for the bundle's own gates and for the images on disk - it never
reads a dossier. The studio's ten local gates read the workspace, and the
three dossier-dependent ones (references, specifics, support) read the archived
source texts. So a research stage in this session, writing the workspace files
`paper pull` would have written, produces the same gated paper at zero calls
against the account's five-hour quota.

    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/paper24_seed.py REQUEST research.json

research.json is what this session actually fetched and read:

    {
      "question": "...",
      "status": "researched",          # the row's state when the paper goes out
      "is_batch": false,
      "user_id": "...",
      "angles":  [{"id", "topic", "description",
                   "findings": [{"claim", "confidence", "source_ids"}]}],
      "claims":   [{"claim", "confidence", "source_ids", "notes"}],
      "synthesis": {"consensus_claims": [...], "convergent_findings": [...],
                    "cross_angle_connections": [...], "contested_claims": [...],
                    "contradictions": [...], "open_questions": [...]},
      "sources":  [{"id", "url", "title", "domain", "reliability_tier", "doi",
                    "authors", "venue", "date", "license", "source_api",
                    "content_type", "fetched_at", "text"}]
    }

Every number the manifest carries is counted from that file; nothing is invented.
The provenance is recorded as what happened: `research.researcher` names the
model that did the research, `llm_calls` and `total_tokens` are 0 because no
Theo run was made, and `debate.rounds` is 0 because no debate stage ran. The
`archive` counters come from `training_corpus.classify_archive_row`, the same
classifier the export uses, over the archive rows this file describes.

Refuses (never repairs): a source id that is not 12 lowercase hex, a duplicate
id, a source without text (it would carry no marker the claim gate can confirm),
a claim or finding citing an unknown source, a file without an angle or a claim,
and a workspace that already holds a published paper.
"""

from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline.lyra.dossier_manifest import DOSSIER_VERSION, cited_source_ids
from pipeline.lyra.theo_publishing import SOURCE_ID_RE
from pipeline.lyra.training_corpus import classify_archive_row
from pipeline.studio import config
from pipeline.studio.errors import StudioError
from pipeline.studio.paper import pull
from pipeline.studio.paper.workspace import Dossier, PaperWorkspace, parse_dossier, workspace

EXPORT_VERSION = 1
DEFAULT_CONTENT_TYPE = "text/html"
#: The artifact kinds a research stage in this session produces. The list is what
#: `manifest.kinds` documents; the six are the same six the DossierHandler writes,
#: except that `specialist_analyses` (corpus material) has no writer here.
LOCAL_KINDS = (
    "moderated",
    "synthesis",
    "debate",
    "angle_findings",
    "citation_registry",
    "image_candidate_pool",
)
_TEXT_KEYS = ("url", "title", "text")
_LIST_KEYS = ("angles", "claims", "sources")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StudioError(message)


def _text(value: Any, where: str) -> str:
    _require(isinstance(value, str) and value.strip(), f"{where} must be a non-empty string")
    return str(value).strip()


def _source_ids(value: Any, known: set[str], where: str) -> list[str]:
    _require(isinstance(value, list) and value, f"{where}: source_ids must be a non-empty list")
    ids = [_text(sid, f"{where}: source id") for sid in value]
    unknown = [sid for sid in ids if sid not in known]
    _require(not unknown, f"{where} cites sources the file does not carry: {unknown}")
    return list(dict.fromkeys(ids))


def _archive_row(source: dict[str, Any], text: str) -> dict[str, Any]:
    """The archive row shape `classify_archive_row` and the brief's status read."""
    return {
        "content_type": _text(
            source.get("content_type", DEFAULT_CONTENT_TYPE), "source content_type"
        ),
        "text_chars": len(text),
        "fetched_at": _text(source.get("fetched_at"), "source fetched_at"),
        "tdm_opt_out": bool(source.get("tdm_opt_out", False)),
    }


def _sources(raw: Any) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, dict[str, Any]]]:
    """(export sources, texts, archive rows) with every id and text validated."""
    _require(isinstance(raw, list) and raw, "the research file carries no sources")
    entries: list[dict[str, Any]] = []
    texts: dict[str, str] = {}
    archive: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(raw):
        where = f"sources[{index}]"
        _require(isinstance(source, dict), f"{where} must be an object")
        sid = _text(source.get("id"), f"{where} id")
        _require(
            bool(SOURCE_ID_RE.fullmatch(sid)),
            f"{where} id {sid!r} is not 12 lowercase hex characters",
        )
        _require(sid not in texts, f"{where} repeats the source id {sid}")
        for key in _TEXT_KEYS:
            _text(source.get(key), f"{where} {key}")
        text = str(source["text"])
        _require(len(text.strip()) >= 200, f"{where} text is too short to carry a claim")
        entry = {
            "id": sid,
            "url": str(source["url"]).strip(),
            "title": " ".join(str(source["title"]).split()),
            "domain": _text(source.get("domain") or _domain(source["url"]), f"{where} domain"),
            "reliability_tier": int(source.get("reliability_tier", 2)),
            "doi": str(source.get("doi") or ""),
            "authors": list(source.get("authors") or []),
            "venue": str(source.get("venue") or ""),
            "date": str(source.get("date") or ""),
            "license": str(source.get("license") or ""),
            "source_api": str(source.get("source_api") or "web"),
        }
        entries.append(entry)
        texts[sid] = text
        archive[sid] = _archive_row(source, text)
    return entries, texts, archive


def _domain(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).netloc or "unknown"


def _angles(raw: Any, known: set[str]) -> list[dict[str, Any]]:
    _require(isinstance(raw, list) and raw, "the research file carries no angle")
    angles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, angle in enumerate(raw):
        where = f"angles[{index}]"
        _require(isinstance(angle, dict), f"{where} must be an object")
        aid = _text(angle.get("id"), f"{where} id")
        _require(aid not in seen, f"{where} repeats the angle id {aid}")
        seen.add(aid)
        findings = angle.get("findings") or []
        _require(isinstance(findings, list) and findings, f"{where} carries no finding")
        angles.append(
            {
                "id": aid,
                "topic": _text(angle.get("topic"), f"{where} topic"),
                "description": str(angle.get("description") or ""),
                "findings": [
                    {
                        "claim": _text(f.get("claim"), f"{where} finding claim"),
                        "confidence": str(f.get("confidence") or "medium"),
                        "source_ids": _source_ids(f.get("source_ids"), known, f"{where} finding"),
                    }
                    for f in findings
                ],
            }
        )
    return angles


def _claims(raw: Any, known: set[str]) -> list[dict[str, Any]]:
    _require(isinstance(raw, list) and raw, "the research file carries no claim")
    return [
        {
            "claim": _text(c.get("claim"), f"claims[{index}] claim"),
            "confidence": str(c.get("confidence") or "medium"),
            "source_ids": _source_ids(c.get("source_ids"), known, f"claims[{index}]"),
            "notes": str(c.get("notes") or ""),
        }
        for index, c in enumerate(raw)
    ]


def build_dossier(research: dict[str, Any], request_id: str) -> dict[str, Any]:
    """The export bundle of a local research stage (contract C3, version 1)."""
    for key in _LIST_KEYS + ("question",):
        _require(key in research, f"the research file lacks {key!r}")
    request_id = config.check_request_id(request_id)
    # A seeded dossier describes research this session did, so the model that did it is
    # a fact about the file, not an optional field. An empty value reaches the writer
    # stamp as `manifest.research.researcher == ""`, `writer_for()` takes its pipeline
    # fallback there, and the paper is published naming a model nobody used to research
    # it — which happened on three papers of the campaign of 2026-10-06/07 (topics 7, 8
    # and 10). Refused here rather than repaired: a research file that forgot to say who
    # did the work is the writer's file to complete, and guessing would write a stamp.
    _require(
        bool(str(research.get("researcher") or "").strip()),
        "the research file lacks a 'researcher': name the model that did the research, "
        "so the paper's writer stamp cannot fall back to the pipeline's model",
    )
    question = _text(research["question"], "question")
    sources, texts, archive = _sources(research["sources"])
    known = {s["id"] for s in sources}
    angles = _angles(research["angles"], known)
    claims = _claims(research["claims"], known)
    moderated = {"final_claims": claims, "revised_claims": [], "speculative_claims": []}
    cited = cited_source_ids(moderated, angles)
    classes = Counter(classify_archive_row(archive[sid]) for sid in cited)
    now = datetime.now(UTC)
    synthesis = research.get("synthesis") or {}
    _require(isinstance(synthesis, dict), "synthesis must be an object")
    manifest = {
        "version": DOSSIER_VERSION,
        "request_id": request_id,
        "question": question,
        "created_at": now.isoformat(),
        "angle_ids": [a["id"] for a in angles],
        "counts": {
            "angles": len(angles),
            "findings": sum(len(a["findings"]) for a in angles),
            "sources": len(sources),
            "final_claims": len(claims),
            "revised_claims": 0,
            "speculative_claims": 0,
            "images": 0,
        },
        "kinds": list(LOCAL_KINDS),
        "archive": {
            "cited_sources": len(cited),
            "full_text": classes["full_text"],
            "abstract_only": classes["abstract_only"],
            "missing": classes["missing"],
            "tdm_reserved": classes["tdm_reserved"],
            "failures": [],
            "duration_s": float(research.get("research_seconds") or 0.0),
            "timed_out": False,
        },
        "research": {
            "llm_calls": 0,
            "total_tokens": 0,
            "duration_s": float(research.get("research_seconds") or 0.0),
            "researcher": str(research.get("researcher") or ""),
            "stage": "mini_max_code_session",
        },
    }
    return {
        "version": EXPORT_VERSION,
        "texts_mode": "all",
        "request": {
            "id": request_id,
            "question": question,
            "status": str(research.get("status") or "researched"),
            "is_batch": bool(research.get("is_batch", False)),
            "user_id": str(research.get("user_id") or ""),
            "created_at": str(research.get("created_at") or now.isoformat()),
            "completed_at": now.isoformat(),
        },
        "manifest": manifest,
        "moderated": moderated,
        # The export's synthesis artifact is the wrapper `{"synthesis": {...}}` the
        # orchestrator's synthesis handler writes; the research file carries the inner object.
        "synthesis": {"synthesis": synthesis},
        "debate": {"rounds": 0, "challenges": [], "defenses": []},
        "angles": angles,
        "sources": [{**s, "archive": archive[s["id"]]} for s in sources],
        "texts": texts,
        "images": {},
    }


def seed(ws: PaperWorkspace, research: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    """Write dossier.json.gz, the archived texts and brief.md; return what it wrote.

    The brief is rendered before anything is written, so a dossier that cannot
    render leaves the workspace as it was.
    """
    if ws.published_bundle.exists():
        raise StudioError(
            f"papers/{ws.request_id} holds a paper this studio published: a published "
            "paper changes through `paper correct`, not through a new dossier"
        )
    if ws.dossier_gz.exists() and not force:
        raise StudioError(
            f"{ws.dossier_gz} exists: pass --force to replace it (a workspace's dossier is "
            "its research record)"
        )
    bundle = build_dossier(research, ws.request_id)
    dossier = Dossier(bundle)
    brief = pull.render_brief(dossier)
    payload = gzip.compress(json.dumps(bundle, ensure_ascii=False).encode("utf-8"), mtime=0)
    ws.root.mkdir(parents=True, exist_ok=True)
    ws.dossier_gz.write_bytes(payload)
    pull.write_texts(ws, dossier)
    ws.brief.write_text(brief, encoding="utf-8")
    check = parse_dossier(ws.dossier_gz.read_bytes())
    _register(ws.request_id)
    return {
        "workspace": str(ws.root),
        "request_id": check.request_id,
        "sources": len(bundle["sources"]),
        "text_chars": sum(len(t) for t in bundle["texts"].values()),
        "claims": len(bundle["moderated"]["final_claims"]),
        "angles": len(bundle["angles"]),
        "citable": len(check.citable_ids),
        "bytes": len(payload),
    }


def _register(request_id: str) -> None:
    """Record the workspace with the campaign driver, so `scan` and `ledger` see it.

    The driver's list is called `pulled` because that is where a workspace used to
    come from; a session-seeded workspace is the same thing from that moment on.
    The driver stays the only writer of its state file.
    """
    spec = importlib.util.spec_from_file_location("paper24", Path(__file__).with_name("paper24.py"))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.register_pulled(request_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python scripts/paper24_seed.py",
        description="Seed a paper workspace from research done in this session.",
    )
    parser.add_argument("request_id")
    parser.add_argument("research", type=Path, help="the research JSON this session produced")
    parser.add_argument(
        "--force", action="store_true", help="replace an existing dossier in the workspace"
    )
    args = parser.parse_args(argv)
    try:
        research = json.loads(args.research.read_text(encoding="utf-8"))
        if not isinstance(research, dict):
            raise StudioError("the research file must be a JSON object")
        summary = seed(workspace(args.request_id), research, force=args.force)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read the research file: {exc}", file=sys.stderr)
        return 2
    except StudioError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
