"""Web search service using Brave Search API with Yandex fallback."""

import logging
import os
from typing import Any

import httpx

from .yandex_web_search import YandexWebSearch

logger = logging.getLogger(__name__)


class WebSearchService:
    """Web search using Brave Search API.

    Brave Search API provides high-quality web search results.
    Free tier: 2000 queries/month.

    Get API key at: https://brave.com/search/api/
    """

    BASE_URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str | None = None):
        """Initialize web search service.

        Args:
            api_key: Brave Search API key. If None, uses BRAVE_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("BRAVE_API_KEY")
        if not self.api_key:
            logger.warning("BRAVE_API_KEY not set - web search will be unavailable")

        # Initialize Yandex as fallback (will auto-disable if not configured)
        self._yandex_fallback: YandexWebSearch | None = None
        try:
            self._yandex_fallback = YandexWebSearch()
            if self._yandex_fallback.enabled:
                logger.info("Yandex Web Search initialized as fallback")
        except Exception as e:
            logger.debug(f"Yandex fallback not available: {e}")

    async def search(
        self,
        query: str,
        count: int = 5,
        freshness: str | None = None,
        country: str = "all",
    ) -> list[dict[str, Any]]:
        """Perform web search.

        Args:
            query: Search query string
            count: Number of results (1-20)
            freshness: Time filter - "pd" (past day), "pw" (past week),
                      "pm" (past month), "py" (past year), or None
            country: Country code for localized results (e.g., "RU", "FR", "US")

        Returns:
            List of search results with keys: title, url, description, age
        """
        if not self.api_key:
            logger.warning("Web search unavailable - no API key")
            return []

        try:
            params = {
                "q": query,
                "count": min(count, 20),
                "text_decorations": False,
                "search_lang": "en",
            }

            if freshness:
                params["freshness"] = freshness
            if country and country != "all":
                params["country"] = country

            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": self.api_key,
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    self.BASE_URL,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

            results = []
            web_results = data.get("web", {}).get("results", [])

            for item in web_results[:count]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "description": item.get("description", ""),
                    "age": item.get("age", ""),
                    "language": item.get("language", ""),
                })

            logger.info(f"Web search for '{query}' returned {len(results)} results")
            return results

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            logger.error(f"Web search HTTP error: {status_code} - {e}")

            # Try Yandex fallback on rate limit (429)
            if status_code == 429 and self._yandex_fallback and self._yandex_fallback.enabled:
                logger.warning(f"Brave Search rate limited (429), trying Yandex fallback for '{query}'")
                try:
                    async with self._yandex_fallback as yandex:
                        yandex_results = await yandex.search(query, count=count)
                        if yandex_results:
                            logger.info(f"Yandex fallback successful: {len(yandex_results)} results")
                            return yandex_results
                except Exception as yandex_error:
                    logger.error(f"Yandex fallback also failed: {yandex_error}")

            return []
        except httpx.TimeoutException:
            logger.error(f"Web search timeout for query: {query}")
            return []
        except Exception as e:
            logger.error(f"Web search error: {e}")
            return []

    async def search_for_coordinates(
        self,
        place_name: str,
        city: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search for place coordinates.

        Args:
            place_name: Name of the place
            city: Optional city name for context

        Returns:
            Search results focused on location/coordinates
        """
        query = f"{place_name} coordinates location"
        if city:
            query = f"{place_name} {city} coordinates"

        return await self.search(query, count=3)

    async def search_for_facts(
        self,
        place_name: str,
        lat: float,
        lon: float,
        language: str = "en",
    ) -> list[dict[str, Any]]:
        """Search for interesting facts about a place.

        Args:
            place_name: Name of the place
            lat: Latitude
            lon: Longitude
            language: Preferred language for results

        Returns:
            Search results about the place's history and facts
        """
        # Build search queries based on language
        queries = []

        if language == "ru":
            queries = [
                f"{place_name} история интересные факты",
                f"{place_name} достопримечательность",
            ]
        elif language == "fr":
            queries = [
                f"{place_name} histoire faits intéressants",
                f"{place_name} patrimoine",
            ]
        else:
            queries = [
                f"{place_name} history interesting facts",
                f"{place_name} landmark heritage",
            ]

        all_results = []
        for query in queries[:2]:  # Limit to 2 queries
            results = await self.search(query, count=3)
            all_results.extend(results)

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for r in all_results:
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                unique_results.append(r)

        return unique_results[:5]

    def format_results_for_prompt(self, results: list[dict[str, Any]]) -> str:
        """Format search results for inclusion in AI prompt.

        Args:
            results: List of search results

        Returns:
            Formatted string for prompt context
        """
        if not results:
            return "No web search results available."

        formatted = ["Web search results:"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "Untitled")
            url = r.get("url", "")
            desc = r.get("description", "")[:200]
            formatted.append(f"{i}. {title}")
            formatted.append(f"   URL: {url}")
            if desc:
                formatted.append(f"   {desc}")

        return "\n".join(formatted)


# Singleton instance
_web_search_service: WebSearchService | None = None


def get_web_search_service() -> WebSearchService:
    """Get or create the web search service singleton."""
    global _web_search_service
    if _web_search_service is None:
        _web_search_service = WebSearchService()
    return _web_search_service
