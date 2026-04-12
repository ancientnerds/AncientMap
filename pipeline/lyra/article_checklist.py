"""Programmatic quality checklist for weekly journal articles.

Runs after the LLM-based assessment as a mechanical final gate.
All checks are deterministic — no LLM calls.

Usage:
    from pipeline.lyra.article_checklist import run_checklist, ensure_youtube_sources

    # Guarantee YouTube sources before assessment
    body, unified_sources = ensure_youtube_sources(body, unified_sources, items)

    # Run all checks after headline generation
    result = run_checklist(body, unified_sources, items, headline, tldr, week_start)
    if not result.passed:
        for name, check in result.checks.items():
            if not check.passed:
                logger.warning("Checklist %s FAILED: %s", name, check.message)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """Result of a single checklist item."""

    passed: bool
    message: str
    details: list[str] = field(default_factory=list)


@dataclass
class ChecklistResult:
    """Result of the full quality checklist."""

    passed: bool
    checks: dict[str, CheckResult] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> dict:
        """Serialize for storage in quality_report JSON."""
        return {
            "passed": self.passed,
            "summary": self.summary,
            "checks": {
                name: {
                    "passed": c.passed,
                    "message": c.message,
                    "details": c.details[:5],  # cap details for storage
                }
                for name, c in self.checks.items()
            },
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _body_without_sources(body: str) -> str:
    """Return body text excluding the ### Sources / ## Sources footer."""
    for marker in ("### Sources", "## Sources"):
        idx = body.find(marker)
        if idx >= 0:
            return body[:idx]
    return body


def _extract_body_citations(body: str) -> set[int]:
    """Extract all [N] citation numbers from body text (excluding Sources section)."""
    return {int(m) for m in re.findall(r"\[(\d+)\]", _body_without_sources(body))}


def _extract_video_id_from_url(url: str) -> str | None:
    """Extract YouTube video ID from a URL."""
    m = re.search(r"youtu\.be/([a-zA-Z0-9_-]{11})", url)
    if m:
        return m.group(1)
    m = re.search(r"youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})", url)
    if m:
        return m.group(1)
    return None


def _significant_keywords(text: str) -> set[str]:
    """Extract keywords (4+ chars, lowercased) for fuzzy matching."""
    return {w.lower() for w in re.findall(r"[A-Za-z]+", text) if len(w) >= 4}


# ---------------------------------------------------------------------------
# ensure_youtube_sources — hard guarantee
# ---------------------------------------------------------------------------


def ensure_youtube_sources(
    body: str,
    unified_sources: list[dict],
    items: list[dict],
) -> tuple[str, list[dict]]:
    """Guarantee every item's YouTube video appears in the sources list.

    For each item whose video_id is missing from unified_sources:
    1. Create a source entry with the YouTube URL + timestamp
    2. Find the best-matching paragraph in the body and insert [N] citation
    3. After all additions, renumber citations sequentially

    Returns (modified_body, modified_sources).
    """
    # Collect video IDs already in sources
    existing_vids: set[str] = set()
    for src in unified_sources:
        vid = _extract_video_id_from_url(src.get("url", ""))
        if vid:
            existing_vids.add(vid)

    # Find missing video IDs
    next_citation = max((s["citation"] for s in unified_sources), default=0) + 1
    added = 0

    for item in items:
        vid = item.get("video_id", "")
        if not vid or vid in existing_vids:
            continue

        # Build YouTube source entry
        ts = item.get("timestamp_seconds", 0)
        url = f"https://youtu.be/{vid}?t={ts}" if ts else f"https://youtu.be/{vid}"
        channel = item.get("channel_name", "YouTube")
        title = item.get("video_title", "")
        label = f'{channel} \u2014 "{title}"'

        unified_sources.append(
            {
                "citation": next_citation,
                "url": url,
                "label": label,
                "snippet": "; ".join(item.get("facts", [])[:3]),
                "type": "youtube",
            }
        )

        # Insert [N] into body after the best-matching paragraph
        headline_kw = _significant_keywords(item.get("headline", ""))
        if headline_kw and len(headline_kw) >= 2:
            check_body = _body_without_sources(body)
            paragraphs = check_body.split("\n\n")
            best_idx = -1
            best_score = 0

            for i, para in enumerate(paragraphs):
                stripped = para.strip()
                if not stripped or stripped.startswith("#") or stripped.startswith("!["):
                    continue
                para_kw = _significant_keywords(stripped)
                score = len(headline_kw & para_kw)
                if score > best_score and score >= 2:
                    best_score = score
                    best_idx = i

            if best_idx >= 0:
                # Append citation to the end of the paragraph's last sentence
                para = paragraphs[best_idx].rstrip()
                if para.endswith("."):
                    para = f"{para[:-1]} [{next_citation}]."
                else:
                    para = f"{para} [{next_citation}]"
                paragraphs[best_idx] = para

                # Reconstruct body with the Sources section
                sources_section = ""
                for marker in ("### Sources", "## Sources"):
                    idx = body.find(marker)
                    if idx >= 0:
                        sources_section = body[idx:]
                        break
                body = "\n\n".join(paragraphs)
                if sources_section:
                    body = body + "\n\n" + sources_section

        existing_vids.add(vid)
        next_citation += 1
        added += 1

    if added:
        logger.info("ensure_youtube_sources: added %d missing YouTube sources", added)

    return body, unified_sources


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_youtube_coverage(items: list[dict], unified_sources: list[dict]) -> CheckResult:
    """Every item's YouTube video_id appears in unified_sources URLs."""
    source_vids: set[str] = set()
    for src in unified_sources:
        vid = _extract_video_id_from_url(src.get("url", ""))
        if vid:
            source_vids.add(vid)

    missing: list[str] = []
    for item in items:
        vid = item.get("video_id", "")
        if vid and vid not in source_vids:
            headline = item.get("headline", "?")[:60]
            missing.append(f"{vid} ({headline})")

    if missing:
        return CheckResult(
            passed=False,
            message=f"{len(missing)} YouTube video(s) missing from sources",
            details=missing,
        )
    return CheckResult(passed=True, message=f"All {len(items)} videos covered")


def _check_citation_integrity(body: str, unified_sources: list[dict]) -> CheckResult:
    """Every [N] in body maps to a source in the list."""
    body_cites = _extract_body_citations(body)
    source_nums = {s["citation"] for s in unified_sources}
    orphans = body_cites - source_nums

    if orphans:
        return CheckResult(
            passed=False,
            message=f"{len(orphans)} orphan citation(s) in body",
            details=[f"[{n}] has no source" for n in sorted(orphans)],
        )
    return CheckResult(passed=True, message=f"All {len(body_cites)} citations valid")


def _check_no_phantom_sources(body: str, unified_sources: list[dict]) -> CheckResult:
    """Every source in the list has at least one [N] in the body."""
    body_cites = _extract_body_citations(body)
    phantoms: list[str] = []

    for src in unified_sources:
        if src["citation"] not in body_cites:
            label = src.get("label", src.get("url", "?"))[:60]
            phantoms.append(f"[{src['citation']}] {label}")

    if phantoms:
        return CheckResult(
            passed=False,
            message=f"{len(phantoms)} source(s) not cited in body",
            details=phantoms,
        )
    return CheckResult(passed=True, message=f"All {len(unified_sources)} sources cited")


def _check_format(body: str, headline: str, tldr: str, week_start: datetime) -> CheckResult:
    """Title format, TLDR exists."""
    issues: list[str] = []

    if not headline.startswith("Week of"):
        issues.append(f"Headline doesn't start with 'Week of': {headline[:40]}")

    if not tldr or len(tldr) < 20:
        issues.append("TLDR missing or too short")

    if issues:
        return CheckResult(passed=False, message="; ".join(issues), details=issues)
    return CheckResult(passed=True, message="Format OK")


def _check_minimum_content(body: str, unified_sources: list[dict]) -> CheckResult:
    """Body > 1000 chars, sources >= 5."""
    issues: list[str] = []
    check_body = _body_without_sources(body)

    if len(check_body) < 1000:
        issues.append(f"Body too short: {len(check_body)} chars (min 1000)")

    if len(unified_sources) < 5:
        issues.append(f"Too few sources: {len(unified_sources)} (min 5)")

    if issues:
        return CheckResult(passed=False, message="; ".join(issues), details=issues)
    return CheckResult(
        passed=True,
        message=f"Content OK: {len(check_body)} chars, {len(unified_sources)} sources",
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_checklist(
    body: str,
    unified_sources: list[dict],
    items: list[dict],
    headline: str,
    tldr: str,
    week_start: datetime,
) -> ChecklistResult:
    """Run all programmatic quality checks. No LLM calls — purely mechanical."""
    checks: dict[str, CheckResult] = {}

    checks["youtube_coverage"] = _check_youtube_coverage(items, unified_sources)
    checks["citation_integrity"] = _check_citation_integrity(body, unified_sources)
    checks["no_phantom_sources"] = _check_no_phantom_sources(body, unified_sources)
    checks["format_compliance"] = _check_format(body, headline, tldr, week_start)
    checks["minimum_content"] = _check_minimum_content(body, unified_sources)

    all_passed = all(c.passed for c in checks.values())
    failed = [name for name, c in checks.items() if not c.passed]
    summary = "ALL PASSED" if all_passed else f"FAILED: {', '.join(failed)}"

    for name, check in checks.items():
        level = "info" if check.passed else "warning"
        getattr(logger, level)("[checklist] %s: %s", name, check.message)

    return ChecklistResult(passed=all_passed, checks=checks, summary=summary)
