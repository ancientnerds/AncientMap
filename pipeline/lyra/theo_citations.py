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
    # 1=academic/institutional, 2=reputable, 3=general, 4=context/self, 0=unscored
    reliability_tier: int = 0
    access_timestamp: str = ""  # ISO timestamp when searched
    search_query: str = ""  # which query found this source
    # Academic metadata — present when the discovering adapter (Semantic
    # Scholar / OpenAlex / CrossRef / CORE) returned them. format_references_list
    # uses these to emit a rich citation when DOI is set; absence falls back to
    # the legacy `[N] Title — URL` shape.
    doi: str = ""
    authors: list[str] = field(default_factory=list)
    venue: str = ""  # journal / conference name
    citation_count: int = 0
    # Own prior papers (ancientnerds_research adapter): context/pointer only,
    # never independent corroboration (spec 2026-08-04 §5). Forces
    # reliability_tier=4 at registration, overriding the domain scorer.
    self_source: bool = False
    # Provenance for the training corpus: which adapter found this source, and
    # the licence it reported (empty when the adapter does not know one —
    # training_corpus.resolve_license falls back to the domain table).
    source_api: str = ""
    license: str = ""


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
        doi: str = "",
        authors: list[str] | None = None,
        venue: str = "",
        citation_count: int = 0,
        self_source: bool = False,
        source_api: str = "",
        license: str = "",
    ) -> str:
        """Register a web source. Returns source id. Deduplicates by canonical URL hash.

        The source_id is hashed from `_normalize_url(url)` so version-padded
        preprint URLs, tracking-tagged URLs, and www-prefixed variants all
        collapse to a single source. The first-seen original URL is preserved
        on CitedSource.url for display.

        Academic metadata (doi/authors/venue/citation_count) is merged on
        re-registration: if a later adapter discovers the same URL with richer
        fields, those overwrite empty ones on the existing record. Non-empty
        fields are preserved (first writer wins for conflicting values).

        `self_source=True` (Ancient Nerds' own prior papers, spec 2026-08-04
        §5) forces `reliability_tier=4` — an adapter's self-knowledge beats
        the URL-domain heuristic. This does NOT change the domain-scorer
        relationship for any other adapter.
        """
        canonical = _normalize_url(url)
        source_id = hashlib.sha256(canonical.encode()).hexdigest()[:12]
        authors = authors or []

        if source_id in self.sources:
            existing = self.sources[source_id]
            if doi and not existing.doi:
                existing.doi = doi
            if authors and not existing.authors:
                existing.authors = authors
            if venue and not existing.venue:
                existing.venue = venue
            if citation_count and not existing.citation_count:
                existing.citation_count = citation_count
            if source_api and not existing.source_api:
                existing.source_api = source_api
            if license and not existing.license:
                existing.license = license
            if self_source and not existing.self_source:
                existing.self_source = True
                existing.reliability_tier = 4
                # Every enforcement surface (prompt rule, References list,
                # audit) reads the title string, not the flag — the marker
                # must land there too, exactly once.
                if existing.title.count("[self]") == 0:
                    existing.title = f"[self] {existing.title}"
            return source_id

        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.removeprefix("www.")

        self.sources[source_id] = CitedSource(
            id=source_id,
            url=url,  # preserve original URL for display
            title=title,
            snippet=snippet,
            date=date,
            domain=domain,
            # Domain-based default, UNLESS the adapter already knows this is
            # our own prior research (self_source=True forces tier 4). Search
            # adapters / angle-audit LLM can still override later via direct
            # attribute assignment when they have better info.
            reliability_tier=4 if self_source else score_tier_by_domain(url),
            access_timestamp=datetime.now(UTC).isoformat(),
            search_query=search_query,
            doi=doi,
            authors=authors,
            venue=venue,
            citation_count=citation_count,
            self_source=self_source,
            source_api=source_api,
            license=license,
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

        Two formats emitted, depending on metadata richness:

        * **Rich (academic)** — used when the source has a DOI, at least one
          author, a venue, and a parseable year. Shape:
              [N] Authors (YYYY). Title. Venue. DOI: 10.xxx/yyy (accessed YYYY-MM-DD) [Academic]

        * **Legacy** — fallback for sources missing any of those fields
          (Wikipedia, YouTube, news, blogs). Shape:
              [N] Title — URL (accessed YYYY-MM-DD) [Tier label]

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

            accessed_date = source.access_timestamp[:10] if source.access_timestamp else ""

            tier_label = ""
            if source.reliability_tier == 1:
                tier_label = " [Academic]"
            elif source.reliability_tier == 2:
                tier_label = " [Reputable]"

            year = _extract_year_from_date(source.date)
            use_rich = bool(source.doi and source.authors and source.venue and year)

            if use_rich:
                authors_str = _format_authors_block(source.authors)
                line = (
                    f"[{num}] {authors_str} ({year}). "
                    f"{source.title}. {source.venue}. DOI: {source.doi}"
                )
            else:
                line = f"[{num}] {source.title} — {source.url}"

            if accessed_date:
                line += f" (accessed {accessed_date})"
            line += tier_label
            lines.append(line)

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Reference formatting helpers
# ---------------------------------------------------------------------------


def _format_authors_block(authors: list[str]) -> str:
    """Join an author list using academic convention.

    * 1 author: ``Smith, J.``
    * 2 authors: ``Smith, J. and Jones, K.``
    * 3+ authors: ``Smith, J., Jones, K., and Lee, M.``

    No "et al." truncation — the writer/judge can decide whether to cap a
    rendered list visually, but the raw bibliography keeps every name.
    """
    if not authors:
        return ""
    if len(authors) == 1:
        return authors[0]
    if len(authors) == 2:
        return f"{authors[0]} and {authors[1]}"
    return ", ".join(authors[:-1]) + f", and {authors[-1]}"


def _extract_year_from_date(date_str: str) -> int | None:
    """Pull a 4-digit year from a free-form date string.

    Adapters return ``date`` in mixed shapes (``2024``, ``2024-03-15``,
    ``March 2024``…). We just grab the first 1xxx/20xx year we see.
    """
    if not date_str:
        return None
    m = re.search(r"\b(1\d{3}|20\d{2})\b", date_str)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Citation audit
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Domain-based reliability tier scorer
# ---------------------------------------------------------------------------

# Mirror of the classification spirit in pipeline/lyra/research_stages.py:95-123
# (_classify_source_type). Kept as a separate list here so CitationRegistry has a
# default tier at registration time without the import risk.
_TIER_1_DOMAINS: tuple[str, ...] = (
    # Academic + institutional
    ".edu",
    ".ac.uk",
    ".ac.jp",
    ".ac.at",
    ".ac.nz",
    ".gov",
    "doi.org",
    "arxiv.org",
    "jstor.org",
    "academia.edu",
    "semanticscholar.org",
    "pubmed.ncbi.nlm.nih.gov",
    "ncbi.nlm.nih.gov",
    "pnas.org",
    "plos.org",
    "springer.com",
    "link.springer.com",
    "sciencedirect.com",
    "cambridge.org",
    "oup.com",
    "nature.com",
    "science.org",
    "sciencemag.org",
    "wiley.com",
    "onlinelibrary.wiley.com",
    "tandfonline.com",
    "royalsocietypublishing.org",
    "cell.com",
    "biorxiv.org",
    "medrxiv.org",
    "frontiersin.org",
    "dainst.org",
)

_TIER_2_DOMAINS: tuple[str, ...] = (
    # Reference works
    "wikipedia.org",
    "britannica.com",
    # Major museums / cultural institutions
    "smithsonianmag.com",
    "si.edu",
    "penn.museum",
    "britishmuseum.org",
    "louvre.fr",
    "metmuseum.org",
    "archive.org",
    # Quality science journalism
    "nationalgeographic.com",
    "scientificamerican.com",
    "newscientist.com",
    "ars-technica.com",
    "arstechnica.com",
    # Major English-language press
    "bbc.co.uk",
    "bbc.com",
    "nytimes.com",
    "theguardian.com",
    "guardian.co.uk",
    "reuters.com",
    "apnews.com",
    "washingtonpost.com",
)


def score_tier_by_domain(url: str) -> int:
    """Return a reliability tier (1=academic, 2=reputable, 3=general) from a URL.

    Used as the default `reliability_tier` at source-registration time. Pipeline
    steps that have better information (search adapter `default_tier`, LLM
    angle-audit) override this later.

    Tier 1: peer-reviewed, .edu/.gov, DOI hosts, major publishers, preprint servers.
    Tier 2: Wikipedia, Britannica, major museums, science journalism, wire services.
    Tier 3: everything else (fallback).

    Empty/invalid URLs return 3.
    """
    if not url:
        return 3
    # Match against the HOST only — substring checks over the whole URL let
    # paths/queries spoof tiers (evil.com/?x=nature.com scored tier 1).
    candidate = url.strip().lower()
    if "://" not in candidate:
        candidate = "//" + candidate  # scheme-less input: force netloc parsing
    # .hostname strips userinfo, port, and IPv6 brackets from the netloc.
    host = (urllib.parse.urlparse(candidate).hostname or "").removeprefix("www.")
    if not host:
        return 3

    def _host_matches(domain: str) -> bool:
        if domain.startswith("."):
            # TLD-style suffix entries (".edu", ".ac.uk", ".gov")
            return host.endswith(domain)
        return host == domain or host.endswith("." + domain)

    # Tier 1 takes priority — check first
    for domain in _TIER_1_DOMAINS:
        if _host_matches(domain):
            return 1
    for domain in _TIER_2_DOMAINS:
        if _host_matches(domain):
            return 2
    return 3


# ---------------------------------------------------------------------------
# Placeholder + language-bleed detection
# ---------------------------------------------------------------------------

# Matches cry-for-help placeholders the LLM emits when it wants a citation
# but wasn't given a number to use. Example: "[N - acoustic resonance]",
# "[N – geopolymer chemistry]" (also en-dash). Both hyphen and en-dash accepted.
_PLACEHOLDER_MARKER_RE = re.compile(r"\[N\s*[-–][^\]]+\]")

# Matches bare debug-token leftovers — `[N]`, `[...]`, `[…]` — that the LLM
# sometimes drops into prose when it can't decide which source to cite.
# These survive finalize_references because they don't match the placeholder
# pattern above, but they're unambiguous pipeline artifacts and should be
# scrubbed before audit. Negative lookahead `(?!\()` avoids touching
# markdown image links like ![alt](src) or footnote forms.
_DEBUG_TOKEN_RE = re.compile(r"\[(?:N|\.\.\.|…)\](?!\()")

# Non-Latin scripts that signal language bleed-through in English prose.
# CJK (Chinese/Japanese/Korean), Cyrillic, Arabic. Greek omitted because legitimate
# scholarship may quote Greek terms; same for Hebrew. Revisit if false positives appear.
_LANGUAGE_BLEED_RE = re.compile(r"[\u4e00-\u9fff\u0400-\u04ff\u0600-\u06ff]+")


def detect_placeholder_markers(text: str) -> list[str]:
    """Return all [N - topic] style unresolved-citation placeholders in text."""
    return _PLACEHOLDER_MARKER_RE.findall(text)


def strip_debug_tokens(text: str) -> str:
    """Remove bare `[N]` / `[...]` / `[…]` debug artifacts from prose.

    The LLM occasionally drops these when it wants a citation but failed
    to resolve a source — they're not legitimate scholarship content and
    they survive finalize_references because they don't match the
    `[N - topic]` placeholder pattern. Audit then flags them as
    non_numeric_markers and demotes the paper's badge to Unverified
    (run #10 hit exactly this — score=100 but badge=Unverified because
    two `[N]` / `[...]` slipped through). Stripping them at presentation
    time is loss-less: nothing of value is in `[N]`.
    """
    return _DEBUG_TOKEN_RE.sub("", text)


def contains_non_latin_script(text: str) -> bool:
    """True when `text` carries any CJK / Cyrillic / Arabic run.

    The unconditional form of the bleed test, for callers deciding whether
    third-party metadata is usable as English prose at all (image captions
    built from Wikimedia's multilingual `description` field). Prose checks
    want `detect_language_bleed`, which tolerates glosses.
    """
    return bool(_LANGUAGE_BLEED_RE.search(text))


# A parenthetical introducing a foreign term — `(遮光器, "light-blocker")` —
# is scholarship, not drift. A whole clause in another script never is, so
# the gloss exemption is capped by how much foreign text the parenthetical
# carries in total (not per run: `「琉球の風」` splits one Japanese sentence
# into short runs that would each slip under a per-run cap).
_GLOSS_MAX_FOREIGN_CHARS = 24


def _foreign_char_count(text: str) -> int:
    """Characters belonging to a non-Latin script.

    Counts the whole foreign span, not just what _LANGUAGE_BLEED_RE matches:
    kana and CJK brackets sit outside the ideograph range but are every bit
    as much Japanese, and a budget that ignores them would read a full
    sentence as a short term. General Punctuation (em-dashes, curly quotes)
    is excluded — that block is ordinary English typography.
    """
    return sum(1 for ch in text if ord(ch) > 0x02FF and not 0x2000 <= ord(ch) <= 0x206F)


def _gloss_spans(text: str) -> list[tuple[int, int]]:
    """Inner spans of parentheticals that read as a term gloss.

    A gloss EXPLAINS the foreign term, so it carries Latin prose alongside
    the script: `(遮光器, "light-blocker")`. A parenthetical holding nothing
    but foreign script is a bare translation of an English phrase —
    `Experimental archaeology (实验考古学)` — which is the exact shape
    MiniMax drift takes, and stays flagged.
    """
    spans: list[tuple[int, int]] = []
    for m in re.finditer(r"\(([^()\n]{0,160})\)", text):
        inner = m.group(1)
        foreign = _foreign_char_count(inner)
        latin = sum(1 for ch in inner if ch.isascii() and ch.isalpha())
        if 0 < foreign <= _GLOSS_MAX_FOREIGN_CHARS and latin >= 3:
            spans.append((m.start(1), m.end(1)))
    return spans


def detect_language_bleed(text: str) -> list[str]:
    """Return non-Latin-script substrings that leaked into English prose.

    Used to catch LLM language drift like '实验考古学' embedded mid-sentence.
    Greek is intentionally not flagged (legitimate for quoting ancient terms).

    Parenthetical glosses are exempt (2026-08-31): a paper introducing
    `the term "shakoki" (遮光器, "light-blocker")` is doing scholarship, and
    treating that as drift held three finished papers in August 2026. The
    exemption is bounded by _GLOSS_MAX_NON_LATIN_CHARS — a parenthetical
    carrying a full foreign clause is still drift.
    """
    spans = _gloss_spans(text)
    return [
        m.group(0)
        for m in _LANGUAGE_BLEED_RE.finditer(text)
        if not any(start <= m.start() and m.end() <= end for start, end in spans)
    ]


# ---------------------------------------------------------------------------
# URL normalization — collapses version-padded and tracking-polluted URLs
# so that v5, v6, v7, ... of the same preprint dedupe to a single source.
# ---------------------------------------------------------------------------

_TRACKING_PARAMS = ("utm_", "fbclid", "gclid", "ref=", "mc_", "_hsenc=")


def _normalize_url(url: str) -> str:
    """Return a canonical form of a URL for dedup purposes.

    Strips version suffixes on preprint hosts, tracking params, fragments,
    trailing whitespace, leading 'www.', lowercases the host. Returns the
    input unchanged for non-URL strings (empty, malformed).
    """
    if not url or "://" not in url:
        return url

    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return url

    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path

    # preprints.org — strip trailing /vN or /v/N segment(s)
    if host == "preprints.org":
        path = re.sub(r"/v\d+(/|$)", r"\1", path)
        path = re.sub(r"/v/\d+(/|$)", r"\1", path)
        # `/download` is the PDF endpoint; collapses to the manuscript page for dedup
        path = re.sub(r"/download/?$", "", path)

    # arxiv — strip trailing vN on abs/pdf path
    elif host == "arxiv.org":
        path = re.sub(r"(/(?:abs|pdf)/[^/]+?)v\d+(\.pdf)?$", r"\1\2", path)

    # biorxiv / medrxiv — strip version segment on content path
    elif host in ("biorxiv.org", "medrxiv.org"):
        path = re.sub(r"(/content/.+?)v\d+(\.full)?(?=/|\?|$|\.pdf)", r"\1\2", path)

    # researchgate — collapse /profile/{user}/publication/{id}/... to
    # /publication/{id}
    elif host == "researchgate.net":
        m = re.search(r"/publication/(\d+_[^/]+|\d+)", path)
        if m:
            path = "/publication/" + m.group(1)

    # Strip tracking query params
    query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query_pairs = [
        (k, v)
        for k, v in query_pairs
        if not any(k.startswith(p) or k == p.rstrip("=") for p in _TRACKING_PARAMS)
    ]
    query = urllib.parse.urlencode(query_pairs)

    # Drop fragment
    rebuilt = urllib.parse.urlunsplit((scheme, host, path, query, ""))
    return rebuilt


# ---------------------------------------------------------------------------
# Reference finalization — assigns contiguous [1..M] numbers to only the
# sources actually cited in the paper, in first-occurrence order
# ---------------------------------------------------------------------------


def prune_orphaned_references(paper_text: str, registry: CitationRegistry) -> int:
    """Remove ref numbers that no longer have a corresponding `[N]` in prose.

    `inject_citation_for_paragraph` calls `registry.assign_reference_number(sid)`
    for every claim it tries to attach to an uncited paragraph. If the paragraph
    is later restored to its un-injected original (e.g. section-preserve
    safeguard in `strip_uncited_factual_paragraphs` triggers), the registry
    keeps the assigned number but the `[N]` marker never reaches prose →
    audit_citations flags it as `orphaned_refs` → audit.passed=false even
    though every actually-cited reference is fine.

    Run this AFTER all injection passes (writer + strip + post-presentation
    strip) and BEFORE the final audit. It walks paper_text once, finds every
    `[N]` actually used, and drops every other entry from
    `registry.reference_numbers`. Returns the number pruned.

    Note: this does NOT renumber survivors. The references list will simply
    skip the dropped numbers, which is fine — the audit only complains about
    `assigned but not cited`, not about gaps.
    """
    cited: set[int] = set()
    refs_start = _find_references_heading(paper_text)
    prose_only = paper_text[:refs_start] if refs_start is not None else paper_text
    for m in re.finditer(r"\[(\d+)\]", prose_only):
        cited.add(int(m.group(1)))

    pruned = 0
    for sid in list(registry.reference_numbers.keys()):
        if registry.reference_numbers[sid] not in cited:
            del registry.reference_numbers[sid]
            pruned += 1
    return pruned


def prune_unrenderable_references(registry: CitationRegistry) -> int:
    """Drop reference_numbers entries whose source is no longer in registry.sources.

    Mirrors the predicate format_references_list uses (lines 166-168) to skip
    entries on render. Stale comment fixed 2026-08-05: the angle_audit
    rejection path this used to also cite was removed as dead code
    (Follow-up-Ticket 1 — its LLM audit body never ran since inception, so
    it never actually popped anything). The live rejection path today is
    research_stages.py's `_stage_audit` (journal pipeline), whose rejection
    loop pops `registry.sources` entirely for rejected source ids — this
    helper restores coherence at publish time so any downstream consumer (and
    the audit) sees the same set of "actually-renderable" references.

    Returns the number pruned. Safe to call multiple times.
    """
    to_drop = [sid for sid in registry.reference_numbers if registry.sources.get(sid) is None]
    for sid in to_drop:
        registry.reference_numbers.pop(sid, None)
    return len(to_drop)


def strip_existing_references_section(text: str) -> tuple[str, int]:
    """Remove any pre-existing `## References` / `## Sources` block from text.

    Run BEFORE appending the canonical references list. The writer LLM
    occasionally emits its own References section (often APA-style without
    URLs) at the end of the paper. When the pipeline then appends the real
    references list on top, the report contains two `## References` headings;
    the frontend splits on the first one and shows the LLM's fake refs —
    leaving every `[N]` marker unlinked and hiding the real bibliography.

    Strips from the first matching heading to end of text. Returns
    (cleaned_text, chars_removed).
    """
    pattern = re.compile(r"\n#{2,3}\s+(?:References|Sources)\b")
    m = pattern.search(text)
    if m is None:
        return text, 0
    removed = len(text) - m.start()
    return text[: m.start()].rstrip() + "\n", removed


def strip_orphan_citation_markers(text: str, valid_nums: set[int]) -> tuple[str, int]:
    """Remove `[N]` markers in prose where N is not in `valid_nums`.

    Orphan markers arise when the writer LLM cites a higher number than the
    reference registry knows about (hallucination) or when downstream pruning
    removes a reference but leaves its marker in prose. The frontend renders
    such markers as plain `[N]` text — readers see broken-looking citations.

    Scans only prose (everything before the first References heading). The
    refs section legitimately starts each line with `[N]` and must not be
    touched. Collapses whitespace left by removed markers so sentences like
    `"... patterns. [33] [34]"` end cleanly.

    Returns (cleaned_text, markers_removed).
    """
    refs_idx = _find_references_heading(text)
    if refs_idx is None:
        prose, tail = text, ""
    else:
        prose, tail = text[:refs_idx], text[refs_idx:]

    removed = 0

    def _drop(m: re.Match[str]) -> str:
        nonlocal removed
        if int(m.group(1)) in valid_nums:
            return m.group(0)
        removed += 1
        return ""

    cleaned = re.sub(r"\[(\d+)\]", _drop, prose)
    if removed:
        cleaned = re.sub(r" {2,}", " ", cleaned)
        cleaned = re.sub(r" +([.,;:?!])", r"\1", cleaned)

    return cleaned + tail, removed


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

    # Populate the registry with ONLY the survivors. Clear stale pre-assignments
    # first — earlier pipeline stages (claim collection, debate) may have called
    # assign_reference_number on source_ids that the writer ultimately didn't
    # cite. Without this clear, the registry retains hundreds of orphan numbers
    # which audit_citations then flags as orphaned_refs.
    registry.reference_numbers.clear()
    final_sid_to_num: dict[str, int] = {}
    for old_num in seen_working:
        sid = num_to_sid[old_num]
        new_num = old_to_new[old_num]
        registry.reference_numbers[sid] = new_num
        final_sid_to_num[sid] = new_num
    # Keep registry._next_ref consistent for any follow-up calls
    if seen_working:
        registry._next_ref = max(old_to_new.values()) + 1
    else:
        registry._next_ref = 1

    return rewritten, final_sid_to_num


# ---------------------------------------------------------------------------
# Citation audit — shared paragraph-classification helpers
# ---------------------------------------------------------------------------

# Sections that don't require per-paragraph citations.
_EXEMPT_SECTIONS = frozenset(
    {
        "abstract",
        "introduction",
        "methodology",
    }
)

# Sentence openings that mark a structural / methodological paragraph (not a
# factual claim). Anything starting with one of these is exempt from the
# uncited-paragraph audit.
_STRUCTURAL_STARTS = (
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


def _split_prose_into_paragraphs(prose_only: str) -> list[tuple[str, str]]:
    """Walk the prose body in reading order; return (section_title, block) per non-empty block."""
    current_section = ""
    out: list[tuple[str, str]] = []
    for block in prose_only.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        heading_match = re.match(r"^##\s+(.+)$", block, re.MULTILINE)
        if heading_match:
            current_section = heading_match.group(1).strip().lower()
        elif not block.startswith("#"):
            out.append((current_section, block))
    return out


def _is_non_prose_block(block: str) -> bool:
    """True for headings, image markdown, italic captions, source-link trailers, lone markdown links."""
    s = block.strip()
    # Headings of any level (`# H1`, `## H2`, ...) are structural, not prose.
    # Without this, the H1 paper title is treated as uncited factual prose
    # (>50 chars, no [N]) and stripped — then the title-extraction fallback
    # downstream lands on the raw user question.
    if re.match(r"^#{1,6}\s+\S", s):
        return True
    if s.startswith("!["):
        return True
    if s.startswith("*") and "[Source](" in s:
        return True
    if s.startswith("*") and s.endswith("*"):
        return True
    if s.startswith("[Source](") and s.endswith(")"):
        return True
    if re.fullmatch(r"\[[^\]]+\]\([^)]+\)", s):
        return True
    return False


def _is_duplicate_heading_block(block: str, section_title: str) -> bool:
    """True when the writer re-emitted the section title as its own paragraph."""
    if not section_title:
        return False
    norm_block = re.sub(r"[^a-z0-9]+", " ", block.lower()).strip()
    norm_sec = re.sub(r"[^a-z0-9]+", " ", section_title.lower()).strip()
    return norm_block == norm_sec


def _is_factual_paragraph(block: str, section_title: str) -> bool:
    """Audit-equivalent check: does this block need an [N] marker to be considered cited?"""
    if len(block) <= 50:
        return False
    if section_title in _EXEMPT_SECTIONS:
        return False
    if block.lower().startswith(_STRUCTURAL_STARTS):
        return False
    if _is_non_prose_block(block):
        return False
    if _is_duplicate_heading_block(block, section_title):
        return False
    return True


# Stopwords used by significant-token tokenization. Kept tight: only function
# words and grammatical scaffolding. Content words like "study", "research",
# "evidence" stay because they carry domain weight in claim text matching.
_TOKENIZE_STOPWORDS = frozenset(
    {
        "about",
        "after",
        "also",
        "been",
        "being",
        "between",
        "both",
        "could",
        "during",
        "each",
        "from",
        "have",
        "having",
        "however",
        "into",
        "more",
        "much",
        "must",
        "other",
        "over",
        "should",
        "some",
        "such",
        "than",
        "that",
        "their",
        "them",
        "then",
        "there",
        "these",
        "this",
        "those",
        "through",
        "thus",
        "under",
        "until",
        "upon",
        "very",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "with",
        "within",
        "without",
        "would",
        "your",
    }
)


def _significant_tokens(text: str) -> set[str]:
    """Lowercase tokens of length >= 4, alphanumerics only, minus stopwords.

    Used to compute lexical overlap between a paragraph and a candidate claim
    text. The length filter discards most articles/conjunctions/prepositions;
    the stopword set removes a small list of high-frequency content-free
    multi-letter words. What remains is mostly domain-bearing nouns, verbs,
    and adjectives — the right signal for "are these texts about the same
    underlying claim?"
    """
    if not text:
        return set()
    raw = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in raw if len(w) >= 4 and w not in _TOKENIZE_STOPWORDS}


def prefer_tier_1_source_ids(source_ids: list[str], registry: CitationRegistry) -> list[str]:
    """Drop tier-2/3 source ids when at least one tier-1 source supports the same claim.

    Theo's source pool intentionally spans peer-reviewed journals, museum
    pages, Wikipedia, YouTube transcripts, and web search results. When a
    single claim is supported by both a tier-1 (DOI / academic) source and
    several tier-3 (YouTube / web) sources, we cite only the tier-1 — the
    YouTube transcript is no longer load-bearing for that claim. Tier-2/3
    sources remain available when they are the ONLY support for a claim.

    Unknown source ids (not yet in registry.sources) pass through unchanged
    in the "other" bucket — downstream code synthesises a reference number
    for them and `prune_unrenderable_references` cleans up if they never
    resolve. The point of this filter is to favour known academic sources,
    not to drop unfamiliar ones.
    """
    tier_1: list[str] = []
    other: list[str] = []
    for sid in source_ids:
        src = registry.sources.get(sid)
        if src is not None and src.reliability_tier == 1:
            tier_1.append(sid)
        else:
            other.append(sid)
    return tier_1 if tier_1 else other


def inject_citation_for_paragraph(
    paragraph: str,
    registry: CitationRegistry,
    *,
    min_overlap_ratio: float = 0.6,
    min_overlap_words: int = 7,
) -> str | None:
    """Try to attach an [N] marker to an uncited paragraph by content match.

    Walks `registry.claims` and computes lexical overlap between the
    paragraph and each claim's text. If the best-scoring claim shares at
    least `min_overlap_words` significant tokens AND a `min_overlap_ratio`
    fraction of the smaller token set, we treat the paragraph as supported
    by that claim and append the claim's reference markers to the paragraph
    end.

    Returns the modified paragraph (with appended ` [N] [M]` markers) on a
    successful injection. Returns `None` when no claim scores high enough,
    when the paragraph already cites every candidate marker, or when no
    claim source resolves to a registered CitedSource.

    Conservative by design: better to leave a paragraph uncited (and have
    the strip drop it or the section-preserve safeguard restore it) than to
    misattribute a citation. Tune `min_overlap_words` upward if false
    matches appear; downward if real matches are missed.
    """
    if not registry.claims:
        return None

    para_tokens = _significant_tokens(paragraph)
    if len(para_tokens) < min_overlap_words:
        return None

    best_score = 0.0
    best_overlap_size = 0
    best_claim: ClaimCitation | None = None
    for claim in registry.claims:
        if not claim.source_ids:
            continue
        c_tokens = _significant_tokens(claim.claim_text)
        if len(c_tokens) < min_overlap_words:
            continue
        overlap = para_tokens & c_tokens
        if len(overlap) < min_overlap_words:
            continue
        score = len(overlap) / min(len(para_tokens), len(c_tokens))
        if score > best_score or (score == best_score and len(overlap) > best_overlap_size):
            best_score = score
            best_overlap_size = len(overlap)
            best_claim = claim

    if best_claim is None or best_score < min_overlap_ratio:
        return None

    # Resolve source_ids → reference numbers, assigning new ones for any
    # source the writer didn't already cite. The new numbers will surface in
    # format_references_list() since it iterates reference_numbers in order.
    #
    # Apply tier preference BEFORE assigning numbers: if any source on this
    # claim is tier-1 (peer-reviewed), drop tier-2/3 sources from this
    # citation. This prevents YouTube transcripts from getting reference
    # numbers when a DOI-bearing alternative exists. Tier-3 sources keep
    # their slot in the registry and can still get numbered by other claims.
    chosen_sids = prefer_tier_1_source_ids(best_claim.source_ids, registry)
    nums: list[int] = []
    for sid in chosen_sids:
        num = registry.reference_numbers.get(sid)
        if num is None:
            num = registry.assign_reference_number(sid)
        if num not in nums:
            nums.append(num)
    if not nums:
        return None

    existing = {int(m) for m in re.findall(r"\[(\d+)\]", paragraph)}
    new_nums = [n for n in nums if n not in existing]
    if not new_nums:
        # All candidate markers already present — paragraph is effectively cited
        return paragraph

    cite_str = " " + " ".join(f"[{n}]" for n in new_nums)
    return paragraph.rstrip() + cite_str


def strip_uncited_factual_paragraphs(
    paper_text: str,
    registry: CitationRegistry,
    *,
    section_preserve_threshold: float = 0.25,
    metrics_out: dict | None = None,
) -> str:
    """Remove factual paragraphs lacking an [N] marker — section-aware.

    Used as the final guarantee step after finalize_references: even if the
    per-section LLM repair passes failed silently, this mechanically prunes
    the prose so audit_citations sees zero uncited paragraphs.

    Before stripping, attempts smart claim-injection via
    `inject_citation_for_paragraph`: for each uncited factual paragraph,
    look up the closest-matching claim in `registry.claims` by content
    overlap and append its [N] marker. Only paragraphs with no plausible
    claim support are stripped. This preserves writer-produced content
    that simply forgot to attach a marker — the citation evidence is in
    the registry, just not in the prose.

    Section-preservation safeguard: if stripping a section would leave it
    with less than `section_preserve_threshold` of its original prose word
    count, the section's original (uncited) content is restored. This
    prevents whole sections from being gutted to satisfy the audit at the
    cost of empty headings — the audit will then flag the surviving
    uncited paragraphs and the writer's earlier repair pass owns it.

    Image blocks, captions, source-link trailers, structural openers,
    exempt sections, duplicate-heading paragraphs, and the References
    section are always preserved.

    If `metrics_out` is provided, the dict is populated with:
        - `uncited_seen`: factual paragraphs that lacked a marker
        - `injected`: paragraphs rescued by registry claim-injection
        - `dropped`: paragraphs deleted (no plausible claim match)
        - `restored_sections`: sections that fell back to original content
          via the section-preservation safeguard
    Use these to track in production whether the writer is improving
    over time vs the safety net silently masking bad output.
    """
    counts = {"uncited_seen": 0, "injected": 0, "dropped": 0, "restored_sections": 0}
    refs_start = _find_references_heading(paper_text)
    if refs_start is not None:
        prose = paper_text[:refs_start]
        refs_tail = paper_text[refs_start:]
    else:
        prose = paper_text
        refs_tail = ""

    # Pass 1: split into per-section block-lists so we can decide per-section
    # whether the strip is safe to apply.
    sections: list[dict] = [{"title_lower": "", "title_block": None, "blocks": []}]
    for block in prose.split("\n\n"):
        stripped = block.strip()
        heading_match = re.match(r"^##\s+(.+)$", stripped, re.MULTILINE) if stripped else None
        if heading_match:
            sections.append(
                {
                    "title_lower": heading_match.group(1).strip().lower(),
                    "title_block": block,
                    "blocks": [],
                }
            )
            continue
        sections[-1]["blocks"].append(block)

    # Pass 2: per-section, compute stripped vs. original word-count and
    # choose to keep stripped or fall back to original.
    out_blocks: list[str] = []
    for sec in sections:
        title_lower = sec["title_lower"]
        title_block = sec["title_block"]
        blocks = sec["blocks"]

        original_word_count = sum(
            len(b.split()) for b in blocks if b.strip() and not b.strip().startswith("#")
        )

        stripped_blocks: list[str] = []
        for b in blocks:
            stripped = b.strip()
            if not stripped:
                stripped_blocks.append(b)
                continue
            if _is_factual_paragraph(stripped, title_lower) and not re.search(r"\[\d+\]", stripped):
                counts["uncited_seen"] += 1
                # Try smart injection before dropping. If a registry claim
                # supports this paragraph, attach its [N] markers in place
                # of removing the content.
                injected = inject_citation_for_paragraph(stripped, registry)
                if injected is not None and re.search(r"\[\d+\]", injected):
                    # Preserve the original block's leading/trailing
                    # whitespace by replacing the stripped slice in-place.
                    new_block = b.replace(stripped, injected, 1)
                    stripped_blocks.append(new_block)
                    counts["injected"] += 1
                else:
                    counts["dropped"] += 1
                continue
            stripped_blocks.append(b)

        stripped_word_count = sum(
            len(b.split()) for b in stripped_blocks if b.strip() and not b.strip().startswith("#")
        )

        # If the strip would gut the section (below threshold), fall back to
        # the original blocks so the section keeps its content. The audit
        # gate then records the surviving uncited paragraphs honestly.
        #
        # BUT: if EVERYTHING in the section was uncited (stripped_word_count
        # == 0), there is nothing meaningful to preserve. Restoring would
        # just keep uncited factual claims, which the audit then flags. The
        # honest behavior is to drop the section. Run 16 had the H1 opening
        # hook (Cortés/Quetzalcoatl) preserved this way: 147 words, all
        # uncited because the verifier rejected the disputed Moctezuma
        # claim's citations. The hook survived only via this safeguard,
        # then failed the audit. Better to drop than to preserve uncited.
        all_uncited = stripped_word_count == 0 and original_word_count > 0
        if (
            not all_uncited
            and original_word_count > 100
            and stripped_word_count < original_word_count * section_preserve_threshold
        ):
            chosen = blocks
            counts["restored_sections"] += 1
        else:
            chosen = stripped_blocks

        if title_block is not None:
            out_blocks.append(title_block)
        out_blocks.extend(chosen)

    new_prose = "\n\n".join(out_blocks)
    new_prose = re.sub(r"\n{3,}", "\n\n", new_prose).rstrip() + "\n"

    if metrics_out is not None:
        metrics_out.update(counts)

    return new_prose + refs_tail


# ---------------------------------------------------------------------------
# Citation audit
# ---------------------------------------------------------------------------


# Quotation spans, for telling an editorial interpolation from an artifact.
# Straight single quotes need the alnum guards or every possessive apostrophe
# ("Beall's collection") would open a span that swallows the rest of the line.
_QUOTATION_RES = (
    re.compile(r"\"([^\"\n]{0,600})\""),
    re.compile(r"“([^”\n]{0,600})”"),
    re.compile(r"‘([^’\n]{0,600})’"),
    re.compile(r"(?<![A-Za-z0-9])'([^'\n]{0,600})'(?![A-Za-z0-9])"),
)


def _quotation_spans(prose: str) -> list[tuple[int, int]]:
    """Inner spans of quoted passages, straight and typographic."""
    return [(m.start(1), m.end(1)) for rx in _QUOTATION_RES for m in rx.finditer(prose)]


def _is_artifact_shaped_token(token: str) -> bool:
    """Token shapes that are pipeline artifacts wherever they appear.

    Used to keep a quotation from laundering an artifact: `"the polish is
    modern [N1]"` is still a defect, `"over [the past 100,000 years]"` is not.
    """
    if _is_strippable_artifact_token(token):
        return True
    return bool(re.fullmatch(r"\d+(?:\s*[,;]\s*\d+)+", token))  # grouped [9, 7, 1]


def _collect_non_numeric_markers(prose: str) -> list[str]:
    """Bracketed tokens in prose that are not plain [N] citations.

    Catches pipeline debug IDs ([5620e1fb87f7]), [N1]-style writer artifacts,
    and grouped forms like [9, 7, 1] (grouped digits are NOT a valid marker —
    they are invisible to renumbering). Markdown links [x](y) are excluded via
    the negative lookahead; footnotes [^n] and [N - topic] placeholders (already
    counted separately) are skipped. Deduplicated, first-seen order.

    Brackets INSIDE a quotation are editorial interpolation — the standard way
    to adapt a quote to its sentence (`"evidence over [the past 100,000 years]
    is inconclusive"`) — and are not flagged unless the token is itself
    artifact-shaped (2026-08-31: two finished papers were held over this).
    """
    quotations = _quotation_spans(prose)
    out: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"\[([^\]\n]+)\](?!\()", prose):
        token = m.group(1).strip()
        if not token or token.isdigit():
            continue
        if token.startswith("^"):
            continue
        if _PLACEHOLDER_MARKER_RE.match(f"[{token}]"):
            continue
        if not _is_artifact_shaped_token(token) and any(
            start <= m.start() and m.end() <= end for start, end in quotations
        ):
            continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def audit_citations(paper_text: str, registry: CitationRegistry) -> dict:
    """Mechanical citation audit — no LLM, pure regex/text analysis.

    Checks:
    1. Every [N] marker in the text maps to a real reference in registry.
    2. Every paragraph with a factual claim has at least one [N]
       (heuristic: paragraphs > 50 chars that don't start with # are factual).
    3. No orphaned references (assigned number but never cited in text).
    4. No unresolved [N - topic] placeholders leaked into prose.
    5. No non-Latin script bleed-through.
    6. No non-numeric bracketed tokens in prose (catches pipeline debug IDs like
       [5620e1fb87f7] that escaped marker resolution). Markdown links [x](y) and
       footnotes [^n] are excluded.

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
            "non_numeric_markers": list[str], # bracketed tokens that aren't [N]
            "issues": list[str],            # human-readable issue descriptions
        }
    """
    issues: list[str] = []

    # Scan only the prose portion (everything before the ## References heading).
    # The references list legitimately contains [N] prefixes for every declared
    # reference; if we scanned the whole paper, every reference would count as
    # "cited" and the audit would be idempotent to the prose but not to the
    # References section. Making prose_only the single source of truth for ALL
    # checks keeps the audit idempotent across "refs appended / not yet appended"
    # states — so paper.py, judge.py, and the edit endpoint all agree.
    refs_start = _find_references_heading(paper_text)
    prose_only = paper_text[:refs_start] if refs_start is not None else paper_text

    # All [N] markers found in the prose
    marker_values: list[int] = [int(m) for m in re.findall(r"\[(\d+)\]", prose_only)]
    total_citations = len(marker_values)
    unique_cited_nums: set[int] = set(marker_values)

    # All assigned reference numbers — only count entries whose source is still
    # resolvable. Mirrors the predicate used by format_references_list (lines
    # 166-168): if sources[sid] is None, the entry won't render in the output,
    # so the assigned number must surface as invalid in the audit. Run 15 had
    # [53]-[59] in prose with no References entries because the journal
    # rejection path popped sources but kept reference_numbers — the old set
    # comprehension thought those numbers were valid.
    assigned_nums: set[int] = {
        num
        for sid, num in registry.reference_numbers.items()
        if registry.sources.get(sid) is not None
    }
    total_references = len(assigned_nums)

    # 1. Invalid markers — [N] in prose with no assigned reference
    invalid_markers = sorted(unique_cited_nums - assigned_nums)
    for n in invalid_markers:
        issues.append(f"[{n}] cited in text but no matching reference assigned")

    # 2. Orphaned references — assigned but never cited in prose
    orphaned_refs = sorted(assigned_nums - unique_cited_nums)
    for n in orphaned_refs:
        issues.append(f"[{n}] assigned as reference but never cited in text")

    # 3. Uncited paragraphs — factual claim paragraphs with no [N]
    #
    # Section-aware: exempt Abstract, Introduction, and Methodology entirely
    # (these are framing sections that don't require per-paragraph citations).
    # For body/discussion/conclusion sections, apply structural-start heuristic
    # to skip transitions, ordinals, and non-factual framing text.

    paragraphs_with_section = _split_prose_into_paragraphs(prose_only)
    factual_paragraphs = [
        p for section, p in paragraphs_with_section if _is_factual_paragraph(p, section)
    ]
    uncited_paragraphs = sum(1 for p in factual_paragraphs if not re.search(r"\[\d+\]", p))
    if uncited_paragraphs:
        issues.append(
            f"{uncited_paragraphs} paragraph(s) longer than 50 chars contain no citation marker"
        )

    # 4. Unresolved [N - topic] placeholders — the LLM's cry-for-help when no
    #    citation number was provided.
    placeholder_markers = detect_placeholder_markers(prose_only)
    if placeholder_markers:
        issues.append(f"{len(placeholder_markers)} unresolved [N - topic] placeholder(s) in prose")

    # 5. Language bleed — non-Latin script in prose
    language_bleed = detect_language_bleed(prose_only)
    if language_bleed:
        issues.append(
            f"{len(language_bleed)} non-Latin script segment(s) in prose: "
            + ", ".join(language_bleed[:3])
        )

    # 6. Non-numeric bracketed markers — pipeline debug tokens like
    #    [5620e1fb87f7] that escaped finalize_references(). Markdown links
    #    [text](url) are excluded via negative lookahead on `(`. Footnotes
    #    [^n] and already-caught [N - topic] placeholders are skipped.
    non_numeric_markers = _collect_non_numeric_markers(prose_only)
    if non_numeric_markers:
        sample = ", ".join(f"[{t}]" for t in non_numeric_markers[:5])
        issues.append(
            f"{len(non_numeric_markers)} non-numeric bracketed marker(s) in prose "
            f"(likely pipeline debug tokens): {sample}"
        )

    passed = (
        not invalid_markers
        and not orphaned_refs
        and uncited_paragraphs == 0
        and not placeholder_markers
        and not language_bleed
        and not non_numeric_markers
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
        "non_numeric_markers": non_numeric_markers,
        "issues": issues,
    }


# Shared references-heading regex — first-match used by
# _find_references_heading (pre-final pipeline text), last-match used by
# split_artifact (final artifact). See each function's docstring for why
# the match direction differs.
#
# Exact-line-end contract: the heading word must be the last thing on the
# line (only trailing whitespace allowed) — no trailing colon, no extra
# words. This mirrors the frontend's `splitBodyAndRefs` (ancient-nerds-map/
# src/pages/ResearchPaperPage.tsx), which requires end-of-line after
# "References"/"Sources" to recognize the heading. Two consequences, both
# verified against the renderer: "## References:" (trailing colon) is NOT a
# refs heading to readers, so the backend must not treat it as one either —
# accepting it would let the gate certify a paper that renders with broken
# citations. Conversely "## Sources of Evidence" is NOT a refs heading (extra
# words after "Sources"), so the loose `\b.*$` version previously false-
# positived on it, both here and in `_find_references_heading` (which feeds
# audit/strip/prune). Note: `strip_existing_references_section` uses its own,
# deliberately looser regex — that's pre-append cleanup of LLM-emitted
# variants (including the colon form) and is unaffected by this change.
_REFS_HEADING_RE = re.compile(r"^#{2,3}\s+(?:References|Sources)\s*$", re.MULTILINE)


def _find_references_heading(text: str) -> int | None:
    """Return the index of the first References/Sources heading line, or None.

    First match, deliberately: this is used on pre-final pipeline text
    (audit/strip/prune), where the conservative choice is to treat the
    earliest heading as the start of the refs region. Contrast with
    `split_artifact`, which uses the LAST heading on final artifacts.
    """
    m = _REFS_HEADING_RE.search(text)
    return m.start() if m else None


# ---------------------------------------------------------------------------
# Artifact splitting — shared by validate_paper_artifact / repair_artifact /
# replace_references_section / presentation's prose-vs-refs split
# ---------------------------------------------------------------------------


def split_artifact(markdown: str) -> tuple[str, str, str]:
    """Split final paper markdown into (prose, heading_line, refs_body).

    Splits on the LAST References/Sources heading, mirroring the frontend's
    `splitBodyAndRefs` (ancient-nerds-map/src/pages/ResearchPaperPage.tsx) —
    both in match direction (last heading) and in requiring the heading word
    to end the line (see `_REFS_HEADING_RE`'s exact-line-end contract: no
    trailing colon, no extra words) so a heading here is only ever recognized
    when the frontend renderer would also recognize it. This defends against
    a writer/presentation LLM injecting a fake "## References" heading
    mid-body: with last-match, everything up to and including the true
    trailing heading stays in scope, so a fake mid-body heading remains
    visible in prose rather than silently truncating real content. Documents
    with multiple headings are rejected by `validate_paper_artifact`.
    Contrast with `_find_references_heading`, which uses the FIRST heading on
    pre-final pipeline text.
    heading_line includes the trailing newline when present. When no heading
    exists, everything is prose and heading/body are empty.
    """
    matches = list(_REFS_HEADING_RE.finditer(markdown))
    if not matches:
        return markdown, "", ""
    m = matches[-1]
    heading_end = markdown.find("\n", m.start())
    if heading_end == -1:
        return markdown[: m.start()], markdown[m.start() :], ""
    return (
        markdown[: m.start()],
        markdown[m.start() : heading_end + 1],
        markdown[heading_end + 1 :],
    )


_GROUPED_MARKER_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)+)\]")

# A thousands-formatted numeral like `[3,000]` or `[30,000,000]` — matches the
# _GROUPED_MARKER_RE shape (digits, comma, digits) but is a number, not a
# citation group. Guarded separately so it's left intact rather than split
# into `[3] [000]`.
_THOUSANDS_NUMERAL_RE = re.compile(r"^\d{1,3}(?:,\d{3})+$")

# Short numeric dash range `[2-4]` / `[7–8]`. Digits-only, so this can never
# collide with _PLACEHOLDER_MARKER_RE (`[N - topic]`, which requires a
# literal letter "N") — the two patterns never compete for the same bracket
# text. Each operand is guarded with `(?!0\d)` so leading-zero forms like
# `07` (day-of-month / two-digit-year style, as in `[07-08]`) never match —
# real reference ranges don't zero-pad.
_RANGE_MARKER_RE = re.compile(r"\[(?!0\d)(\d+)\s*[-–]\s*(?!0\d)(\d+)\]")


def normalize_grouped_markers(text: str) -> tuple[str, int]:
    """Split grouped citation markers `[9, 7, 1]` into `[9] [7] [1]`, and
    expand short numeric dash ranges `[2-4]` into `[2] [3] [4]`.

    MUST run before finalize_references(): grouped digits are invisible to
    the `\\[(\\d+)\\]` renumbering regex, so an unsplit group keeps its OLD
    working numbers after renumbering — silent misattribution, worse than an
    orphan. Only prose is touched; the References section may legitimately
    contain commas inside titles.

    Two guards against false positives:
    * Thousands-formatted numerals like `[3,000]` are left intact — the
      bracket content matches `\\d{1,3}(?:,\\d{3})+` exactly, so it's a
      numeral rather than a citation group. The validator then flags the
      surviving non-numeric marker and the paper HOLDS instead of being
      silently shredded into `[3] [000]`.
    * Dash ranges are only expanded when both operands have no leading zero,
      `start < end`, `end < 100`, and `end - start <= 10`; anything outside
      that (reversed, equal, oversized, zero-padded, or 100+) is left intact.
      No paper has 100+ references, so a range like `[1990-1995]` is a year
      span in prose, not a citation range, and `[07-08]` (leading zeros) is
      the same shape — both are left intact rather than fabricating
      citations, and the validator flags the surviving marker so the paper
      HOLDS instead of publishing invented references.

    Returns (new_text, groups_split) — groups_split counts both comma-groups
    and dash-ranges that were actually expanded.
    """
    prose, heading, body = split_artifact(text)
    count = 0

    def _split(m: re.Match[str]) -> str:
        nonlocal count
        token = m.group(1)
        compact = re.sub(r"\s+", "", token)
        if _THOUSANDS_NUMERAL_RE.fullmatch(compact):
            return m.group(0)  # a numeral like [3,000], not a citation group
        count += 1
        return " ".join(f"[{n.strip()}]" for n in token.split(","))

    prose = _GROUPED_MARKER_RE.sub(_split, prose)

    def _expand_range(m: re.Match[str]) -> str:
        nonlocal count
        start, end = int(m.group(1)), int(m.group(2))
        if start < end and end < 100 and end - start <= 10:
            count += 1
            return " ".join(f"[{n}]" for n in range(start, end + 1))
        return m.group(0)

    prose = _RANGE_MARKER_RE.sub(_expand_range, prose)

    return prose + heading + body, count


def validate_paper_artifact(markdown: str) -> dict:
    """Artifact-only citation integrity check — validates what readers see.

    Unlike audit_citations() this takes NO registry: it parses the rendered
    ## References list out of the markdown and checks the prose against it.
    Registry and rendered artifact can drift (injection assigns numbers after
    the list was rendered; presentation re-appended the stale block verbatim
    while prune mutated the registry) — this function is immune to the drift
    because it never sees the registry. Run it on the exact text being
    persisted or published.

    Returns the audit_result dict shape (superset): every audit_citations key
    plus references_sections, unparseable_ref_lines, duplicate_ref_nums,
    non_contiguous. `passed` is True iff `issues` is empty.
    """
    # Normalize CRLF -> LF up front. A CRLF paper (possible via the PATCH edit
    # path) otherwise disables the uncited-paragraph check downstream, since
    # `_split_prose_into_paragraphs` splits on a bare "\n\n" and would never
    # see a blank-line boundary written as "\r\n\r\n".
    markdown = markdown.replace("\r\n", "\n")

    issues: list[str] = []

    references_sections = len(_REFS_HEADING_RE.findall(markdown))
    if references_sections == 0:
        issues.append("no References section found")
    elif references_sections > 1:
        issues.append(f"{references_sections} References/Sources headings (expected 1)")

    prose_only, _heading, refs_body = split_artifact(markdown)

    # Every non-empty rendered line must parse as a reference entry.
    parsed = parse_references_section(refs_body)
    parsed_nums = [r["num"] for r in parsed]
    if references_sections and not parsed:
        issues.append("References section contains no parseable entries")
    unparseable_ref_lines: list[str] = []
    for line in refs_body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not (_RICH_REF_LINE_RE.match(stripped) or _REF_LINE_RE.match(stripped)):
            unparseable_ref_lines.append(stripped[:120])
    if unparseable_ref_lines:
        issues.append(
            f"{len(unparseable_ref_lines)} unparseable line(s) in References: "
            + "; ".join(unparseable_ref_lines[:3])
        )

    duplicate_ref_nums = sorted({n for n in parsed_nums if parsed_nums.count(n) > 1})
    if duplicate_ref_nums:
        issues.append(f"duplicate reference number(s): {duplicate_ref_nums}")

    ref_nums = set(parsed_nums)
    non_contiguous = bool(ref_nums) and sorted(ref_nums) != list(range(1, max(ref_nums) + 1))
    if non_contiguous:
        issues.append(f"reference numbers not contiguous 1..{max(ref_nums)}")

    marker_values = [int(m) for m in re.findall(r"\[(\d+)\]", prose_only)]
    total_citations = len(marker_values)
    unique_cited = set(marker_values)

    invalid_markers = sorted(unique_cited - ref_nums)
    for n in invalid_markers:
        issues.append(f"[{n}] cited in text but not in the rendered References list")

    orphaned_refs = sorted(ref_nums - unique_cited)
    for n in orphaned_refs:
        issues.append(f"[{n}] in References list but never cited in text")

    # Prose-quality checks — same helpers audit_citations uses, so the dict
    # keeps its full shape for the judge/UI.
    paragraphs_with_section = _split_prose_into_paragraphs(prose_only)
    factual = [p for s, p in paragraphs_with_section if _is_factual_paragraph(p, s)]
    uncited_paragraphs = sum(1 for p in factual if not re.search(r"\[\d+\]", p))
    if uncited_paragraphs:
        issues.append(
            f"{uncited_paragraphs} paragraph(s) longer than 50 chars contain no citation marker"
        )

    placeholder_markers = detect_placeholder_markers(prose_only)
    if placeholder_markers:
        issues.append(f"{len(placeholder_markers)} unresolved [N - topic] placeholder(s) in prose")

    language_bleed = detect_language_bleed(prose_only)
    if language_bleed:
        issues.append(
            f"{len(language_bleed)} non-Latin script segment(s) in prose: "
            + ", ".join(language_bleed[:3])
        )

    non_numeric_markers = _collect_non_numeric_markers(prose_only)
    if non_numeric_markers:
        sample = ", ".join(f"[{t}]" for t in non_numeric_markers[:5])
        issues.append(
            f"{len(non_numeric_markers)} non-numeric bracketed marker(s) in prose: {sample}"
        )

    return {
        "passed": not issues,
        "total_citations": total_citations,
        "total_references": len(parsed),
        "orphaned_refs": orphaned_refs,
        "invalid_markers": invalid_markers,
        "uncited_paragraphs": uncited_paragraphs,
        "placeholder_markers": placeholder_markers,
        "language_bleed": language_bleed,
        "non_numeric_markers": non_numeric_markers,
        "references_sections": references_sections,
        "unparseable_ref_lines": unparseable_ref_lines,
        "duplicate_ref_nums": duplicate_ref_nums,
        "non_contiguous": non_contiguous,
        "issues": issues,
    }


def replace_references_section(text: str, refs_md: str) -> str:
    """Replace (or append) the rendered References block with refs_md.

    Presentation renders the canonical list from the registry AFTER all
    injection/prune passes; this swaps out whatever stale block the text
    carries. Empty refs_md just drops the block.
    """
    prose, _heading, _body = split_artifact(text)
    if not refs_md:
        return prose.rstrip() + "\n"
    return prose.rstrip() + f"\n\n## References\n\n{refs_md}\n"


def _is_strippable_artifact_token(token: str) -> bool:
    """Bracket tokens that are unambiguous pipeline artifacts — safe to strip.

    Everything else ([sic], quote interpolations like [the king], reference-style
    link labels, nested-bracket alt text) is left in place; the validator then
    flags it and the paper HOLDS for a human instead of being silently rewritten.
    """
    if not token:  # `[ ]` — what a stripped marker leaves behind, reader-visible
        return True
    if re.fullmatch(r"N\d*", token):  # [N], [N1], [N7] writer artifacts
        return True
    if token in ("...", "…"):
        return True
    if re.fullmatch(r"(?=.*\d)[a-f0-9]{12}", token):  # source-id debug tokens (sha256[:12])
        # Digit required: pure-letter hex words like "facade"/"decade" must NOT match.
        return True
    if _PLACEHOLDER_MARKER_RE.fullmatch(f"[{token}]"):  # [N - topic]
        return True
    if token == "self":  # noqa: S105 - [self] provenance marker, not a password
        return True
    return False


def repair_artifact(markdown: str) -> tuple[str, dict]:
    """Deterministic citation repair. Never adds or remaps a citation.

    Order matters:
      1. split grouped markers so every digit is visible (also expands short
         dash ranges like [2-4] and skips thousands-formatted numerals),
      2. strip ONLY allowlisted pipeline-artifact bracket tokens ([N1],
         [N - topic], [...], hex source-id tokens, [self] provenance markers)
         — everything else (quote interpolations, [sic], nested markdown alt
         text) is left untouched, so the validator flags it and the paper
         HOLDS for a human instead of being silently rewritten,
      3. strip numeric prose markers with no rendered list entry,
      4. drop rendered entries never cited in prose,
      5. renumber prose + list atomically to 1..M in first-citation order.

    Bails (steps 3-5 skipped) when: the rendered list itself is broken — no
    refs section, a non-empty line that isn't `[N] ...`, or duplicate numbers
    — OR a numeric marker is immediately followed by `(` or `]` (`[1](...)`
    reads as a markdown link to a reader but as a citation to the naive
    validator census; `[1]]` means the marker is nested inside a larger
    bracket span, e.g. markdown image alt text; letting the lookahead skip
    either shape would let a stale number survive renumbering, i.e. silent
    misattribution) — OR the text already contains a `\x00` sentinel byte
    (renumbering could not tell it apart from its own scratch markers).
    Repairing against a broken list would be guessing, and guessing is the
    failure mode this module exists to prevent. The caller must HOLD such
    papers, not publish them.

    Returns (repaired_markdown, validate_paper_artifact(repaired_markdown)).
    """
    markdown = markdown.replace("\r\n", "\n")  # mixed-EOL repairs otherwise
    if "\x00" in markdown:  # sentinel collision — cannot renumber safely
        return markdown, validate_paper_artifact(markdown)

    text, _groups = normalize_grouped_markers(markdown)
    prose, heading, refs_body = split_artifact(text)

    # Step 2 — strip ONLY allowlisted pipeline-artifact bracket tokens. The
    # regex consumes an optional single leading space so a stripped token
    # never leaves a doubled space or a space-before-punctuation behind;
    # kept tokens return their full match unchanged (no-op).
    def _drop_non_numeric(m: re.Match[str]) -> str:
        token = m.group(1).strip()
        if token.isdigit() or token.startswith("^"):
            return m.group(0)
        if _is_strippable_artifact_token(token):
            return ""
        return m.group(0)

    prose = re.sub(r" ?\[([^\]\n]+)\](?!\()", _drop_non_numeric, prose)

    # Numeric markers glued to another bracket-ish character are ambiguous —
    # bail rather than guess. `[1](url)` reads as a markdown link to a reader
    # but as a citation to the naive (no-lookahead) validator census; `[1]]`
    # means the marker sits inside a larger bracket span our regexes can't
    # parse (e.g. markdown image alt text `![... [1]](url)` — the `]]` here
    # is the inner marker's `]` immediately followed by the alt-text's own
    # closing `]`). Either shape risks a stale digit surviving renumbering
    # inside content it doesn't own — silent misattribution.
    ambiguous_adjacency = bool(re.search(r"\[\d+\][(\]]", prose))

    # Parse the rendered list; bail on anything broken.
    line_by_num: dict[int, str] = {}
    broken = not heading or ambiguous_adjacency
    for line in refs_body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r"^\[(\d+)\]\s+(.+)$", stripped)
        if m is None or int(m.group(1)) in line_by_num:
            broken = True
            break
        line_by_num[int(m.group(1))] = m.group(2)

    if broken:
        repaired = prose + heading + refs_body
        return repaired, validate_paper_artifact(repaired)

    # Step 3 — strip numeric markers with no rendered entry.
    ref_nums = set(line_by_num)

    def _drop_invalid(m: re.Match[str]) -> str:
        return m.group(0) if int(m.group(1)) in ref_nums else ""

    prose = re.sub(r" ?\[(\d+)\](?!\()", _drop_invalid, prose)

    # Steps 4+5 — first-citation order, renumber prose and rebuild the list.
    order: list[int] = []
    seen: set[int] = set()
    for m in re.finditer(r"\[(\d+)\](?!\()", prose):
        n = int(m.group(1))
        if n not in seen:
            seen.add(n)
            order.append(n)
    old_to_new = {old: new for new, old in enumerate(order, start=1)}

    prose = re.sub(r"\[(\d+)\](?!\()", lambda m: f"\x00{old_to_new[int(m.group(1))]}\x00", prose)
    prose = re.sub(r"\x00(\d+)\x00", r"[\1]", prose)

    new_lines = [f"[{old_to_new[old]}] {line_by_num[old]}" for old in order]
    repaired = replace_references_section(prose, "\n".join(new_lines))
    return repaired, validate_paper_artifact(repaired)


def validate_or_repair(markdown: str) -> tuple[str, dict]:
    """Validate; on failure attempt the deterministic repair once.

    Returns (text, report). The repair never fabricates or remaps a citation,
    so its output is kept whenever it strictly reduces the issue count — even
    when the paper still fails and the caller must hold it.

    Discarding a partial repair (behaviour until 2026-08-31) left held papers
    BOTH broken and unpublished: all six papers held that August had their
    reference numbering repaired and then thrown away, so the manual publish
    they were waiting for would have shipped the broken numbering anyway.
    """
    report = validate_paper_artifact(markdown)
    if report["passed"]:
        return markdown, report
    repaired, repaired_report = repair_artifact(markdown)
    if repaired_report["passed"]:
        return repaired, repaired_report
    if len(repaired_report["issues"]) < len(report["issues"]):
        return repaired, repaired_report
    return markdown, report


# ---------------------------------------------------------------------------
# References-section parser (mirrors ancient-nerds-map/src/pages/
# ResearchPaperPage.tsx:parseReferences — keep field names aligned)
# ---------------------------------------------------------------------------

# Legacy line: "[N] Title — URL (accessed YYYY-MM-DD) [Tier]"
# Dash variants accepted: em-dash (— U+2014), en-dash (– U+2013), ascii " - ".
_REF_LINE_RE = re.compile(
    r"^\[(?P<num>\d+)\]\s+(?P<title>.+?)\s+[—–-]\s+"
    r"(?P<url>https?://\S+)"
    r"(?:\s+\(accessed\s+(?P<accessed>\d{4}-\d{2}-\d{2})\))?"
    r"(?:\s+\[(?P<tier>Academic|Reputable)\])?"
    r"\s*$"
)

# Rich (academic) line: "[N] Authors (YYYY). Title. Venue. DOI: 10.xxx/yyy
# (accessed YYYY-MM-DD) [Academic]". The `(YYYY).` anchor disambiguates the
# author block from title text; venue and DOI are required for this format.
_RICH_REF_LINE_RE = re.compile(
    r"^\[(?P<num>\d+)\]\s+"
    r"(?P<authors>.+?)\s+\((?P<year>\d{4})\)\.\s+"
    r"(?P<title>.+?)\.\s+"
    r"(?P<venue>.+?)\.\s+"
    r"DOI:\s+(?P<doi>\S+?)"
    r"(?:\s+\(accessed\s+(?P<accessed>\d{4}-\d{2}-\d{2})\))?"
    r"(?:\s+\[(?P<tier>Academic|Reputable)\])?"
    r"\s*$"
)


def parse_references_section(refs_text: str) -> list[dict]:
    """Parse a `## References` body into structured dicts.

    Input: the text AFTER the `## References` heading (the markdown list of refs).
    Output: list of dicts with keys {num, title, url, accessed, tier_label,
    authors, year, venue, doi} (rich-format-only keys may be None).
    Unparseable lines are skipped silently — they're preserved by the PATCH
    handler via the raw `## References` split rather than by this parser.
    """
    out: list[dict] = []
    for line in refs_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # Try rich format first — its anchor `(YYYY).` is specific enough that
        # it won't accidentally match a legacy `Title — URL` line.
        m = _RICH_REF_LINE_RE.match(stripped)
        if m:
            doi = m.group("doi")
            out.append(
                {
                    "num": int(m.group("num")),
                    "title": m.group("title"),
                    "url": f"https://doi.org/{doi}",
                    "accessed": m.group("accessed"),
                    "tier_label": m.group("tier"),
                    "authors": m.group("authors"),
                    "year": int(m.group("year")),
                    "venue": m.group("venue"),
                    "doi": doi,
                }
            )
            continue

        m = _REF_LINE_RE.match(stripped)
        if not m:
            continue
        out.append(
            {
                "num": int(m.group("num")),
                "title": m.group("title"),
                "url": m.group("url"),
                "accessed": m.group("accessed"),
                "tier_label": m.group("tier"),
                "authors": None,
                "year": None,
                "venue": None,
                "doi": None,
            }
        )
    return out
