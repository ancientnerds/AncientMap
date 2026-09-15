"""Grounded mentions: the model points, the code reads.

The extraction schema has no free-text fact fields. The model returns the
place name AS WRITTEN in the window, the country phrase AS WRITTEN and the
period phrase AS WRITTEN, plus a classification. The code then LOCATES each
string in the window; a string that is not in the text is not a fact, it is
dropped and counted. A hallucinated country is therefore structurally
impossible: it cannot be stored unless it is a verbatim substring of the
same paragraph that names the place.

Why surface strings rather than character offsets (which the design first
proposed): models cannot count characters reliably, so offsets fail the
grounding check for reasons that have nothing to do with hallucination.
Requiring the verbatim string gives the identical guarantee — the code
computes the offsets itself — with a rejection rate that measures the model's
honesty, not its arithmetic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pipeline.lyra.prospector.corpus import paragraph_bounds
from pipeline.lyra.text_sentences import sentence_span
from pipeline.utils.text import clean_llm_name, normalize_name

# Only "site" proceeds to a proposal a human is asked to approve. The other
# classes are still recorded (status not_a_place) so the skip channel stays
# auditable — the design's one irreversible failure is a silent loss.
PLACE_CLASSES = (
    "site",
    "landform",
    "region",
    "settlement_modern",
    "institution",
    "protected_area",
    "body_of_water",
    "off_earth",
    "other",
)

MENTION_SCHEMA = {
    "type": "object",
    "properties": {
        "mentions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name_as_written": {"type": "string"},
                    "place_class": {"type": "string", "enum": list(PLACE_CLASSES)},
                    "country_as_written": {"type": "string"},
                    "period_as_written": {"type": "string"},
                },
                "required": [
                    "name_as_written",
                    "place_class",
                    "country_as_written",
                    "period_as_written",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["mentions"],
    "additionalProperties": False,
}

_FOOTNOTE_RE = re.compile(r"\[(\d{1,3})\]")


@dataclass
class Mention:
    """A grounded mention: every string below is a verbatim slice of `source`."""

    name: str
    place_class: str
    char_start: int  # absolute, into the stored source text
    char_end: int
    quote: str
    quote_start: int
    footnotes: list[int] = field(default_factory=list)
    country_in_text: str | None = None
    period_phrase: str | None = None


@dataclass
class GroundingStats:
    emitted: int = 0
    grounded: int = 0
    rejected: int = 0
    duplicates: int = 0

    @property
    def reject_rate(self) -> float:
        return self.rejected / self.emitted if self.emitted else 0.0


def _find_all(haystack: str, needle: str) -> list[int]:
    out: list[int] = []
    start = 0
    while True:
        i = haystack.find(needle, start)
        if i == -1:
            return out
        out.append(i)
        start = i + 1


def ground_mentions(
    raw_mentions: list[dict],
    window_text: str,
    window_abs_start: int,
    source_text: str,
    stats: GroundingStats,
) -> list[Mention]:
    """Turn model output for one window into grounded Mentions.

    Assertion 1 — the name must occur verbatim in the window; every
    occurrence becomes a mention (a place named three times in a window is
    three evidence rows, deduplicated later by char_start).
    Assertion 2 — country/period phrases must occur verbatim inside the SAME
    paragraph as that occurrence; otherwise the field is set to None and the
    mention survives. Only the unverifiable claim dies, not the sighting.
    """
    grounded: list[Mention] = []
    seen_starts: set[int] = set()
    for raw in raw_mentions:
        stats.emitted += 1
        name = clean_llm_name(raw.get("name_as_written"))
        place_class = raw.get("place_class") if raw.get("place_class") in PLACE_CLASSES else None
        if not name or not place_class:
            stats.rejected += 1
            continue
        positions = _find_all(window_text, name)
        if not positions:
            # One retry the code can vouch for: case-insensitive, then the
            # slice itself (what the text actually says) becomes the name.
            lowered = _find_all(window_text.lower(), name.lower())
            positions = lowered
        if not positions:
            stats.rejected += 1
            continue
        stats.grounded += 1

        for rel in positions:
            abs_start = window_abs_start + rel
            if abs_start in seen_starts:
                stats.duplicates += 1
                continue
            seen_starts.add(abs_start)
            abs_end = abs_start + len(name)
            surface = source_text[abs_start:abs_end]
            # The slice is the fact; the model's string only located it.
            if normalize_name(surface) != normalize_name(name):
                stats.rejected += 1
                continue
            p_start, p_end = paragraph_bounds(source_text, abs_start)
            paragraph = source_text[p_start:p_end]
            # sentence_span only splits on sentence punctuation, so a heading
            # or a list item without a period would ride into the quote.
            # A quote never crosses its paragraph.
            q_start, q_end = sentence_span(source_text, abs_start)
            q_start, q_end = max(q_start, p_start), min(q_end, p_end)
            # A markdown heading ("## What Three Projects Revealed") is a valid
            # sighting, but the rendered page shows it without the hashes, so
            # the quote and its text-fragment link must not carry them either.
            heading = re.match(r"#{1,6}\s+", source_text[q_start:q_end])
            if heading:
                q_start += heading.end()
            grounded.append(
                Mention(
                    name=surface,
                    place_class=place_class,
                    char_start=abs_start,
                    char_end=abs_end,
                    quote=source_text[q_start:q_end].strip(),
                    quote_start=q_start,
                    footnotes=[int(n) for n in _FOOTNOTE_RE.findall(paragraph)],
                    country_in_text=_verbatim_in(
                        paragraph, raw.get("country_as_written"), country=True
                    ),
                    period_phrase=_verbatim_in(paragraph, raw.get("period_as_written")),
                )
            )
    return grounded


def _verbatim_in(paragraph: str, phrase: str | None, *, country: bool = False) -> str | None:
    """The phrase if it occurs verbatim, on word boundaries, in the paragraph.

    For countries a fragment of a longer capitalised name is rejected: the
    first real paper returned "Mexico" for a paragraph saying "highland New
    Mexico", and "Africa" would match "South Africa", "Guinea" match "Papua
    New Guinea". A capitalised word directly before the match means the
    phrase is part of a bigger proper name — not the country.
    """
    cleaned = clean_llm_name(phrase)
    if not cleaned:
        return None
    pattern = r"(?<!\w)" + re.escape(cleaned) + r"(?!\w)"
    m = re.search(pattern, paragraph) or re.search(pattern, paragraph, re.IGNORECASE)
    if not m:
        return None
    if country:
        before = paragraph[: m.start()]
        prev = re.search(r"([A-Z][\w'’-]*)\s+$", before)
        if prev:
            return None
    return paragraph[m.start() : m.end()]
