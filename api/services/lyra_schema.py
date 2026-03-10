"""
Lyra structured output schema and marker expansion.

Mercury supports `response_format: json_schema` for guaranteed structured JSON.
The LLM places guillemet markers (e.g. «s0», «c0») in its text and fills
corresponding arrays. expand_markers() resolves these into the markdown link
syntax the frontend already handles.
"""

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON Schema for Mercury structured output (OpenAI json_schema format)
# ---------------------------------------------------------------------------

LYRA_RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "LyraResponse",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Markdown response with guillemet markers like «s0», «c0», «v0», «e0», «i0», «l0», «f0»",
                },
                "sites": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "marker": {"type": "string"},
                            "name": {"type": "string"},
                            "id": {"type": "string"},
                        },
                        "required": ["marker", "name", "id"],
                        "additionalProperties": False,
                    },
                },
                "coords": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "marker": {"type": "string"},
                            "lat": {"type": "number"},
                            "lon": {"type": "number"},
                        },
                        "required": ["marker", "lat", "lon"],
                        "additionalProperties": False,
                    },
                },
                "videos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "marker": {"type": "string"},
                            "channel": {"type": "string"},
                            "video_id": {"type": "string"},
                            "timestamp_seconds": {"type": "integer"},
                        },
                        "required": ["marker", "channel", "video_id", "timestamp_seconds"],
                        "additionalProperties": False,
                    },
                },
                "empires": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "marker": {"type": "string"},
                            "name": {"type": "string"},
                            "polity_id": {"type": "string"},
                        },
                        "required": ["marker", "name", "polity_id"],
                        "additionalProperties": False,
                    },
                },
                "images": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "marker": {"type": "string"},
                            "title": {"type": "string"},
                            "original_url": {"type": "string"},
                            "author": {"type": "string"},
                            "license": {"type": "string"},
                        },
                        "required": ["marker", "title", "original_url", "author", "license"],
                        "additionalProperties": False,
                    },
                },
                "links": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "marker": {"type": "string"},
                            "text": {"type": "string"},
                            "url": {"type": "string"},
                        },
                        "required": ["marker", "text", "url"],
                        "additionalProperties": False,
                    },
                },
                "countries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "marker": {"type": "string"},
                            "name": {"type": "string"},
                            "code": {"type": "string"},
                        },
                        "required": ["marker", "name", "code"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": [
                "text",
                "sites",
                "coords",
                "videos",
                "empires",
                "images",
                "links",
                "countries",
            ],
            "additionalProperties": False,
        },
    },
}


# ---------------------------------------------------------------------------
# Marker expansion — resolve guillemet markers into frontend markdown links
# ---------------------------------------------------------------------------

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
_MARKER_RE = re.compile(
    r"\u00ab[a-z]+\d+(?:[–\-][a-z]*\d+)?\u00bb"
)  # Matches «s0», «c1», «c2–c5», etc.

# Reference array key names used in structured output
_REF_KEYS = ("sites", "coords", "videos", "empires", "images", "links", "countries")


def clean_response_text(text: str) -> str:
    """Strip artifacts that should never appear in user-facing responses.

    Consolidates ALL text cleanup into one place:
    - JSON code blocks containing marker data
    - Bare JSON array patterns with marker keys
    - Stray guillemet markers
    - JSON wrapper remnants
    """
    # 1. Remove ```json ... ``` fenced code blocks (handles nested braces)
    text = re.sub(r"```json\s*[\s\S]*?```", "", text)
    # 2. Remove bare JSON object blocks with marker keys (e.g. { "sites": [...], ... })
    #    Match opening { through closing } when the block contains ref array keys
    text = re.sub(
        r'\{\s*"(?:text|sites|coords|videos|empires|images|links|countries)"\s*:[\s\S]*?\n\}',
        "",
        text,
    )
    # 3. Remove stray guillemet markers
    text = _MARKER_RE.sub("", text)
    # 4. Clean up empty JSON wrapper remnants
    text = re.sub(r"[{},]\s*[{},]", "", text)
    text = re.sub(r"^\s*[{}]\s*$", "", text, flags=re.MULTILINE)
    # 5. Remove "text": "..." JSON wrapper if present
    text = re.sub(r'^"text"\s*:\s*"', "", text)
    # 6. Fix doubled image markdown: ![title]![title](url) → ![title](url)
    text = re.sub(r"!\[([^\]]*)\]\s*!\[([^\]]*)\]\(", r"![\1](", text)
    # 7. Fix nested image markdown: ![outer](![inner](url)attr) → ![inner](url)attr
    text = re.sub(r"!\[[^\]]*\]\(\s*(!\[[^\]]*\]\([^)]+\))([^)]*)\)", r"\1\2", text)
    # 8. Fix broken link syntax: [text][text](url) → [text](url)
    text = re.sub(r"\[([^\]]*)\]\s*\[([^\]]*)\]\(", r"[\1](", text)
    # 9. Strip bare marker references without guillemets: [s0], [c1], etc.
    text = re.sub(r"\[(?:s|c|v|e|i|l|f)\d+\](?!\()", "", text)
    # 10. Clean orphaned "see ." left after marker removal
    text = re.sub(r",?\s+see\s+\.\s*$", ".", text, flags=re.MULTILINE)
    # 11. Collapse excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"  +", " ", text)
    return text.strip()


def _format_timestamp(seconds: int) -> str:
    """Format seconds as m:ss."""
    m = seconds // 60
    s = seconds % 60
    return f"{m}:{s:02d}"


def expand_markers(parsed: dict, all_news: list[dict] | None = None) -> tuple[str, list[str]]:
    """Expand guillemet markers in parsed structured response into markdown links.

    Args:
        parsed: Parsed LyraResponse JSON with text + reference arrays.
        all_news: List of news items (from SSE news events) for video index lookup.

    Returns:
        (expanded_text, validation_issues) — the final markdown and any issues found.
    """
    text = parsed.get("text", "")
    issues: list[str] = []

    # Build lookup dicts: normalized marker string -> entry
    # LLM may use "s0" or "«s0»" in arrays — normalize to bare form (s0)
    def _norm(m: str) -> str:
        return m.strip("\u00ab\u00bb")

    site_map = {_norm(e["marker"]): e for e in parsed.get("sites", [])}
    coord_map = {_norm(e["marker"]): e for e in parsed.get("coords", [])}
    video_map = {_norm(e["marker"]): e for e in parsed.get("videos", [])}
    empire_map = {_norm(e["marker"]): e for e in parsed.get("empires", [])}
    image_map = {_norm(e["marker"]): e for e in parsed.get("images", [])}
    link_map = {_norm(e["marker"]): e for e in parsed.get("links", [])}
    country_map = {_norm(e["marker"]): e for e in parsed.get("countries", [])}

    # Build news video_id -> index lookup
    news_index: dict[str, int] = {}
    if all_news:
        for i, n in enumerate(all_news):
            vid = n.get("video_id", "")
            if vid:
                news_index[vid] = i

    def _replace_marker(match: re.Match) -> str:
        raw_marker = match.group(0)
        marker = _norm(raw_marker)  # Strip guillemets: «s0» → s0

        # Sites: «sN» → [name](site:id) — only if id is a valid UUID
        if marker in site_map:
            e = site_map[marker]
            sid = e.get("id", "")
            if sid and _UUID_RE.match(sid):
                return f"[{e['name']}](site:{sid})"
            # Non-UUID or empty ID: output plain name, don't create broken link
            issues.append(f"Site '{e['name']}' has invalid ID '{sid}', rendered as plain text")
            return e["name"]

        # Coords: «cN» → [lat, lon](lyra-coord:lat,lon)
        if marker in coord_map:
            e = coord_map[marker]
            return f"[{e['lat']}, {e['lon']}](lyra-coord:{e['lat']},{e['lon']})"

        # Videos: «vN» → [▶ channel MM:SS](lyra-video:INDEX) or direct YouTube link
        if marker in video_map:
            e = video_map[marker]
            ts = e.get("timestamp_seconds", 0)
            ts_label = f" {_format_timestamp(ts)}" if ts else ""
            # Try to find video in all_news for lyra-video:INDEX
            idx = news_index.get(e["video_id"])
            if idx is not None:
                return f"[▶ {e['channel']}{ts_label}](lyra-video:{idx})"
            # Fallback: direct YouTube link
            yt_url = f"https://youtu.be/{e['video_id']}"
            if ts:
                yt_url += f"?t={ts}"
            return f"[▶ {e['channel']}{ts_label}]({yt_url})"

        # Empires: «eN» → [name](empire:polity_id)
        if marker in empire_map:
            e = empire_map[marker]
            return f"[{e['name']}](empire:{e['polity_id']})"

        # Images: «iN» → ![title](original_url)\n*Photo: author · license*
        if marker in image_map:
            e = image_map[marker]
            attribution = f"*Photo: {e['author']} · {e['license']}*" if e.get("author") else ""
            img_line = f"![{e['title']}]({e['original_url']})"
            return f"{img_line}\n{attribution}" if attribution else img_line

        # Links: «lN» → [text](url)
        if marker in link_map:
            e = link_map[marker]
            return f"[{e['text']}]({e['url']})"

        # Countries: «fN» → [name](flag:code)
        if marker in country_map:
            e = country_map[marker]
            return f"[{e['name']}](flag:{e['code']})"

        issues.append(f"Unresolved marker: {raw_marker}")
        return raw_marker

    expanded = _MARKER_RE.sub(_replace_marker, text)

    # Run validation
    issues.extend(validate_structured_response(parsed, expanded))

    # Strip any remaining unresolved guillemet markers from final text
    # (Mercury sometimes outputs markers without matching array entries)
    cleaned = _MARKER_RE.sub("", expanded)
    if cleaned != expanded:
        # Collapse whitespace from removed markers
        cleaned = re.sub(r"  +", " ", cleaned).strip()
        expanded = cleaned

    return expanded, issues


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_structured_response(parsed: dict, expanded_text: str | None = None) -> list[str]:
    """Validate a structured response for consistency.

    Checks:
    - All markers in text have matching array entries
    - No orphaned array entries
    - UUID format for site IDs
    - Coordinate ranges
    - ISO country codes (2-letter)
    """
    issues: list[str] = []
    text = parsed.get("text", "")

    # Normalize markers: strip guillemets for comparison
    def _norm(m: str) -> str:
        return m.strip("\u00ab\u00bb")

    # Find all markers in text (normalized)
    markers_in_text = {_norm(m) for m in _MARKER_RE.findall(text)}

    # Collect all markers from arrays (normalized)
    all_array_markers: set[str] = set()
    for arr_name in ("sites", "coords", "videos", "empires", "images", "links", "countries"):
        for entry in parsed.get(arr_name, []):
            m = _norm(entry.get("marker", ""))
            if m:
                all_array_markers.add(m)

    # Check for markers in text without array entries
    missing = markers_in_text - all_array_markers
    for m in missing:
        issues.append(f"Marker {m} in text but not in arrays")

    # Check for orphaned array entries
    orphaned = all_array_markers - markers_in_text
    for m in orphaned:
        issues.append(f"Marker {m} in arrays but not in text")

    # Validate site UUIDs
    for site in parsed.get("sites", []):
        sid = site.get("id", "")
        if sid and not _UUID_RE.match(sid):
            issues.append(f"Invalid UUID for site '{site.get('name', '?')}': {sid}")

    # Validate coordinate ranges
    for coord in parsed.get("coords", []):
        lat = coord.get("lat", 0)
        lon = coord.get("lon", 0)
        if not (-90 <= lat <= 90):
            issues.append(f"Invalid latitude {lat} in {coord.get('marker', '?')}")
        if not (-180 <= lon <= 180):
            issues.append(f"Invalid longitude {lon} in {coord.get('marker', '?')}")

    # Validate ISO country codes (2-letter uppercase)
    for country in parsed.get("countries", []):
        code = country.get("code", "")
        if not re.match(r"^[A-Z]{2}$", code):
            issues.append(f"Invalid country code '{code}' for {country.get('name', '?')}")

    # Check expanded text for remaining guillemet markers (expansion failure)
    if expanded_text and "\u00ab" in expanded_text:
        remaining = _MARKER_RE.findall(expanded_text)
        if remaining:
            issues.append(f"Unresolved markers in expanded text: {remaining}")

    return issues
