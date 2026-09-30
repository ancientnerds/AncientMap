"""`paper number`: [S:<source_id>] -> [N], References, selected images -> paper.md.

paper.md is always derived: `# <title>` + the numbered draft + the checked images (inserted
after the paragraph their opportunity anchors) + `## References` rendered by
CitationRegistry.format_references_list, the exact line format validate_paper_artifact
accepts. Numbers are assigned in order of first citation. Claude edits draft.md only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pipeline.lyra.image_fetcher import ImageCandidate
from pipeline.lyra.theo_citations import CitationRegistry
from pipeline.lyra.theo_image_captions import image_markdown, insert_image_after_paragraph
from pipeline.studio.errors import StudioError
from pipeline.studio.paper.anchors import matching_paragraphs, paragraphs
from pipeline.studio.paper.workspace import (
    Dossier,
    PaperWorkspace,
    load_dossier,
    read_json,
    read_meta,
    write_json,
)

S_MARKER_RE = re.compile(r"\[S:([0-9a-f]{12})\]")
_LOOSE_S_MARKER_RE = re.compile(r"\[S:[^\]]*\]")
_BARE_NUMERIC_RE = re.compile(r"\[\d+\]")
_H1_RE = re.compile(r"^#\s", re.MULTILINE)
_REFS_RE = re.compile(r"^#{2,3}\s+(?:References|Sources)\s*$", re.MULTILINE | re.IGNORECASE)
EMBED_STRATEGIES = frozenset({"exact"})


@dataclass(frozen=True)
class BuiltPaper:
    markdown: str
    registry: CitationRegistry
    sources: list[dict[str, Any]]
    probative_images: list[dict[str, Any]]


def draft_problems(draft: str, dossier: Dossier) -> list[str]:
    problems: list[str] = []
    if _H1_RE.search(draft):
        problems.append("draft.md carries a '# ' title line; the title lives in paper_meta.json")
    if _REFS_RE.search(draft):
        problems.append("draft.md carries a References/Sources heading; `paper number` adds it")
    bare = sorted(set(_BARE_NUMERIC_RE.findall(draft)))
    if bare:
        problems.append(f"draft.md carries bare numeric markers {bare[:5]}; cite with [S:<id>]")
    malformed = sorted(
        {m for m in _LOOSE_S_MARKER_RE.findall(draft) if not S_MARKER_RE.fullmatch(m)}
    )
    if malformed:
        problems.append(f"malformed source markers {malformed[:5]} (need [S:<12 hex>])")
    cited = set(S_MARKER_RE.findall(draft))
    unknown = sorted(sid for sid in cited if sid not in dossier.sources)
    if unknown:
        problems.append(f"cited source ids not in the dossier: {unknown}")
    citable = set(dossier.citable_ids)
    outside = sorted(sid for sid in cited if sid in dossier.sources and sid not in citable)
    if outside:
        problems.append(f"cited source ids outside the brief's source list: {outside}")
    if "![" in draft:
        problems.append("draft.md embeds images; images come only through images-import")
    if not cited:
        problems.append("draft.md cites nothing")
    return problems


def number_draft(draft: str, dossier: Dossier) -> tuple[str, CitationRegistry]:
    problems = draft_problems(draft, dossier)
    if problems:
        raise StudioError("; ".join(problems))
    registry = CitationRegistry()
    for sid in dict.fromkeys(S_MARKER_RE.findall(draft)):
        registry.sources[sid] = dossier.cited_source(sid)
        registry.assign_reference_number(sid)
    body = S_MARKER_RE.sub(lambda m: f"[{registry.reference_numbers[m.group(1)]}]", draft)
    return body, registry


def sources_table(registry: CitationRegistry) -> list[dict[str, Any]]:
    rows = []
    for sid, n in sorted(registry.reference_numbers.items(), key=lambda kv: kv[1]):
        s = registry.sources[sid]
        rows.append(
            {"n": n, "source_id": sid, "url": s.url, "title": s.title, "tier": s.reliability_tier}
        )
    return rows


def _candidate(entry: dict[str, Any]) -> ImageCandidate:
    return ImageCandidate(
        url=entry["source_url"],
        source=entry["source_name"],
        title=entry["title"],
        description=entry["description"],
        artist=entry["artist"],
        license=entry["license"],
        license_url=entry["license_url"],
    )


def embed_images(paper: str, images: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Insert each checked image after the paragraph its anchor matches (exactly one).

    A selection that an edit of draft.md made stale is refused in one error naming every
    image whose anchor no longer opens exactly one paragraph, and the way out: images-export
    builds the paper without the selection (`build_paper(ws, with_images=False)`).
    """
    placed: list[dict[str, Any]] = []
    stale: list[str] = []
    for entry in images:
        paras = paragraphs(paper)
        hits = matching_paragraphs(paras, entry["anchor_text"])
        if len(hits) != 1:
            stale.append(
                f"image {entry['file']} ({entry['opportunity_id']}): its anchor matches "
                f"{len(hits)} paragraphs of the current draft"
            )
            continue
        para = paras[hits[0]]
        md = image_markdown(
            _candidate(entry), entry["web_path"], entry["rationale"], verified=entry["verified"]
        )
        paper, strategy = insert_image_after_paragraph(paper, para.section, para.text, md)
        if strategy not in EMBED_STRATEGIES:
            raise StudioError(f"image {entry['file']}: embed strategy {strategy!r}, not exact")
        placed.append(
            {
                **entry,
                "paragraph_text": para.text,
                "paragraph_index": para.index,
                "section_heading": para.section,
            }
        )
    if stale:
        raise StudioError(
            "images/selected.json no longer fits draft.md: "
            + "; ".join(stale)
            + ". Fix the anchor_text of these opportunities in images/opportunities.json, "
            "then run `paper images-export` (it ignores the stale selection), answer its "
            "tasks and run `paper images-import`"
        )
    return paper, placed


def compose(
    title: str, body: str, registry: CitationRegistry, images: list[dict[str, Any]]
) -> tuple[str, list[dict[str, Any]]]:
    paper = f"# {title}\n\n{body.strip()}\n"
    paper, placed = embed_images(paper, images)
    refs = registry.format_references_list()
    return f"{paper.rstrip()}\n\n## References\n\n{refs}\n", placed


def selected_images(ws: PaperWorkspace) -> list[dict[str, Any]]:
    path = ws.images_dir / "selected.json"
    return read_json(path, "") if path.exists() else []


def build_paper(ws: PaperWorkspace, *, with_images: bool = True) -> BuiltPaper:
    """The numbered paper with the images of images/selected.json.

    with_images=False builds it without that selection: images-export chooses the images for
    the current draft, so a selection an edit of draft.md made stale must not stop it. Every
    other caller builds the paper as it will be published (claims-export too: the coherence
    task lists the measurements of the image captions).
    """
    dossier = load_dossier(ws)
    draft = ws.require(ws.draft, "write draft.md from brief.md").read_text(encoding="utf-8")
    meta = read_meta(ws)
    body, registry = number_draft(draft, dossier)
    images = selected_images(ws) if with_images else []
    markdown, placed = compose(meta["title"], body, registry, images)
    return BuiltPaper(markdown, registry, sources_table(registry), placed)


def number(ws: PaperWorkspace) -> BuiltPaper:
    built = build_paper(ws)
    write_json(ws.sources_json, built.sources)
    ws.paper.write_text(built.markdown, encoding="utf-8")
    return built
