"""Programmatic quality checklist for Theo research papers.

Runs after the LLM-based assessment as a mechanical final gate.
All checks are deterministic — no LLM calls.

Usage:
    from pipeline.lyra.research_checklist import run_research_checklist

    result = run_research_checklist(body, registry)
    if not result.passed:
        for name, check in result.checks.items():
            if not check.passed:
                logger.warning("Checklist %s FAILED: %s", name, check.message)
"""

from __future__ import annotations

import logging
import re

from pipeline.lyra.article_checklist import ChecklistResult, CheckResult
from pipeline.lyra.theo_citations import CitationRegistry

logger = logging.getLogger(__name__)

# Sections exempt from citation requirements
_EXEMPT_SECTIONS = frozenset(
    {
        "abstract",
        "introduction",
        "methodology",
        "references",
        "sources",
        "acknowledgements",
        "acknowledgments",
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _body_without_refs(body: str) -> str:
    """Return body text excluding the ## References / ## Sources footer."""
    for marker in ("## References", "## Sources", "### Sources"):
        idx = body.find(marker)
        if idx >= 0:
            return body[:idx]
    return body


def _extract_body_citations(body: str) -> set[int]:
    """Extract all [N] citation numbers from body text (excluding refs section)."""
    return {int(m) for m in re.findall(r"\[(\d+)\]", _body_without_refs(body))}


def _assigned_ref_numbers(registry: CitationRegistry) -> set[int]:
    """Get all assigned reference numbers from the registry."""
    return set(registry.reference_numbers.values())


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_citation_integrity(body: str, registry: CitationRegistry) -> CheckResult:
    """Every [N] in body maps to a real reference in the registry."""
    body_citations = _extract_body_citations(body)
    assigned = _assigned_ref_numbers(registry)

    invalid = sorted(body_citations - assigned)
    if invalid:
        details = [f"[{n}] cited in text but no matching reference" for n in invalid]
        return CheckResult(
            passed=False,
            message=f"{len(invalid)} invalid citation(s): {invalid}",
            details=details,
        )
    return CheckResult(passed=True, message="All citations map to references")


def _check_no_phantom_sources(body: str, registry: CitationRegistry) -> CheckResult:
    """Every assigned reference number appears at least once as [N] in body."""
    body_citations = _extract_body_citations(body)
    assigned = _assigned_ref_numbers(registry)

    phantom = sorted(assigned - body_citations)
    if phantom:
        details = [f"[{n}] assigned but never cited in paper" for n in phantom]
        return CheckResult(
            passed=False,
            message=f"{len(phantom)} phantom source(s): {phantom}",
            details=details,
        )
    return CheckResult(passed=True, message="All references are cited")


def _check_minimum_content(body: str, registry: CitationRegistry) -> CheckResult:
    """Body > 2000 chars, sources >= 3."""
    issues: list[str] = []
    clean_body = _body_without_refs(body)

    if len(clean_body) < 2000:
        issues.append(f"Body too short: {len(clean_body)} chars (min 2000)")

    source_count = len(registry.reference_numbers)
    if source_count < 3:
        issues.append(f"Too few sources: {source_count} (min 3)")

    if issues:
        return CheckResult(passed=False, message="; ".join(issues), details=issues)
    return CheckResult(
        passed=True,
        message=f"Content OK: {len(clean_body)} chars, {source_count} sources",
    )


def _check_section_structure(body: str) -> CheckResult:
    """Paper has required structure: Abstract/Introduction + body + References."""
    issues: list[str] = []

    headings = [m.group(1).strip().lower() for m in re.finditer(r"^##\s+(.+)$", body, re.MULTILINE)]

    has_refs = any(h in ("references", "sources") for h in headings)
    if not has_refs:
        issues.append("Missing ## References or ## Sources")

    has_intro = any(h in ("abstract", "introduction") for h in headings)
    if not has_intro:
        issues.append("Missing ## Abstract or ## Introduction")

    body_sections = [h for h in headings if h not in _EXEMPT_SECTIONS]
    if not body_sections:
        issues.append(
            "No body sections (need at least one ## section beyond Abstract/Introduction/References)"
        )

    if issues:
        return CheckResult(passed=False, message="; ".join(issues), details=issues)
    return CheckResult(passed=True, message=f"Structure OK: {len(headings)} sections")


def _check_no_uncited_sections(body: str) -> CheckResult:
    """Every body section (excluding exempt ones) has at least one [N] citation."""
    clean_body = _body_without_refs(body)

    # Split into sections by ## headings
    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_content: list[str] = []

    for line in clean_body.split("\n"):
        heading_match = re.match(r"^##\s+(.+)$", line)
        if heading_match:
            if current_heading:
                sections.append((current_heading, "\n".join(current_content)))
            current_heading = heading_match.group(1).strip()
            current_content = []
        else:
            current_content.append(line)

    # Don't forget the last section
    if current_heading:
        sections.append((current_heading, "\n".join(current_content)))

    uncited: list[str] = []
    for heading, content in sections:
        if heading.lower() in _EXEMPT_SECTIONS:
            continue
        # Only flag sections with substantial content (>100 chars)
        if len(content.strip()) > 100 and not re.search(r"\[\d+\]", content):
            uncited.append(heading)

    if uncited:
        details = [f"Section '{h}' has no citations" for h in uncited]
        return CheckResult(
            passed=False,
            message=f"{len(uncited)} uncited section(s): {uncited}",
            details=details,
        )
    return CheckResult(passed=True, message="All body sections have citations")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_research_checklist(body: str, registry: CitationRegistry) -> ChecklistResult:
    """Run all programmatic quality checks. No LLM calls — purely mechanical."""
    checks: dict[str, CheckResult] = {}

    checks["citation_integrity"] = _check_citation_integrity(body, registry)
    checks["no_phantom_sources"] = _check_no_phantom_sources(body, registry)
    checks["minimum_content"] = _check_minimum_content(body, registry)
    checks["section_structure"] = _check_section_structure(body)
    checks["no_uncited_sections"] = _check_no_uncited_sections(body)

    all_passed = all(c.passed for c in checks.values())
    failed = [name for name, c in checks.items() if not c.passed]
    summary = "ALL PASSED" if all_passed else f"FAILED: {', '.join(failed)}"

    for name, check in checks.items():
        level = "info" if check.passed else "warning"
        getattr(logger, level)("[research-checklist] %s: %s", name, check.message)

    return ChecklistResult(passed=all_passed, checks=checks, summary=summary)
