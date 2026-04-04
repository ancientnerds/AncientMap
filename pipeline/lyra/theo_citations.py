"""Citation tracking backbone for Theo's research pipeline.

Tracks every web source found during research and ensures every factual
claim in the final paper traces to a verifiable source.

Usage:
    registry = CitationRegistry()
    source_id = registry.register_source(url, title, snippet, search_query=q)
    registry.add_claim("Rome was founded in 753 BC", [source_id], specialist_id="historian")
    ref_num = registry.assign_reference_number(source_id)
    refs_md = registry.format_references_list()
    audit = audit_citations(paper_text, registry)
"""

from __future__ import annotations

import hashlib
import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import UTC, datetime

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CitedSource:
    """A web source found during research, tracked through the pipeline."""

    id: str                     # deterministic: sha256(url)[:12]
    url: str
    title: str
    snippet: str
    date: str = ""
    domain: str = ""            # extracted from URL (e.g. "en.wikipedia.org")
    reliability_tier: int = 0   # 1=academic/institutional, 2=reputable, 3=general, 0=unscored
    access_timestamp: str = ""  # ISO timestamp when searched
    search_query: str = ""      # which query found this source


@dataclass
class ClaimCitation:
    """Links a factual claim to its supporting sources."""

    claim_text: str
    source_ids: list[str]       # CitedSource.id values
    specialist_id: str = ""     # which specialist made this claim
    confidence: str = "medium"  # "high", "medium", "low"


@dataclass
class CitationRegistry:
    """Global citation state passed through the entire pipeline."""

    sources: dict[str, CitedSource] = field(default_factory=dict)   # id -> CitedSource
    claims: list[ClaimCitation] = field(default_factory=list)
    reference_numbers: dict[str, int] = field(default_factory=dict) # source_id -> [N]
    _next_ref: int = field(default=1, repr=False)

    # ---------------------------------------------------------------------------
    # Source management
    # ---------------------------------------------------------------------------

    def register_source(
        self,
        url: str,
        title: str,
        snippet: str,
        date: str = "",
        search_query: str = "",
    ) -> str:
        """Register a web source. Returns source id. Deduplicates by URL hash."""
        source_id = hashlib.sha256(url.encode()).hexdigest()[:12]

        if source_id in self.sources:
            return source_id

        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.removeprefix("www.")

        self.sources[source_id] = CitedSource(
            id=source_id,
            url=url,
            title=title,
            snippet=snippet,
            date=date,
            domain=domain,
            access_timestamp=datetime.now(UTC).isoformat(),
            search_query=search_query,
        )
        return source_id

    # ---------------------------------------------------------------------------
    # Claim tracking
    # ---------------------------------------------------------------------------

    def add_claim(
        self,
        claim_text: str,
        source_ids: list[str],
        specialist_id: str = "",
        confidence: str = "medium",
    ) -> None:
        """Register a claim with its supporting sources."""
        self.claims.append(
            ClaimCitation(
                claim_text=claim_text,
                source_ids=source_ids,
                specialist_id=specialist_id,
                confidence=confidence,
            )
        )

    # ---------------------------------------------------------------------------
    # Reference numbering
    # ---------------------------------------------------------------------------

    def assign_reference_number(self, source_id: str) -> int:
        """Assign a [N] number when a source is actually cited in the paper.

        Same source always gets the same number. Returns the number.
        """
        if source_id in self.reference_numbers:
            return self.reference_numbers[source_id]

        num = self._next_ref
        self.reference_numbers[source_id] = num
        self._next_ref += 1
        return num

    def get_reference(self, source_id: str) -> CitedSource | None:
        """Get a source by id."""
        return self.sources.get(source_id)

    # ---------------------------------------------------------------------------
    # Formatting
    # ---------------------------------------------------------------------------

    def format_references_list(self) -> str:
        """Generate the References section as markdown.

        Only includes sources that were assigned reference numbers.
        Sorted by reference number.
        Format: [N] Title — URL (accessed YYYY-MM-DD) [Tier label]
        Tier labels: [Academic] for tier 1, [Reputable] for tier 2, omit for tier 3.
        """
        if not self.reference_numbers:
            return ""

        ordered = sorted(self.reference_numbers.items(), key=lambda kv: kv[1])
        lines: list[str] = []

        for source_id, num in ordered:
            source = self.sources.get(source_id)
            if source is None:
                continue

            # Extract YYYY-MM-DD from ISO access_timestamp
            accessed_date = ""
            if source.access_timestamp:
                accessed_date = source.access_timestamp[:10]

            tier_label = ""
            if source.reliability_tier == 1:
                tier_label = " [Academic]"
            elif source.reliability_tier == 2:
                tier_label = " [Reputable]"

            line = f"[{num}] {source.title} — {source.url}"
            if accessed_date:
                line += f" (accessed {accessed_date})"
            line += tier_label
            lines.append(line)

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Citation audit
# ---------------------------------------------------------------------------


def audit_citations(paper_text: str, registry: CitationRegistry) -> dict:
    """Mechanical citation audit — no LLM, pure regex/text analysis.

    Checks:
    1. Every [N] marker in the text maps to a real reference in registry.
    2. Every paragraph with a factual claim has at least one [N]
       (heuristic: paragraphs > 50 chars that don't start with # are factual).
    3. No orphaned references (assigned number but never cited in text).

    Returns:
        {
            "passed": bool,
            "total_citations": int,         # count of [N] markers in text
            "total_references": int,        # count of assigned reference numbers
            "orphaned_refs": list[int],     # reference numbers never cited
            "invalid_markers": list[int],   # [N] values with no matching reference
            "uncited_paragraphs": int,      # paragraphs without any citation
            "issues": list[str],            # human-readable issue descriptions
        }
    """
    issues: list[str] = []

    # All [N] markers found in the paper text
    marker_values: list[int] = [int(m) for m in re.findall(r"\[(\d+)\]", paper_text)]
    total_citations = len(marker_values)
    unique_cited_nums: set[int] = set(marker_values)

    # All assigned reference numbers
    assigned_nums: set[int] = set(registry.reference_numbers.values())
    total_references = len(assigned_nums)

    # 1. Invalid markers — [N] in text with no assigned reference
    invalid_markers = sorted(unique_cited_nums - assigned_nums)
    for n in invalid_markers:
        issues.append(f"[{n}] cited in text but no matching reference assigned")

    # 2. Orphaned references — assigned but never cited in text
    orphaned_refs = sorted(assigned_nums - unique_cited_nums)
    for n in orphaned_refs:
        issues.append(f"[{n}] assigned as reference but never cited in text")

    # 3. Uncited paragraphs — factual paragraphs with no [N]
    paragraphs = [p.strip() for p in paper_text.split("\n\n") if p.strip()]
    factual_paragraphs = [
        p for p in paragraphs if len(p) > 50 and not p.startswith("#")
    ]
    uncited_paragraphs = sum(
        1 for p in factual_paragraphs if not re.search(r"\[\d+\]", p)
    )
    if uncited_paragraphs:
        issues.append(
            f"{uncited_paragraphs} paragraph(s) longer than 50 chars contain no citation marker"
        )

    passed = not invalid_markers and not orphaned_refs and uncited_paragraphs == 0

    return {
        "passed": passed,
        "total_citations": total_citations,
        "total_references": total_references,
        "orphaned_refs": orphaned_refs,
        "invalid_markers": invalid_markers,
        "uncited_paragraphs": uncited_paragraphs,
        "issues": issues,
    }
