"""
Web Search Service using SearXNG (self-hosted).

Provides FREE FOREVER web search with no rate limits.
Falls back to Wikipedia API for knowledge queries.

Configuration:
    SEARXNG_URL: SearXNG server URL (default: http://localhost:8888)
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8888")


class WebSearchService:
    """Web search using self-hosted SearXNG + Wikipedia API fallback."""

    def __init__(self):
        self.searxng_url = SEARXNG_URL
        self.wikipedia_api = "https://en.wikipedia.org/api/rest_v1"
        self._searxng_available = None

    @property
    def is_searxng_available(self) -> bool:
        """Check if SearXNG is running."""
        if self._searxng_available is None:
            try:
                with httpx.Client(timeout=5) as client:
                    # SearXNG doesn't have /healthz, check root
                    response = client.get(f"{self.searxng_url}/")
                    self._searxng_available = response.status_code == 200
            except Exception:
                self._searxng_available = False
                logger.warning(f"SearXNG not available at {self.searxng_url}")
        return self._searxng_available

    async def search(
        self,
        query: str,
        max_results: int = 5,
        categories: str = "general",  # general, images, news, science
        language: str = "en"
    ) -> dict:
        """
        Search using SearXNG (aggregates 70+ engines).

        Returns:
            {
                "success": bool,
                "results": [{"title", "url", "content", "engine"}],
                "source": "searxng" | "wikipedia",
                "error": str or None
            }
        """
        # Try SearXNG first
        if self.is_searxng_available:
            result = await self._search_searxng(query, max_results, categories, language)
            if result["success"]:
                return result

        # Fallback to Wikipedia for knowledge queries
        return await self._search_wikipedia(query, max_results)

    async def _search_searxng(
        self,
        query: str,
        max_results: int,
        categories: str,
        language: str
    ) -> dict:
        """Search using SearXNG."""
        params = {
            "q": query,
            "format": "json",
            "categories": categories,
            "language": language,
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.searxng_url}/search",
                    params=params
                )
                response.raise_for_status()

                data = response.json()
                results = data.get("results", [])[:max_results]

                return {
                    "success": True,
                    "results": [
                        {
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "content": r.get("content", "")[:500],
                            "engine": r.get("engine", "unknown")
                        }
                        for r in results
                    ],
                    "source": "searxng",
                    "error": None
                }

        except httpx.TimeoutException:
            logger.error("SearXNG search timed out")
            return {"success": False, "results": [], "source": "searxng", "error": "Search timed out"}
        except Exception as e:
            logger.error(f"SearXNG error: {e}")
            return {"success": False, "results": [], "source": "searxng", "error": str(e)}

    async def _search_wikipedia(self, query: str, max_results: int = 3) -> dict:
        """
        Fallback search using Wikipedia API.
        FREE FOREVER with 200 req/s limit.
        """
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                # First, search for articles
                search_url = f"{self.wikipedia_api}/page/related/{query.replace(' ', '_')}"

                # Try direct page summary first
                summary_url = f"{self.wikipedia_api}/page/summary/{query.replace(' ', '_')}"
                response = await client.get(summary_url)

                results = []

                if response.status_code == 200:
                    data = response.json()
                    results.append({
                        "title": data.get("title", query),
                        "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                        "content": data.get("extract", "")[:500],
                        "engine": "wikipedia"
                    })

                # Also try search endpoint
                search_url = "https://en.wikipedia.org/w/api.php"
                search_params = {
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "format": "json",
                    "srlimit": max_results
                }
                search_response = await client.get(search_url, params=search_params)

                if search_response.status_code == 200:
                    search_data = search_response.json()
                    for item in search_data.get("query", {}).get("search", []):
                        if len(results) >= max_results:
                            break
                        # Skip if we already have this article
                        if any(r["title"] == item["title"] for r in results):
                            continue
                        results.append({
                            "title": item.get("title", ""),
                            "url": f"https://en.wikipedia.org/wiki/{item.get('title', '').replace(' ', '_')}",
                            "content": item.get("snippet", "").replace("<span class=\"searchmatch\">", "").replace("</span>", "")[:500],
                            "engine": "wikipedia"
                        })

                return {
                    "success": len(results) > 0,
                    "results": results[:max_results],
                    "source": "wikipedia",
                    "error": None if results else "No results found"
                }

        except Exception as e:
            logger.error(f"Wikipedia search error: {e}")
            return {"success": False, "results": [], "source": "wikipedia", "error": str(e)}

    async def search_archaeology(self, query: str, max_results: int = 3) -> dict:
        """Search with archaeology context."""
        enhanced_query = f"archaeology ancient history {query}"
        return await self.search(enhanced_query, max_results, categories="science")

    def format_for_context(self, results: list[dict], max_chars: int = 1500) -> str:
        """Format results for LLM context."""
        if not results:
            return ""

        lines = ["WEB SEARCH RESULTS:", "---"]
        char_count = 0

        for r in results:
            entry = f"- {r['title']}\n  {r['content']}\n  Source: {r['url']}\n"
            if char_count + len(entry) > max_chars:
                break
            lines.append(entry)
            char_count += len(entry)

        return "\n".join(lines)

    def health_check(self) -> dict:
        """Check web search service health."""
        return {
            "searxng_available": self.is_searxng_available,
            "searxng_url": self.searxng_url,
            "wikipedia_available": True,  # Always available
            "status": "healthy" if self.is_searxng_available else "degraded"
        }


# Singleton
_instance: WebSearchService | None = None


def get_web_search_service() -> WebSearchService:
    """Get singleton WebSearchService instance."""
    global _instance
    if _instance is None:
        _instance = WebSearchService()
    return _instance
