"""Yandex Cloud Search API client for web search (alternative to Brave Search).

This module provides web search functionality using Yandex Cloud Search API.
Can be used as a fallback when Brave Search returns 429 rate limit errors.

Environment variables required:
  - YANDEX_API_KEY: API key for Yandex Cloud Search API
  - YANDEX_FOLDER_ID: Folder ID in Yandex Cloud
"""

from __future__ import annotations

import hashlib
import logging
import os
import time

import aiohttp

logger = logging.getLogger(__name__)


class YandexWebSearch:
    """Async client for Yandex Cloud Search API web search."""

    # Try both v2 and v1 endpoints
    BASE_URLS = [
        "https://searchapi.api.cloud.yandex.net/v2/web/search",
        "https://searchapi.api.cloud.yandex.net/v1/web",
    ]

    def __init__(self, api_key: str | None = None, folder_id: str | None = None):
        """Initialize Yandex Web Search client.

        Args:
            api_key: Yandex Cloud API key (from env if not provided)
            folder_id: Yandex Cloud folder ID (from env if not provided)
        """
        self.api_key = api_key or os.getenv("YANDEX_API_KEY")
        self.folder_id = folder_id or os.getenv("YANDEX_FOLDER_ID")

        if not self.api_key or not self.folder_id:
            logger.warning(
                "Yandex Web Search not configured (missing API_KEY or FOLDER_ID)"
            )
            self.enabled = False
        else:
            self.enabled = True
            logger.info("Yandex Web Search initialized")

        self.session: aiohttp.ClientSession | None = None
        # Simple cache to reduce API calls
        self._cache: dict[str, dict] = {}
        self._cache_ttl_seconds: int = 1800  # 30 minutes

    async def __aenter__(self) -> YandexWebSearch:
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.session:
            await self.session.close()

    def _cache_key(self, query: str) -> str:
        return hashlib.md5(query.encode()).hexdigest()

    def _cache_get(self, key: str) -> list[dict] | None:
        entry = self._cache.get(key)
        if not entry:
            return None
        if time.time() - entry["ts"] > self._cache_ttl_seconds:
            try:
                del self._cache[key]
            except KeyError:
                pass
            return None
        return entry["results"].copy()

    def _cache_set(self, key: str, results: list[dict]) -> None:
        self._cache[key] = {"ts": time.time(), "results": results[:10]}

    async def search(self, query: str, count: int = 5) -> list[dict]:
        """Search for web pages using Yandex Cloud Search API.

        Args:
            query: Search query
            count: Max number of results (1-10)

        Returns:
            List of dicts with keys: title, url, snippet
        """
        if not self.enabled:
            logger.debug("Yandex Web Search not enabled, returning empty results")
            return []

        if not self.session:
            raise RuntimeError("YandexWebSearch must be used as async context manager")

        count = max(1, min(count, 10))
        cache_key = self._cache_key(query)
        cached = self._cache_get(cache_key)
        if cached:
            logger.debug(f"YandexWebSearch: returning cached results for '{query}'")
            return cached[:count]

        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json",
        }

        # Try different payload variants for web search
        payload_variants = [
            {
                "folderId": self.folder_id,
                "query": {
                    "query_text": query,
                    "search_type": "SEARCH_TYPE_WEB",
                    "page": 0,
                },
            },
            {
                "folderId": self.folder_id,
                "query": {
                    "queryText": query,
                    "searchType": "SEARCH_TYPE_WEB",
                    "page": 0,
                },
            },
            {
                "folderId": self.folder_id,
                "query": {
                    "query_text": query,
                    "search_type": 1,  # WEB=1, IMAGE=2
                    "page": 0,
                },
            },
        ]

        timeout = aiohttp.ClientTimeout(total=10)

        # Try each URL and payload variant
        for base_url in self.BASE_URLS:
            for variant in payload_variants:
                try:
                    async with self.session.post(
                        base_url, headers=headers, json=variant, timeout=timeout
                    ) as resp:
                        if resp.status != 200:
                            logger.debug(
                                f"Yandex Web Search: {base_url} returned {resp.status}"
                            )
                            continue

                        data = await resp.json()
                        results = self._parse_results(data)

                        if results:
                            logger.info(
                                f"Yandex Web Search: found {len(results)} results for '{query}'"
                            )
                            self._cache_set(cache_key, results)
                            return results[:count]

                except aiohttp.ClientError as e:
                    logger.debug(f"Yandex Web Search error: {e}")
                    continue
                except Exception as e:
                    logger.debug(f"Yandex Web Search unexpected error: {e}")
                    continue

        logger.warning(
            f"Yandex Web Search: no results for '{query}' (all attempts failed)"
        )
        return []

    def _parse_results(self, data: dict) -> list[dict]:
        """Parse Yandex API response to extract web results.

        Args:
            data: JSON response from Yandex API

        Returns:
            List of dicts with title, url, snippet
        """
        results = []

        try:
            # Try different response formats
            items = (
                data.get("searchResults", {}).get("grouping", [{}])[0].get("group", [])
                or data.get("results", [])
                or data.get("items", [])
            )

            for item in items[:10]:
                try:
                    # Extract doc/document
                    doc = item.get("doc") or item.get("document") or item

                    title = (
                        doc.get("title") or doc.get("snippet", {}).get("title") or ""
                    )
                    url = doc.get("url") or doc.get("link") or doc.get("href") or ""
                    snippet = (
                        doc.get("snippet", {}).get("text")
                        or doc.get("snippet")
                        or doc.get("description")
                        or ""
                    )

                    if title and url:
                        results.append(
                            {
                                "title": str(title)[:200],
                                "url": str(url),
                                "snippet": str(snippet)[:500] if snippet else "",
                            }
                        )

                except Exception as e:
                    logger.debug(f"Error parsing Yandex result item: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Error parsing Yandex search results: {e}")

        return results
