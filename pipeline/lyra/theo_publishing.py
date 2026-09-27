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
import re
import unicodedata

from pipeline.lyra.theo_citations import (
    _is_non_prose_block,
    _split_prose_into_paragraphs,
    split_artifact,
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
