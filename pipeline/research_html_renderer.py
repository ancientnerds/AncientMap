"""
Markdown preparation and post-render steps for the public research papers.

The paper pages themselves render through React since the react-ssr
cutover (Task 12; Task 16 deleted the full-document renderers that lived
here). What stays Python is the stored-markdown massaging shared by the
paper route and its Medium copy (api/routes/research_html.py): reference
reflow, leading-title stripping and the Medium-safe caption rewrite. Since
the studio (spec 2026-09-26 §2.7/§3.7) it also validates the optional
evidence/videos/corrections/writer keys of a Claude-written paper and
injects the #ev-NN evidence anchors into the rendered body.

Module-level imports stay stdlib-only: static_exporter and the landing
route import PUBLIC_PAPER_WHERE from here. What comes from
pipeline.lyra.theo_publishing (EVIDENCE_ID_RE, YOUTUBE_ID_RE,
poster_web_path, normalize_anchor_text, MIN_ANCHOR_CHARS) is imported
inside the functions that use it.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, NamedTuple

from pipeline.lyra.theo_image_captions import _META_VOICE_RE

# What makes a paper public: reviewed and released, finished, and addressable.
# The one definition, shared by the SEO pages (api/routes/research_html.py)
# and the homepage hub snapshot (pipeline/static_exporter.py) so a paper
# cannot be listed in one place and 404 in the other. Expects the
# research_requests alias `r`.
PUBLIC_PAPER_WHERE = "r.is_public = TRUE AND r.status = 'completed' AND r.slug IS NOT NULL"

_REFERENCES_HEADING_RE = re.compile(
    r"^#{1,3}\s*(References|Sources|Bibliography)\b.*$", re.M | re.I
)
_BARE_URL_RE = re.compile(r"(?<![(<\[])(https?://[^\s<>()\[\]]+)")
_DOI_RE = re.compile(r"\bDOI:\s*(10\.\S+?)(?=[\s,;]|$)")


def format_references_md(content_md: str) -> str:
    """
    Rework the References section of a paper for clean rendering.

    Theo emits references as consecutive '[N] ...' lines with bare URLs —
    markdown collapses those into one giant paragraph with dead links.
    This gives each reference its own paragraph and turns bare URLs and
    DOIs into clickable links. Only text after the References heading is
    touched; the paper body stays untouched.
    """
    m = _REFERENCES_HEADING_RE.search(content_md)
    if not m:
        return content_md
    body, refs = content_md[: m.end()], content_md[m.end() :]
    refs = re.sub(r"\n(?=\[\d+\]\s)", "\n\n", refs)
    refs = _DOI_RE.sub(r"DOI: [\1](https://doi.org/\1)", refs)
    refs = _BARE_URL_RE.sub(r"<\1>", refs)
    return body + refs


# Image block as Theo stores it: image line, blank line, italic caption
# line, [Source](...) line.
_FIGURE_BLOCK_RE = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<img>[^)\s]+)\)\s*\n\s*\n"
    r"\*(?P<cap>[^*\n]+)\*\s*\n"
    r"\[Source\]\((?P<src>[^)]+)\)"
)

# Editorial meta-voice that older papers baked into caption tails ("Lets the
# reader verify that...", "Image placed by the paper writer..."). The caption
# builder no longer emits these (theo_image_captions._META_VOICE_RE), but
# published papers carry them in stored markdown — scrub at render time.
_CAPTION_LEAK_RE = re.compile(
    r"\s*(?:Lets?\s+the\s+reader\s+verify\b|Allows?\s+the\s+reader\b|"
    r"Image\s+placed\s+by\s+the\s+paper\s+writer\b)[^*]*$",
    re.IGNORECASE,
)

# Caption + Source block WITHOUT a preceding image (reflow sometimes detaches
# writer-image captions). "Photo:" is required so normal italic emphasis in
# prose is never touched.
_ORPHAN_CAPTION_RE = re.compile(
    r"\*(?P<cap>[^*\n]*Photo:[^*\n]+)\*\s*\n\[Source\]\((?P<src>[^)]+)\)"
)

# Structural caption split: "{lead}. Photo: {artist} / {SOURCE_LABEL}. {tail}".
# The attribution always ends with a known source label; the tail (LLM
# rationale) never contains one — verified across all 10 published papers
# (2026-07-31). Greedy head = split at the LAST label, so artists like
# "Internet Archive Book Images" can't cut the attribution short.
_ATTRIBUTION_SPLIT_RE = re.compile(
    r"^(?P<head>.*Photo:.*"
    r"(?:Wikimedia Commons|Europeana|Open Access|Internet Archive|Getty Museum|"
    r"Musée du Louvre|Portable Antiquities Scheme|The Met|Smithsonian))"
    r"\.\s*(?P<tail>.+)$",
    re.S,
)


_LEADING_HEADING_RE = re.compile(r"^\s*(#{1,3})\s+([^\n]+)\n+")


def strip_leading_title_heading(content_md: str, title: str) -> str:
    """Papers begin with their own title as a markdown heading — 7 of 10
    stored papers use '## Title', 3 use '# Title' (checked 2026-07-31). The
    paper page and the Medium copy template render the title themselves, so
    the leading heading is stripped when it's an H1 (always the title in
    these papers) or when its text matches the paper title. A genuine
    section heading like '## Introduction' is never touched."""
    m = _LEADING_HEADING_RE.match(content_md)
    if not m:
        return content_md

    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", s.casefold())

    if m.group(1) == "#" or norm(m.group(2)) == norm(title or ""):
        return content_md[m.end() :]
    return content_md


def _scrub_caption(raw_cap: str) -> str:
    """Scrub editorial meta-voice out of a stored caption.

    Generic scrub: drop any rationale tail after the attribution that talks
    about the paper/reader/evidence apparatus instead of the artifact (28
    leaked captions across 9 of 10 published papers, many phrasings —
    pattern lists don't scale).
    """
    cap = _CAPTION_LEAK_RE.sub("", raw_cap).strip()
    m = _ATTRIBUTION_SPLIT_RE.match(cap)
    if m and _META_VOICE_RE.search(m.group("tail")):
        cap = m.group("head")
    cap = cap.replace("Unknown authorUnknown author", "Unknown author")
    return cap.strip().rstrip(".")


# The reflow step sometimes splits a caption block INTO a sentence — the
# stored markdown then continues with "\n. The excitement was..." right
# after [Source](...). Consumed together with the caption block so no
# orphaned "." starts the following paragraph.
_STRAY_PERIOD = r"(?P<stray>\s*\n\.\s*)?"


def format_image_captions_medium(content_md: str) -> str:
    """
    Medium-paste-safe variant: Medium's editor DROPS figcaption content when
    pasting (images lost their captions entirely — observed 2026-07-31), but
    keeps italic text paragraphs. Rewrite caption blocks as scrubbed markdown:
    image, then '*caption.* [Source](url)' as its own paragraph.
    """

    def _cap_md(raw_cap: str, src: str) -> str:
        cap = _scrub_caption(raw_cap)
        lead = f"*{cap}.* " if cap else ""
        return f"{lead}[Source]({src})"

    def _fig(m: re.Match) -> str:
        alt = m.group("alt").split("|")[-1].strip()
        return f"![{alt}]({m.group('img')})\n\n{_cap_md(m.group('cap'), m.group('src'))}\n\n"

    result = _figure_re_with_stray().sub(_fig, content_md)

    def _orphan(m: re.Match) -> str:
        return f"{_cap_md(m.group('cap'), m.group('src'))}\n\n"

    return _orphan_re_with_stray().sub(_orphan, result)


def _figure_re_with_stray() -> re.Pattern:
    return re.compile(_FIGURE_BLOCK_RE.pattern + _STRAY_PERIOD)


def _orphan_re_with_stray() -> re.Pattern:
    return re.compile(_ORPHAN_CAPTION_RE.pattern + _STRAY_PERIOD)


def paper_markdown(report: str, title: str) -> str:
    """The stored report, prepared for rendering: the leading title heading
    stripped and the References reflowed (the two helpers above).

    One definition for the paper page, its Medium copy and the publish gate's
    evidence-anchor check, so the gate resolves anchors against exactly the
    HTML the page will serve.
    """
    return format_references_md(strip_leading_title_heading(report, title))


# ── Claude-written papers: evidence, videos, corrections, writer ─────────────
# Studio spec 2026-09-26 §2.7/§3.7. Four optional result_json keys sit next to
# the report: evidence[] (checkable claims, each tied to one paragraph by its
# anchor_text), videos[] (registered YouTube videos, the second each evidence
# paragraph appears at and, optionally, our own poster image), corrections[]
# (the public log) and writer (who wrote and published the paper, the source
# of the AI disclosure line).
# The evidence stays out of the markdown on purpose: the citation gate, TTS,
# the Qdrant index and the CC BY API all read the report text, and none of
# them should see anchor syntax. Papers without these keys render as before.

# Selected next to PAPER_SUMMARY_COLUMNS (api/routes/public_v1.py) wherever a
# single paper is read. jsonb `->` hands psycopg2 a decoded list/dict, and
# NULL (key absent) arrives as None.
PAPER_EXTRAS_COLUMNS = """
    r.result_json::jsonb->'evidence' AS evidence,
    r.result_json::jsonb->'videos' AS videos,
    r.result_json::jsonb->'corrections' AS corrections,
    r.result_json::jsonb->'writer' AS writer
"""

# Evidence ids ("ev-NN") are linked from video descriptions forever: never
# renumbered, retired only by a correction that names them (spec §2.7). Their
# format is pipeline.lyra.theo_publishing.EVIDENCE_ID_RE, the one definition the
# publish gate, this page, the studio's local check and the case file share;
# parse_evidence and parse_corrections import it inside the function. A video's
# id format is theo_publishing.YOUTUBE_ID_RE and its poster's path
# theo_publishing.poster_web_path, both imported by parse_videos.
_ISO_DAY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_WRITER_PUBLISHED = ("automatic", "manual")


class PaperPageError(ValueError):
    """A paper's result_json extras cannot be rendered as stored.

    Raised, never swallowed: the publish gate runs the same checks before a
    paper goes public, so meeting this on a page means gate and page disagree,
    which is a bug to fix rather than a state to paper over.
    """


class VideoMoment(NamedTuple):
    """One "video at m:ss" link: where in which video an evidence paragraph is shown."""

    youtube_id: str
    seconds: int
    title: str


@dataclass(frozen=True)
class PaperExtras:
    """The validated optional keys of one paper (see parse_* below)."""

    evidence: list[dict[str, Any]]
    videos: list[dict[str, Any]]
    corrections: list[dict[str, Any]]
    writer: dict[str, Any] | None


def _text_field(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PaperPageError(f"{where} must be a non-empty string, got {value!r}")
    return value


def _objects(value: Any, key: str) -> list[dict[str, Any]]:
    """A list of JSON objects; None means the paper has no such key."""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise PaperPageError(f"result_json.{key} must be a list of objects, got {value!r}")
    return value


def parse_evidence(raw: Any) -> list[dict[str, Any]]:
    """result_json.evidence -> [{id, anchor_text, claim}] with unique ev-NN ids."""
    # Imported here, not at module level: the light importers of this module
    # (static_exporter, the landing route) never need the publish module, and
    # theo_publishing's gates import this module back.
    from pipeline.lyra.theo_publishing import EVIDENCE_ID_RE

    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, item in enumerate(_objects(raw, "evidence")):
        ev_id = item.get("id")
        if not isinstance(ev_id, str) or not EVIDENCE_ID_RE.fullmatch(ev_id):
            raise PaperPageError(f"evidence[{i}].id must look like ev-NN, got {ev_id!r}")
        if ev_id in seen:
            raise PaperPageError(f"evidence id {ev_id} appears twice")
        seen.add(ev_id)
        entries.append(
            {
                "id": ev_id,
                "anchor_text": _text_field(item.get("anchor_text"), f"{ev_id}.anchor_text"),
                "claim": _text_field(item.get("claim"), f"{ev_id}.claim"),
            }
        )
    return entries


def parse_corrections(raw: Any, evidence_ids: set[str]) -> list[dict[str, Any]]:
    """result_json.corrections -> [{date, text, evidence_id, holds_anchor}].

    A correction may name the evidence paragraph it concerns. When that id is
    no longer among the paper's evidence, a correction retired it: the last
    entry naming it (the publish gate lets earlier entries name the id only
    while it was current, and never lets anyone name it once retired). That
    entry carries the id itself (holds_anchor): a video description that links
    #ev-NN then lands on the correction that explains the change instead of
    nowhere.
    """
    # Lazy for the same reason as in parse_evidence.
    from pipeline.lyra.theo_publishing import EVIDENCE_ID_RE

    entries: list[dict[str, Any]] = []
    for i, item in enumerate(_objects(raw, "corrections")):
        day = item.get("date")
        if not isinstance(day, str) or not _ISO_DAY_RE.fullmatch(day):
            raise PaperPageError(f"corrections[{i}].date must be YYYY-MM-DD, got {day!r}")
        try:
            date.fromisoformat(day)
        except ValueError as exc:
            raise PaperPageError(f"corrections[{i}].date {day!r} is not a calendar day") from exc
        ev_id = item.get("evidence_id")
        if ev_id is not None and (
            not isinstance(ev_id, str) or not EVIDENCE_ID_RE.fullmatch(ev_id)
        ):
            raise PaperPageError(
                f"corrections[{i}].evidence_id must look like ev-NN, got {ev_id!r}"
            )
        entries.append(
            {
                "date": day,
                "text": _text_field(item.get("text"), f"corrections[{i}].text"),
                "evidence_id": ev_id,
                "holds_anchor": False,
            }
        )
    anchored: set[str] = set()
    for entry in reversed(entries):
        ev_id = entry["evidence_id"]
        if ev_id is not None and ev_id not in evidence_ids and ev_id not in anchored:
            entry["holds_anchor"] = True
            anchored.add(ev_id)
    return entries


def parse_videos(raw: Any, anchor_ids: set[str], request_id: str) -> list[dict[str, Any]]:
    """result_json.videos -> [{youtube_id, title, published_at, evidence_timestamps, poster}].

    anchor_ids are the ids a timestamp may name: the current evidence ids plus
    the ids retired by a correction (a video published before the correction
    keeps its timestamps). `poster` is our own studio thumbnail (owner
    decision #13, spec §2.7), stored only when the video was registered with
    one and then exactly theo_publishing.poster_web_path(request_id,
    youtube_id); the page draws it from our server inside the click-to-play
    link. None means the video was registered without one, a valid state:
    the page shows the posterless player. Either way the page loads nothing
    from YouTube before the click.
    """
    # Lazy for the same reason as in parse_evidence.
    from pipeline.lyra.theo_publishing import YOUTUBE_ID_RE, poster_web_path

    entries: list[dict[str, Any]] = []
    for i, item in enumerate(_objects(raw, "videos")):
        youtube_id = item.get("youtube_id")
        if not isinstance(youtube_id, str) or not YOUTUBE_ID_RE.fullmatch(youtube_id):
            raise PaperPageError(f"videos[{i}].youtube_id must be a YouTube id, got {youtube_id!r}")
        poster = item.get("poster")
        if "poster" in item:
            expected = poster_web_path(request_id, youtube_id)
            if poster != expected:
                raise PaperPageError(f"videos[{i}].poster must be {expected}, got {poster!r}")
        published_at = _text_field(item.get("published_at"), f"videos[{i}].published_at")
        try:
            datetime.fromisoformat(published_at)
        except ValueError as exc:
            raise PaperPageError(
                f"videos[{i}].published_at {published_at!r} is not ISO 8601"
            ) from exc
        stamps = item.get("evidence_timestamps")
        if not isinstance(stamps, dict):
            raise PaperPageError(f"videos[{i}].evidence_timestamps must be an object")
        for ev_id, seconds in stamps.items():
            if ev_id not in anchor_ids:
                raise PaperPageError(
                    f"videos[{i}] times {ev_id!r}, which is neither an evidence id "
                    "nor retired by a correction"
                )
            if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds < 0:
                raise PaperPageError(f"videos[{i}] time for {ev_id} must be whole seconds >= 0")
        entries.append(
            {
                "youtube_id": youtube_id,
                "title": _text_field(item.get("title"), f"videos[{i}].title"),
                "published_at": published_at,
                "evidence_timestamps": dict(stamps),
                "poster": poster,
            }
        )
    return entries


def parse_writer(raw: Any) -> dict[str, Any] | None:
    """result_json.writer -> the five disclosure fields, or None for older papers."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise PaperPageError(f"result_json.writer must be an object, got {raw!r}")
    published = raw.get("published")
    if published not in _WRITER_PUBLISHED:
        raise PaperPageError(
            f"writer.published must be one of {_WRITER_PUBLISHED}, got {published!r}"
        )
    human_review = raw.get("human_review")
    if not isinstance(human_review, bool):
        raise PaperPageError(f"writer.human_review must be true or false, got {human_review!r}")
    return {
        "model": _text_field(raw.get("model"), "writer.model"),
        "tool": _text_field(raw.get("tool"), "writer.tool"),
        "research_model": _text_field(raw.get("research_model"), "writer.research_model"),
        "published": published,
        "human_review": human_review,
    }


def paper_extras(row: Any) -> PaperExtras:
    """Validate a paper row's PAPER_EXTRAS_COLUMNS in one pass.

    row.id is the request id in text form, as PAPER_SUMMARY_COLUMNS selects it
    (r.id::text) and the publish gate's check_page passes it: it names the one
    valid poster path of each video. Other attributes are ignored.
    """
    evidence = parse_evidence(row.evidence)
    current = {entry["id"] for entry in evidence}
    corrections = parse_corrections(row.corrections, current)
    retired = {c["evidence_id"] for c in corrections if c["holds_anchor"]}
    videos = parse_videos(row.videos, current | retired, row.id)
    return PaperExtras(evidence, videos, corrections, parse_writer(row.writer))


def evidence_video_moments(extras: PaperExtras) -> dict[str, list[VideoMoment]]:
    """ev id -> its moments in the paper's videos, in video order.

    Only current evidence ids get a link: a retired id has no paragraph left,
    its anchor lives on the correction that retired it.
    """
    current = {entry["id"] for entry in extras.evidence}
    moments: dict[str, list[VideoMoment]] = {}
    for video in extras.videos:
        for ev_id, seconds in video["evidence_timestamps"].items():
            if ev_id in current:
                moments.setdefault(ev_id, []).append(
                    VideoMoment(video["youtube_id"], seconds, video["title"])
                )
    return moments


def page_extras_payload(extras: PaperExtras) -> dict[str, Any]:
    """The SSR payload keys for the extras, each present only when the paper has it.

    An older paper gets {}, so its route payload stays byte-identical to the
    one before this feature (ResearchRoute declares the keys optional). A
    video's poster is its web path or None (ResearchVideo.poster).
    """
    payload: dict[str, Any] = {}
    if extras.videos:
        payload["videos"] = [
            {key: video[key] for key in ("youtube_id", "title", "published_at", "poster")}
            for video in extras.videos
        ]
    if extras.corrections:
        payload["corrections"] = extras.corrections
    if extras.writer is not None:
        payload["writer"] = extras.writer
    return payload
