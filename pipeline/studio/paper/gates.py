"""`paper check`: the deterministic gates of spec 3.4 and the quality_score they produce.

Pure functions over the built paper, the dossier and Claude's files; `run_check` wires them
and writes check_report.json. A paper is publishable only when every gate passes.

 1 artifact    validate_paper_artifact(report) passes (theo_citations)
 2 structure   1-2 hook paragraphs under the title (no heading), 3-6 investigation sections,
               the three fixed sections, References, in order; every heading preceded and
               followed by a blank line; 5,000-7,500 prose words
   meta        title and card description follow the house rules
 3 references  every [N] resolves in sources.json and every source id is in the dossier
 4 specifics   every person/date/measurement/quote/title/institution of a cited paragraph is
               found in the archived texts of the sources that paragraph cites (a
               TDM-reserved source: the text the claim check read live, claims.source_texts)
 5 coherence   every multi-word title term appears in the prose paragraphs (the title
               line itself does not count); 0 numeric conflicts
               (the claim check's coherence task)
 6 evidence    evidence.json validates (evidence.py): the publish gate's own rule
               (theo_publishing.check_evidence: shape, `supported` only, anchors), then every
               quote verbatim in its source's archived text or, for a TDM-reserved source,
               the live text the claim check saved (claims.source_texts)
   page_anchors the paper page's own resolver finds every #ev-NN on the served HTML (the
               page half of stream A's check_evidence_anchors)
 7 claims      every claim-check task answered and `supported` (claims.py)
 8 images      every embedded image checked meaningful/weak, licence + attribution + source
               URL + caption, file present; the paper embeds exactly the selected images;
               every content section carries at least one image
 9 hero        hero_picker.pick_hero_image found a banner among the checked images
10 quality     quality_score, passed only when 1-9 pass and quality_gate_passed agrees
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from pipeline.lyra.coherence_pass import check_title_terms_in_body, extract_title_terms
from pipeline.lyra.hallucination_gate import extract_specifics, verify_against_pack
from pipeline.lyra.hero_picker import HERO_MIN_WIDTH, pick_hero_image
from pipeline.lyra.quality_gate import (
    citation_coverage_score,
    quality_gate_passed,
    reference_integrity_score,
)
from pipeline.lyra.text_sentences import split_sentences
from pipeline.lyra.theo_citations import split_artifact, validate_paper_artifact
from pipeline.lyra.theo_image_captions import images_per_section
from pipeline.studio.paper.anchors import MARKER_RE, paragraphs
from pipeline.studio.paper.claims import ClaimStatus, claim_status, source_texts
from pipeline.studio.paper.evidence import PAGE_PREFIX, evidence_problems
from pipeline.studio.paper.numbering import BuiltPaper, number
from pipeline.studio.paper.workspace import (
    Dossier,
    PaperWorkspace,
    load_dossier,
    read_json,
    read_meta,
    write_json,
)
from pipeline.utils.card_provenance import text_sha256 as sha256_text

WORD_MIN = 5000
WORD_MAX = 7500
FIXED_SECTIONS = ("Connecting the Dots", "The Other Side", "What We Actually Know")
# Owner decision 2026-10-04: 3-6 investigation sections, not 2-4. The old cap
# bound 14 of the 31 live papers and 4 of them had a single investigation
# section, which left the image budget nowhere to go. 6-9 sections at the 5,000
# word floor is ~550-830 words per section, the current median is 634.
INVESTIGATIONS = (3, 6)
# One image per section is the hard rule; four is the target and is reported, not
# enforced (the measured loss is dominated by rejected candidates).
IMAGES_MIN_PER_SECTION = 1
IMAGES_TARGET_PER_SECTION = 4
HOOK_PARAGRAPHS = (1, 2)
TITLE_MAX_CHARS = 80
TITLE_WORDS = (4, 12)
CARD_MAX_CHARS = 400
QUESTION_STEMS = ("what if", "could they", "are there", "is it possible")
BADGE = "Claim-checked"
_CITATION_RE = re.compile(r"\[(\d+)\]")
_H2_LINE_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_HEADING_LINE_RE = re.compile(r"#{1,6}\s")


@dataclass
class Gate:
    name: str
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


def _plain(text: str) -> str:
    """Paragraph text without citation markers, whitespace collapsed."""
    return " ".join(MARKER_RE.sub(" ", text).split())


def prose_word_count(report: str) -> int:
    return sum(len(_plain(p.text).split()) for p in paragraphs(report))


def gate_artifact(report: str) -> Gate:
    audit = validate_paper_artifact(report)
    return Gate("artifact", bool(audit["passed"]), {"audit": audit})


def gate_structure(report: str) -> Gate:
    prose, _heading, _refs = split_artifact(report)
    h2 = _H2_LINE_RE.findall(report)
    problems: list[str] = []
    if not h2 or h2[-1] != "References":
        problems.append("the last h2 must be 'References'")
    body = h2[:-1] if h2 and h2[-1] == "References" else h2
    if tuple(body[-3:]) != FIXED_SECTIONS:
        problems.append(f"the last three sections must be {list(FIXED_SECTIONS)}, got {body[-3:]}")
    investigations = body[:-3]
    if any(t in FIXED_SECTIONS or t == "References" for t in investigations):
        problems.append("a fixed section appears twice or out of order")
    if not INVESTIGATIONS[0] <= len(investigations) <= INVESTIGATIONS[1]:
        problems.append(
            f"need {INVESTIGATIONS[0]} to {INVESTIGATIONS[1]} investigation sections, "
            f"got {len(investigations)}"
        )
    hook = [p for p in paragraphs(report) if p.section == ""]
    if not HOOK_PARAGRAPHS[0] <= len(hook) <= HOOK_PARAGRAPHS[1]:
        problems.append(
            f"the paper opens with {len(hook)} hook paragraphs before the first ## heading "
            f"(needs {HOOK_PARAGRAPHS[0]} to {HOOK_PARAGRAPHS[1]})"
        )
    for block in prose.split("\n\n"):
        lines = block.strip().splitlines()
        if lines and lines[0].startswith("#") and len(lines) > 1:
            problems.append(f"heading {lines[0]!r} is not followed by a blank line")
        # A heading under a prose line in the same block: markdown still renders it, but
        # report_paragraphs (blank-line blocks) reads it as part of the paragraph above.
        problems.extend(
            f"heading {line!r} is not preceded by a blank line"
            for line in lines[1:]
            if _HEADING_LINE_RE.match(line)
        )
    words = prose_word_count(report)
    if not WORD_MIN <= words <= WORD_MAX:
        problems.append(f"{words} prose words; the house range is {WORD_MIN}-{WORD_MAX}")
    return Gate(
        "structure",
        not problems,
        {
            "problems": problems,
            "sections": h2,
            "investigations": len(investigations),
            "hook_paragraphs": len(hook),
            "word_count": words,
        },
    )


def gate_meta(meta: Any, question: str) -> Gate:
    problems: list[str] = []
    if not isinstance(meta, dict) or set(meta) != {"title", "card_description"}:
        return Gate(
            "meta", False, {"problems": ["paper_meta.json must be {title, card_description}"]}
        )
    title = str(meta["title"]).strip()
    card = str(meta["card_description"]).strip()
    words = len(title.split())
    if not TITLE_WORDS[0] <= words <= TITLE_WORDS[1]:
        problems.append(f"title has {words} words (needs {TITLE_WORDS[0]}-{TITLE_WORDS[1]})")
    if len(title) > TITLE_MAX_CHARS:
        problems.append(f"title is {len(title)} characters (max {TITLE_MAX_CHARS})")
    if any(ch in title for ch in '?:—–"“”'):
        problems.append("title must not contain ? : dashes or quotes")
    if title.lower().startswith(QUESTION_STEMS):
        problems.append("title starts with a question stem")
    if title.lower().rstrip("?. ") == question.lower().rstrip("?. "):
        problems.append("title echoes the research question")
    if not card or len(card) > CARD_MAX_CHARS:
        problems.append(f"card_description must be 1 to {CARD_MAX_CHARS} characters")
    elif len(split_sentences(card)) > 3:
        problems.append("card_description has more than three sentences")
    if any(tok in card for tok in ("[", "](", "#", "*")):
        problems.append("card_description must be plain text (no citations, no markdown)")
    return Gate("meta", not problems, {"problems": problems})


def gate_references(report: str, sources_rows: list[dict[str, Any]], dossier: Dossier) -> Gate:
    prose, _h, _r = split_artifact(report)
    numbers = {int(n) for n in _CITATION_RE.findall(prose)}
    table = {row["n"]: row["source_id"] for row in sources_rows}
    unresolved = sorted(numbers - set(table))
    unknown = sorted(sid for sid in table.values() if sid not in dossier.sources)
    return Gate(
        "references",
        not unresolved and not unknown,
        {"unresolved_numbers": unresolved, "unknown_source_ids": unknown},
    )


def gate_specifics(
    report: str, sources_rows: list[dict[str, Any]], dossier: Dossier, texts: dict[str, str]
) -> Gate:
    """Gate 4 against `texts` (claims.source_texts: the archived texts plus the live texts of
    the TDM-reserved sources the claim check read)."""
    table = {row["n"]: row["source_id"] for row in sources_rows}
    failing: list[dict[str, Any]] = []
    uncited: list[dict[str, Any]] = []
    for para in paragraphs(report):
        sids = list(
            dict.fromkeys(table[int(n)] for n in _CITATION_RE.findall(para.text) if int(n) in table)
        )
        specifics = extract_specifics(_plain(para.text))
        if not specifics:
            continue
        if not sids:
            uncited.append({"paragraph": para.index, "specifics": [s.text for s in specifics]})
            continue
        pack = "\n".join(texts.get(sid, "") for sid in sids)
        titles = {sid: dossier.cited_source(sid) for sid in sids}
        unsupported = verify_against_pack(specifics, pack, titles, dossier.question)
        if unsupported:
            failing.append(
                {
                    "paragraph": para.index,
                    "section": para.section,
                    "sources": sids,
                    "unmatched": [f"{s.kind}: {s.text}" for s in unsupported],
                }
            )
    unmatched = sum(len(f["unmatched"]) for f in failing)
    return Gate(
        "specifics",
        not failing,
        {"unmatched_in_cited_paragraphs": unmatched, "failing": failing, "uncited": uncited},
    )


def gate_coherence(title: str, report: str, status: ClaimStatus | None) -> Gate:
    """Title terms are looked up in the prose paragraphs only: paper.md opens with the
    `# <title>` line itself (numbering.compose), which would otherwise define every term."""
    body = "\n".join(_plain(p.text) for p in paragraphs(report))
    terms = extract_title_terms(title)
    undefined = [t for t, ok in check_title_terms_in_body(terms, body).items() if not ok]
    conflicts = status.coherence_conflicts if status is not None else 0
    problems = []
    if undefined:
        problems.append(f"title terms missing from the body: {undefined}")
    if status is None:
        problems.append("numeric coherence not checked (claim check incomplete)")
    elif conflicts:
        problems.append(f"{conflicts} numeric conflict(s) found by the claim check")
    return Gate(
        "coherence",
        not problems,
        {"problems": problems, "undefined_title_terms": undefined, "high_conflicts": conflicts},
    )


def gate_images(ws: PaperWorkspace, report: str, placed: list[dict[str, Any]]) -> Gate:
    problems: list[str] = []
    for entry in placed:
        name = entry["file"]
        if not (ws.images_dir / "selected" / name).exists():
            problems.append(f"{name}: file missing from images/selected/")
        if not entry["license"].strip() or not entry["source_url"].strip():
            problems.append(f"{name}: licence or source URL missing")
        if not entry["artist"].strip() and not entry["source_name"].strip():
            problems.append(f"{name}: attribution missing")
        if not entry["description"].strip():
            problems.append(f"{name}: caption missing")
    embedded = report.count("![")
    if embedded != len(placed):
        problems.append(f"report embeds {embedded} images, images-import selected {len(placed)}")
    # Owner decision 2026-10-04: one image per section is the hard floor, four is
    # the target. Measured on the 31 live papers before the rule existed: 109 of
    # 189 sections carried no image, the three fixed tail sections 76 of 93.
    # A total count cannot see that, so the floor is checked per section.
    coverage = images_per_section(report)
    without = [name for name, count in coverage.items() if count < IMAGES_MIN_PER_SECTION]
    if without:
        problems.append(
            f"sections without {IMAGES_MIN_PER_SECTION} image: {without} "
            f"(the opportunities in images/opportunities.json must name every section)"
        )
    return Gate(
        "images",
        not problems,
        {
            "problems": problems,
            "embedded": len(placed),
            "meaningful": sum(1 for e in placed if e["verified"]),
            "weak": sum(1 for e in placed if not e["verified"]),
            "images_per_section": coverage,
            "sections_without_image": without,
        },
    )


def pick_hero(title: str, placed: list[dict[str, Any]]) -> dict[str, Any] | None:
    """hero_picker's choice, with the sizes it cannot read locally applied up front.

    pick_hero_image ranks every image at least HERO_MIN_WIDTH wide above every narrower one,
    reading widths from the repo's public/data. The workspace images live elsewhere, so the
    same ranking is applied here from the measured widths: only the wide images are offered
    when any exist.
    """
    wide = [e for e in placed if e["width"] >= HERO_MIN_WIDTH]
    return pick_hero_image(title, wide or placed)


def gate_hero(title: str, placed: list[dict[str, Any]]) -> tuple[Gate, dict[str, Any] | None]:
    hero = pick_hero(title, placed)
    if hero is None:
        return Gate("hero", False, {"problems": ["no checked image to use as the banner"]}), None
    return Gate("hero", True, {"hero": hero}), hero


def _debate_rounds(dossier: Dossier) -> int:
    rounds = dossier.data["debate"].get("rounds", 0)
    return len(rounds) if isinstance(rounds, list) else int(rounds or 0)


def quality_score(
    gates: list[Gate],
    audit: dict[str, Any],
    built: BuiltPaper,
    dossier: Dossier,
    status: ClaimStatus | None,
) -> dict[str, Any]:
    by = {g.name: g for g in gates}
    structure = by["structure"]
    sections = structure.details["sections"]
    fixed_present = sum(1 for s in FIXED_SECTIONS if s in sections)
    investigations = structure.details["investigations"]
    n_sources = len(built.registry.sources)
    counts = dossier.data["manifest"]["counts"]
    archive = dossier.data["manifest"]["archive"]
    finals = int(counts["final_claims"])
    share = archive["full_text"] / archive["cited_sources"] if archive["cited_sources"] else 0.0
    metrics = {
        "citation_coverage": citation_coverage_score(audit),
        "reference_integrity": reference_integrity_score(audit),
        "section_completeness": 20
        if structure.passed
        else round(15 * fixed_present / 3) + (5 if 2 <= investigations <= 4 else 0),
        "source_diversity": 15
        if n_sources >= 20
        else 12
        if n_sources >= 10
        else 8
        if n_sources >= 5
        else 2 * n_sources,
        "research_depth": min(
            20,
            min(8, 2 * int(counts["angles"]))
            + (6 if finals >= 20 else 4 if finals >= 10 else 2 if finals >= 5 else 0)
            + min(3, _debate_rounds(dossier))
            + round(3 * share),
        ),
    }
    hallucination_final = by["specifics"].details["unmatched_in_cited_paragraphs"]
    conflicts = by["coherence"].details["high_conflicts"]
    undefined = len(by["coherence"].details["undefined_title_terms"])
    failures = {
        "audit_passed": bool(audit["passed"]),
        "invalid_markers": len(audit["invalid_markers"]),
        "orphaned_refs": len(audit["orphaned_refs"]),
        "uncited_paragraphs": audit["uncited_paragraphs"],
        "placeholder_markers": len(audit["placeholder_markers"]),
        "language_bleed": len(audit["language_bleed"]),
        "non_numeric_markers": len(audit["non_numeric_markers"]),
        "hallucination_final": hallucination_final,
        "high_contradictions": conflicts,
        "undefined_title_terms": undefined,
        "numeric_conflicts": conflicts,
        "high_numeric_conflicts": conflicts,
    }
    gate_ok = quality_gate_passed(
        audit_passed=failures["audit_passed"],
        citation_coverage=metrics["citation_coverage"],
        reference_integrity=metrics["reference_integrity"],
        placeholder_markers=failures["placeholder_markers"],
        language_bleed=failures["language_bleed"],
        hallucination_final=hallucination_final,
        high_contradictions=conflicts,
        undefined_title_terms=undefined,
    )
    passed = gate_ok and all(g.passed for g in gates)
    answered = status.answered if status is not None else 0
    return {
        "score": round(sum(metrics.values()) * 100 / 80),
        "badge": BADGE if passed else "Unverified",
        "passed": passed,
        "metrics": metrics,
        "meta": {
            "word_count": structure.details["word_count"],
            "total_sources": n_sources,
            "total_claims": status.tasks if status is not None else 0,
            "claims_checked": answered,
            "claims_verified": answered - len(status.not_supported) if status is not None else 0,
            "images_verified": by["images"].details["meaningful"],
        },
        "audit_gate_failures": failures,
    }


def run_check(ws: PaperWorkspace) -> dict[str, Any]:
    built = number(ws)
    dossier = load_dossier(ws)
    meta = read_meta(ws)
    evidence = read_json(ws.evidence, "write evidence.json")
    report = built.markdown
    artifact = gate_artifact(report)
    audit = artifact.details["audit"]
    texts = source_texts(ws, dossier)
    found = evidence_problems(
        evidence,
        report,
        meta["title"],
        dossier,
        set(built.registry.sources),
        texts,
        after_claim_check=True,
    )
    ev_problems = [p for p in found if not p.startswith(PAGE_PREFIX)]
    evidence_gate = Gate("evidence", not ev_problems, {"problems": ev_problems})
    page_problems = (
        [p for p in found if p.startswith(PAGE_PREFIX)]
        if not ev_problems
        else ["evidence.json invalid"]
    )
    page_gate = Gate("page_anchors", not page_problems, {"problems": page_problems})
    status = claim_status(ws, built, dossier, evidence) if not ev_problems else None
    claims_gate = Gate(
        "claims",
        status is not None and status.passed,
        {"status": asdict(status)}
        if status is not None
        else {"problems": ["evidence.json invalid"]},
    )
    hero_gate, hero = gate_hero(meta["title"], built.probative_images)
    gates = [
        artifact,
        gate_structure(report),
        gate_meta(meta, dossier.question),
        gate_references(report, built.sources, dossier),
        gate_specifics(report, built.sources, dossier, texts),
        gate_coherence(meta["title"], report, status),
        evidence_gate,
        page_gate,
        claims_gate,
        gate_images(ws, report, built.probative_images),
        hero_gate,
    ]
    score = quality_score(gates, audit, built, dossier, status)
    gates.append(Gate("quality", score["passed"], {"score": score["score"]}))
    result = {
        "request_id": ws.request_id,
        "checked_at": datetime.now(UTC).isoformat(),
        "paper_sha256": sha256_text(report),
        "evidence_sha256": sha256_text(ws.evidence.read_text(encoding="utf-8")),
        "meta_sha256": sha256_text(ws.meta.read_text(encoding="utf-8")),
        "passed": all(g.passed for g in gates),
        "gates": [asdict(g) for g in gates],
        "quality_score": score,
        "audit": audit,
        "hero_image": hero,
    }
    write_json(ws.check_report, result)
    return result
