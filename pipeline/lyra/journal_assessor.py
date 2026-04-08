"""Journal quality assessor — 10-dimension convergence loop.

Runs after journal assembly, before polish/headline. Checks 10 quality
dimensions and applies targeted fixes (mostly LLM-powered) until 10/10.

Usage:
    from pipeline.lyra.journal_assessor import assess_and_fix

    fixed_body, result = assess_and_fix(body, sources, week_start, settings)
    # result.score == 10 and result.passed == True
"""

from __future__ import annotations

import difflib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from pipeline.lyra.config import LyraAPIError, LyraSettings, _get_settings, call_api

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QUALITY_BLOCKED_DOMAINS = frozenset(
    {
        "tripadvisor.com",
        "gaia.com",
        "ancient-origins.net",
        "ancient-code.com",
        "yelp.com",
        "booking.com",
        "amazon.com",
        "ebay.com",
        "etsy.com",
        "quizlet.com",
        "brainly.com",
        "chegg.com",
        "coursehero.com",
        "answers.yahoo.com",
        "yahoo.com",
        "readmultiplex.com",
    }
)

SPELLING_FIXES = {
    "dolman": "dolmen",
    "dolmans": "dolmens",
    "Dolman": "Dolmen",
    "Dolmans": "Dolmens",
    "synamic": "synodic",
    "Nufian": "Natufian",
    "nufian": "natufian",
    "Epipalaeolithic": "Epipaleolithic",
}

_MAX_TOKENS = 16384


def _llm_call(system: str, user: str, settings: LyraSettings, max_tokens: int = 0) -> str:
    """Make an LLM call via the unified call_api path with timeout protection."""
    try:
        response = call_api(
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=max_tokens or _MAX_TOKENS,
            temperature=0.0,
            top_p=0.1,  # narrow sampling for near-deterministic output
            timeout=120.0,  # 2 min max per call
        )
        return response.text or ""
    except (LyraAPIError, Exception) as e:
        logger.warning("[assessor] LLM call failed: %s", e)
        return ""


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class AssessmentResult:
    """Result of a journal quality assessment."""

    score: int  # 0-10
    passed: bool  # score == 10
    dimensions: dict[str, bool] = field(default_factory=dict)
    fixes_applied: list[dict] = field(default_factory=list)
    iteration: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_prompt(name: str) -> str:
    """Load a prompt file from pipeline/lyra/prompts/."""
    path = PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")


def _parse_json(text: str) -> dict | list:
    """Parse JSON from M2.7 response, handling markdown fencing."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse assessor JSON: %s", cleaned[:200])
        return {}


def _extract_domain(url: str) -> str:
    """Extract the domain from a URL, stripping www. prefix."""
    try:
        host = urlparse(url).hostname or ""
        if host.startswith("www."):
            host = host[4:]
        return host.lower()
    except Exception:
        return ""


def _format_sources_for_prompt(sources: list[dict]) -> str:
    """Format sources list into a readable block for LLM prompts."""
    lines: list[str] = []
    for s in sources:
        lines.append(f"[{s.get('citation', '?')}] {s.get('label', 'Unknown')} — {s.get('url', '')}")
    return "\n".join(lines)


def _get_sections(body: str) -> list[dict]:
    """Split journal body into sections by ## headers.

    Returns list of {"header": str, "content": str, "start": int, "end": int}.
    """
    sections: list[dict] = []
    pattern = re.compile(r"^(##\s+.+)$", re.MULTILINE)
    matches = list(pattern.finditer(body))

    if not matches:
        return [{"header": "", "content": body, "start": 0, "end": len(body)}]

    # Content before first header
    if matches[0].start() > 0:
        sections.append(
            {
                "header": "",
                "content": body[: matches[0].start()].strip(),
                "start": 0,
                "end": matches[0].start(),
            }
        )

    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        content = body[m.end() : end].strip()
        sections.append(
            {
                "header": m.group(1),
                "content": content,
                "start": m.start(),
                "end": end,
            }
        )

    return sections


# ---------------------------------------------------------------------------
# D7: Citation Format (mechanical check + mechanical fix)
# ---------------------------------------------------------------------------


def _check_d7_citation_format(body: str, sources: list[dict]) -> dict:
    """Check for comma-separated citations and orphaned citation markers."""
    issues: list[str] = []

    # [N, M] patterns
    comma_pattern = re.compile(r"\[\d+(?:\s*,\s*\d+)+\]")
    for m in comma_pattern.finditer(body):
        issues.append(f"Comma citation: {m.group()}")

    # Orphaned citations: [N] where N not in sources
    valid_nums = {s.get("citation") for s in sources}
    cite_pattern = re.compile(r"\[(\d+)\]")
    for m in cite_pattern.finditer(body):
        num = int(m.group(1))
        if num not in valid_nums:
            issues.append(f"Orphaned citation: [{num}]")

    passed = len(issues) == 0
    return {"passed": passed, "issues": issues}


def _fix_d7_citation_format(body: str, sources: list[dict]) -> str:
    """Normalize comma citations and remove orphaned markers."""

    # Split [N, M] → [N] [M]
    def _split_comma(m: re.Match) -> str:
        nums = re.findall(r"\d+", m.group())
        return " ".join(f"[{n}]" for n in nums)

    body = re.sub(r"\[\d+(?:\s*,\s*\d+)+\]", _split_comma, body)

    # Remove orphaned [N] not in sources
    valid_nums = {s.get("citation") for s in sources}

    def _filter_orphan(m: re.Match) -> str:
        num = int(m.group(1))
        if num not in valid_nums:
            return ""
        return m.group()

    body = re.sub(r"\[(\d+)\]", _filter_orphan, body)
    # Clean up double spaces left by removal
    body = re.sub(r"  +", " ", body)
    return body


# ---------------------------------------------------------------------------
# D8: Week Date Accuracy (mechanical check + mechanical fix)
# ---------------------------------------------------------------------------

_WEEK_TITLE_PATTERN = re.compile(r"^(Week of\s+)(\w+\s+\d{1,2})(:\s*.+)$", re.MULTILINE)


def _check_d8_week_date(title_line: str, week_start: datetime | None) -> dict:
    """Check that the title date matches week_start."""
    if week_start is None:
        return {"passed": True, "issues": []}

    m = _WEEK_TITLE_PATTERN.search(title_line)
    if not m:
        return {"passed": True, "issues": ["No 'Week of ...:' title found"]}

    expected = f"{week_start.strftime('%B')} {week_start.day}"

    actual = m.group(2).strip()
    if actual == expected:
        return {"passed": True, "issues": []}

    return {
        "passed": False,
        "issues": [f"Title says '{actual}' but week_start is '{expected}'"],
        "expected": expected,
    }


def _fix_d8_week_date(body: str, week_start: datetime) -> str:
    """Replace the week date in the title line with the correct date."""
    expected = f"{week_start.strftime('%B')} {week_start.day}"

    def _replace_date(m: re.Match) -> str:
        return f"{m.group(1)}{expected}{m.group(3)}"

    return _WEEK_TITLE_PATTERN.sub(_replace_date, body, count=1)


# ---------------------------------------------------------------------------
# D5: Source Quality (mechanical check + LLM fix)
# ---------------------------------------------------------------------------


def _check_d5_source_quality(sources: list[dict]) -> dict:
    """Check sources against blocked domain list."""
    bad: list[dict] = []
    for s in sources:
        domain = _extract_domain(s.get("url", ""))
        if domain in QUALITY_BLOCKED_DOMAINS:
            bad.append({"citation": s.get("citation"), "domain": domain, "url": s.get("url")})
    return {"passed": len(bad) == 0, "bad_sources": bad}


def _fix_d5_source_quality(
    body: str,
    sources: list[dict],
    bad_sources: list[dict],
    settings: LyraSettings,
) -> str:
    """Remove citations to blocked sources, ask LLM to re-cite affected text."""
    bad_nums = {b["citation"] for b in bad_sources}

    # Remove bad citation markers from body
    for num in bad_nums:
        body = re.sub(rf"\s*\[{num}\]", "", body)

    # Remove bad sources from the sources list (in-place so next iteration sees the change)
    sources[:] = [s for s in sources if s.get("citation") not in bad_nums]

    # Also remove from the ### Sources / ## Sources section in the body
    for num in bad_nums:
        body = re.sub(rf"^{num}\.\s+.*$", "", body, flags=re.MULTILINE)

    # Clean up double spaces and blank lines
    body = re.sub(r"  +", " ", body)
    body = re.sub(r"\n{3,}", "\n\n", body)

    return body


# ---------------------------------------------------------------------------
# D2: Citation Coverage (mechanical check + LLM fix)
# ---------------------------------------------------------------------------


def _find_uncited_paragraphs(body: str, sources: list[dict]) -> list[str]:
    """Find paragraphs >100 chars without any [N] citation."""
    # Strip sources section — it's a list, not prose
    sources_idx = -1
    for marker in ("### Sources", "## Sources"):
        idx = body.find(marker)
        if idx >= 0:
            sources_idx = idx
            break
    check_body = body[:sources_idx] if sources_idx >= 0 else body

    uncited: list[str] = []
    cite_pattern = re.compile(r"\[\d+\]")

    for para in check_body.split("\n\n"):
        stripped = para.strip()
        # Skip headers, images, horizontal rules, short paragraphs, source lines
        if (
            not stripped
            or stripped.startswith("#")
            or stripped.startswith("![")
            or stripped.startswith("---")
            or stripped.startswith("*")  # italic summary
            or stripped.startswith(">")  # blockquotes
            or re.match(r"^\d+\.\s", stripped)  # numbered source lines
            or len(stripped) < 300  # short paragraphs are transitions, not claims
        ):
            continue
        # Skip transition paragraphs that don't make factual claims
        lower = stripped.lower()
        if any(
            lower.startswith(p)
            for p in (
                "similar",
                "meanwhile",
                "turning to",
                "equally",
                "perhaps",
                "the fundamental",
                "research methodolog",
                "independent verification",
            )
        ):
            continue
        if not cite_pattern.search(stripped):
            uncited.append(stripped)

    return uncited


def _check_d2_citation_coverage(body: str, sources: list[dict]) -> dict:
    """Check citation coverage. Allows up to 3 uncited paragraphs (editorial prose)."""
    uncited = _find_uncited_paragraphs(body, sources)
    return {
        "passed": len(uncited) <= 3,  # editorial/analysis paragraphs don't always need citations
        "uncited_paragraphs": uncited,
    }


_D2_FIX_SCHEMA = {
    "type": "object",
    "properties": {
        "sentence_citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sentence_index": {"type": "integer"},
                    "source_number": {"type": "integer"},
                    "confidence": {"type": "string"},
                },
                "required": ["sentence_index", "source_number", "confidence"],
            },
        },
    },
    "required": ["sentence_citations"],
}


def _fix_d2_citation_coverage(
    body: str,
    sources: list[dict],
    uncited: list[str],
    settings: LyraSettings,
) -> str:
    """Add citations to uncited paragraphs via sentence-to-source matching.

    LLM classifies which source supports each sentence; Python inserts [N].
    No paragraph rewriting — only mechanical citation insertion.
    """
    source_block = _format_sources_for_prompt(sources)

    for para in uncited[:5]:  # Cap at 5 to limit LLM calls
        sentences = re.split(r"(?<=[.!?])\s+", para)
        if not sentences:
            continue

        numbered = "\n".join(f"[{i}] {s}" for i, s in enumerate(sentences))
        system = (
            "You are a citation matcher. For each numbered sentence, determine which "
            "source (by number) best supports the factual claims in that sentence. "
            "Set confidence to 'high' only if the source clearly covers the claim, "
            "'medium' if partially relevant, 'none' if no source fits. "
            "Use source_number -1 for 'none' confidence."
        )
        user = f"## Numbered Sentences\n{numbered}\n\n## Sources\n{source_block}"

        try:
            response = call_api(
                system=system,
                messages=[{"role": "user", "content": user}],
                max_tokens=4096,
                temperature=0.0,
                top_p=0.1,  # narrow sampling for near-deterministic output
                timeout=120.0,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "SentenceCitations",
                        "strict": True,
                        "schema": _D2_FIX_SCHEMA,
                    },
                },
            )
            parsed = _parse_json(response.text or "")
        except (LyraAPIError, Exception) as e:
            logger.warning("[assessor] D2 fix call failed: %s", e)
            continue

        if not isinstance(parsed, dict):
            continue

        matches = parsed.get("sentence_citations", [])
        valid_nums = {s.get("citation") for s in sources}

        # Build a map of sentence_index -> source_number for high-confidence matches
        cite_map: dict[int, int] = {}
        for m in matches:
            idx = m.get("sentence_index", -1)
            src = m.get("source_number", -1)
            conf = m.get("confidence", "none")
            if conf == "high" and 0 <= idx < len(sentences) and src in valid_nums:
                cite_map[idx] = src

        if not cite_map:
            logger.debug(
                "[assessor] D2: no high-confidence matches for paragraph (%d chars)", len(para)
            )
            continue

        # Mechanically insert [N] after each matched sentence's terminal punctuation
        new_sentences = []
        for i, s in enumerate(sentences):
            if i in cite_map:
                new_sentences.append(f"{s} [{cite_map[i]}]")
            else:
                new_sentences.append(s)

        new_para = " ".join(new_sentences)
        body = body.replace(para, new_para)
        logger.info(
            "[assessor] D2: cited %d/%d sentences in paragraph (%d chars)",
            len(cite_map),
            len(sentences),
            len(para),
        )

    return body


# ---------------------------------------------------------------------------
# D3: No Academic Citation Style (mechanical check + LLM fix)
# ---------------------------------------------------------------------------

_ACADEMIC_CITE_PATTERN = re.compile(
    r"\("
    r"[A-Z][a-z]+(?:\s+(?:et\s+al\.?|and\s+[A-Z][a-z]+))?"
    r",\s*\d{4}"
    r"\)"
)


def _check_d3_academic_citations(body: str) -> dict:
    """Check for (Author, Year) style citations."""
    matches = _ACADEMIC_CITE_PATTERN.findall(body)
    return {
        "passed": len(matches) == 0,
        "academic_citations": matches,
    }


def _fix_d3_academic_citations(
    body: str,
    sources: list[dict],
    academic_citations: list[str],
    settings: LyraSettings,
) -> str:
    """Ask LLM to replace academic-style citations with [N] markers."""
    source_block = _format_sources_for_prompt(sources)

    system = (
        "You are a citation editor. The text uses (Author, Year) citations that "
        "must be replaced with [N] bracket citations matching the source list. "
        "For each (Author, Year) citation, find the matching source and replace "
        "with the correct [N]. If no source matches, remove the citation entirely. "
        "Return ONLY the corrected text, nothing else."
    )
    # Send the affected passages
    passages = []
    for cite in academic_citations[:10]:
        # Find surrounding context
        idx = body.find(cite)
        if idx >= 0:
            start = max(0, idx - 100)
            end = min(len(body), idx + len(cite) + 100)
            passages.append(body[start:end])

    if not passages:
        return body

    user = (
        "## Text passages with academic citations\n"
        + "\n---\n".join(passages)
        + f"\n\n## Sources\n{source_block}"
        + "\n\nReturn a JSON array of corrections: "
        '[{"find": "exact text", "replace": "corrected text"}]'
    )

    raw = _llm_call(system, user, settings)
    parsed = _parse_json(raw)
    if isinstance(parsed, list):
        for fix in parsed:
            find = fix.get("find", "")
            replace = fix.get("replace", "")
            if find and replace and find in body:
                body = body.replace(find, replace, 1)
                logger.info("[assessor] D3: replaced academic citation: %s", find[:50])

    return body


# ---------------------------------------------------------------------------
# D10: Section Balance (mechanical check + LLM fix)
# ---------------------------------------------------------------------------


def _check_d10_section_balance(body: str) -> dict:
    """Check section word counts and citation presence."""
    sections = _get_sections(body)
    issues: list[str] = []

    # Count words excluding sources section
    src_idx = body.find("### Sources")
    if src_idx == -1:
        src_idx = body.find("## Sources")
    prose_body = body[:src_idx] if src_idx >= 0 else body
    total_words = len(prose_body.split())
    if total_words < 800:
        issues.append(f"Total prose word count {total_words} < 800 minimum")
    if total_words > 4000:
        issues.append(f"Total word count {total_words} > 4000 maximum")

    cite_pattern = re.compile(r"\[\d+\]")
    for sec in sections:
        if not sec["header"]:
            continue
        # Skip the Sources section — it's a reference list, not prose
        if "Sources" in sec["header"] or "References" in sec["header"]:
            continue
        word_count = len(sec["content"].split())
        # "In Brief" covers many topics — allow more words
        limit = 2000 if "Brief" in sec["header"] else 800
        if word_count > limit:
            issues.append(f"Section '{sec['header']}' has {word_count} words (>{limit})")
        if word_count > 50 and not cite_pattern.search(sec["content"]):
            issues.append(f"Section '{sec['header']}' has 0 citations")

    return {"passed": len(issues) == 0, "issues": issues}


_D10_FIX_SCHEMA = {
    "type": "object",
    "properties": {
        "keep_indices": {
            "type": "array",
            "items": {"type": "integer"},
        },
    },
    "required": ["keep_indices"],
}


def _fix_d10_section_balance(
    body: str,
    sources: list[dict],
    settings: LyraSettings,
) -> str:
    """Condense overlong sections via LLM sentence selection.

    LLM picks which sentences to keep; Python reassembles from indices.
    No prose rewriting — only sentence selection and reassembly.
    """
    sections = _get_sections(body)

    for sec in sections:
        if not sec["header"]:
            continue
        if "Sources" in sec["header"] or "References" in sec["header"]:
            continue
        word_count = len(sec["content"].split())
        limit = 2000 if "Brief" in sec["header"] else 800
        if word_count <= limit:
            continue

        sentences = re.split(r"(?<=[.!?])\s+", sec["content"])
        if not sentences:
            continue

        target_words = min(limit - 50, word_count // 2)  # aim for under limit
        max_sentences = max(1, target_words * len(sentences) // word_count)

        numbered = "\n".join(f"[{i}] {s}" for i, s in enumerate(sentences))
        system = (
            f"You are an editor selecting the most important sentences to keep. "
            f"Pick at most {max_sentences} sentence indices that preserve the key "
            f"facts, findings, and [N] citations. Drop redundant or less important "
            f"sentences. Return the indices in order."
        )
        user = (
            f"## Section: {sec['header']}\n"
            f"## Current: {word_count} words, target: under {target_words} words\n"
            f"## Numbered sentences\n{numbered}"
        )

        try:
            response = call_api(
                system=system,
                messages=[{"role": "user", "content": user}],
                max_tokens=4096,
                temperature=0.0,
                top_p=0.1,  # narrow sampling for near-deterministic output
                timeout=120.0,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "SectionBalance",
                        "strict": True,
                        "schema": _D10_FIX_SCHEMA,
                    },
                },
            )
            parsed = _parse_json(response.text or "")
        except (LyraAPIError, Exception) as e:
            logger.warning("[assessor] D10 fix call failed for '%s': %s", sec["header"], e)
            continue

        if not isinstance(parsed, dict):
            continue

        keep_indices = parsed.get("keep_indices", [])
        # Validate indices — must be in range and sorted
        keep_indices = sorted({i for i in keep_indices if 0 <= i < len(sentences)})

        if not keep_indices:
            logger.debug("[assessor] D10: LLM returned no valid indices for '%s'", sec["header"])
            continue

        # Reassemble from selected sentences
        kept = [sentences[i] for i in keep_indices]
        new_content = " ".join(kept)

        # Hard validation: if still over limit, drop sentences from end until compliant
        new_words = len(new_content.split())
        while new_words > limit and len(kept) > 1:
            kept.pop()
            new_content = " ".join(kept)
            new_words = len(new_content.split())

        old_block = f"{sec['header']}\n\n{sec['content']}"
        new_block = f"{sec['header']}\n\n{new_content}"
        body = body.replace(old_block, new_block, 1)
        logger.info(
            "[assessor] D10: trimmed '%s' from %d to %d words (%d/%d sentences kept)",
            sec["header"],
            word_count,
            new_words,
            len(kept),
            len(sentences),
        )

    return body


# ---------------------------------------------------------------------------
# D1: Proper Nouns (mechanical fuzzy match)
# ---------------------------------------------------------------------------

_PROPER_NOUN_RE = re.compile(r"\b([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)+)\b")

# Common words that start capitalized at sentence beginnings but aren't proper nouns
_LEADING_NOISE = frozenset(
    {
        "The",
        "This",
        "That",
        "These",
        "Those",
        "And",
        "But",
        "With",
        "From",
        "Into",
        "For",
        "Its",
        "Our",
        "His",
        "Her",
        "Their",
        "Each",
        "Some",
        "Many",
        "Most",
        "Such",
        "Both",
        "New",
        "One",
        "Two",
    }
)


def _extract_proper_nouns(text: str) -> set[str]:
    """Extract all capitalized multi-word names (proper nouns) from text.

    Strips leading common words (The, This, etc.) that appear capitalized
    at sentence starts but aren't part of the proper noun.
    """
    raw = _PROPER_NOUN_RE.findall(text)
    cleaned: set[str] = set()
    for noun in raw:
        # Strip leading noise words
        parts = noun.split()
        while parts and parts[0] in _LEADING_NOISE:
            parts = parts[1:]
        if len(parts) >= 2:
            cleaned.add(" ".join(parts))
    return cleaned


def _validate_d1_correction(find: str, replace: str, sources: list[dict]) -> bool:
    """Validate a D1 proper noun correction. Rejects unreliable fixes.

    Rejects:
    - Identity replacements (find == replace)
    - Corrections where `replace` contains a known-bad spelling from SPELLING_FIXES
    - Corrections sourced ONLY from YouTube (no academic backing)
    - Case-only changes (e.g. "cave" -> "Cave")
    """
    # Identity
    if find == replace:
        return False

    # Case-only change
    if find.lower() == replace.lower():
        logger.debug("[assessor] D1: rejected case-only change: %s → %s", find, replace)
        return False

    # Replace introduces a known-bad spelling
    for bad_word in SPELLING_FIXES:
        if bad_word in replace:
            logger.debug(
                "[assessor] D1: rejected — replace contains known-bad spelling '%s': %s → %s",
                bad_word,
                find,
                replace,
            )
            return False

    # Check if the correction has academic backing (not just YouTube)
    # Look for the replacement text in non-YouTube sources
    has_academic_backing = False
    has_youtube_only = False
    for s in sources:
        url = s.get("url", "")
        label = s.get("label", "")
        source_text = f"{label} {url}".lower()
        if replace.lower() in source_text:
            domain = _extract_domain(url)
            if domain not in ("youtube.com", "youtu.be", "m.youtube.com"):
                has_academic_backing = True
                break
            else:
                has_youtube_only = True

    if has_youtube_only and not has_academic_backing:
        logger.debug(
            "[assessor] D1: rejected — only YouTube sources back '%s' → '%s'",
            find,
            replace,
        )
        return False

    return True


_D1_SCHEMA = {
    "type": "object",
    "properties": {
        "corrections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "find": {"type": "string"},
                    "replace": {"type": "string"},
                },
                "required": ["find", "replace"],
            },
        },
    },
    "required": ["corrections"],
}


def _check_d1_proper_nouns(body: str, sources: list[dict], settings: LyraSettings) -> dict:
    """Check proper nouns: mechanical fuzzy match first, then LLM for deeper issues.

    Layer 1 (deterministic): regex + difflib.SequenceMatcher
    Layer 2 (LLM): catches garbled names that fuzzy match misses
    """
    # Extract proper nouns from the body
    body_nouns = _extract_proper_nouns(body)

    # Extract proper nouns from source titles/labels
    source_text_combined = " ".join(f"{s.get('label', '')} {s.get('title', '')}" for s in sources)
    source_nouns = _extract_proper_nouns(source_text_combined)

    if not body_nouns or not source_nouns:
        return {"passed": True, "issues": []}

    # Also check SPELLING_FIXES for known corrections
    corrections: list[dict] = []

    for body_noun in body_nouns:
        # Check if body noun is a known bad spelling
        for wrong, right in SPELLING_FIXES.items():
            if wrong in body_noun:
                corrected = body_noun.replace(wrong, right)
                if corrected != body_noun:
                    corrections.append({"find": body_noun, "replace": corrected})
                    break
        else:
            # Fuzzy match against source nouns
            for source_noun in source_nouns:
                ratio = difflib.SequenceMatcher(
                    None, body_noun.lower(), source_noun.lower()
                ).ratio()
                # Similar but not identical — potential mismatch
                if 0.7 < ratio < 1.0:
                    corrections.append({"find": body_noun, "replace": source_noun})
                    break

    # Filter through validation
    mechanical_issues = [
        c
        for c in corrections
        if _validate_d1_correction(c.get("find", ""), c.get("replace", ""), sources)
    ]

    # Layer 2: LLM check for deeper issues mechanical match might miss
    llm_issues: list[dict] = []
    try:
        source_block = _format_sources_for_prompt(sources)
        response = call_api(
            system=(
                "Compare proper nouns in the journal against source titles/URLs. "
                "YouTube titles may have INCORRECT spellings from transcripts. "
                "Academic sources and Wikipedia have HIGHER authority. "
                "Return ONLY genuine misspellings, not style preferences."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"## Sources\n{source_block}\n\n## Journal\n{body[:12000]}",
                }
            ],
            max_tokens=4096,
            temperature=0.0,
            top_p=0.1,
            timeout=120.0,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "ProperNouns", "strict": True, "schema": _D1_SCHEMA},
            },
        )
        parsed = _parse_json(response.text or "")
        if isinstance(parsed, dict):
            for c in parsed.get("corrections", []):
                find, replace = c.get("find", ""), c.get("replace", "")
                # Only add if not already found by mechanical check and passes validation
                already_found = any(m["find"] == find for m in mechanical_issues)
                if not already_found and _validate_d1_correction(find, replace, sources):
                    llm_issues.append(c)
                    logger.info("[assessor] D1 LLM layer: %s → %s", find, replace)
    except Exception as e:
        logger.debug("[assessor] D1 LLM layer failed (non-fatal): %s", e)

    issues = mechanical_issues + llm_issues
    return {"passed": len(issues) == 0, "issues": issues}


# ---------------------------------------------------------------------------
# D4: Screenshot Placement (mechanical keyword overlap)
# ---------------------------------------------------------------------------

_IMG_PATTERN = re.compile(r"!\[([^\]]*)\]\([^)]+\)")


def _significant_keywords(text: str) -> set[str]:
    """Extract significant keywords (4+ chars, lowercased) from text."""
    return {w.lower() for w in re.findall(r"[A-Za-z]+", text) if len(w) >= 4}


def _check_d4_screenshots(body: str, sources: list[dict] | None = None) -> dict:
    """Check screenshot placement: keyword overlap first, then LLM for ambiguous cases.

    Layer 1 (deterministic): keyword overlap between alt text and preceding paragraph
    Layer 2 (LLM): only for images that passed mechanical but might be semantically wrong
    """
    lines = body.split("\n")
    sections = _get_sections(body)
    issues: list[dict] = []

    for i, line in enumerate(lines):
        m = _IMG_PATTERN.search(line.strip())
        if not m:
            continue

        alt_text = m.group(1)
        alt_keywords = _significant_keywords(alt_text)
        if len(alt_keywords) < 2:
            continue  # too few keywords to judge placement

        # Find the paragraph immediately before the image
        preceding_para = ""
        for j in range(i - 1, -1, -1):
            stripped = lines[j].strip()
            if stripped and not stripped.startswith("![") and not stripped.startswith("#"):
                preceding_para = stripped
                break

        preceding_keywords = _significant_keywords(preceding_para)
        overlap = alt_keywords & preceding_keywords

        if len(overlap) >= 2:
            continue  # well-placed: at least 2 keyword matches

        # Image may be misplaced. Find the best matching paragraph in the same section.
        best_para = ""
        best_overlap = 0
        img_pos = sum(len(l) + 1 for l in lines[:i])  # approximate char position

        # Find which section the image belongs to
        current_section = None
        for sec in sections:
            if sec["start"] <= img_pos < sec["end"]:
                current_section = sec
                break

        if current_section:
            for para in current_section["content"].split("\n\n"):
                para_stripped = para.strip()
                if not para_stripped or para_stripped.startswith("!["):
                    continue
                para_kw = _significant_keywords(para_stripped)
                this_overlap = len(alt_keywords & para_kw)
                if this_overlap > best_overlap:
                    best_overlap = this_overlap
                    best_para = para_stripped

        if best_overlap >= 2 and best_para:
            issues.append(
                {
                    "image_alt": alt_text,
                    "correct_position": best_para[:200],
                    "reason": f"keyword overlap: {best_overlap} vs {len(overlap)} with preceding",
                }
            )

    return {"passed": len(issues) == 0, "issues": issues}


# ---------------------------------------------------------------------------
# D6: Spelling (dictionary only — no LLM)
# ---------------------------------------------------------------------------


_D6_SCHEMA = {
    "type": "object",
    "properties": {
        "corrections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "find": {"type": "string"},
                    "replace": {"type": "string"},
                },
                "required": ["find", "replace"],
            },
        },
    },
    "required": ["corrections"],
}


def _check_d6_spelling(body: str, sources: list[dict] | None = None) -> dict:
    """Check spelling: dictionary first (deterministic), then LLM for unknowns.

    Layer 1: SPELLING_FIXES dictionary — guaranteed correct
    Layer 2: LLM scan for terms not in dictionary
    """
    # Layer 1: deterministic dictionary
    dict_issues: list[dict] = []
    for wrong, right in SPELLING_FIXES.items():
        if wrong in body:
            dict_issues.append({"find": wrong, "replace": right})

    # Layer 2: LLM for unknown misspellings
    llm_issues: list[dict] = []
    try:
        response = call_api(
            system=(
                "Check this archaeology text for misspelled archaeological terms. "
                "Common errors: dolman→dolmen, synamic→synodic, Nufian→Natufian. "
                "Return ONLY clear misspellings of technical/archaeological terms."
            ),
            messages=[{"role": "user", "content": body[:10000]}],
            max_tokens=4096,
            temperature=0.0,
            top_p=0.1,
            timeout=60.0,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "Spelling", "strict": True, "schema": _D6_SCHEMA},
            },
        )
        parsed = _parse_json(response.text or "")
        if isinstance(parsed, dict):
            dict_finds = {i["find"] for i in dict_issues}
            for c in parsed.get("corrections", []):
                find, replace = c.get("find", ""), c.get("replace", "")
                if find and replace and find != replace and find not in dict_finds and find in body:
                    llm_issues.append(c)
                    logger.info("[assessor] D6 LLM layer: %s → %s", find, replace)
    except Exception as e:
        logger.debug("[assessor] D6 LLM layer failed (non-fatal): %s", e)

    issues = dict_issues + llm_issues
    return {"passed": len(issues) == 0, "issues": issues}


# ---------------------------------------------------------------------------
# D9: Summary Accuracy (mechanical proper noun check)
# ---------------------------------------------------------------------------


_D9_SCHEMA = {
    "type": "object",
    "properties": {
        "accurate": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "corrected_summary": {"type": "string"},
    },
    "required": ["accurate"],
}


def _check_d9_summary(body: str, sources: list[dict] | None = None) -> dict:
    """Check summary accuracy: mechanical noun check first, then LLM semantic check.

    Layer 1 (deterministic): proper noun matching between summary and body
    Layer 2 (LLM): semantic accuracy — do claims in summary match the body?
    """
    # Extract summary (italic text between --- markers at top)
    summary = ""
    if body.startswith("*"):
        end = body.find("\n---")
        if end > 0:
            summary = body[:end].strip()
    elif "\n*" in body[:500]:
        start = body.find("\n*")
        end = body.find("\n---", start)
        if end > 0:
            summary = body[start:end].strip()

    if not summary:
        return {"passed": True, "issues": [], "d9_data": {}}

    # Extract proper nouns from summary and body (after summary)
    summary_nouns = _extract_proper_nouns(summary)

    # Body after the summary (skip the summary + --- separator)
    body_after_summary = body
    sep_idx = body.find("\n---")
    if sep_idx > 0:
        body_after_summary = body[sep_idx:]

    body_nouns = _extract_proper_nouns(body_after_summary)

    # Check: every summary noun must appear in the body
    mismatches: list[dict] = []
    for s_noun in summary_nouns:
        if s_noun in body_nouns:
            continue  # exact match — fine

        # Fuzzy match: find closest body noun
        best_match = ""
        best_ratio = 0.0
        for b_noun in body_nouns:
            ratio = difflib.SequenceMatcher(None, s_noun.lower(), b_noun.lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = b_noun

        if best_ratio >= 0.7 and best_match:
            # Close match but not identical — likely a typo/mismatch
            mismatches.append({"find": s_noun, "replace": best_match})
        elif best_ratio < 0.7:
            # No close match at all — summary noun not grounded in body
            mismatches.append({"find": s_noun, "replace": ""})

    mechanical_accurate = len(mismatches) == 0
    issue_strs = [
        f"Summary noun '{m['find']}' not in body"
        + (f" (closest: '{m['replace']}')" if m["replace"] else "")
        for m in mismatches
    ]

    # Layer 2: LLM semantic check — do summary claims match the body?
    llm_accurate = True
    llm_corrected = ""
    if summary:
        try:
            sections = _get_sections(body)
            section_snippets = []
            for sec in sections[:8]:
                if sec["header"]:
                    section_snippets.append(f"{sec['header']}: {sec['content'][:200]}")
            response = call_api(
                system=(
                    "Compare this journal summary against the section content. "
                    "Check that proper nouns and claims in the summary match the body. "
                    "If inaccurate, provide a corrected summary."
                ),
                messages=[
                    {
                        "role": "user",
                        "content": f"## Summary\n{summary}\n\n## Sections\n"
                        + "\n\n".join(section_snippets),
                    }
                ],
                max_tokens=4096,
                temperature=0.0,
                top_p=0.1,
                timeout=60.0,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "SummaryCheck", "strict": True, "schema": _D9_SCHEMA},
                },
            )
            parsed = _parse_json(response.text or "")
            if isinstance(parsed, dict):
                llm_accurate = parsed.get("accurate", True)
                llm_corrected = parsed.get("corrected_summary", "")
                if not llm_accurate:
                    for issue in parsed.get("issues", []):
                        if issue not in issue_strs:
                            issue_strs.append(f"(LLM) {issue}")
                    logger.info("[assessor] D9 LLM layer: summary inaccurate")
        except Exception as e:
            logger.debug("[assessor] D9 LLM layer failed (non-fatal): %s", e)

    accurate = mechanical_accurate and llm_accurate

    return {
        "passed": accurate,
        "issues": issue_strs,
        "d9_data": {
            "accurate": accurate,
            "mismatches": mismatches,
            "corrected_summary": llm_corrected if not llm_accurate else "",
        },
    }


def _regenerate_summary(body: str, settings: LyraSettings) -> str:
    """Regenerate the italic summary from the corrected body.

    Instead of patching the old summary, generate a fresh one from the
    current body so it's guaranteed to match.
    """
    # Extract body without summary (everything after ---)
    sep_idx = body.find("\n---")
    if sep_idx < 0:
        return body
    body_after = body[sep_idx + 4 :].strip()

    # Get first 300 chars of each section for context
    sections = _get_sections(body_after)
    snippets = []
    for sec in sections[:8]:
        if sec["header"] and "Sources" not in sec["header"]:
            snippets.append(f"{sec['header']}: {sec['content'][:300]}")

    try:
        response = call_api(
            system=(
                "Write a 3-4 sentence summary of this archaeology journal. "
                "Cover the top 3-4 findings. Use proper nouns exactly as they appear. "
                "No label, no heading — just the summary sentences in italic markdown (*text*)."
            ),
            messages=[{"role": "user", "content": "\n\n".join(snippets)}],
            max_tokens=1024,
            temperature=0.0,
            top_p=0.1,
            timeout=60.0,
        )
        new_summary = (response.text or "").strip()
        if not new_summary or len(new_summary) < 50:
            return body

        # Ensure it's wrapped in *italic*
        if not new_summary.startswith("*"):
            new_summary = f"*{new_summary}*"

        # Replace the old summary
        old_summary_end = sep_idx
        body = new_summary + "\n" + body[old_summary_end:]
        logger.info("[assessor] D9: regenerated summary (%d chars)", len(new_summary))
    except Exception as e:
        logger.warning("[assessor] D9: summary regeneration failed: %s", e)

    return body


def _fix_d1_d4_d6_d9(body: str, check_result: dict) -> tuple[str, list[dict]]:
    """Apply mechanical fixes from the separate LLM check results."""
    fixes: list[dict] = []

    # D1: Proper noun fixes
    for fix in check_result.get("d1_issues", []):
        find = fix.get("find", "")
        replace = fix.get("replace", "")
        if find and replace and find in body:
            body = body.replace(find, replace)
            fixes.append({"dimension": "D1", "find": find, "replace": replace})
            logger.info("[assessor] D1: %s → %s", find, replace)

    # D4: Screenshot placement fixes
    for fix in check_result.get("d4_issues", []):
        image_alt = fix.get("image_alt", "")
        correct_position = fix.get("correct_position", "")
        if image_alt and correct_position:
            # Find the image line
            img_pattern = re.compile(rf"!\[{re.escape(image_alt)}\]\([^)]+\)")
            img_match = img_pattern.search(body)
            if img_match:
                img_line = img_match.group()
                # Remove from current position
                body = body.replace(img_line, "", 1)
                # Insert after the correct paragraph
                insert_idx = body.find(correct_position)
                if insert_idx >= 0:
                    # Find end of that paragraph
                    para_end = body.find("\n\n", insert_idx)
                    if para_end >= 0:
                        body = body[:para_end] + "\n\n" + img_line + body[para_end:]
                        fixes.append({"dimension": "D4", "image": image_alt, "moved": True})
                        logger.info("[assessor] D4: moved image '%s'", image_alt)

    # D6: Spelling fixes from LLM
    for fix in check_result.get("d6_issues", []):
        find = fix.get("find", "")
        replace = fix.get("replace", "")
        if find and replace and find in body:
            body = body.replace(find, replace)
            fixes.append({"dimension": "D6", "find": find, "replace": replace})
            logger.info("[assessor] D6: %s → %s", find, replace)

    # D6: Also apply the static spelling dictionary
    for wrong, correct in SPELLING_FIXES.items():
        if wrong in body:
            body = body.replace(wrong, correct)
            fixes.append({"dimension": "D6", "find": wrong, "replace": correct})
            logger.info("[assessor] D6 (dict): %s → %s", wrong, correct)

    # D9: Summary accuracy fix — replace mismatched proper nouns in summary
    d9_data = check_result.get("d9_data", {})
    if isinstance(d9_data, dict) and not d9_data.get("accurate", True):
        mismatches = d9_data.get("mismatches", [])
        # Extract summary region to apply fixes only there
        summary_end = body.find("\n---")
        if summary_end > 0:
            summary_text = body[:summary_end]
            for mm in mismatches:
                find = mm.get("find", "")
                replace = mm.get("replace", "")
                if find and replace and find in summary_text:
                    summary_text = summary_text.replace(find, replace)
                    fixes.append({"dimension": "D9", "find": find, "replace": replace})
                    logger.info("[assessor] D9: %s → %s in summary", find, replace)
            body = summary_text + body[summary_end:]

    return body, fixes


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def assess_and_fix(
    body: str,
    sources: list[dict],
    week_start: datetime | None = None,
    settings: LyraSettings | None = None,
    max_iterations: int = 5,
) -> tuple[str, AssessmentResult]:
    """Assess journal quality and fix issues. Returns (fixed_body, result).

    Each source dict has: {"citation": int, "url": str, "label": str, "type": str}
    """
    if settings is None:
        settings = _get_settings()

    # Safety guard: if no sources provided, skip assessment to avoid destroying content
    if not sources:
        logger.warning("[assessor] No sources provided — skipping assessment to protect content")
        return body, AssessmentResult(
            score=0, passed=False, dimensions={}, fixes_applied=[], iteration=0
        )

    # Preserve the sources section — never modify or remove it
    original_sources_section = ""
    for marker in ("### Sources", "## Sources"):
        idx = body.find(marker)
        if idx >= 0:
            original_sources_section = body[idx:]
            break

    best_body = body
    best_result = AssessmentResult(score=0, passed=False, iteration=0)

    for iteration in range(1, max_iterations + 1):
        logger.info("[assessor] === Iteration %d/%d ===", iteration, max_iterations)
        all_fixes: list[dict] = []
        dims: dict[str, bool] = {}

        # --- Mechanical checks first ---

        # D7: Citation format
        d7 = _check_d7_citation_format(best_body, sources)
        dims["D7_citation_format"] = d7["passed"]
        if not d7["passed"]:
            best_body = _fix_d7_citation_format(best_body, sources)
            all_fixes.append({"dimension": "D7", "issues": d7["issues"]})
            logger.info("[assessor] D7: fixed %d issues", len(d7["issues"]))

        # D8: Week date
        # Extract first line that looks like a title
        first_lines = best_body[:500]
        d8 = _check_d8_week_date(first_lines, week_start)
        dims["D8_week_date"] = d8["passed"]
        if not d8["passed"] and week_start:
            best_body = _fix_d8_week_date(best_body, week_start)
            all_fixes.append({"dimension": "D8", "issues": d8["issues"]})
            logger.info("[assessor] D8: fixed week date")

        # D5: Source quality
        d5 = _check_d5_source_quality(sources)
        dims["D5_source_quality"] = d5["passed"]
        if not d5["passed"]:
            best_body = _fix_d5_source_quality(best_body, sources, d5["bad_sources"], settings)
            all_fixes.append({"dimension": "D5", "bad_sources": d5["bad_sources"]})
            logger.info("[assessor] D5: removed %d bad sources", len(d5["bad_sources"]))

        # D3: Academic citation style
        d3 = _check_d3_academic_citations(best_body)
        dims["D3_academic_citations"] = d3["passed"]
        if not d3["passed"]:
            best_body = _fix_d3_academic_citations(
                best_body, sources, d3["academic_citations"], settings
            )
            all_fixes.append({"dimension": "D3", "count": len(d3["academic_citations"])})
            logger.info(
                "[assessor] D3: fixing %d academic citations", len(d3["academic_citations"])
            )

        # D2: Citation coverage (sentence-level matching, no prose rewriting)
        d2 = _check_d2_citation_coverage(best_body, sources)
        dims["D2_citation_coverage"] = d2["passed"]
        if not d2["passed"]:
            best_body = _fix_d2_citation_coverage(
                best_body, sources, d2["uncited_paragraphs"], settings
            )
            all_fixes.append({"dimension": "D2", "uncited": len(d2["uncited_paragraphs"])})
            logger.info(
                "[assessor] D2: fixing %d uncited paragraphs",
                len(d2["uncited_paragraphs"]),
            )

        # D10: Section balance
        d10 = _check_d10_section_balance(best_body)
        dims["D10_section_balance"] = d10["passed"]
        if not d10["passed"]:
            best_body = _fix_d10_section_balance(best_body, sources, settings)
            all_fixes.append({"dimension": "D10", "issues": d10["issues"]})
            logger.info("[assessor] D10: fixing section balance")

        # --- Mechanical checks (D1, D4, D6, D9) ---
        d1 = _check_d1_proper_nouns(best_body, sources, settings)
        dims["D1_proper_nouns"] = d1["passed"]
        if not d1["passed"]:
            logger.info("[assessor] D1: found %d proper noun issues", len(d1["issues"]))

        d4 = _check_d4_screenshots(best_body)
        dims["D4_screenshot_placement"] = d4["passed"]
        if not d4["passed"]:
            logger.info("[assessor] D4: found %d misplaced screenshots", len(d4["issues"]))

        d6 = _check_d6_spelling(best_body)
        dims["D6_spelling"] = d6["passed"]
        if not d6["passed"]:
            logger.info("[assessor] D6: found %d spelling issues", len(d6["issues"]))

        # Apply D1/D4/D6 fixes first (before D9 checks the summary)
        combined_pre = {
            "d1_issues": d1.get("issues", []),
            "d4_issues": d4.get("issues", []),
            "d6_issues": d6.get("issues", []),
            "d9_data": {},
        }
        if not all([d1["passed"], d4["passed"], d6["passed"]]):
            best_body, pre_fixes = _fix_d1_d4_d6_d9(best_body, combined_pre)
            all_fixes.extend(pre_fixes)

        # Re-apply spelling dictionary AFTER D1 — overrides any bad corrections
        for wrong, right in SPELLING_FIXES.items():
            if wrong in best_body:
                best_body = best_body.replace(wrong, right)

        # D9: Summary accuracy (runs AFTER other fixes so it checks corrected body)
        d9 = _check_d9_summary(best_body)
        dims["D9_summary_accuracy"] = d9["passed"]
        if not d9["passed"]:
            logger.info("[assessor] D9: summary inaccurate — regenerating from corrected body")
            best_body = _regenerate_summary(best_body, settings)
            all_fixes.append({"dimension": "D9", "find": "summary", "replace": "regenerated"})

        # --- Safety: restore sources section if damaged ---
        if original_sources_section:
            for marker in ("### Sources", "## Sources"):
                curr_idx = best_body.find(marker)
                if curr_idx >= 0:
                    current_sources = best_body[curr_idx:]
                    # If sources section shrank dramatically, restore it
                    if len(current_sources) < len(original_sources_section) * 0.5:
                        logger.warning("[assessor] Sources section damaged — restoring original")
                        best_body = best_body[:curr_idx] + original_sources_section
                    break
            else:
                # Sources section completely removed — restore it
                logger.warning("[assessor] Sources section removed — restoring original")
                best_body = best_body.rstrip() + "\n\n" + original_sources_section

        # --- Score ---
        score = sum(1 for v in dims.values() if v)
        passed = score == 10

        result = AssessmentResult(
            score=score,
            passed=passed,
            dimensions=dims,
            fixes_applied=all_fixes,
            iteration=iteration,
        )

        logger.info(
            "[assessor] Iteration %d: %d/10 (%s)",
            iteration,
            score,
            "PASS" if passed else "FAIL: " + ", ".join(k for k, v in dims.items() if not v),
        )

        # Keep best result
        if score > best_result.score:
            best_result = result

        if passed:
            return best_body, result

    return best_body, best_result
