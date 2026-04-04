"""Multi-source academic search for Theo's research pipeline.

Searches multiple academic and web APIs in parallel, deduplicates
results, and filters junk domains.  Each adapter creates its own
httpx.Client and handles errors independently.

Usage:
    from pipeline.lyra.theo_sources import MultiSourceSearch, RawSource

    searcher = MultiSourceSearch(settings)
    results = await searcher.search(queries=["Gobekli Tepe dating"], source_group="standard")
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Load .env so os.getenv() picks up THEO_* keys
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from pipeline.lyra.config import LyraSettings
from pipeline.lyra.minimax_shared import (
    WebSearchResult,
    create_minimax_client,
    minimax_search,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Timeout for all academic API calls (seconds)
# ---------------------------------------------------------------------------
_API_TIMEOUT = 10.0

# ---------------------------------------------------------------------------
# Domain blocklist — filter out social media and low-quality sources
# ---------------------------------------------------------------------------
BLOCKED_DOMAINS = frozenset(
    {
        "reddit.com",
        "old.reddit.com",
        "quora.com",
        "facebook.com",
        "m.facebook.com",
        "twitter.com",
        "x.com",
        "tiktok.com",
        "instagram.com",
        "pinterest.com",
        "youtube.com",
        "m.youtube.com",
        "linkedin.com",
        "medium.com",
        "tumblr.com",
        "4chan.org",
    }
)

# ---------------------------------------------------------------------------
# Source group -> adapter name mapping
# ---------------------------------------------------------------------------
SOURCE_GROUPS: dict[str, list[str]] = {
    "minimal": ["ancientnerds_db", "semantic_scholar", "minimax"],
    "standard": ["ancientnerds_db", "semantic_scholar", "openalex", "crossref", "wikipedia", "minimax"],
    "full": [
        "ancientnerds_db",
        "semantic_scholar",
        "openalex",
        "crossref",
        "core",
        "europeana",
        "smithsonian",
        "wikipedia",
        "minimax",
    ],
    "exhaustive": [
        "ancientnerds_db",
        "semantic_scholar",
        "openalex",
        "crossref",
        "core",
        "europeana",
        "smithsonian",
        "wikipedia",
        "internet_archive",
        "minimax",
    ],
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class RawSource:
    """Unified source result from any search API."""

    url: str
    title: str
    snippet: str  # abstract or search snippet
    date: str = ""
    doi: str = ""  # Digital Object Identifier if available
    authors: list[str] = field(default_factory=list)
    venue: str = ""  # journal/conference name
    citation_count: int = 0
    source_api: str = ""  # which API found this (e.g., "semantic_scholar")
    default_tier: int = 0  # suggested reliability: 1=academic, 2=reputable, 3=general


# ---------------------------------------------------------------------------
# Abstract adapter
# ---------------------------------------------------------------------------


class SourceAdapter(ABC):
    """Abstract adapter for a search API."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def search(self, query: str, max_results: int = 10) -> list[RawSource]: ...

    @property
    @abstractmethod
    def default_tier(self) -> int: ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reconstruct_abstract(inverted: dict) -> str:
    """Reconstruct abstract from OpenAlex inverted index format.

    OpenAlex stores abstracts as ``{"word": [positions]}``.
    """
    if not inverted:
        return ""
    words: dict[int, str] = {}
    for word, positions in inverted.items():
        for pos in positions:
            words[pos] = word
    return " ".join(words[i] for i in sorted(words))


def _strip_html(text: str) -> str:
    """Remove HTML tags from a string."""
    return re.sub(r"<[^>]+>", "", text)


def _extract_domain(url: str) -> str:
    """Extract the domain from a URL, stripping www. prefix."""
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc.removeprefix("www.")


def _is_blocked(url: str) -> bool:
    """Check if a URL's domain is in the blocklist."""
    domain = _extract_domain(url)
    # Check exact match and parent domain (e.g., "old.reddit.com" -> "reddit.com")
    parts = domain.split(".")
    for i in range(len(parts) - 1):
        candidate = ".".join(parts[i:])
        if candidate in BLOCKED_DOMAINS:
            return True
    return False


# ---------------------------------------------------------------------------
# Adapter implementations
# ---------------------------------------------------------------------------


class SemanticScholarAdapter(SourceAdapter):
    """Semantic Scholar API — free tier with optional API key."""

    @property
    def name(self) -> str:
        return "semantic_scholar"

    @property
    def default_tier(self) -> int:
        return 1

    def __init__(self) -> None:
        headers = {"Accept": "application/json"}
        api_key = os.getenv("THEO_SEMANTIC_SCHOLAR_KEY", "")
        if api_key:
            headers["x-api-key"] = api_key
        self._client = httpx.Client(
            base_url="https://api.semanticscholar.org/graph/v1",
            headers=headers,
            timeout=_API_TIMEOUT,
        )

    async def search(self, query: str, max_results: int = 10) -> list[RawSource]:
        def _do() -> list[RawSource]:
            resp = self._client.get(
                "/paper/search",
                params={
                    "query": query,
                    "fields": "title,abstract,year,citationCount,externalIds,openAccessPdf,venue,authors",
                    "limit": max_results,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            results: list[RawSource] = []
            for paper in data.get("data", []):
                doi = ""
                ext_ids = paper.get("externalIds") or {}
                if ext_ids.get("DOI"):
                    doi = ext_ids["DOI"]

                url = f"https://doi.org/{doi}" if doi else ""
                oa_pdf = paper.get("openAccessPdf") or {}
                if oa_pdf.get("url"):
                    url = oa_pdf["url"]
                elif not url:
                    paper_id = paper.get("paperId", "")
                    url = f"https://www.semanticscholar.org/paper/{paper_id}" if paper_id else ""

                if not url:
                    continue

                authors = [a.get("name", "") for a in (paper.get("authors") or []) if a.get("name")]

                results.append(
                    RawSource(
                        url=url,
                        title=paper.get("title") or "",
                        snippet=paper.get("abstract") or "",
                        date=str(paper.get("year") or ""),
                        doi=doi,
                        authors=authors,
                        venue=paper.get("venue") or "",
                        citation_count=paper.get("citationCount") or 0,
                        source_api=self.name,
                        default_tier=self.default_tier,
                    )
                )
            return results

        try:
            return await asyncio.to_thread(_do)
        except Exception as exc:
            logger.warning("Semantic Scholar search failed for '%s': %s", query, exc)
            return []


class OpenAlexAdapter(SourceAdapter):
    """OpenAlex API — $1/day free with key, full-text search, sorted by impact.

    Follows the LLM quick reference at developers.openalex.org/guides/llm-quick-reference:
    - Uses api_key param (not just mailto) for $1/day free credit
    - Uses search= for full-text across title/abstract/fulltext
    - Sorts by cited_by_count:desc for highest-impact papers first
    - Filters out paratext (editorials, TOCs, etc.)
    - Exponential backoff on 429/500
    """

    @property
    def name(self) -> str:
        return "openalex"

    @property
    def default_tier(self) -> int:
        return 1

    def __init__(self) -> None:
        self._api_key = os.getenv("THEO_OPENALEX_KEY", "")
        self._email = os.getenv("THEO_OPENALEX_EMAIL", "")
        self._client = httpx.Client(
            base_url="https://api.openalex.org",
            headers={"Accept": "application/json"},
            timeout=30.0,  # OpenAlex recommends 30s timeout
        )

    def _request_with_retry(self, params: dict) -> dict:
        """GET /works with exponential backoff on 429/500."""
        import time as _time

        for attempt in range(4):  # initial + 3 retries
            resp = self._client.get("/works", params=params)
            if resp.status_code in (429, 500, 503):
                wait = 2 ** attempt  # 1, 2, 4 seconds
                logger.info("OpenAlex %d, retrying in %ds...", resp.status_code, wait)
                _time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        # Final attempt — let it raise
        resp = self._client.get("/works", params=params)
        resp.raise_for_status()
        return resp.json()

    async def search(self, query: str, max_results: int = 10) -> list[RawSource]:
        def _do() -> list[RawSource]:
            params: dict[str, str] = {
                "search": query,
                "filter": "type:!paratext",
                "select": "id,title,doi,publication_date,cited_by_count,authorships,primary_location,abstract_inverted_index,open_access",
                "sort": "cited_by_count:desc",
                "per_page": str(min(max_results, 100)),
            }
            # api_key gives $1/day free; mailto gives polite pool only
            if self._api_key:
                params["api_key"] = self._api_key
            if self._email:
                params["mailto"] = self._email

            data = self._request_with_retry(params)

            results: list[RawSource] = []
            for work in data.get("results", []):
                doi = (work.get("doi") or "").removeprefix("https://doi.org/")
                url = work.get("doi") or work.get("id") or ""
                if not url:
                    continue

                title = work.get("title") or ""
                snippet = _reconstruct_abstract(work.get("abstract_inverted_index") or {})
                date = work.get("publication_date") or ""

                authors = []
                for authorship in work.get("authorships") or []:
                    author_obj = authorship.get("author") or {}
                    aname = author_obj.get("display_name", "")
                    if aname:
                        authors.append(aname)

                venue = ""
                loc = work.get("primary_location") or {}
                source_obj = loc.get("source") or {}
                if source_obj.get("display_name"):
                    venue = source_obj["display_name"]

                results.append(
                    RawSource(
                        url=url,
                        title=title,
                        snippet=snippet,
                        date=date,
                        doi=doi,
                        authors=authors,
                        venue=venue,
                        citation_count=work.get("cited_by_count") or 0,
                        source_api=self.name,
                        default_tier=self.default_tier,
                    )
                )
            return results

        try:
            return await asyncio.to_thread(_do)
        except Exception as exc:
            logger.warning("OpenAlex search failed for '%s': %s", query, exc)
            return []


class CrossrefAdapter(SourceAdapter):
    """Crossref API — free, polite pool via mailto."""

    @property
    def name(self) -> str:
        return "crossref"

    @property
    def default_tier(self) -> int:
        return 1

    def __init__(self) -> None:
        email = os.getenv("THEO_CROSSREF_EMAIL", "")
        headers: dict[str, str] = {"Accept": "application/json"}
        if email:
            headers["User-Agent"] = f"AncientMap/1.0 (mailto:{email})"
        self._client = httpx.Client(
            base_url="https://api.crossref.org",
            headers=headers,
            timeout=_API_TIMEOUT,
        )

    async def search(self, query: str, max_results: int = 10) -> list[RawSource]:
        def _do() -> list[RawSource]:
            resp = self._client.get(
                "/works",
                params={
                    "query": query,
                    "rows": str(max_results),
                    "select": "DOI,title,author,container-title,published,abstract,is-referenced-by-count",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            results: list[RawSource] = []
            for item in data.get("message", {}).get("items", []):
                doi = item.get("DOI") or ""
                url = f"https://doi.org/{doi}" if doi else ""
                if not url:
                    continue

                titles = item.get("title") or []
                title = titles[0] if titles else ""

                abstract = _strip_html(item.get("abstract") or "")

                authors = []
                for author in item.get("author") or []:
                    parts = []
                    if author.get("given"):
                        parts.append(author["given"])
                    if author.get("family"):
                        parts.append(author["family"])
                    if parts:
                        authors.append(" ".join(parts))

                venue_list = item.get("container-title") or []
                venue = venue_list[0] if venue_list else ""

                date = ""
                published = item.get("published") or {}
                date_parts = published.get("date-parts") or []
                if date_parts and date_parts[0]:
                    date = "-".join(str(p) for p in date_parts[0])

                results.append(
                    RawSource(
                        url=url,
                        title=title,
                        snippet=abstract,
                        date=date,
                        doi=doi,
                        authors=authors,
                        venue=venue,
                        citation_count=item.get("is-referenced-by-count") or 0,
                        source_api=self.name,
                        default_tier=self.default_tier,
                    )
                )
            return results

        try:
            return await asyncio.to_thread(_do)
        except Exception as exc:
            logger.warning("Crossref search failed for '%s': %s", query, exc)
            return []


class CoreAdapter(SourceAdapter):
    """CORE API — requires API key."""

    @property
    def name(self) -> str:
        return "core"

    @property
    def default_tier(self) -> int:
        return 1

    def __init__(self, api_key: str) -> None:
        self._client = httpx.Client(
            base_url="https://api.core.ac.uk/v3",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
            timeout=_API_TIMEOUT,
        )

    async def search(self, query: str, max_results: int = 10) -> list[RawSource]:
        def _do() -> list[RawSource]:
            resp = self._client.get(
                "/search/works/",
                params={"q": query, "limit": str(max_results)},
            )
            resp.raise_for_status()
            data = resp.json()

            results: list[RawSource] = []
            for item in data.get("results", []):
                url = item.get("downloadUrl") or ""
                if not url:
                    urls = item.get("sourceFulltextUrls") or []
                    url = urls[0] if urls else ""
                if not url:
                    continue

                authors = [a.get("name", "") for a in (item.get("authors") or []) if a.get("name")]

                results.append(
                    RawSource(
                        url=url,
                        title=item.get("title") or "",
                        snippet=item.get("abstract") or "",
                        doi=item.get("doi") or "",
                        authors=authors,
                        source_api=self.name,
                        default_tier=self.default_tier,
                    )
                )
            return results

        try:
            return await asyncio.to_thread(_do)
        except Exception as exc:
            logger.warning("CORE search failed for '%s': %s", query, exc)
            return []


class EuropeanaAdapter(SourceAdapter):
    """Europeana API — requires API key (wskey)."""

    @property
    def name(self) -> str:
        return "europeana"

    @property
    def default_tier(self) -> int:
        return 2

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = httpx.Client(
            base_url="https://api.europeana.eu/record/v2",
            headers={"Accept": "application/json"},
            timeout=_API_TIMEOUT,
        )

    async def search(self, query: str, max_results: int = 10) -> list[RawSource]:
        def _do() -> list[RawSource]:
            resp = self._client.get(
                "/search.json",
                params={
                    "query": query,
                    "rows": str(max_results),
                    "wskey": self._api_key,
                    "profile": "standard",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            results: list[RawSource] = []
            for item in data.get("items", []):
                url_list = item.get("edmIsShownAt") or []
                url = url_list[0] if url_list else ""
                if not url:
                    continue

                title_list = item.get("dcTitle") or item.get("title") or []
                if isinstance(title_list, dict):
                    title_list = list(title_list.values())
                    title_list = title_list[0] if title_list else []
                title = (
                    title_list[0]
                    if isinstance(title_list, list) and title_list
                    else str(title_list)
                    if title_list
                    else ""
                )

                desc_list = item.get("dcDescription") or []
                if isinstance(desc_list, dict):
                    desc_list = list(desc_list.values())
                    desc_list = desc_list[0] if desc_list else []
                snippet = (
                    desc_list[0]
                    if isinstance(desc_list, list) and desc_list
                    else str(desc_list)
                    if desc_list
                    else ""
                )

                date_list = item.get("dcDate") or []
                if isinstance(date_list, list) and date_list:
                    date = str(date_list[0])
                else:
                    date = str(date_list) if date_list else ""

                creators = item.get("dcCreator") or []
                if isinstance(creators, dict):
                    creators = list(creators.values())
                    creators = creators[0] if creators else []
                authors = (
                    list(creators)
                    if isinstance(creators, list)
                    else [str(creators)]
                    if creators
                    else []
                )

                venue_list = item.get("dataProvider") or []
                venue = (
                    venue_list[0]
                    if isinstance(venue_list, list) and venue_list
                    else str(venue_list)
                    if venue_list
                    else ""
                )

                results.append(
                    RawSource(
                        url=url,
                        title=title,
                        snippet=snippet,
                        date=date,
                        authors=authors,
                        venue=venue,
                        source_api=self.name,
                        default_tier=self.default_tier,
                    )
                )
            return results

        try:
            return await asyncio.to_thread(_do)
        except Exception as exc:
            logger.warning("Europeana search failed for '%s': %s", query, exc)
            return []


class SmithsonianAdapter(SourceAdapter):
    """Smithsonian Open Access API — requires API key."""

    @property
    def name(self) -> str:
        return "smithsonian"

    @property
    def default_tier(self) -> int:
        return 2

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = httpx.Client(
            base_url="https://api.si.edu/openaccess/api/v1.0",
            headers={"Accept": "application/json"},
            timeout=_API_TIMEOUT,
        )

    async def search(self, query: str, max_results: int = 10) -> list[RawSource]:
        def _do() -> list[RawSource]:
            resp = self._client.get(
                "/search",
                params={
                    "q": query,
                    "rows": str(max_results),
                    "api_key": self._api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            results: list[RawSource] = []
            for row in data.get("response", {}).get("rows", []):
                content = row.get("content") or {}
                desc_nr = content.get("descriptiveNonRepeating") or {}

                title_obj = desc_nr.get("title") or {}
                title = (
                    title_obj.get("content") or title_obj
                    if isinstance(title_obj, str)
                    else str(title_obj.get("content", ""))
                )

                url = desc_nr.get("record_link") or ""
                if not url:
                    continue

                # Build snippet from freetext notes
                freetext = content.get("freetext") or {}
                notes = freetext.get("notes") or []
                snippet_parts = []
                for note in notes if isinstance(notes, list) else [notes]:
                    if isinstance(note, dict):
                        snippet_parts.append(note.get("content", ""))
                    elif isinstance(note, str):
                        snippet_parts.append(note)
                snippet = " ".join(snippet_parts)[:500]

                results.append(
                    RawSource(
                        url=url,
                        title=title,
                        snippet=snippet,
                        source_api=self.name,
                        default_tier=self.default_tier,
                    )
                )
            return results

        try:
            return await asyncio.to_thread(_do)
        except Exception as exc:
            logger.warning("Smithsonian search failed for '%s': %s", query, exc)
            return []


class WikipediaAdapter(SourceAdapter):
    """Wikipedia search API — no key needed."""

    @property
    def name(self) -> str:
        return "wikipedia"

    @property
    def default_tier(self) -> int:
        return 2

    def __init__(self) -> None:
        self._client = httpx.Client(
            base_url="https://en.wikipedia.org/w",
            headers={
                "Accept": "application/json",
                "User-Agent": "AncientNerdsTheo/1.0 (https://ancientnerds.com; research pipeline)",
            },
            timeout=_API_TIMEOUT,
        )

    async def search(self, query: str, max_results: int = 5) -> list[RawSource]:
        def _do() -> list[RawSource]:
            resp = self._client.get(
                "/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": str(max_results),
                    "format": "json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            results: list[RawSource] = []
            for item in data.get("query", {}).get("search", []):
                title = item.get("title") or ""
                url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                snippet = _strip_html(item.get("snippet") or "")

                results.append(
                    RawSource(
                        url=url,
                        title=title,
                        snippet=snippet,
                        source_api=self.name,
                        default_tier=self.default_tier,
                    )
                )
            return results

        try:
            return await asyncio.to_thread(_do)
        except Exception as exc:
            logger.warning("Wikipedia search failed for '%s': %s", query, exc)
            return []


class InternetArchiveAdapter(SourceAdapter):
    """Internet Archive search API — no key needed."""

    @property
    def name(self) -> str:
        return "internet_archive"

    @property
    def default_tier(self) -> int:
        return 2

    def __init__(self) -> None:
        self._client = httpx.Client(
            base_url="https://archive.org",
            headers={"Accept": "application/json"},
            timeout=_API_TIMEOUT,
        )

    async def search(self, query: str, max_results: int = 10) -> list[RawSource]:
        def _do() -> list[RawSource]:
            resp = self._client.get(
                "/advancedsearch.php",
                params={
                    "q": query,
                    "output": "json",
                    "rows": str(max_results),
                    "fl[]": "identifier,title,description,date,creator",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            results: list[RawSource] = []
            for doc in data.get("response", {}).get("docs", []):
                identifier = doc.get("identifier") or ""
                if not identifier:
                    continue

                url = f"https://archive.org/details/{identifier}"
                title = doc.get("title") or ""
                snippet = doc.get("description") or ""
                if isinstance(snippet, list):
                    snippet = " ".join(snippet)
                date = doc.get("date") or ""

                creator = doc.get("creator") or []
                if isinstance(creator, str):
                    authors = [creator]
                elif isinstance(creator, list):
                    authors = list(creator)
                else:
                    authors = []

                results.append(
                    RawSource(
                        url=url,
                        title=title,
                        snippet=snippet[:500],
                        date=date,
                        authors=authors,
                        source_api=self.name,
                        default_tier=self.default_tier,
                    )
                )
            return results

        try:
            return await asyncio.to_thread(_do)
        except Exception as exc:
            logger.warning("Internet Archive search failed for '%s': %s", query, exc)
            return []


class MiniMaxSearchAdapter(SourceAdapter):
    """MiniMax web search — reuses minimax_shared.py."""

    @property
    def name(self) -> str:
        return "minimax"

    @property
    def default_tier(self) -> int:
        return 3

    def __init__(self, settings: LyraSettings) -> None:
        self._client = create_minimax_client(
            settings.minimax_base_url,
            settings.minimax_api_key,
        )

    async def search(self, query: str, max_results: int = 10) -> list[RawSource]:
        def _do() -> list[RawSource]:
            ws_results: list[WebSearchResult] = minimax_search(self._client, query)
            return [
                RawSource(
                    url=r.url,
                    title=r.title,
                    snippet=r.snippet,
                    date=r.date,
                    source_api=self.name,
                    default_tier=self.default_tier,
                )
                for r in ws_results[:max_results]
                if r.url
            ]

        try:
            return await asyncio.to_thread(_do)
        except Exception as exc:
            logger.warning("MiniMax search failed for '%s': %s", query, exc)
            return []


# ---------------------------------------------------------------------------
# Internal database adapter — search our own unified_sites
# ---------------------------------------------------------------------------


class UnifiedSitesAdapter(SourceAdapter):
    """Search the AncientNerds unified_sites database for matching sites.

    Reuses the same search_sites() function that Lyra chat uses — same
    ILIKE matching, source priority ordering, and deduplication.
    """

    @property
    def name(self) -> str:
        return "ancientnerds_db"

    @property
    def default_tier(self) -> int:
        return 1  # Our own curated data

    async def search(self, query: str, max_results: int = 10) -> list[RawSource]:
        def _do() -> list[RawSource]:
            import json as _json

            from api.services.lyra_tools import search_sites

            # search_sites is a LangChain @tool — use .invoke()
            raw_json = search_sites.invoke({"query": query, "limit": min(max_results, 25)})
            if raw_json.startswith("No sites found"):
                return []

            sites = _json.loads(raw_json)
            results: list[RawSource] = []
            for site in sites:
                snippet_parts = []
                if site.get("description"):
                    snippet_parts.append(site["description"])
                if site.get("period"):
                    snippet_parts.append(f"Period: {site['period']}")
                if site.get("country"):
                    snippet_parts.append(f"Country: {site['country']}")
                if site.get("type"):
                    snippet_parts.append(f"Type: {site['type']}")
                snippet = ". ".join(snippet_parts) if snippet_parts else site.get("name", "")

                url = f"https://ancientnerds.com/?site={site['name'].replace(' ', '+')}"

                results.append(
                    RawSource(
                        url=url,
                        title=f"{site['name']} (AncientNerds Database)",
                        snippet=snippet,
                        source_api=self.name,
                        default_tier=self.default_tier,
                    )
                )
            return results

        try:
            return await asyncio.to_thread(_do)
        except Exception as exc:
            logger.warning("UnifiedSites DB search failed for '%s': %s", query, exc)
            return []


# ---------------------------------------------------------------------------
# Unpaywall enricher (post-search, not a search adapter)
# ---------------------------------------------------------------------------


async def enrich_with_unpaywall(sources: list[RawSource]) -> None:
    """For sources with a DOI, check Unpaywall for free PDF availability.

    Modifies sources in-place: sets url to the OA PDF if found and the
    current url is just a doi.org redirect.
    """
    email = os.getenv("THEO_UNPAYWALL_EMAIL", "")
    if not email:
        return

    client = httpx.Client(
        base_url="https://api.unpaywall.org/v2",
        headers={"Accept": "application/json"},
        timeout=_API_TIMEOUT,
    )

    def _enrich_one(source: RawSource) -> None:
        if not source.doi:
            return
        try:
            resp = client.get(f"/{source.doi}", params={"email": email})
            resp.raise_for_status()
            data = resp.json()
            best_oa = data.get("best_oa_location") or {}
            oa_url = best_oa.get("url_for_pdf") or best_oa.get("url") or ""
            if oa_url and source.url.startswith("https://doi.org/"):
                source.url = oa_url
        except Exception as exc:
            logger.debug("Unpaywall lookup failed for DOI %s: %s", source.doi, exc)

    doi_sources = [s for s in sources if s.doi]
    if not doi_sources:
        return

    try:
        await asyncio.gather(*[asyncio.to_thread(_enrich_one, s) for s in doi_sources])
    except Exception as exc:
        logger.warning("Unpaywall enrichment failed: %s", exc)
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class MultiSourceSearch:
    """Orchestrates parallel searches across multiple APIs."""

    def __init__(self, settings: LyraSettings) -> None:
        self._settings = settings
        self._adapters: dict[str, SourceAdapter] = {}
        self._init_adapters()

    def _init_adapters(self) -> None:
        """Initialize all available adapters based on which API keys are set."""
        # Always available (no key required, or key is optional)
        self._adapters["ancientnerds_db"] = UnifiedSitesAdapter()
        self._adapters["semantic_scholar"] = SemanticScholarAdapter()
        self._adapters["openalex"] = OpenAlexAdapter()
        self._adapters["crossref"] = CrossrefAdapter()
        self._adapters["wikipedia"] = WikipediaAdapter()
        self._adapters["internet_archive"] = InternetArchiveAdapter()

        # MiniMax — requires key from LyraSettings
        if self._settings.minimax_api_key:
            self._adapters["minimax"] = MiniMaxSearchAdapter(self._settings)

        # Key-gated adapters
        core_key = os.getenv("THEO_CORE_KEY", "")
        if core_key:
            self._adapters["core"] = CoreAdapter(core_key)

        europeana_key = os.getenv("THEO_EUROPEANA_KEY", "")
        if europeana_key:
            self._adapters["europeana"] = EuropeanaAdapter(europeana_key)

        smithsonian_key = os.getenv("THEO_SMITHSONIAN_KEY", "")
        if smithsonian_key:
            self._adapters["smithsonian"] = SmithsonianAdapter(smithsonian_key)

        available = list(self._adapters.keys())
        logger.info("MultiSourceSearch initialized with %d adapters: %s", len(available), available)

    async def search(
        self,
        queries: list[str],
        source_group: str,
    ) -> list[RawSource]:
        """Run searches across APIs appropriate for the source_group.

        source_group values (from TierConfig.source_apis):
        - "minimal": AncientNerds DB + Semantic Scholar + MiniMax
        - "standard": + OpenAlex + Wikipedia + Crossref
        - "full": + CORE + Europeana + Smithsonian
        - "exhaustive": all sources + Internet Archive + Unpaywall enrichment

        Returns deduplicated list of RawSource, sorted by default_tier then citation_count.
        """
        # 1. Determine which adapters to use
        wanted_names = SOURCE_GROUPS.get(source_group, SOURCE_GROUPS["minimal"])
        active_adapters = [self._adapters[name] for name in wanted_names if name in self._adapters]

        if not active_adapters:
            logger.warning("No adapters available for source_group '%s'", source_group)
            return []

        # 2. For each query, run all selected adapters in parallel
        all_tasks = []
        for query in queries:
            for adapter in active_adapters:
                all_tasks.append(adapter.search(query))

        all_results: list[list[RawSource]] = await asyncio.gather(*all_tasks)

        # 3. Flatten
        flat: list[RawSource] = []
        for result_list in all_results:
            flat.extend(result_list)

        # 4. Filter blocked domains
        filtered = [r for r in flat if not _is_blocked(r.url)]

        # 5. Deduplicate by URL (keep first seen)
        seen_urls: set[str] = set()
        url_deduped: list[RawSource] = []
        for r in filtered:
            normalized_url = r.url.rstrip("/")
            if normalized_url not in seen_urls:
                seen_urls.add(normalized_url)
                url_deduped.append(r)

        # 6. Deduplicate by DOI (prefer higher-tier source)
        doi_best: dict[str, RawSource] = {}
        no_doi: list[RawSource] = []
        for r in url_deduped:
            if r.doi:
                doi_lower = r.doi.lower()
                existing = doi_best.get(doi_lower)
                if existing is None:
                    doi_best[doi_lower] = r
                elif r.default_tier < existing.default_tier:
                    # Lower tier number = higher quality
                    doi_best[doi_lower] = r
                elif (
                    r.default_tier == existing.default_tier
                    and r.citation_count > existing.citation_count
                ):
                    doi_best[doi_lower] = r
            else:
                no_doi.append(r)

        deduped = list(doi_best.values()) + no_doi

        # 7. Unpaywall enrichment for exhaustive searches
        if source_group == "exhaustive":
            await enrich_with_unpaywall(deduped)

        # 8. Sort: tier 1 first, then tier 2, then tier 3.
        #    Within each tier, sort by citation_count descending.
        deduped.sort(key=lambda r: (r.default_tier, -r.citation_count))

        logger.info(
            "MultiSourceSearch: %d queries x %d adapters -> %d raw -> %d after dedup (group=%s)",
            len(queries),
            len(active_adapters),
            len(flat),
            len(deduped),
            source_group,
        )

        return deduped
