"""Hallucination gate for Theo research paper prose.

Extracts specific claims from generated prose (person names, book titles,
years, measurements, quoted phrases) and verifies each appears in the
evidence pack, source snippets, or user question. Unsupported specifics
are returned so the writer can be asked to rewrite (Task D4 adds the
LLM repair loop).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass
class Specific:
    """A specific claim extracted from prose that must trace to the evidence pack."""

    kind: Literal["person", "title", "date", "measurement", "quote"]
    text: str
    sentence: str


# ---------------------------------------------------------------------------
# Regex bank
# ---------------------------------------------------------------------------

_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]")

_PERSON_RE = re.compile(r"\b(?:[A-Z][a-z]+)(?:\s+[A-Z][a-z]+){1,3}\b")

# Dates: 3-4 digit year optionally followed by BCE/CE/AD/BC, or 19xx/20xx.
_DATE_RE = re.compile(
    r"\b(?:\d{3,4}\s?(?:BCE|CE|AD|BC)|(?:19|20)\d{2})\b",
    re.IGNORECASE,
)

_MEASUREMENT_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:Hz|kHz|MHz|kg|tonnes?|tons?|km|meters?|metres?|feet|ft|mm|cm)\b",
    re.IGNORECASE,
)

# Quoted spans (10-200 chars inside the quotes) — filtered later to quotes >= 5 words.
_QUOTED_RE = re.compile(r'"([^"\n]{10,200})"')

# Titled works: quoted OR italicized spans that look title-case-y, 2-10 words.
_TITLE_RE = re.compile(r'["*]([A-Z][^"*\n]{1,80})["*]')


# ---------------------------------------------------------------------------
# Person stop-list — extend as false positives appear in real prose
# ---------------------------------------------------------------------------

_PERSON_STOPWORDS = frozenset(
    {
        # Places
        "hal saflieni",
        "gobekli tepe",
        "puma punku",
        "puma punku precision",
        "baalbek",
        "new york",
        "los angeles",
        "san francisco",
        "mexico city",
        "ancient egypt",
        "ancient greece",
        "ancient rome",
        "middle east",
        # Institutions / museums
        "british museum",
        "the louvre",
        "getty museum",
        "national geographic",
        "smithsonian institution",
        # Topics that happen to look like Title Case
        "ancient origins",
    }
)


# ---------------------------------------------------------------------------
# extract_specifics
# ---------------------------------------------------------------------------


def extract_specifics(prose: str) -> list[Specific]:
    """Return every specific worth verifying against the evidence pack.

    Scans each sentence of the prose and extracts proper nouns, dates,
    measurements, quoted phrases, and titled works.
    """
    if not prose:
        return []

    out: list[Specific] = []
    for s_match in _SENTENCE_RE.finditer(prose):
        sentence = s_match.group(0).strip()
        if not sentence:
            continue

        for m in _PERSON_RE.finditer(sentence):
            text = m.group(0)
            if text.lower() in _PERSON_STOPWORDS:
                continue
            out.append(Specific(kind="person", text=text, sentence=sentence))

        for m in _DATE_RE.finditer(sentence):
            out.append(Specific(kind="date", text=m.group(0), sentence=sentence))

        for m in _MEASUREMENT_RE.finditer(sentence):
            out.append(Specific(kind="measurement", text=m.group(0), sentence=sentence))

        for m in _QUOTED_RE.finditer(sentence):
            inner = m.group(1).strip()
            if len(inner.split()) >= 5:
                out.append(Specific(kind="quote", text=inner, sentence=sentence))

        for m in _TITLE_RE.finditer(sentence):
            inner = m.group(1).strip()
            word_count = len(inner.split())
            if 2 <= word_count <= 10 and inner[0].isupper():
                out.append(Specific(kind="title", text=inner, sentence=sentence))

    return out


# ---------------------------------------------------------------------------
# verify_against_pack
# ---------------------------------------------------------------------------


def _normalize_for_match(s: str) -> str:
    """Lowercase, strip honorifics/titles, collapse whitespace."""
    s = s.lower()
    s = re.sub(r"\b(dr|prof|mr|mrs|ms|sir|dame|phd|md|frcp|glasg)\.?\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def verify_against_pack(
    specifics: list[Specific],
    pack: str,
    sources: dict,
    original_question: str,
) -> list[Specific]:
    """Return specifics not found in pack, source snippets, or user question.

    Normalization strips common honorifics from both sides so "Dr. Paolo
    Debertolis" in prose matches "Debertolis" in a source snippet. Persons
    also get a last-name fallback: if the full name isn't in the haystack
    but the last token is (>=4 chars), treat as supported.
    """
    haystack_parts = [_normalize_for_match(pack), _normalize_for_match(original_question)]
    for src in sources.values():
        haystack_parts.append(_normalize_for_match(getattr(src, "title", "") or ""))
        haystack_parts.append(_normalize_for_match(getattr(src, "snippet", "") or ""))
    haystack = " ||| ".join(haystack_parts)

    unsupported: list[Specific] = []
    for spec in specifics:
        needle = _normalize_for_match(spec.text)
        if needle and needle in haystack:
            continue
        if spec.kind == "person":
            tokens = needle.split()
            last = tokens[-1] if tokens else ""
            if last and len(last) >= 4 and last in haystack:
                continue
        unsupported.append(spec)
    return unsupported
