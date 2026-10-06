"""`paper bundle`: the publish bundle theo_publish reads on stdin (stream A's C4, spec 2.6 / 3.2).

    {"version": 1, "request_id": str, "writer": WRITER,
     "result": {report, published_report (== report), title, card_description,
                probative_images, hero_image, published_hero_image (== hero_image),
                published_block_ids: [], quality_score, audit, evidence, corrections: [],
                writer, sentence_evidence}}

`sentence_evidence` is the audit artefact of
docs/reports/theo-paper-defects-2026-10-04.md: per cited sentence, the
reference numbers of its paragraph and the quote `claim_support.locate_support`
found in that reference's fetched text, with character offsets. It is stored so
a reader can check which source supports which sentence without redoing the
research. The markers stay paragraph-level (1,136 of 1,136 references cited, 0
of 853 paragraphs uncited in the 31-paper corpus) and the rendered report is
byte-identical with and without it.

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
import re
from pathlib import PurePosixPath
from typing import Any

from pipeline.studio.errors import StudioError
from pipeline.studio.paper.claims import source_texts
from pipeline.studio.paper.evidence_card import build_evidence_card
from pipeline.studio.paper.gates import sha256_text, texts_by_number
from pipeline.studio.paper.numbering import BuiltPaper, build_paper
from pipeline.studio.paper.workspace import (
    PaperWorkspace,
    load_dossier,
    read_json,
    read_meta,
)

#: The writer record every bundle carries. A stamp is never a guess: since 2026-10-03 the
#: studio runs on MiniMax Code (`mcode`, model `MiniMax-M3.1-Flash-Preview`, owner decision
#: 2026-10-03), so a new paper names the model that wrote it. Papers published earlier keep
#: the writer they were published with.
WRITER = {
    "model": "MiniMax-M3.1-Flash-Preview",
    "tool": "mcode",
    "research_model": "MiniMax-M3",
    "published": "automatic",
    "human_review": False,
}

#: A model name as it is written in a stamp. The dashes belong to the name, not to a
#: word boundary: `MiniMax-M3.1-Flash-Preview` is one token.
_MODEL_RE = re.compile(r"MiniMax-[A-Za-z0-9.]+(?:-[A-Za-z0-9.]+)*")


def writer_for(dossier: Any) -> dict[str, Any]:
    """The writer record with `research_model` naming who actually did the research.

    A stamp that is wrong is worse than no stamp: the four papers of the current
    campaign were researched and written in the writing session, and the constant
    still named the pipeline's model. The dossier says who researched it, in
    `manifest.research.researcher`; a dossier that does not name a model keeps the
    constant, which is never invented.
    """
    data = getattr(dossier, "data", dossier) or {}
    research = (data.get("manifest") or {}).get("research") or {}
    named = _MODEL_RE.search(str(research.get("researcher") or ""))
    if named is None:
        return dict(WRITER)
    return {**WRITER, "research_model": named.group(0)}


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
    evidence = ws.require(ws.evidence, "restore it and run `paper check` again")
    if sha256_text(evidence.read_text(encoding="utf-8")) != report["evidence_sha256"]:
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
    meta = read_meta(ws)
    evidence = read_json(ws.evidence, "")
    hero = report["hero_image"]
    dossier = load_dossier(ws)
    writer = writer_for(dossier)
    texts = texts_by_number(built, source_texts(ws, dossier))
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
        "writer": writer,
        # Per cited sentence, the reference numbers of its paragraph and the
        # quote locate_support found for it in that reference's fetched text,
        # with character offsets. The audit artefact of
        # docs/reports/theo-paper-defects-2026-10-04.md: a reader of
        # result_json can see which source supports which sentence without
        # redoing the research. The markers stay paragraph-level and the
        # rendered report is byte-identical with and without this key.
        "sentence_evidence": build_evidence_card(built.markdown, texts),
    }
    return {"version": 1, "request_id": ws.request_id, "writer": writer, "result": result}


def write_bundle(ws: PaperWorkspace) -> dict[str, Any]:
    bundle = build_bundle(ws)
    ws.bundle.write_text(json.dumps(bundle, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return bundle
