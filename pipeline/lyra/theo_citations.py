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

    id: str  # deterministic: sha256(url)[:12]
    url: str
    title: str
    snippet: str
    date: str = ""
    domain: str = ""  # extracted from URL (e.g. "en.wikipedia.org")
    reliability_tier: int = 0  # 1=academic/institutional, 2=reputable, 3=general, 0=unscored
    access_timestamp: str = ""  # ISO timestamp when searched
    search_query: str = ""  # which query found this source


@dataclass
class ClaimCitation:
    """Links a factual claim to its supporting sources."""

    claim_text: str
    source_ids: list[str]  # CitedSource.id values
    specialist_id: str = ""  # which specialist made this claim
    confidence: str = "medium"  # "high", "medium", "low"


@dataclass
class CitationRegistry:
    """Global citation state passed through the entire pipeline."""

    sources: dict[str, CitedSource] = field(default_factory=dict)  # id -> CitedSource
    claims: list[ClaimCitation] = field(default_factory=list)
    reference_numbers: dict[str, int] = field(default_factory=dict)  # source_id -> [N]
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


# ---------------------------------------------------------------------------
# Placeholder + language-bleed detection
# ---------------------------------------------------------------------------

# Matches cry-for-help placeholders the LLM emits when it wants a citation
# but wasn't given a number to use. Example: "[N - acoustic resonance]",
# "[N – geopolymer chemistry]" (also en-dash). Both hyphen and en-dash accepted.
_PLACEHOLDER_MARKER_RE = re.compile(r"\[N\s*[-–][^\]]+\]")

# Non-Latin scripts that signal language bleed-through in English prose.
# CJK (Chinese/Japanese/Korean), Cyrillic, Arabic. Greek omitted because legitimate
# scholarship may quote Greek terms; same for Hebrew. Revisit if false positives appear.
_LANGUAGE_BLEED_RE = re.compile(r"[\u4e00-\u9fff\u0400-\u04ff\u0600-\u06ff]+")


def detect_placeholder_markers(text: str) -> list[str]:
    """Return all [N - topic] style unresolved-citation placeholders in text."""
    return _PLACEHOLDER_MARKER_RE.findall(text)


def detect_language_bleed(text: str) -> list[str]:
    """Return non-Latin-script substrings that leaked into English prose.

    Used to catch LLM language drift like '实验考古学' embedded mid-sentence.
    Greek is intentionally not flagged (legitimate for quoting ancient terms).
    """
    return _LANGUAGE_BLEED_RE.findall(text)


# ---------------------------------------------------------------------------
# Reference finalization — assigns contiguous [1..M] numbers to only the
# sources actually cited in the paper, in first-occurrence order
# ---------------------------------------------------------------------------


def finalize_references(
    paper_text: str,
    working_sid_to_num: dict[str, int],
    registry: CitationRegistry,
) -> tuple[str, dict[str, int]]:
    """Re-number [N] markers in paper_text to contiguous [1..M] by first use.

    Pipeline context: during section writing, prompts embed working numbers
    (`working_sid_to_num`) so the LLM has stable [N] markers. After verification
    removes unsupported citations, many working numbers are unused. This function:

    1. Walks the paper in reading order, finds [N] markers that survived.
    2. Assigns NEW numbers [1..M] in first-occurrence order.
    3. Rewrites paper_text substituting old→new atomically (two-pass so no
       collision between an old number and a newly-assigned one).
    4. Calls registry.assign_reference_number(sid) only for survivors, in order.

    The registry's format_references_list() will then emit exactly M entries,
    contiguous, in citation order — no ghosts.

    Args:
        paper_text: Full paper markdown with working [N] markers (no References
            section appended yet).
        working_sid_to_num: sid -> working_num map used during prose emission.
        registry: CitationRegistry to be populated with final numbers.

    Returns:
        (rewritten_paper_text, final_sid_to_num)
    """
    # Reverse lookup: working_num -> sid
    num_to_sid: dict[int, str] = {num: sid for sid, num in working_sid_to_num.items()}

    # Walk paper in reading order, collect first occurrence of each working num
    # that corresponds to a real source in our map. Unknown numbers (e.g. hallucinated)
    # are left alone — they'll be caught by audit_citations as invalid_markers.
    seen_working: list[int] = []
    seen_set: set[int] = set()
    for match in re.finditer(r"\[(\d+)\]", paper_text):
        n = int(match.group(1))
        if n in num_to_sid and n not in seen_set:
            seen_working.append(n)
            seen_set.add(n)

    # Assign new numbers in first-occurrence order
    old_to_new: dict[int, int] = {old: new for new, old in enumerate(seen_working, start=1)}

    # Two-pass substitution to avoid collisions (old 5 → new 2 then old 2 → new 7
    # must not see the freshly-written "[2]" and remap it).
    # Pass 1: replace [OLD] with sentinel \x00NEW\x00. Pass 2: replace sentinels with [NEW].
    def _sub_to_sentinel(m: re.Match) -> str:
        n = int(m.group(1))
        if n in old_to_new:
            return f"\x00{old_to_new[n]}\x00"
        return m.group(0)  # leave unknown markers alone

    rewritten = re.sub(r"\[(\d+)\]", _sub_to_sentinel, paper_text)
    rewritten = re.sub(r"\x00(\d+)\x00", r"[\1]", rewritten)

    # Populate the registry with survivors, in new order
    final_sid_to_num: dict[str, int] = {}
    for old_num in seen_working:
        sid = num_to_sid[old_num]
        new_num = old_to_new[old_num]
        # Force the assignment: CitationRegistry assigns monotonically, so seed it
        # directly rather than via assign_reference_number which ignores requested numbers.
        registry.reference_numbers[sid] = new_num
        final_sid_to_num[sid] = new_num
    # Keep registry._next_ref consistent for any follow-up calls
    if seen_working:
        registry._next_ref = max(old_to_new.values()) + 1

    return rewritten, final_sid_to_num


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
    4. No unresolved [N - topic] placeholders leaked into prose.
    5. No non-Latin script bleed-through.

    Returns:
        {
            "passed": bool,
            "total_citations": int,         # count of [N] markers in text
            "total_references": int,        # count of assigned reference numbers
            "orphaned_refs": list[int],     # reference numbers never cited
            "invalid_markers": list[int],   # [N] values with no matching reference
            "uncited_paragraphs": int,      # paragraphs without any citation
            "placeholder_markers": list[str], # [N - topic] strings found in prose
            "language_bleed": list[str],    # non-Latin substrings in prose
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

    # 3. Uncited paragraphs — factual claim paragraphs with no [N]
    #
    # Section-aware: exempt Abstract, Introduction, and Methodology entirely
    # (these are framing sections that don't require per-paragraph citations).
    # For body/discussion/conclusion sections, apply structural-start heuristic
    # to skip transitions, ordinals, and non-factual framing text.

    _EXEMPT_SECTIONS = frozenset(
        {
            "abstract",
            "introduction",
            "methodology",
        }
    )

    _STRUCTURAL_STARTS = (
        # Genuinely structural / methodological text only
        "this paper",
        "this research",
        "this study",
        "this review",
        "this investigation",
        "we used",
        "we employed",
        "our approach",
        "our method",
        "in summary",
        "to summarize",
        "future research",
        # Bullet points
        "- **",
        "- ",
    )

    # Split into sections by ## headings and track section for each paragraph
    current_section = ""
    paragraphs_with_section: list[tuple[str, str]] = []
    for block in paper_text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        heading_match = re.match(r"^##\s+(.+)$", block, re.MULTILINE)
        if heading_match:
            current_section = heading_match.group(1).strip().lower()
        elif not block.startswith("#"):
            paragraphs_with_section.append((current_section, block))

    factual_paragraphs = [
        p
        for section, p in paragraphs_with_section
        if len(p) > 50
        and section not in _EXEMPT_SECTIONS
        and not p.lower().startswith(_STRUCTURAL_STARTS)
    ]
    uncited_paragraphs = sum(1 for p in factual_paragraphs if not re.search(r"\[\d+\]", p))
    if uncited_paragraphs:
        issues.append(
            f"{uncited_paragraphs} paragraph(s) longer than 50 chars contain no citation marker"
        )

    # 4. Unresolved [N - topic] placeholders — the LLM's cry-for-help when no
    #    citation number was provided. Scan the prose only, not the References
    #    section (which may legitimately contain brackets in titles).
    refs_start = _find_references_heading(paper_text)
    prose_only = paper_text[:refs_start] if refs_start is not None else paper_text
    placeholder_markers = detect_placeholder_markers(prose_only)
    if placeholder_markers:
        issues.append(
            f"{len(placeholder_markers)} unresolved [N - topic] placeholder(s) in prose"
        )

    # 5. Language bleed — non-Latin script in prose
    language_bleed = detect_language_bleed(prose_only)
    if language_bleed:
        issues.append(
            f"{len(language_bleed)} non-Latin script segment(s) in prose: "
            + ", ".join(language_bleed[:3])
        )

    passed = (
        not invalid_markers
        and not orphaned_refs
        and uncited_paragraphs == 0
        and not placeholder_markers
        and not language_bleed
    )

    return {
        "passed": passed,
        "total_citations": total_citations,
        "total_references": total_references,
        "orphaned_refs": orphaned_refs,
        "invalid_markers": invalid_markers,
        "uncited_paragraphs": uncited_paragraphs,
        "placeholder_markers": placeholder_markers,
        "language_bleed": language_bleed,
        "issues": issues,
    }


def _find_references_heading(text: str) -> int | None:
    """Return the index of the ## References / ## Sources heading, or None."""
    for marker in ("## References", "### References", "## Sources", "### Sources"):
        idx = text.find(marker)
        if idx != -1:
            return idx
    return None
