"""Paragraphs of a paper and the evidence-anchor checks, aligned with the publish gate and page.

One rule everywhere (stream A's C9): an anchor names the one paragraph whose normalised text
STARTS WITH the normalised anchor, and the normalised anchor has at least MIN_ANCHOR_CHARS
characters. `pipeline.lyra.theo_publishing` (stream A) owns the normaliser, MIN_ANCHOR_CHARS,
`report_paragraphs` and the markdown resolver the publish gate runs; the paper page
(`pipeline.research_html_renderer.resolve_evidence_anchors`, stream B) applies the same rule
to the `<p>` elements it serves. The normaliser drops citation markers (`[N]`, `[S:<id>]`),
so an anchor copied from the draft still names its paragraph in the numbered paper.

- `paragraphs` is `report_paragraphs` plus the h2 each paragraph sits in (same blocks, same
  order, same indices as the gate); `matching_paragraphs` finds the paragraphs an anchor
  opens (evidence entries and image opportunities).
- `resolve_evidence_anchors` is the publish gate's own markdown resolver (claim tasks need
  the paragraph an evidence entry belongs to). The acceptance of evidence.json, markdown and
  page together, is stream A's `check_evidence_anchors` (evidence.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline.lyra import theo_publishing
from pipeline.lyra.theo_citations import _is_non_prose_block, split_artifact
from pipeline.lyra.theo_publishing import MIN_ANCHOR_CHARS, normalize_anchor_text

MARKER_RE = re.compile(r"\[(?:\d+|S:[^\]]*)\]")
_H2_RE = re.compile(r"^##\s+(.+?)\s*$")


class AnchorError(ValueError):
    """One or more anchors do not resolve to exactly one paragraph."""


@dataclass(frozen=True)
class Paragraph:
    index: int
    section: str  # the h2 text as written; "" before the first h2
    text: str


def normalize(text: str) -> str:
    """The shared anchor key (stream A's normalize_anchor_text)."""
    return normalize_anchor_text(text)


def anchor_problem(anchor_text: str) -> str | None:
    if len(normalize(anchor_text)) < MIN_ANCHOR_CHARS:
        return f"anchor_text is shorter than {MIN_ANCHOR_CHARS} characters"
    return None


def paragraphs(report: str) -> list[Paragraph]:
    """Prose paragraphs in reading order: no headings, images, captions or References.

    The blocks of `theo_publishing.report_paragraphs` (the walk of theo_citations'
    `_split_prose_into_paragraphs`), with the section kept as written.
    """
    prose, _heading, _refs = split_artifact(report.replace("\r\n", "\n"))
    out: list[Paragraph] = []
    section = ""
    for raw in prose.split("\n\n"):
        block = raw.strip()
        if not block:
            continue
        if block.startswith("#"):
            first = block.splitlines()[0]
            match = _H2_RE.match(first)
            if match and not first.startswith("###"):
                section = match.group(1)
            continue
        if _is_non_prose_block(block):
            continue
        out.append(Paragraph(len(out), section, block))
    return out


def matching_paragraphs(paras: list[Paragraph], anchor_text: str) -> list[int]:
    """Indices of the paragraphs whose normalised text starts with the normalised anchor."""
    key = normalize(anchor_text)
    if not key:
        return []
    return [p.index for p in paras if normalize(p.text).startswith(key)]


def resolve_evidence_anchors(report: str, evidence: list[dict]) -> dict[str, int]:
    """{evidence id: paragraph index}, by the publish gate's own resolver.

    Raises AnchorError naming every entry that does not resolve (too short after
    normalisation, or opening 0 or several paragraphs).
    """
    resolved, issues = theo_publishing.resolve_evidence_anchors(report, evidence)
    if issues:
        raise AnchorError("; ".join(issues))
    return resolved
