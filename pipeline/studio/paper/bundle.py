"""`paper bundle`: the publish bundle theo_publish reads on stdin (stream A's C4, spec 2.6 / 3.2).

    {"version": 1, "request_id": str, "writer": WRITER,
     "result": {report, published_report (== report), title, card_description,
                probative_images, hero_image, published_hero_image (== hero_image),
                published_block_ids: [], quality_score, audit, evidence, corrections: [],
                writer}}

Exactly these four top-level keys: theo_publish refuses any other (exit 2); a first publish
credits published_by = 'Theo', a republish keeps the stored publisher (spec 3.7, owner decision
19). `corrections` is always []: on a republish theo_publish keeps the published log itself
(stream A's C5). The files `paper publish` uploads first are derived from the
result itself (`upload_names`). Built only from a passing check_report.json whose paper_sha256,
evidence_sha256 and meta_sha256 match the paper as it builds now, evidence.json and
paper_meta.json; anything else means a file changed after the check, and the publish gate
(which re-checks shape, verdicts and anchors, never the quotes) would not catch it.
"""

from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any

from pipeline.studio.errors import StudioError
from pipeline.studio.paper.gates import sha256_text
from pipeline.studio.paper.numbering import BuiltPaper, build_paper
from pipeline.studio.paper.workspace import PaperWorkspace, read_json

WRITER = {
    "model": "claude-opus-5-5",
    "tool": "claude-code",
    "research_model": "MiniMax-M3",
    "published": "automatic",
    "human_review": False,
}
#: The probative_images keys every stored paper carries (theo-worker-api map, 415 items).
PROBATIVE_KEYS = (
    "title",
    "artist",
    "keyword",
    "license",
    "license_url",
    "verified",
    "web_path",
    "image_path",
    "source_url",
    "source_name",
    "description",
    "rationale",
    "search_query",
    "paragraph_text",
    "paragraph_index",
    "section_heading",
)


def require_fresh_check(ws: PaperWorkspace) -> tuple[dict[str, Any], BuiltPaper]:
    report = read_json(
        ws.check_report, f"run `python -m pipeline.studio paper check {ws.request_id}`"
    )
    if not report["passed"]:
        failing = [g["name"] for g in report["gates"] if not g["passed"]]
        raise StudioError(f"check_report.json has failing gates {failing}; fix and re-run check")
    built = build_paper(ws)
    if sha256_text(built.markdown) != report["paper_sha256"]:
        raise StudioError("the paper changed after the last check; run `paper check` again")
    if sha256_text(ws.evidence.read_text(encoding="utf-8")) != report["evidence_sha256"]:
        raise StudioError("evidence.json changed after the last check; run `paper check` again")
    if sha256_text(ws.meta.read_text(encoding="utf-8")) != report["meta_sha256"]:
        raise StudioError("paper_meta.json changed after the last check; run `paper check` again")
    return report, built


def upload_names(result: dict[str, Any]) -> list[str]:
    """The files under images/selected/ a result references: every probative image and the hero."""
    paths = [e["web_path"] for e in result["probative_images"]]
    hero = result["hero_image"]
    if hero is not None:
        paths.extend([hero["src"], hero["web_path"]])
    return sorted({PurePosixPath(p).name for p in paths})


def build_bundle(ws: PaperWorkspace) -> dict[str, Any]:
    report, built = require_fresh_check(ws)
    meta = read_json(ws.meta, "")
    evidence = read_json(ws.evidence, "")
    hero = report["hero_image"]
    result = {
        "report": built.markdown,
        "published_report": built.markdown,
        "title": meta["title"].strip(),
        "card_description": meta["card_description"].strip(),
        "probative_images": [{k: e[k] for k in PROBATIVE_KEYS} for e in built.probative_images],
        "hero_image": hero,
        "published_hero_image": hero,
        "published_block_ids": [],
        "quality_score": report["quality_score"],
        "audit": report["audit"],
        "evidence": evidence,
        "corrections": [],
        "writer": WRITER,
    }
    return {"version": 1, "request_id": ws.request_id, "writer": WRITER, "result": result}


def write_bundle(ws: PaperWorkspace) -> dict[str, Any]:
    bundle = build_bundle(ws)
    ws.bundle.write_text(json.dumps(bundle, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return bundle
