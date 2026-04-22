"""Theo research paper block splitter.

Splits a Theo paper markdown body into individually-approvable blocks for the
per-section approval editor (`docs/superpowers/plans/2026-04-21-*.md`).

Critical design rule: **parse-only, no re-stringify.** The paper markdown
contains shapes we cannot round-trip losslessly through `mdast-util-to-markdown`
or `markdown_it_py`'s renderer:

- `wireCitationAnchors` escape sequences `[\\[N\\]](#ref-N)`
- Custom link protocols `site:`, `lyra-video:`, `youtube:`
- The strict inline-figure pattern
  `![alt](/data/research-images/...)\\n\\n*caption*\\n[Source](url)`
  (see `galleryParser.ts` → `FIGURE_RE`)

So we parse with `markdown-it-py`, use `token.map` line offsets to slice raw
markdown out of the original source, and keep the byte sequence intact.

Snapshot invariant: ``"".join(b["content"] for b in blocks) == original_body``
(modulo the trailing newline normalization performed when segments are emitted).

Block identity is a hybrid of ``content_hash = sha1(normalized_content)[:10]``
(survives reorders) and ``position = {segment_idx, block_idx}`` (fallback when
the hash changes). The server rewrites the hash on its own edits so decisions
carry forward; any other content change cleanly resets that block to pending.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from markdown_it import MarkdownIt

# Mirror of the frontend regex in `ancient-nerds-map/src/components/theo/galleryParser.ts`.
# Keep these two in sync.
_FIGURE_RE = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<src>/data/research-images/[^)]+)\)"
    r"(?:\s*\n\n\*(?P<caption>[^*\n][^*]*?)\*"
    r"(?:\s*\n\[Source\]\((?P<url>[^)]+)\))?)?"
)

_GALLERY_ALT_RE = re.compile(r"^gallery:[^|]+\|(?:verified:(?:yes|no)\|)?(.*)$")


def _clean_alt(alt: str) -> str:
    """Strip legacy `gallery:ID|verified:yes|` alt prefixes — matches galleryParser.ts."""
    m = _GALLERY_ALT_RE.match(alt)
    cleaned = (m.group(1) if m else alt).strip()
    return cleaned or "Research image"


@dataclass
class Block:
    """One reviewable block in a Theo paper."""

    block_id: str
    content_hash: str
    position: dict[str, int]
    kind: str
    content: str
    # Only populated for figure / mosaic kinds. Frontend uses this to render
    # the image(s) identically to the read-only view without re-parsing.
    figures: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "block_id": self.block_id,
            "content_hash": self.content_hash,
            "position": self.position,
            "kind": self.kind,
            "content": self.content,
        }
        if self.figures:
            out["figures"] = self.figures
        return out


# ---------------------------------------------------------------------------
# Figure/mosaic segmentation — Python port of `splitIntoImageSegments` in
# `ancient-nerds-map/src/components/theo/galleryParser.ts`.
# ---------------------------------------------------------------------------


@dataclass
class _Segment:
    kind: str  # 'text' | 'figure' | 'mosaic'
    content: str = ""
    figures: list[dict[str, str]] = field(default_factory=list)


def _split_into_image_segments(md: str) -> list[_Segment]:
    matches: list[tuple[int, int, dict[str, str]]] = []
    for m in _FIGURE_RE.finditer(md):
        matches.append(
            (
                m.start(),
                m.end(),
                {
                    "src": m.group("src") or "",
                    "title": _clean_alt(m.group("alt") or ""),
                    "caption": (m.group("caption") or "").strip(),
                    "sourceUrl": m.group("url") or "",
                },
            )
        )

    if not matches:
        return [_Segment(kind="text", content=md)]

    # Group adjacent image matches separated only by whitespace → mosaic.
    groups: list[dict[str, Any]] = []
    for start, end, figure in matches:
        if groups and md[groups[-1]["end"] : start].strip() == "":
            groups[-1]["end"] = end
            groups[-1]["figures"].append(figure)
        else:
            groups.append({"start": start, "end": end, "figures": [figure]})

    segments: list[_Segment] = []
    cursor = 0
    for group in groups:
        if group["start"] > cursor:
            segments.append(_Segment(kind="text", content=md[cursor : group["start"]]))
        # Carry the exact raw markdown slice (including caption / source trailer
        # and any inter-figure whitespace for mosaics) as the segment content so
        # concatenating block.content round-trips to the original paper byte-
        # for-byte.
        raw = md[group["start"] : group["end"]]
        if len(group["figures"]) == 1:
            segments.append(_Segment(kind="figure", content=raw, figures=group["figures"]))
        else:
            segments.append(_Segment(kind="mosaic", content=raw, figures=group["figures"]))
        cursor = group["end"]
    if cursor < len(md):
        segments.append(_Segment(kind="text", content=md[cursor:]))
    return segments


# ---------------------------------------------------------------------------
# Text-segment splitting — markdown-it-py token.map → raw slices.
# ---------------------------------------------------------------------------


# Block-opening tokens we treat as independent reviewable units. Nested blocks
# (e.g. a paragraph inside a list item) are NOT split out — the outer list is
# one decision.
_BLOCK_OPEN_TO_KIND = {
    "paragraph_open": "paragraph",
    "heading_open": "heading",
    "bullet_list_open": "list",
    "ordered_list_open": "list",
    "blockquote_open": "blockquote",
    "table_open": "table",
}
_STANDALONE_BLOCK_TO_KIND = {
    "fence": "code",
    "code_block": "code",
    "hr": "hr",
    "html_block": "html",
}


def _compute_line_offsets(text: str) -> list[int]:
    """Return char offset of start of each line, plus one past-the-end."""
    offsets = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            offsets.append(i + 1)
    # Past-the-end marker so last block can slice to len(text).
    offsets.append(len(text))
    return offsets


def _top_level_block_starts(md: str) -> list[tuple[int, str]]:
    """Return [(start_line, kind), ...] for each top-level block in the text.

    Only emits the outermost token for each block — paragraph_open inside a
    list_item is skipped because the list as a whole is one decision.
    """
    parser = MarkdownIt("commonmark").enable("table").enable("strikethrough")
    tokens = parser.parse(md)
    starts: list[tuple[int, str]] = []
    for tok in tokens:
        if tok.level != 0:
            continue
        if tok.map is None:
            continue
        if tok.type in _BLOCK_OPEN_TO_KIND:
            starts.append((tok.map[0], _BLOCK_OPEN_TO_KIND[tok.type]))
        elif tok.type in _STANDALONE_BLOCK_TO_KIND:
            starts.append((tok.map[0], _STANDALONE_BLOCK_TO_KIND[tok.type]))
    # markdown-it-py already emits tokens in document order, but sort to be safe.
    starts.sort(key=lambda p: p[0])
    return starts


def _split_text_segment(md: str) -> list[tuple[str, str]]:
    """Split a text segment into (kind, raw_content) pairs with byte-exact fidelity.

    Every character of `md` appears in exactly one returned block (leading
    whitespace is prepended to the first block; trailing whitespace is appended
    to the last block) so concatenation reconstructs the segment.
    """
    if not md:
        return []

    starts = _top_level_block_starts(md)
    if not starts:
        # No recognisable blocks — treat the whole segment as one paragraph.
        return [("paragraph", md)]

    line_offsets = _compute_line_offsets(md)
    blocks: list[tuple[str, str]] = []
    for i, (start_line, kind) in enumerate(starts):
        char_start = line_offsets[start_line]
        if i + 1 < len(starts):
            char_end = line_offsets[starts[i + 1][0]]
        else:
            char_end = len(md)
        # First block owns any leading whitespace in the segment.
        if i == 0 and char_start > 0:
            char_start = 0
        blocks.append((kind, md[char_start:char_end]))
    return blocks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _normalize_for_hash(content: str) -> str:
    """Stable normalization for content hashing — strip outer whitespace only.

    Whitespace-only differences between saves don't spuriously reset decisions.
    Anything stronger (unicode normalization, newline canonicalization) risks
    collapsing semantically-distinct markdown.
    """
    return content.strip()


def _hash_content(content: str) -> str:
    return hashlib.sha1(_normalize_for_hash(content).encode("utf-8")).hexdigest()[:10]


def split_paper_into_blocks(report: str) -> list[Block]:
    """Split a Theo paper body into reviewable blocks.

    Figures and mosaics become their own blocks (the entire raw markdown match
    is the content). Text segments are further split via markdown-it-py so each
    paragraph / heading / list / blockquote / table / code block is independent.

    Args:
        report: The full paper markdown (`result_json.report`).

    Returns:
        Ordered list of Block objects. Concatenating `block.content` across all
        blocks reproduces `report` byte-for-byte (modulo the split boundary of
        the figure regex, which consumes trailing whitespace inside the match).
    """
    segments = _split_into_image_segments(report)
    blocks: list[Block] = []

    for seg_idx, seg in enumerate(segments):
        if seg.kind in ("figure", "mosaic"):
            # Hash on `src` list rather than caption so a caption-only edit
            # doesn't reset the block's decision to pending (caption edits are
            # the expected in-place change for figures / mosaics).
            hash_basis = "|".join(f["src"] for f in seg.figures)
            h = _hash_content(hash_basis)
            blocks.append(
                Block(
                    block_id=h,
                    content_hash=h,
                    position={"segment_idx": seg_idx, "block_idx": 0},
                    kind=seg.kind,
                    content=seg.content,
                    figures=list(seg.figures),
                )
            )
        else:
            for block_idx, (kind, content) in enumerate(_split_text_segment(seg.content)):
                h = _hash_content(content)
                blocks.append(
                    Block(
                        block_id=h,
                        content_hash=h,
                        position={"segment_idx": seg_idx, "block_idx": block_idx},
                        kind=kind,
                        content=content,
                    )
                )

    # Deduplicate block_ids by appending position suffix on collisions. Two
    # identical paragraphs in the same paper would otherwise share one decision.
    seen: dict[str, int] = {}
    for b in blocks:
        if b.block_id in seen:
            seen[b.block_id] += 1
            b.block_id = f"{b.content_hash}-{seen[b.content_hash]}"
        else:
            seen[b.block_id] = 0
    return blocks


def build_block_list_response(
    report: str,
    section_approvals: dict[str, Any] | None,
    hero_image: dict[str, Any] | None,
) -> dict[str, Any]:
    """Assemble the `GET /theo/research/{id}/blocks` response payload.

    Merges the canonical block list with any stored decisions, matching first
    by `content_hash` and falling back to `position`.
    """
    approvals = section_approvals or {}
    version = int(approvals.get("version") or 0)
    decisions = approvals.get("decisions") or []

    by_hash: dict[str, dict[str, Any]] = {}
    by_position: dict[tuple[int, int], dict[str, Any]] = {}
    for d in decisions:
        h = d.get("content_hash")
        if h:
            by_hash[h] = d
        pos = d.get("position") or {}
        key = (int(pos.get("segment_idx", -1)), int(pos.get("block_idx", -1)))
        if key != (-1, -1):
            by_position[key] = d

    blocks: list[dict[str, Any]] = []

    # Hero image becomes block id "hero" if present. We don't merge it into
    # segments because it lives in `result_json.hero_image`, not the report body.
    if hero_image and hero_image.get("src"):
        hero_decision = by_hash.get("hero") or next(
            (d for d in decisions if d.get("block_id") == "hero"),
            None,
        )
        blocks.append(
            {
                "block_id": "hero",
                "content_hash": "hero",
                "position": {"segment_idx": -1, "block_idx": 0},
                "kind": "hero",
                "content": hero_image.get("caption") or "",
                "hero": {
                    "src": hero_image.get("src"),
                    "caption": hero_image.get("caption") or "",
                    "sourceUrl": hero_image.get("sourceUrl") or hero_image.get("source_url") or "",
                    "title": hero_image.get("title") or "",
                },
                "state": (hero_decision or {}).get("state", "pending"),
                "decided_by": (hero_decision or {}).get("decided_by"),
                "decided_at": (hero_decision or {}).get("decided_at"),
                "edited_content": (hero_decision or {}).get("edited_content"),
            }
        )

    for b in split_paper_into_blocks(report):
        pos_key = (b.position["segment_idx"], b.position["block_idx"])
        decision = by_hash.get(b.content_hash) or by_position.get(pos_key)
        payload = b.to_dict()
        payload["state"] = (decision or {}).get("state", "pending")
        payload["decided_by"] = (decision or {}).get("decided_by")
        payload["decided_at"] = (decision or {}).get("decided_at")
        payload["edited_content"] = (decision or {}).get("edited_content")
        blocks.append(payload)

    return {"version": version, "blocks": blocks}
