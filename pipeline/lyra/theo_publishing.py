"""Shared publish sequence for Theo papers written in a Claude session (spec 2.6, 2.7).

Theo researches on the VPS and stops at a dossier (status 'researched'). A
Claude session writes, checks and publishes the paper through
`python -m pipeline.lyra.theo_publish` inside the API container; this module is
the sequence that CLI runs. It lives under pipeline/ so the CLI and
api/routes/theo.py (the manual founder route) share one slug rule and one
side-effect sequence: pipeline must not import api.

Nothing here repairs a paper. Every gate either passes or reports what is wrong;
the local check (pipeline/studio/paper) is the only place a paper gets fixed.

Module-level imports stay light (no pipeline.indexnow, no DB models, no
markdown/nh3): stream B's paper renderer imports normalize_anchor_text from
here, and the Lyra image (no markdown, no nh3) must be able to import it.
"""

from __future__ import annotations

import html
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy import text

from pipeline.lyra.quality_gate import recompute_quality_passed
from pipeline.lyra.theo_citations import (
    _is_non_prose_block,
    _split_prose_into_paragraphs,
    split_artifact,
    validate_paper_artifact,
)

# ---------------------------------------------------------------------------
# Evidence anchors (contract C9, shared with the paper page)
# ---------------------------------------------------------------------------

#: An evidence id: "ev-" plus at least two ASCII digits ("ev-03", "ev-117"; \d
#: would also take other Unicode digits, which the frontend copy refuses).
#: Always applied with fullmatch: "$" in re.match also accepts a trailing
#: newline. The one definition: the paper page (pipeline.research_html_renderer)
#: and the studio (pipeline.studio) import it, the frontend's PAPER_HASH_RE
#: copies it.
EVIDENCE_ID_RE = re.compile(r"ev-[0-9]{2,}")

#: A YouTube video id: 11 characters of [A-Za-z0-9_-]. Always applied with
#: fullmatch, like EVIDENCE_ID_RE. The one definition: the video gate
#: (check_video_shape) and archive completion (youtube_video_id) here, the
#: paper page (stream B's parse_videos) and the studio (stream C's publish
#: step and ledger) import it.
YOUTUBE_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")

#: Shortest normalised anchor text accepted. Shorter openings ("The site")
#: match many paragraphs and say nothing about which one is meant.
MIN_ANCHOR_CHARS = 20

_TYPOGRAPHY = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "‛": "'",
        "′": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "‟": '"',
        "″": '"',
        "«": '"',
        "»": '"',
        "‒": "-",
        "–": "-",
        "—": "-",
        "―": "-",
        "−": "-",
    }
)
_MD_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!])")
_AUTOLINK_RE = re.compile(r"<(https?://[^>\s]+)>")
_MD_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_CITATION_MARKER_RE = re.compile(r"\[(?:\d+(?:\s*[,-]\s*\d+)*|S:[^\]\s]+)\]")
_DASH_RUN_RE = re.compile(r"-{2,}")
_EDGE_UNDERSCORE_RE = re.compile(r"(?<!\w)_+|_+(?!\w)")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_anchor_text(text: str) -> str:
    """Fold paragraph text so markdown source and rendered HTML text compare equal.

    The matching rule shared with the paper page (contract C9): an evidence
    entry anchors to the paragraph whose normalised text STARTS WITH its
    normalised anchor_text. Apply this to the markdown paragraph here and to
    the paragraph's text content (tags stripped, entities unescaped) on the page.

    Steps, in order: HTML entities decoded ("&amp;" in the markdown is "&" on
    the page); curly and angle quotes, primes to straight ones, the dash family
    and minus to "-" (before NFKC, which would split a double prime in two);
    Unicode NFKC (an ellipsis becomes "...", a no-break space a space); markdown
    backslash escapes dropped; autolinks <https://...> to their URL; markdown
    links and images to their text; citation markers [N], [N, M], [N-M] and
    draft markers [S:<id>] removed; runs of "-" folded to one ("--" is what the
    renderer turns into an en dash); emphasis markers * and ` removed, _ removed
    at word edges; whitespace folded to single spaces; stripped; case-folded.
    """
    folded = unicodedata.normalize("NFKC", html.unescape(text).translate(_TYPOGRAPHY))
    folded = _MD_ESCAPE_RE.sub(r"\1", folded)
    folded = _AUTOLINK_RE.sub(r"\1", folded)
    folded = _MD_LINK_RE.sub(r"\1", folded)
    folded = _CITATION_MARKER_RE.sub(" ", folded)
    folded = _DASH_RUN_RE.sub("-", folded)
    folded = folded.replace("*", "").replace("`", "")
    folded = _EDGE_UNDERSCORE_RE.sub("", folded)
    return _WHITESPACE_RE.sub(" ", folded).strip().casefold()


def report_paragraphs(report: str) -> list[str]:
    """The prose paragraphs of a paper, in reading order.

    Blocks are split on a blank line, as the artifact gate splits them
    (theo_citations). Headings, image blocks, italic captions, [Source]( trailers
    and lone links are not paragraphs; nothing from the References heading on is.
    """
    prose, _heading, _refs = split_artifact(report.replace("\r\n", "\n"))
    return [
        block
        for _section, block in _split_prose_into_paragraphs(prose)
        if not _is_non_prose_block(block)
    ]


def resolve_evidence_anchors(report: str, evidence: list[dict]) -> tuple[dict[str, int], list[str]]:
    """Map each evidence id to the index (in report_paragraphs) of the paragraph it anchors to.

    Returns (resolved, issues). An entry resolves only when exactly one
    paragraph's normalised text starts with its normalised anchor_text. Entries
    must already carry string `id` and `anchor_text` (check_evidence validates
    the shape first).
    """
    normalized = [normalize_anchor_text(p) for p in report_paragraphs(report)]
    resolved: dict[str, int] = {}
    issues: list[str] = []
    for entry in evidence:
        ev_id = entry["id"]
        anchor = normalize_anchor_text(entry["anchor_text"])
        if len(anchor) < MIN_ANCHOR_CHARS:
            issues.append(
                f"{ev_id}: anchor_text shorter than {MIN_ANCHOR_CHARS} characters after normalisation"
            )
            continue
        hits = [index for index, para in enumerate(normalized) if para.startswith(anchor)]
        if len(hits) != 1:
            issues.append(f"{ev_id}: anchor_text matches {len(hits)} paragraphs (needs exactly 1)")
            continue
        resolved[ev_id] = hits[0]
    return resolved, issues


# ---------------------------------------------------------------------------
# Video poster (contract C6, owner decision 13)
# ---------------------------------------------------------------------------


def poster_web_path(request_id: str, youtube_id: str) -> str:
    """The web path of a registered video's poster: our own studio thumbnail.

    The one definition. theo_publish --register-video accepts a `poster` only
    when it equals this path and the file exists in the paper's folder; the
    paper page (stream B's parse_videos) and the studio (stream C, which
    uploads the chosen thumbnail under this name) import it.
    """
    return f"/data/research-images/{request_id}/video_{youtube_id}.jpg"


def check_evidence_anchors(
    report: str, title: str, evidence: list[dict]
) -> tuple[dict[str, int], list[str]]:
    """Contract C9's one acceptance function: every anchor resolves in the markdown and on the page.

    First among report_paragraphs (resolve_evidence_anchors above); when that
    passes, among the plain <p> of the HTML /research/{slug} serves, through the
    page's own resolver (stream B, pipeline.research_html_renderer). The two
    paragraph sets differ (captions, reference lines, blockquotes, list items),
    so passing one does not imply the other. `resolved` holds report_paragraphs
    indices; a page-side failure is one issue "paper page: <message>". Entries
    must already be well-formed (check_evidence validates the shape first).
    """
    resolved, issues = resolve_evidence_anchors(report, evidence)
    if issues:
        return resolved, issues
    # Imported here: the renderers need markdown and nh3, which the Lyra image
    # lacks, and research_html_renderer imports this module back.
    from pipeline.article_html_renderer import markdown_to_html
    from pipeline.research_html_renderer import PaperPageError, paper_markdown, parse_evidence
    from pipeline.research_html_renderer import resolve_evidence_anchors as resolve_on_page

    try:
        resolve_on_page(markdown_to_html(paper_markdown(report, title)), parse_evidence(evidence))
    except PaperPageError as exc:
        return resolved, [f"paper page: {exc}"]
    return resolved, []


# ---------------------------------------------------------------------------
# Slug
# ---------------------------------------------------------------------------

#: published_by of a Theo paper at its first publish. 'Theo' keeps the
#: Organization author in the page's JSON-LD and the "AI research agent" label
#: (spec 3.7). A full republish keeps the stored published_by (owner decision
#: 19: a founder who published a legacy paper stays credited as publisher).
PUBLISH_AUTHOR = "Theo"


def make_slug(title: str) -> str:
    """URL slug of a paper title (moved unchanged from api/routes/theo.py::_make_slug)."""
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug).strip("-")
    return slug[:250]


_SLUG_TAKEN_SQL = text("SELECT 1 FROM research_requests WHERE slug = :slug AND id != :id")


def pick_slug(session: Any, title: str, request_id: str) -> str:
    """make_slug(title), suffixed with -<id[:8]> when another paper already holds it."""
    slug = make_slug(title)
    taken = session.execute(_SLUG_TAKEN_SQL, {"slug": slug, "id": request_id}).fetchone()
    return f"{slug}-{request_id[:8]}" if taken else slug


# ---------------------------------------------------------------------------
# Gates. Each returns {"passed": bool, "issues": [str], ...}.
# ---------------------------------------------------------------------------

#: /app/public/data/research-images in the API container (bind mount of the VPS's
#: /var/www/ancientnerds/public/data); the repo root's public/data elsewhere.
RESEARCH_IMAGES_DIR = Path(__file__).resolve().parents[2] / "public" / "data" / "research-images"

#: A citation-registry source id; applied with fullmatch like every id pattern here.
SOURCE_ID_RE = re.compile(r"[0-9a-f]{12}")
WRITER_KEYS = ("model", "tool", "research_model", "published", "human_review")
#: writer.published values the page's disclosure line knows (stream B's parse_writer).
WRITER_PUBLISHED = ("automatic", "manual")
MAX_TITLE_CHARS = 200
MAX_CARD_CHARS = 600

_IMAGE_REF_RE = re.compile(r"/data/research-images/[^\s)\"'<>]+")
_IMAGE_PATH_RE = re.compile(
    r"/data/research-images/(?P<rid>[^/]+)/(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
)
_EVIDENCE_KEYS = frozenset(
    {"id", "anchor_text", "claim", "source_ids", "quote", "quote_source_id", "verdict"}
)
_RESULT_REQUIRED: dict[str, type] = {
    "title": str,
    "card_description": str,
    "report": str,
    "published_report": str,
    "probative_images": list,
    "published_block_ids": list,
    "quality_score": dict,
    "evidence": list,
    "corrections": list,
}
_RESULT_NULLABLE_DICTS = ("hero_image", "published_hero_image")
_RESULT_OPTIONAL = frozenset({"audit", "writer"})


def _gate(issues: list[str], **extra: Any) -> dict:
    return {"passed": not issues, "issues": issues, **extra}


def check_writer(writer: Any) -> list[str]:
    """Issues with a writer object (contract C4 `writer`)."""
    if not isinstance(writer, dict):
        return ["writer must be an object"]
    issues = [f"writer.{key} missing" for key in WRITER_KEYS if key not in writer]
    for key in ("model", "tool", "research_model"):
        if key in writer and not (isinstance(writer[key], str) and writer[key].strip()):
            issues.append(f"writer.{key} must be a non-empty string")
    if "published" in writer and writer["published"] not in WRITER_PUBLISHED:
        issues.append("writer.published must be 'automatic' or 'manual'")
    if "human_review" in writer and not isinstance(writer["human_review"], bool):
        issues.append("writer.human_review must be true or false")
    unknown = sorted(set(writer) - set(WRITER_KEYS))
    if unknown:
        issues.append(f"writer has unknown keys: {unknown}")
    return issues


def _result_issues(result: dict, writer: Any, *, republish: bool) -> list[str]:
    """Issues with a C4 `result`; the caller checks `writer` itself.

    result.corrections must be [] for a first publish and for a full republish
    through --correct alike (C5): the server owns the published log, which a
    republish keeps and extends by corrections_append. `republish` only picks
    the hint of that issue.
    """
    issues: list[str] = []
    for key, kind in _RESULT_REQUIRED.items():
        if not isinstance(result.get(key), kind):
            issues.append(f"result.{key} must be a {kind.__name__}")
    for key in _RESULT_NULLABLE_DICTS:
        if key not in result:
            issues.append(f"result.{key} missing (null when the paper has no hero image)")
        elif result[key] is not None and not isinstance(result[key], dict):
            issues.append(f"result.{key} must be an object or null")
    unknown = sorted(
        set(result) - set(_RESULT_REQUIRED) - set(_RESULT_NULLABLE_DICTS) - _RESULT_OPTIONAL
    )
    if unknown:
        issues.append(f"result has unknown keys: {unknown}")
    if issues:
        return issues
    title = result["title"].strip()
    if not title or "\n" in title or len(title) > MAX_TITLE_CHARS:
        issues.append(f"result.title must be one line of 1-{MAX_TITLE_CHARS} characters")
    elif not make_slug(title):
        issues.append("result.title yields an empty slug")
    card = result["card_description"].strip()
    if not card or len(card) > MAX_CARD_CHARS:
        issues.append(f"result.card_description must be 1-{MAX_CARD_CHARS} characters")
    if result["published_block_ids"]:
        issues.append("result.published_block_ids must be [] (no block review on this path)")
    if result["corrections"]:
        issues.append(
            "result.corrections must be []: the published log is kept and grows only through corrections_append"
            if republish
            else "result.corrections must be [] at first publish (use --correct afterwards)"
        )
    if not result["evidence"]:
        issues.append("result.evidence is empty: every paper carries evidence entries")
    if "writer" in result and result["writer"] != writer:
        issues.append("result.writer differs from the bundle's writer")
    if not isinstance(result["quality_score"].get("audit_gate_failures"), dict):
        issues.append("result.quality_score.audit_gate_failures missing")
    return issues


def check_publish_shape(result: dict, writer: Any) -> dict:
    """Every key the published paper needs, with the right type, and nothing else."""
    return _gate(check_writer(writer) + _result_issues(result, writer, republish=False))


def check_snapshot(result: dict) -> dict:
    """Spec 2.6.3: every reader (page, TTS, Qdrant, curator) sees the same text and hero."""
    issues = []
    if result["report"] != result["published_report"]:
        issues.append("report and published_report differ: every reader must see the same text")
    if result["hero_image"] != result["published_hero_image"]:
        issues.append("hero_image and published_hero_image differ")
    return _gate(issues)


def check_artifact(report: str) -> tuple[dict, dict]:
    """validate_paper_artifact on the exact text being published: (gate, audit). No repair."""
    audit = validate_paper_artifact(report)
    return _gate(list(audit["issues"])[:20]), audit


def check_quality(quality_score: dict, audit: dict, *, require_stored_passed: bool) -> dict:
    """recompute_quality_passed against the fresh audit; for a first publish also the stored verdict.

    A correction recomputes only: the stored `passed` predates the corrected text
    and cannot be refreshed (the 2026-08-31 lesson in quality_gate.py).
    """
    stored = quality_score.get("passed") is True
    recomputed = recompute_quality_passed(quality_score, audit)
    issues = []
    if require_stored_passed and not stored:
        issues.append("quality_score.passed is not true")
    if not recomputed:
        issues.append("recompute_quality_passed rejects the paper against the fresh audit")
    return _gate(issues, stored_passed=stored, recomputed_passed=recomputed)


def check_evidence(report: str, title: str, evidence: list) -> dict:
    """Every entry well-formed and 'supported'; every anchor on exactly one paragraph
    of the markdown and of the served page (C9, check_evidence_anchors).

    The one validator of publishable evidence: stream C's local check calls it
    and takes its issues unchanged (C9).
    """
    issues = evidence_shape_issues(evidence)
    if issues:
        return _gate(issues, resolved={})
    resolved, anchor_issues = check_evidence_anchors(report, title, evidence)
    return _gate(anchor_issues, resolved=resolved)


def evidence_shape_issues(evidence: list) -> list[str]:
    """What check_evidence reports before it resolves any anchor (contract C9).

    Exactly the seven keys, an EVIDENCE_ID_RE id used once, non-empty
    anchor_text, claim and quote, 12-hex source_ids with quote_source_id among
    them, and verdict 'supported'. Stream C runs its dossier checks only when
    every issue check_evidence reports starts with 'paper page: ' (this list
    empty and every markdown anchor resolved).
    """
    issues: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(evidence):
        if not isinstance(entry, dict):
            issues.append(f"evidence[{index}]: must be an object")
            continue
        label = entry["id"] if isinstance(entry.get("id"), str) else f"evidence[{index}]"
        missing = sorted(_EVIDENCE_KEYS - set(entry))
        unknown = sorted(set(entry) - _EVIDENCE_KEYS)
        if missing:
            issues.append(f"{label}: missing {missing}")
        if unknown:
            issues.append(f"{label}: unknown keys {unknown}")
        if missing:
            continue
        if not isinstance(entry["id"], str) or not EVIDENCE_ID_RE.fullmatch(entry["id"]):
            issues.append(f"{label}: id must look like ev-NN")
        elif entry["id"] in seen:
            issues.append(f"{label}: duplicate id")
        else:
            seen.add(entry["id"])
        for key in ("anchor_text", "claim", "quote"):
            if not (isinstance(entry[key], str) and entry[key].strip()):
                issues.append(f"{label}: {key} must be a non-empty string")
        source_ids = entry["source_ids"]
        if not (
            isinstance(source_ids, list)
            and source_ids
            and all(isinstance(s, str) and SOURCE_ID_RE.fullmatch(s) for s in source_ids)
        ):
            issues.append(f"{label}: source_ids must be a non-empty list of 12-hex source ids")
        elif entry["quote_source_id"] not in source_ids:
            issues.append(f"{label}: quote_source_id is not one of source_ids")
        if entry["verdict"] != "supported":
            issues.append(
                f"{label}: verdict is {entry['verdict']!r}; only 'supported' may be published"
            )
    return issues


def referenced_images(
    report: str, probative_images: list, hero_image: dict | None
) -> tuple[list[str], list[str]]:
    """(web paths the paper references, issues about entries that carry none)."""
    paths = list(_IMAGE_REF_RE.findall(report))
    issues: list[str] = []
    for index, entry in enumerate(probative_images):
        web_path = entry.get("web_path") if isinstance(entry, dict) else None
        if not isinstance(web_path, str):
            issues.append(f"probative_images[{index}] has no web_path")
            continue
        paths.append(web_path)
    if hero_image is not None:
        if isinstance(hero_image.get("src"), str):
            paths.append(hero_image["src"])
        else:
            issues.append("hero_image has no src")
        if isinstance(hero_image.get("web_path"), str):
            paths.append(hero_image["web_path"])
    return list(dict.fromkeys(paths)), issues


def check_images(
    request_id: str,
    report: str,
    probative_images: list,
    hero_image: dict | None,
    *,
    images_root: Path,
) -> dict:
    """Every referenced image is a file in research-images/<request_id>/ (uploaded before the dry run)."""
    paths, issues = referenced_images(report, probative_images, hero_image)
    missing: list[str] = []
    foreign: list[str] = []
    for path in paths:
        match = _IMAGE_PATH_RE.fullmatch(path)
        if match is None:
            issues.append(f"not a research-images path: {path}")
            continue
        if match["rid"] != request_id:
            foreign.append(path)
            continue
        if not (images_root / request_id / match["name"]).is_file():
            missing.append(path)
    if foreign:
        issues.append(f"{len(foreign)} image(s) belong to another paper's folder")
    if missing:
        issues.append(f"{len(missing)} image(s) missing under research-images/{request_id}/")
    return _gate(issues, checked=len(paths), missing=missing, foreign=foreign)


def check_publish_status(status: str, is_public: bool, *, dry_run: bool) -> dict:
    """Publish needs a 'researched' or 'completed' row; --apply also needs it not public.

    A dry run on a public row passes (it answers "would this content pass") but
    reports apply_allowed=false: a public paper changes only through --correct.
    """
    eligible = status in ("researched", "completed")
    apply_allowed = eligible and not is_public
    issues = []
    if not eligible:
        issues.append(f"status is {status!r}; publish needs 'researched' or 'completed'")
    if is_public and not dry_run:
        issues.append("the paper is already public: --apply is refused, use --correct")
    return {
        "passed": not issues,
        "issues": issues,
        "status": status,
        "is_public": bool(is_public),
        "apply_allowed": apply_allowed,
    }


def check_page(request_id: str, stored: dict) -> dict:
    """The paper page's own validators on exactly the result_json about to be stored.

    pipeline.research_html_renderer.paper_extras raises PaperPageError (an HTTP
    500 on /research/{slug} and /api/v1/research/{slug}) for evidence,
    corrections, videos or a writer record it cannot render. The gates above
    check the same rules, so a failure here means gate and page disagree. The
    page-side anchor resolution runs in the evidence gate (check_evidence_anchors).
    The four keys are optional in result_json (legacy papers have none), which
    is why they are read with .get: absent is what the page's jsonb columns see.
    """
    from pipeline.research_html_renderer import PaperPageError, paper_extras

    row = SimpleNamespace(
        id=request_id,
        evidence=stored.get("evidence"),
        videos=stored.get("videos"),
        corrections=stored.get("corrections"),
        writer=stored.get("writer"),
    )
    try:
        paper_extras(row)
    except PaperPageError as exc:
        return _gate([str(exc)])
    return _gate([])


# ---------------------------------------------------------------------------
# Outcome, errors, row access, journal
# ---------------------------------------------------------------------------


class PublishInputError(ValueError):
    """The input or its target row cannot be processed at all (CLI exit 2)."""


class PublishConflictError(RuntimeError):
    """The row changed between read and write; nothing was committed (CLI exit 3)."""


class PublishVerificationError(RuntimeError):
    """Committed, but the re-read row differs from what was written (CLI exit 4)."""


@dataclass
class PublishOutcome:
    """What every theo_publish mode prints (contract C8)."""

    ok: bool
    action: str
    request_id: str
    dry_run: bool
    slug: str | None = None
    url: str | None = None
    gates: dict[str, dict] = field(default_factory=dict)
    side_effects: dict[str, dict] = field(default_factory=dict)
    journal_id: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


_ROW_SQL = text("""
    SELECT id::text AS id, status, is_public, slug, question, user_id,
           published_by, published_at, result_json
    FROM research_requests
    WHERE id = :id
""")
_VERIFY_SQL = text(
    "SELECT status, is_public, slug, published_by, result_json FROM research_requests WHERE id = :id"
)
_JOURNAL_SQL = text("""
    INSERT INTO theo_paper_publications
        (request_id, action, slug, writer, bundle_sha256, gates, side_effects)
    VALUES (CAST(:request_id AS uuid), :action, :slug, CAST(:writer AS jsonb),
            :bundle_sha256, CAST(:gates AS jsonb), NULL)
    RETURNING id
""")
_SIDE_EFFECTS_SQL = text(
    "UPDATE theo_paper_publications SET side_effects = CAST(:side_effects AS jsonb) WHERE id = :id"
)
_PUBLISH_SQL = text("""
    UPDATE research_requests
    SET status = 'completed',
        completed_at = NOW(),
        result_json = :result,
        is_public = TRUE,
        published_at = NOW(),
        published_by = :author,
        slug = :slug
    WHERE id = :id AND status IN ('researched', 'completed') AND is_public = FALSE
""")


def _read_row(session: Any, request_id: str) -> Any:
    row = session.execute(_ROW_SQL, {"id": request_id}).fetchone()
    if row is None:
        raise PublishInputError(f"research request {request_id} does not exist")
    return row


def _stored_result(row: Any) -> dict:
    return json.loads(row.result_json) if row.result_json else {}


def _journal(
    session: Any,
    *,
    request_id: str,
    action: str,
    slug: str | None,
    writer: dict,
    bundle_sha256: str,
    gates: dict,
) -> int:
    journal_id = session.execute(
        _JOURNAL_SQL,
        {
            "request_id": request_id,
            "action": action,
            "slug": slug,
            "writer": json.dumps(writer),
            "bundle_sha256": bundle_sha256,
            "gates": json.dumps(gates),
        },
    ).scalar_one()
    return int(journal_id)


def _verify(
    session: Any,
    request_id: str,
    *,
    result: dict,
    slug: str | None,
    published_by: str | None = None,
) -> None:
    """Re-read the committed row; raise when it is not what was written.

    published_by is checked when the write set it (a publish, a full republish).
    """
    row = session.execute(_VERIFY_SQL, {"id": request_id}).fetchone()
    if row is None:
        raise PublishVerificationError(f"{request_id} vanished after the commit")
    problems = []
    if row.status != "completed":
        problems.append(f"status is {row.status!r}")
    if row.is_public is not True:
        problems.append("is_public is not true")
    if row.slug != slug:
        problems.append(f"slug is {row.slug!r}, expected {slug!r}")
    if published_by is not None and row.published_by != published_by:
        problems.append(f"published_by is {row.published_by!r}, expected {published_by!r}")
    if json.loads(row.result_json or "null") != result:
        problems.append("result_json differs from what was written")
    if problems:
        raise PublishVerificationError(
            f"{request_id} was committed but the re-read row differs: " + "; ".join(problems)
        )


def _record_side_effects(session: Any, journal_id: int, effects: dict) -> None:
    session.execute(_SIDE_EFFECTS_SQL, {"id": journal_id, "side_effects": json.dumps(effects)})
    session.commit()


def run_publish_side_effects(
    *,
    request_id: str,
    slug: str,
    title: str,
    paper_text: str,
    author_username: str,
    author_discord_id: str,
    published_at: str,
    reindex: bool,
) -> dict[str, dict]:
    """IndexNow ping and Qdrant index after the commit (spec 2.6.5); also used by the founder route.

    Failures are returned, not raised: they are journalled and never undo a
    publish. The nightly 03:00 UTC reindex (vector_sync) is the backstop for
    Qdrant; Lyra's submit_recent re-announces papers published in the last 2 h.
    `reindex` deletes the paper's old sections first (a correction may have fewer).
    """
    from pipeline.indexnow import page_url
    from pipeline.indexnow import submit as indexnow_submit
    from pipeline.lyra.theo_research_index import delete_paper, index_paper

    effects: dict[str, dict] = {
        "indexnow": {"ok": indexnow_submit([page_url(f"/research/{slug}"), page_url("/research/")])}
    }
    try:
        if reindex:
            delete_paper(request_id)
        sections = index_paper(
            paper_id=request_id,
            paper_text=paper_text,
            paper_title=title,
            paper_slug=slug,
            author_username=author_username,
            author_discord_id=author_discord_id,
            published_at=published_at,
        )
    except Exception as exc:  # noqa: BLE001 — journalled in side_effects, never undoes the publish (spec 2.6.5)
        effects["qdrant"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    else:
        effects["qdrant"] = {"ok": sections > 0, "sections": sections}
    return effects


def notify_published(
    request_id: str, title: str, slug: str, url: str, journal_id: int, writer: dict
) -> dict[str, bool]:
    """Tell the owner that Claude published a paper (spec 0: automatic publish, owner notified).

    The thinking_log run_event is always written (log_thinking logs its own
    failure). The Discord embed goes out only while DISCORD_WEBHOOK_URL is set:
    send_discord_webhook returns False otherwise, and owner decision 5 keeps it
    unset for now. The sender is pipeline.utils.notify (api.services.notify only
    re-exports it): pipeline must not import api.
    """
    from pipeline.lyra.thinking_log import log_thinking
    from pipeline.utils.notify import send_discord_webhook

    log_thinking(
        "run_event",
        f"Paper published: {title[:200]}",
        {
            "request_id": request_id,
            "event": "paper_published",
            "slug": slug,
            "url": url,
            "journal_id": journal_id,
            "writer_model": writer["model"],
        },
    )
    sent = send_discord_webhook(
        {
            "embeds": [
                {
                    "title": "Theo paper published (written by Claude)",
                    "description": f"`{request_id}`\n**{title[:200]}**\n{url}",
                    "color": 0x2ECC71,
                }
            ]
        }
    )
    return {"discord": sent}


# ---------------------------------------------------------------------------
# Publish (spec 2.6)
# ---------------------------------------------------------------------------


def check_evidence_retention(
    old_evidence: list, new_evidence: list, old_corrections: list, appended: list
) -> dict:
    """Published evidence ids stay: an id is retired only by a correction naming it.

    A retired id is never reused and never named again, so the correction that
    retired it stays the last entry naming it: the page anchors a retired id
    on that entry (stream B's parse_corrections). Used by publish_paper (a
    paper the founder route unpublished keeps its ids; appended is [] there)
    and by correct_paper.
    """
    old_ids = {entry["id"] for entry in old_evidence}
    new_ids = {entry["id"] for entry in new_evidence if isinstance(entry, dict) and "id" in entry}
    named = {entry["evidence_id"] for entry in appended if entry.get("evidence_id")}
    previously_retired = {
        entry["evidence_id"] for entry in old_corrections if entry.get("evidence_id")
    } - old_ids
    issues = [
        f"{ev} removed without a correction entry naming it"
        for ev in sorted(old_ids - new_ids - named)
    ]
    issues += [
        f"{ev} was retired earlier and may not be reused"
        for ev in sorted(new_ids & previously_retired)
    ]
    issues += [
        f"{ev} was retired earlier; a retired id cannot be named again"
        for ev in sorted(named & previously_retired)
    ]
    issues += [
        f"a correction names {ev}, which this paper never had"
        for ev in sorted(named - old_ids - new_ids - previously_retired)
    ]
    return _gate(issues)


def publish_paper(
    session: Any,
    request_id: str,
    result: dict,
    *,
    author: str = PUBLISH_AUTHOR,
    writer: dict,
    dry_run: bool,
    bundle_sha256: str,
    images_root: Path = RESEARCH_IMAGES_DIR,
) -> PublishOutcome:
    """Gate, then publish a Claude-written paper in one guarded transaction with its journal row.

    Order: every gate (no repair; the last one runs the page's own validators
    on exactly the result_json about to be stored) -> slug with collision
    handling -> UPDATE guarded on status IN ('researched','completed') AND
    is_public = FALSE plus the journal INSERT, one commit -> re-read and verify
    -> IndexNow + Qdrant -> owner notice; the side effects are recorded in the
    journal row. A dry run stops after the slug. result_json keeps the row's
    `dossier` summary and, for a paper the founder route unpublished, its public
    record: the `corrections` log, the `videos` and every evidence id it had
    (the retention gate, spec 2.7). result.corrections itself must be [].
    """
    row = _read_row(session, request_id)
    previous = _stored_result(row)
    gates: dict[str, dict] = {
        "status": check_publish_status(row.status, row.is_public, dry_run=dry_run),
        "shape": check_publish_shape(result, writer),
    }
    stored: dict = {}
    if gates["shape"]["passed"]:
        gates["snapshot"] = check_snapshot(result)
        gates["artifact"], audit = check_artifact(result["report"])
        gates["quality"] = check_quality(result["quality_score"], audit, require_stored_passed=True)
        gates["evidence"] = check_evidence(result["report"], result["title"], result["evidence"])
        gates["retention"] = check_evidence_retention(
            previous.get("evidence", []), result["evidence"], previous.get("corrections", []), []
        )
        gates["images"] = check_images(
            request_id,
            result["report"],
            result["probative_images"],
            result["hero_image"],
            images_root=images_root,
        )
        stored = {**result, "audit": audit, "writer": writer}
        for key in ("dossier", "corrections", "videos"):
            if key in previous:
                stored[key] = previous[key]
        gates["page"] = check_page(request_id, stored)
    outcome = PublishOutcome(
        ok=all(gate["passed"] for gate in gates.values()),
        action="publish",
        request_id=request_id,
        dry_run=dry_run,
        gates=gates,
    )
    if not gates["shape"]["passed"]:
        return outcome

    from pipeline.indexnow import page_url

    slug = pick_slug(session, result["title"], request_id)
    outcome.slug = slug
    outcome.url = page_url(f"/research/{slug}")
    if dry_run or not outcome.ok:
        return outcome

    updated = session.execute(
        _PUBLISH_SQL,
        {"id": request_id, "result": json.dumps(stored), "author": author, "slug": slug},
    )
    if updated.rowcount != 1:
        session.rollback()
        raise PublishConflictError(
            f"{request_id} changed between read and write (status or is_public); nothing committed"
        )
    outcome.journal_id = _journal(
        session,
        request_id=request_id,
        action="publish",
        slug=slug,
        writer=writer,
        bundle_sha256=bundle_sha256,
        gates=gates,
    )
    session.commit()
    _verify(session, request_id, result=stored, slug=slug, published_by=author)
    outcome.side_effects = {
        **run_publish_side_effects(
            request_id=request_id,
            slug=slug,
            title=result["title"],
            paper_text=stored["published_report"],
            author_username=author,
            author_discord_id=row.user_id,
            published_at=datetime.now(UTC).isoformat(),
            reindex=False,
        ),
        "notify": notify_published(
            request_id, result["title"], slug, outcome.url, outcome.journal_id, writer
        ),
    }
    _record_side_effects(session, outcome.journal_id, outcome.side_effects)
    return outcome


# ---------------------------------------------------------------------------
# Corrections and videos (spec 2.7). Only a completed, public paper changes here.
# ---------------------------------------------------------------------------

_CORRECTION_ENTRY_KEYS = frozenset({"date", "text", "evidence_id"})
#: Every change to a public paper rewrites result_json only: slug, published_at
#: and published_by stay (a full republish included, owner decision 19).
_UPDATE_RESULT_SQL = text("""
    UPDATE research_requests
    SET result_json = :result
    WHERE id = :id AND status = 'completed' AND is_public = TRUE AND result_json = :previous
""")
#: The fresh Theo run a full republish was written from (C5 dossier_request_id)
#: leaves 'researched' in the republish's own transaction.
_CLOSE_DOSSIER_RUN_SQL = text("""
    UPDATE research_requests
    SET status = 'cancelled', error_message = :reason
    WHERE id = :id AND status = 'researched'
""")


def check_live_status(status: str, is_public: bool) -> dict:
    """Corrections and videos apply to a completed, public paper only."""
    issues = []
    if not (status == "completed" and is_public is True):
        issues.append(
            f"the paper must be completed and public (status={status!r}, is_public={is_public})"
        )
    return _gate(issues, status=status, is_public=bool(is_public))


def _correction_entry_issues(entries: Any, *, earliest: date | None, latest: date) -> list[str]:
    """Issues with corrections_append. Dates lie in [earliest, latest]: the page
    turns the newest one into JSON-LD dateModified. earliest is None only while
    the row is not public (the status gate reports that)."""
    if not isinstance(entries, list) or not entries:
        return ["corrections_append must be a non-empty list: every change is logged on the page"]
    issues = []
    for index, entry in enumerate(entries):
        label = f"corrections_append[{index}]"
        if not isinstance(entry, dict):
            issues.append(f"{label} must be an object")
            continue
        unknown = sorted(set(entry) - _CORRECTION_ENTRY_KEYS)
        if unknown:
            issues.append(f"{label} has unknown keys {unknown}")
        day = entry.get("date")
        try:
            parsed = date.fromisoformat(day) if isinstance(day, str) else None
        except ValueError:
            parsed = None
        if parsed is None or parsed.isoformat() != day:
            issues.append(f"{label}.date must be YYYY-MM-DD")
        elif (earliest is not None and parsed < earliest) or parsed > latest:
            issues.append(f"{label}.date must lie between the publication day and today")
        if not (isinstance(entry.get("text"), str) and entry["text"].strip()):
            issues.append(f"{label}.text must be a non-empty string")
        if "evidence_id" in entry and not (
            isinstance(entry["evidence_id"], str) and EVIDENCE_ID_RE.fullmatch(entry["evidence_id"])
        ):
            issues.append(f"{label}.evidence_id must look like ev-NN")
    return issues


def check_correction_shape(correction: dict, *, published_on: date | None, today: date) -> dict:
    """Value types of a correction input (the CLI checked the keys, contract C5).

    A full republish (`result`) is checked like a first publish: result.corrections
    must be [] there too, because the stored log is kept and grows only through
    corrections_append.
    """
    issues = check_writer(correction.get("writer"))
    if "report" in correction and not (
        isinstance(correction["report"], str) and correction["report"].strip()
    ):
        issues.append("report must be a non-empty string when given")
    if "evidence" in correction and not isinstance(correction["evidence"], list):
        issues.append("evidence must be a list when given")
    if "result" in correction:
        issues.extend(
            _result_issues(correction["result"], correction.get("writer"), republish=True)
        )
    issues.extend(
        _correction_entry_issues(
            correction.get("corrections_append"), earliest=published_on, latest=today
        )
    )
    return _gate(issues)


def _update_result(session: Any, row: Any, stored: dict) -> None:
    """Guarded write of a public paper's result_json (nothing else of the row changes)."""
    updated = session.execute(
        _UPDATE_RESULT_SQL,
        {"id": row.id, "result": json.dumps(stored), "previous": row.result_json},
    )
    if updated.rowcount != 1:
        session.rollback()
        raise PublishConflictError(f"{row.id} changed between read and write; nothing committed")


def check_dossier_source(session: Any, request_id: str, run_id: str) -> tuple[dict, dict | None]:
    """The fresh Theo run a full republish was written from (C5 `dossier_request_id`).

    Owner decisions 17 and 18: a legacy paper rewritten from a new Theo run on
    its question keeps its slug and published_at, so the rewrite republishes the
    public paper and takes the run's dossier. The run must exist, be
    'researched' and not be the paper itself. Returns (gate, the run's C2
    dossier summary when the gate passes, else None); the gate records the
    run's id and status, so the journal row names both runs.
    """
    run = None if run_id == request_id else session.execute(_ROW_SQL, {"id": run_id}).fetchone()
    status = run.status if run is not None else None
    if run_id == request_id:
        issues = ["dossier_request_id names the paper being republished"]
    elif run is None:
        issues = [f"research request {run_id} does not exist"]
    elif status != "researched":
        issues = [f"research request {run_id} is {status!r}, not 'researched'"]
    else:
        issues = []
    gate = _gate(issues, request_id=run_id, status=status)
    return gate, (None if issues else _stored_result(run)["dossier"])


def _close_dossier_run(session: Any, run_id: str, request_id: str) -> None:
    """Close the run whose dossier a republish used, in the republish's transaction.

    It leaves `theo_dossier list` and the feeder's unwritten-dossier count
    (Task 14); a run that is no longer 'researched' aborts the republish.
    """
    closed = session.execute(
        _CLOSE_DOSSIER_RUN_SQL,
        {"id": run_id, "reason": f"dossier used by the republish of {request_id}"},
    )
    if closed.rowcount != 1:
        session.rollback()
        raise PublishConflictError(f"{run_id} is no longer 'researched'; nothing committed")


def correct_paper(
    session: Any,
    request_id: str,
    correction: dict,
    *,
    bundle_sha256: str,
    dry_run: bool,
    images_root: Path = RESEARCH_IMAGES_DIR,
) -> PublishOutcome:
    """Re-gate and apply a correction to a public paper (contract C5).

    Three kinds: a log entry only (report and published_report stay exactly as
    stored, and the gates run on the text the page serves); a text correction
    (report and published_report change together, title, card, images, hero,
    quality_score and writer stay, except that `rewrite: true` stores this
    correction's writer); or, with `result`, a full republish that replaces the
    paper wholesale (a Claude rewrite of a legacy M3 paper, spec 2.6 step 4),
    gated like a first publish. A full republish and a `rewrite: true` text
    correction (owner decision 18's rewrite from the stored text) are announced
    with the same owner notice as a first publish (owner decision 21); a small
    fix and a log entry send none. The corrections log grows in every case,
    every evidence id is kept unless a correction names it, and slug,
    published_at and published_by never change (owner decision 19: a founder
    who published the legacy paper stays its publisher; the writer record says
    who wrote the rewrite). A full
    republish written from a fresh Theo run names it in `dossier_request_id`
    (owner decisions 17 and 18): the `dossier_source` gate checks the run, the
    stored `dossier` becomes the run's summary, and the run is closed in the
    same transaction. The CLI refuses `result` together with `report` or
    `evidence`, a `rewrite` that is not true, comes without `report` or with
    `evidence`, and a `dossier_request_id` without `result` (exit 2).
    """
    from pipeline.indexnow import page_url

    row = _read_row(session, request_id)
    current = _stored_result(row)
    stored_corrections = current.get("corrections", [])
    republish = "result" in correction
    # Claude's text replaces the public one wholesale: a full republish, or a
    # legacy paper rewritten from its stored text (C5 `rewrite`, owner decision
    # 18). Either stores this correction's writer and notifies the owner.
    claude_rewrite = republish or correction.get("rewrite") is True
    dossier_run = correction.get("dossier_request_id")
    dossier = None
    gates: dict[str, dict] = {
        "status": check_live_status(row.status, row.is_public),
        # published_at is `timestamp without time zone`, written as NOW() by the
        # UTC database: its date is the UTC publication day.
        "shape": check_correction_shape(
            correction,
            published_on=row.published_at.date() if row.published_at is not None else None,
            today=datetime.now(UTC).date(),
        ),
    }
    stored: dict = {}
    served = ""
    if gates["status"]["passed"] and gates["shape"]["passed"]:
        if republish:
            paper = correction["result"]
            gates["snapshot"] = check_snapshot(paper)
            if dossier_run is not None:
                gates["dossier_source"], dossier = check_dossier_source(
                    session, request_id, dossier_run
                )
            served = paper["report"]
            quality_score, require_stored_passed = paper["quality_score"], True
        else:
            paper = {**current, "evidence": correction.get("evidence", current.get("evidence", []))}
            # The page serves published_report (report only on a legacy row
            # without one). The founder block workflow assembles published_report
            # from the approved blocks, so it can differ from report: a
            # correction without `report` keeps both as stored and is gated on
            # the served text, never on the draft.
            if "report" in correction:
                served = correction["report"]
            else:
                served = current.get("published_report") or current.get("report", "")
            quality_score, require_stored_passed = current.get("quality_score") or {}, False
        gates["retention"] = check_evidence_retention(
            current.get("evidence", []),
            paper["evidence"],
            stored_corrections,
            correction["corrections_append"],
        )
        gates["artifact"], audit = check_artifact(served)
        gates["quality"] = check_quality(
            quality_score, audit, require_stored_passed=require_stored_passed
        )
        gates["evidence"] = check_evidence(served, paper["title"], paper["evidence"])
        gates["images"] = check_images(
            request_id,
            served,
            paper.get("probative_images") or [],
            paper.get("hero_image"),
            images_root=images_root,
        )
        stored = {
            **current,
            **paper,
            "corrections": [*stored_corrections, *correction["corrections_append"]],
            "audit": audit,
        }
        if republish or "report" in correction:
            stored["report"] = stored["published_report"] = served
        if claude_rewrite:
            stored["writer"] = correction["writer"]
        if dossier is not None:
            # The rewrite's research basis (C7): the fresh run's dossier summary.
            stored["dossier"] = dossier
        gates["page"] = check_page(request_id, stored)
    outcome = PublishOutcome(
        ok=all(gate["passed"] for gate in gates.values()),
        action="correct",
        request_id=request_id,
        dry_run=dry_run,
        slug=row.slug,
        url=page_url(f"/research/{row.slug}") if row.slug else None,
        gates=gates,
    )
    if dry_run or not outcome.ok:
        return outcome

    _update_result(session, row, stored)
    if dossier_run is not None:
        _close_dossier_run(session, dossier_run, request_id)
    outcome.journal_id = _journal(
        session,
        request_id=request_id,
        action="correct",
        slug=row.slug,
        writer=correction["writer"],
        bundle_sha256=bundle_sha256,
        gates=gates,
    )
    session.commit()
    _verify(session, request_id, result=stored, slug=row.slug)
    outcome.side_effects = run_publish_side_effects(
        request_id=request_id,
        slug=row.slug,
        title=stored["title"],
        paper_text=served,
        author_username=row.published_by,
        author_discord_id=row.user_id,
        # `timestamp without time zone`, written as NOW() by the UTC database: the same
        # '+00:00' form a first publish indexes.
        published_at=row.published_at.replace(tzinfo=UTC).isoformat(),
        reindex=True,
    )
    if claude_rewrite:
        # The same paper_published notice as a first publish (owner decision 21,
        # spec 0: Claude publishes automatically and the owner is notified).
        outcome.side_effects = {
            **outcome.side_effects,
            "notify": notify_published(
                request_id,
                stored["title"],
                row.slug,
                outcome.url,
                outcome.journal_id,
                correction["writer"],
            ),
        }
    _record_side_effects(session, outcome.journal_id, outcome.side_effects)
    return outcome


def check_video_shape(video: dict) -> dict:
    """Value types of a video registration (the CLI checked the keys, contract C6).

    An optional `poster` must be exactly poster_web_path(request_id,
    youtube_id): our own studio thumbnail in the paper's folder (owner decision
    13). Whether the file exists is the images gate's business.
    """
    issues = check_writer(video.get("writer"))
    if not (
        isinstance(video.get("youtube_id"), str) and YOUTUBE_ID_RE.fullmatch(video["youtube_id"])
    ):
        issues.append("youtube_id must be an 11-character YouTube id")
    if "poster" in video and video["poster"] != poster_web_path(
        video["request_id"], video["youtube_id"]
    ):
        issues.append("poster must be /data/research-images/<request_id>/video_<youtube_id>.jpg")
    if not (isinstance(video.get("title"), str) and video["title"].strip()):
        issues.append("title must be a non-empty string")
    published_at = video.get("published_at")
    try:
        valid_time = (
            isinstance(published_at, str)
            and datetime.fromisoformat(published_at).tzinfo is not None
        )
    except ValueError:
        valid_time = False
    if not valid_time:
        issues.append("published_at must be an ISO 8601 date-time with a UTC offset")
    stamps = video.get("evidence_timestamps")
    if not isinstance(stamps, dict):
        issues.append("evidence_timestamps must be an object")
    else:
        for ev, seconds in stamps.items():
            if not (isinstance(seconds, int) and not isinstance(seconds, bool) and seconds >= 0):
                issues.append(f"evidence_timestamps[{ev!r}] must be a whole number of seconds >= 0")
    return _gate(issues)


def register_video(
    session: Any,
    request_id: str,
    video: dict,
    *,
    bundle_sha256: str,
    dry_run: bool,
    images_root: Path = RESEARCH_IMAGES_DIR,
) -> PublishOutcome:
    """Append a YouTube video to result_json.videos of a public paper (C6) and ping IndexNow.

    A `poster` (owner decision 13) is stored with the video only when the
    registration sends one, and only once its file exists in the paper's
    folder: the images gate runs check_images on it. Without a poster the
    images gate checks nothing and the page keeps its posterless player.
    """
    from pipeline.indexnow import page_url
    from pipeline.indexnow import submit as indexnow_submit

    row = _read_row(session, request_id)
    gates: dict[str, dict] = {
        "status": check_live_status(row.status, row.is_public),
        "shape": check_video_shape(video),
    }
    current = _stored_result(row)
    stored: dict = {}
    if gates["status"]["passed"] and gates["shape"]["passed"]:
        # A timestamp may name a current evidence id or one a correction retired
        # (a video made before the correction keeps it): the page's anchor_ids.
        current_ids = {entry["id"] for entry in current.get("evidence", [])}
        retired = {
            entry["evidence_id"]
            for entry in current.get("corrections", [])
            if entry.get("evidence_id")
        } - current_ids
        gates["evidence_refs"] = _gate(
            [
                f"{ev} is neither an evidence id of this paper nor retired by a correction"
                for ev in sorted(set(video["evidence_timestamps"]) - current_ids - retired)
            ]
        )
        already = any(v.get("youtube_id") == video["youtube_id"] for v in current.get("videos", []))
        gates["duplicate"] = _gate(
            [f"video {video['youtube_id']} is already registered"] if already else []
        )
        gates["images"] = check_images(
            request_id,
            "",
            [{"web_path": video["poster"]}] if "poster" in video else [],
            None,
            images_root=images_root,
        )
        entry = {
            "youtube_id": video["youtube_id"],
            "title": video["title"],
            "published_at": video["published_at"],
            "evidence_timestamps": video["evidence_timestamps"],
            "registered_at": datetime.now(UTC).isoformat(),
        }
        if "poster" in video:
            entry["poster"] = video["poster"]
        stored = {**current, "videos": [*current.get("videos", []), entry]}
        gates["page"] = check_page(request_id, stored)
    outcome = PublishOutcome(
        ok=all(gate["passed"] for gate in gates.values()),
        action="register_video",
        request_id=request_id,
        dry_run=dry_run,
        slug=row.slug,
        url=page_url(f"/research/{row.slug}") if row.slug else None,
        gates=gates,
    )
    if dry_run or not outcome.ok:
        return outcome

    _update_result(session, row, stored)
    outcome.journal_id = _journal(
        session,
        request_id=request_id,
        action="register_video",
        slug=row.slug,
        writer=video["writer"],
        bundle_sha256=bundle_sha256,
        gates=gates,
    )
    session.commit()
    _verify(session, request_id, result=stored, slug=row.slug)
    outcome.side_effects = {
        "indexnow": {"ok": indexnow_submit([page_url(f"/research/{row.slug}")])}
    }
    _record_side_effects(session, outcome.journal_id, outcome.side_effects)
    return outcome


# ---------------------------------------------------------------------------
# Maintenance tools (Task 21b). A journalled paper changes only through this module.
# ---------------------------------------------------------------------------

#: SQL condition on a research_requests row (unqualified column, no alias): its
#: result_json carries one of the four keys only this module writes and the
#: paper page validates (stream B's PAPER_EXTRAS_COLUMNS). Such a paper changes
#: only through theo_publish, where every write passes the page's own
#: validators and is journalled (C7). The maintenance tools that rewrite
#: result_json (the image backfills and cleaners in pipeline/lyra, the citation
#: repair, the payload swap and the gallery script in scripts/) put
#: `AND NOT (JOURNALLED_PAPER_SQL)` into their row SELECT and their UPDATE.
#: A NULL result_json satisfies neither the condition nor its NOT (SQL NULL),
#: so those statements never reach a row without a payload. The one definition.
JOURNALLED_PAPER_SQL = "result_json::jsonb ?| array['evidence','videos','corrections','writer']"

_NAMED_JOURNALLED_SQL = text(
    "SELECT 1 FROM research_requests "
    f"WHERE (slug = :name OR id::text = :name) AND {JOURNALLED_PAPER_SQL}"
)
_UNJOURNALLED_UPDATE_SQL = text(
    "UPDATE research_requests SET result_json = :json "
    f"WHERE id = :id AND NOT ({JOURNALLED_PAPER_SQL})"
)


class JournalledPaperError(RuntimeError):
    """A maintenance tool reached a paper that changes only through theo_publish."""


def refuse_journalled_paper(conn: Any, name: str) -> None:
    """Raise when the paper a maintenance tool names (slug or request id) is journalled.

    The tools' own SELECT skips a journalled row, so without this a run that
    names one would print "No papers found" instead of saying why.
    """
    if conn.execute(_NAMED_JOURNALLED_SQL, {"name": name}).fetchone() is not None:
        raise JournalledPaperError(
            f"{name}: a journalled paper changes only through theo_publish --correct"
        )


def write_unjournalled_result(conn: Any, request_id: str, result: dict) -> None:
    """A maintenance tool's write of result_json, never onto a journalled paper.

    The tools read first and write later (the image backfill spends minutes of
    LLM calls on each paper): a paper theo_publish wrote in between is
    journalled by then, and this UPDATE matches no row instead of overwriting
    it. The caller commits.
    """
    written = conn.execute(_UNJOURNALLED_UPDATE_SQL, {"id": request_id, "json": json.dumps(result)})
    if written.rowcount != 1:
        conn.rollback()
        raise JournalledPaperError(
            f"{request_id}: journalled or deleted since it was read; nothing written "
            "(a journalled paper changes only through theo_publish --correct)"
        )
