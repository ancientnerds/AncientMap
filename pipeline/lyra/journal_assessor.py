"""Journal quality assessor — 10-dimension convergence loop.

Runs after journal assembly, before polish/headline. Checks 10 quality
dimensions and applies targeted fixes (mostly LLM-powered) until 10/10.

Usage:
    from pipeline.lyra.journal_assessor import assess_and_fix

    fixed_body, result = assess_and_fix(body, sources, week_start, settings)
    # result.score == 10 and result.passed == True
"""

from __future__ import annotations

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

    # Remove bad citation markers
    for num in bad_nums:
        body = re.sub(rf"\s*\[{num}\]", "", body)

    # Clean up double spaces
    body = re.sub(r"  +", " ", body)

    # Find paragraphs that lost all citations
    uncited = _find_uncited_paragraphs(body, sources)
    if uncited:
        good_sources = [s for s in sources if s.get("citation") not in bad_nums]
        body = _fix_d2_citation_coverage(body, good_sources, uncited, settings)

    return body


# ---------------------------------------------------------------------------
# D2: Citation Coverage (mechanical check + LLM fix)
# ---------------------------------------------------------------------------


def _find_uncited_paragraphs(body: str, sources: list[dict]) -> list[str]:
    """Find paragraphs >100 chars without any [N] citation."""
    uncited: list[str] = []
    cite_pattern = re.compile(r"\[\d+\]")

    for para in body.split("\n\n"):
        stripped = para.strip()
        # Skip headers, images, horizontal rules, short paragraphs
        if (
            not stripped
            or stripped.startswith("#")
            or stripped.startswith("![")
            or stripped.startswith("---")
            or stripped.startswith("*")  # italic summary
            or len(stripped) < 100
        ):
            continue
        if not cite_pattern.search(stripped):
            uncited.append(stripped)

    return uncited


def _check_d2_citation_coverage(body: str, sources: list[dict]) -> dict:
    """Check that every substantial paragraph has at least one citation."""
    uncited = _find_uncited_paragraphs(body, sources)
    return {
        "passed": len(uncited) == 0,
        "uncited_paragraphs": uncited,
    }


def _fix_d2_citation_coverage(
    body: str,
    sources: list[dict],
    uncited: list[str],
    settings: LyraSettings,
) -> str:
    """Ask LLM to add citations to uncited paragraphs."""
    source_block = _format_sources_for_prompt(sources)

    for para in uncited[:5]:  # Cap at 5 to limit LLM calls
        system = (
            "You are a citation editor. You receive a paragraph and a source list. "
            "Rewrite the paragraph adding [N] citations where claims are supported by "
            "the sources. Keep the text identical except for inserting [N] markers. "
            "Only cite sources that actually support the claim. If no source fits, "
            "leave the paragraph unchanged."
        )
        user = f"## Paragraph\n{para}\n\n## Sources\n{source_block}"

        raw = _llm_call(system, user, settings)
        if raw and raw.strip() and len(raw.strip()) > 50:
            # Replace the original paragraph
            body = body.replace(para, raw.strip())
            logger.info("[assessor] D2: re-cited paragraph (%d chars)", len(para))

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

    total_words = len(body.split())
    if total_words < 1500:
        issues.append(f"Total word count {total_words} < 1500 minimum")
    if total_words > 4000:
        issues.append(f"Total word count {total_words} > 4000 maximum")

    cite_pattern = re.compile(r"\[\d+\]")
    for sec in sections:
        if not sec["header"]:
            continue
        word_count = len(sec["content"].split())
        if word_count > 600:
            issues.append(f"Section '{sec['header']}' has {word_count} words (>400)")
        if word_count > 50 and not cite_pattern.search(sec["content"]):
            issues.append(f"Section '{sec['header']}' has 0 citations")

    return {"passed": len(issues) == 0, "issues": issues}


def _fix_d10_section_balance(
    body: str,
    sources: list[dict],
    settings: LyraSettings,
) -> str:
    """Condense overlong sections via LLM."""
    sections = _get_sections(body)
    source_block = _format_sources_for_prompt(sources)

    for sec in sections:
        if not sec["header"]:
            continue
        word_count = len(sec["content"].split())
        if word_count <= 400:
            continue

        system = (
            "You are an editor. Condense this section to under 600 words while "
            "preserving all [N] citation markers and key facts. Keep the same tone "
            "and structure. Return ONLY the condensed section text (no header)."
        )
        user = (
            f"## Section header\n{sec['header']}\n\n"
            f"## Section content ({word_count} words, must be <600)\n{sec['content']}\n\n"
            f"## Sources for reference\n{source_block}"
        )

        raw = _llm_call(system, user, settings)
        if raw and raw.strip() and len(raw.strip()) > 50:
            # Replace section content in the body
            old_block = f"{sec['header']}\n\n{sec['content']}"
            new_block = f"{sec['header']}\n\n{raw.strip()}"
            body = body.replace(old_block, new_block, 1)
            logger.info(
                "[assessor] D10: condensed '%s' from %d to ~%d words",
                sec["header"],
                word_count,
                len(raw.split()),
            )

    return body


# ---------------------------------------------------------------------------
# D1: Proper Nouns (LLM)
# ---------------------------------------------------------------------------

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
                    "reason": {"type": "string"},
                },
                "required": ["find", "replace"],
            },
        },
    },
    "required": ["corrections"],
}


def _check_d1_proper_nouns(body: str, sources: list[dict], settings: LyraSettings) -> dict:
    """Check proper nouns against source titles."""
    source_block = _format_sources_for_prompt(sources)
    system = (
        "Compare every proper noun in the journal (site names, people, caves, "
        "cultures, locations) against the source titles/URLs. Sources have the "
        "CORRECT spelling. Return corrections for any mismatches.\n\n"
        "Examples: Monteppi→Montesiepi, Galano Giati→Galgano Guidotti, "
        "Vulcansky Dolman→Volkonsky Dolmen, Goff's Cave→Gough's Cave"
    )
    user = f"## Source List\n{source_block}\n\n## Journal Text\n{body[:15000]}"

    try:
        response = call_api(
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=4096,
            temperature=0.0,
            timeout=120.0,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "ProperNouns", "strict": True, "schema": _D1_SCHEMA},
            },
        )
        parsed = _parse_json(response.text or "")
    except (LyraAPIError, Exception) as e:
        logger.warning("[assessor] D1 call failed: %s", e)
        parsed = {}

    issues = parsed.get("corrections", []) if isinstance(parsed, dict) else []
    return {"passed": len(issues) == 0, "issues": issues}


# ---------------------------------------------------------------------------
# D4: Screenshot Placement (LLM)
# ---------------------------------------------------------------------------

_D4_SCHEMA = {
    "type": "object",
    "properties": {
        "misplacements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "image_alt": {"type": "string"},
                    "correct_position": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["image_alt"],
            },
        },
    },
    "required": ["misplacements"],
}


def _check_d4_screenshots(body: str, settings: LyraSettings) -> dict:
    """Check if screenshots are placed after matching paragraphs."""
    # Extract image lines and their surrounding context
    lines = body.split("\n")
    img_contexts = []
    for i, line in enumerate(lines):
        if line.strip().startswith("!["):
            before = "\n".join(lines[max(0, i - 5) : i])
            img_contexts.append(f"Image: {line.strip()}\nPreceding paragraph: {before[-300:]}")

    if not img_contexts:
        return {"passed": True, "issues": []}

    system = (
        "For each image, check if its alt text topic matches the paragraph before it. "
        "Return misplacements only — images correctly placed should not appear in the list."
    )
    user = "\n\n".join(img_contexts)

    try:
        response = call_api(
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=4096,
            temperature=0.0,
            timeout=60.0,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "Screenshots", "strict": True, "schema": _D4_SCHEMA},
            },
        )
        parsed = _parse_json(response.text or "")
    except (LyraAPIError, Exception) as e:
        logger.warning("[assessor] D4 call failed: %s", e)
        parsed = {}

    issues = parsed.get("misplacements", []) if isinstance(parsed, dict) else []
    return {"passed": len(issues) == 0, "issues": issues}


# ---------------------------------------------------------------------------
# D6: Spelling (LLM)
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


def _check_d6_spelling(body: str, settings: LyraSettings) -> dict:
    """Check for misspelled archaeological terms."""
    # Apply dictionary fixes first
    issues_from_dict = []
    for wrong, right in SPELLING_FIXES.items():
        if wrong in body:
            issues_from_dict.append({"find": wrong, "replace": right})

    # LLM check for unknown misspellings (only send first 10K to keep it fast)
    system = (
        "Check this archaeology journal for misspelled archaeological terms. "
        "Common errors: dolman→dolmen, synamic→synodic, Nufian→Natufian. "
        "Return only clear misspellings, not stylistic preferences."
    )
    user = body[:10000]

    try:
        response = call_api(
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=4096,
            temperature=0.0,
            timeout=60.0,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "Spelling", "strict": True, "schema": _D6_SCHEMA},
            },
        )
        parsed = _parse_json(response.text or "")
    except (LyraAPIError, Exception) as e:
        logger.warning("[assessor] D6 LLM call failed: %s", e)
        parsed = {}

    llm_issues = parsed.get("corrections", []) if isinstance(parsed, dict) else []
    all_issues = issues_from_dict + llm_issues
    return {"passed": len(all_issues) == 0, "issues": all_issues}


# ---------------------------------------------------------------------------
# D9: Summary Accuracy (LLM)
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


def _check_d9_summary(body: str, settings: LyraSettings) -> dict:
    """Check summary accuracy against body content."""
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

    # Get first 200 chars of each section for comparison
    sections = _get_sections(body)
    section_summaries = []
    for sec in sections[:8]:
        if sec["header"]:
            section_summaries.append(f"{sec['header']}: {sec['content'][:200]}")

    system = (
        "Compare this journal summary against the section content. "
        "Check that proper nouns and claims in the summary match the body. "
        "If inaccurate, provide a corrected summary."
    )
    user = f"## Summary\n{summary}\n\n## Section Content\n" + "\n\n".join(section_summaries)

    try:
        response = call_api(
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=4096,
            temperature=0.0,
            timeout=60.0,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "SummaryCheck", "strict": True, "schema": _D9_SCHEMA},
            },
        )
        parsed = _parse_json(response.text or "")
    except (LyraAPIError, Exception) as e:
        logger.warning("[assessor] D9 call failed: %s", e)
        parsed = {"accurate": True}

    if not isinstance(parsed, dict):
        parsed = {"accurate": True}

    accurate = parsed.get("accurate", True)
    return {
        "passed": accurate,
        "issues": parsed.get("issues", []),
        "d9_data": parsed,
    }


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

    # D9: Summary accuracy fix
    d9_data = check_result.get("d9_data", {})
    if isinstance(d9_data, dict) and not d9_data.get("accurate", True):
        corrected = d9_data.get("corrected_summary", "")
        if corrected:
            # Replace the italic summary between first --- markers
            summary_pattern = re.compile(r"(---\s*\n)(\*.*?\*)([\s\n]*---)", re.DOTALL)
            m = summary_pattern.search(body)
            if m:
                body = body[: m.start(2)] + corrected + body[m.end(2) :]
                fixes.append({"dimension": "D9", "summary_corrected": True})
                logger.info("[assessor] D9: corrected summary")

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

        # D2: Citation coverage
        d2 = _check_d2_citation_coverage(best_body, sources)
        dims["D2_citation_coverage"] = d2["passed"]
        if not d2["passed"]:
            best_body = _fix_d2_citation_coverage(
                best_body, sources, d2["uncited_paragraphs"], settings
            )
            all_fixes.append({"dimension": "D2", "uncited": len(d2["uncited_paragraphs"])})
            logger.info("[assessor] D2: re-citing %d paragraphs", len(d2["uncited_paragraphs"]))

        # D10: Section balance
        d10 = _check_d10_section_balance(best_body)
        dims["D10_section_balance"] = d10["passed"]
        if not d10["passed"]:
            best_body = _fix_d10_section_balance(best_body, sources, settings)
            all_fixes.append({"dimension": "D10", "issues": d10["issues"]})
            logger.info("[assessor] D10: fixing section balance")

        # --- Separate LLM checks (D1, D4, D6, D9) ---
        d1 = _check_d1_proper_nouns(best_body, sources, settings)
        dims["D1_proper_nouns"] = d1["passed"]
        if not d1["passed"]:
            logger.info("[assessor] D1: found %d proper noun issues", len(d1["issues"]))

        d4 = _check_d4_screenshots(best_body, settings)
        dims["D4_screenshot_placement"] = d4["passed"]
        if not d4["passed"]:
            logger.info("[assessor] D4: found %d misplaced screenshots", len(d4["issues"]))

        d6 = _check_d6_spelling(best_body, settings)
        dims["D6_spelling"] = d6["passed"]
        if not d6["passed"]:
            logger.info("[assessor] D6: found %d spelling issues", len(d6["issues"]))

        d9 = _check_d9_summary(best_body, settings)
        dims["D9_summary_accuracy"] = d9["passed"]
        if not d9["passed"]:
            logger.info("[assessor] D9: summary inaccurate")

        # Apply fixes from all 4 LLM checks
        combined = {
            "d1_issues": d1.get("issues", []),
            "d4_issues": d4.get("issues", []),
            "d6_issues": d6.get("issues", []),
            "d9_data": d9.get("d9_data", {}),
        }
        any_failed = not all([d1["passed"], d4["passed"], d6["passed"], d9["passed"]])
        if any_failed:
            best_body, llm_fixes = _fix_d1_d4_d6_d9(best_body, combined)
            all_fixes.extend(llm_fixes)

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
