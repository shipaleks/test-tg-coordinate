"""Yandex Search API client for image search.

This module integrates with Yandex Cloud Search API to fetch relevant images
for a given text query. It is designed to be used as the primary image source
with Wikimedia Commons as a fallback.

Environment variables required:
  - YANDEX_API_KEY: API key for Yandex Cloud Search API (Authorization: Api-Key ...)
  - YANDEX_FOLDER_ID: Folder ID in Yandex Cloud (e.g., b1gXXXXXXXX)
  - YANDEX_SEARCH_REGION: Optional numeric region code (213=Moscow, 2=SPb, 225=RU)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from typing import Dict, List, Optional

import aiohttp


logger = logging.getLogger(__name__)


class YandexImageSearch:
    """Minimal async client for Yandex Cloud Search API image search.

    Notes:
        - The actual response schema may evolve. This client parses conservatively
          and ignores unknown structures, returning an empty list on errors.
        - All network operations have short timeouts and raise on ClientError; callers
          should handle exceptions and provide fallbacks.
    """

    BASE_URL = "https://searchapi.api.cloud.yandex.net/v2/image/search"

    def __init__(self, api_key: str, folder_id: str):
        self.api_key = api_key
        self.folder_id = folder_id
        self.session: Optional[aiohttp.ClientSession] = None
        # Simple in-memory cache to reduce API usage and latency
        self._cache: Dict[str, Dict] = {}
        self._cache_ttl_seconds: int = 3600

    async def __aenter__(self) -> "YandexImageSearch":
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.session:
            await self.session.close()

    def _cache_key(self, query: str, region: Optional[int]) -> str:
        return hashlib.md5(f"{query}|{region}".encode("utf-8")).hexdigest()

    def _cache_get(self, key: str) -> Optional[List[str]]:
        entry = self._cache.get(key)
        if not entry:
            return None
        if time.time() - entry["ts"] > self._cache_ttl_seconds:
            # Expired
            try:
                del self._cache[key]
            except KeyError:
                pass
            return None
        return entry["images"].copy()

    def _cache_set(self, key: str, images: List[str]) -> None:
        self._cache[key] = {"ts": time.time(), "images": images[:20]}

    async def search_images(
        self,
        query: str,
        max_images: int = 8,
        *,
        region: Optional[int] = None,
        safe_mode: bool = True,
    ) -> List[str]:
        """Search for images using Yandex Cloud Search API.

        Args:
            query: Text query in any language.
            max_images: Max number of image URLs to return (1-20).
            region: Optional region code (213=Moscow, 2=SPb, 225=Russia).
            safe_mode: If True, enable moderate filtering.

        Returns:
            List of direct image URLs (best-effort).
        """
        if not self.session:
            raise RuntimeError("YandexImageSearch must be used as an async context manager")

        max_images = max(1, min(max_images, 20))
        cache_key = self._cache_key(query, region)
        cached = self._cache_get(cache_key)
        if cached:
            logger.debug("YandexImageSearch: returning cached results for '%s'", query)
            return cached[:max_images]

        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json",
        }

        # The public docs indicate folderId + query settings in JSON body.
        # We keep the payload lean and schema-tolerant.
        payload: Dict = {
            "folderId": self.folder_id,
            # Some public examples use "text"; others nest under "query".
            # Send both for compatibility; the backend ignores unknown fields.
            "text": query,
            "query": {
                "text": query,
                # Do not send familyMode; API rejects string enum values here in prod
                "page": 0,
            },
        }
        if region is not None:
            payload["query"]["region"] = region

        timeout = aiohttp.ClientTimeout(total=10)
        try:
            async with self.session.post(self.BASE_URL, headers=headers, json=payload, timeout=timeout) as resp:
                # Accept JSON primarily; some deployments may return XML/HTML on error
                content_type = resp.headers.get("Content-Type", "")
                if resp.status != 200:
                    text = await resp.text()
                    raise aiohttp.ClientResponseError(
                        resp.request_info,
                        resp.history,
                        status=resp.status,
                        message=f"Unexpected status {resp.status}; body: {text[:200]}",
                        headers=resp.headers,
                    )
                if "application/json" in content_type:
                    data = await resp.json()
                else:
                    # Best-effort: try JSON first anyway
                    try:
                        data = await resp.json()
                    except Exception:
                        # Fallback to text, return no images
                        logger.warning("YandexImageSearch: non-JSON response: %s", content_type)
                        return []
        except aiohttp.ClientError as e:
            logger.warning("YandexImageSearch request failed: %s", e)
            return []

        images = self._extract_images(data, max_images)
        if images:
            self._cache_set(cache_key, images)
        return images[:max_images]

    def _extract_images(self, data: Dict, max_images: int) -> List[str]:
        """Extract image URLs from API response with defensive parsing."""
        images: List[str] = []

        # Try common shapes observed in docs/snippets
        # 1) { "items": [ { "type": "IMAGE", "url": "...", "image": {"width":..} } ] }
        items = data.get("items")
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                if item_type and str(item_type).upper() != "IMAGE":
                    continue
                url = item.get("url") or item.get("image", {}).get("url")
                if not url:
                    continue
                if self._passes_basic_filters(item):
                    images.append(url)
                if len(images) >= max_images:
                    return images

        # 2) { "results": [ { "image": { "url": "..." } } ] }
        results = data.get("results")
        if isinstance(results, list) and len(images) < max_images:
            for item in results:
                if not isinstance(item, dict):
                    continue
                url = None
                img = item.get("image")
                if isinstance(img, dict):
                    url = img.get("url")
                if not url:
                    url = item.get("url")
                if not url:
                    continue
                if self._passes_basic_filters(item):
                    images.append(url)
                if len(images) >= max_images:
                    break

        # Deduplicate while preserving order
        deduped: List[str] = []
        seen = set()
        for u in images:
            if u and u not in seen:
                seen.add(u)
                deduped.append(u)
        return deduped

    def _passes_basic_filters(self, item: Dict) -> bool:
        """Filter out non-photo content heuristically."""
        snippet = item.get("snippet") or {}
        title = str(snippet.get("title", "")).lower()
        skip_tokens = (
            "logo",
            "иконка",
            "логотип",
            "map",
            "карта",
            "схема",
            "diagram",
            "banner",
            "баннер",
            "coat_of_arms",
            "emblem",
            "герб",
            "flag",
            "флаг",
        )
        if any(t in title for t in skip_tokens):
            return False

        image_meta = item.get("image") or {}
        width = int(image_meta.get("width", 0) or 0)
        height = int(image_meta.get("height", 0) or 0)
        if width and height and (width < 400 or height < 300):
            return False
        return True

    @staticmethod
    def detect_region(lat: Optional[float], lon: Optional[float]) -> Optional[int]:
        """Very rough region detection for better local relevance.

        Returns a Yandex region code or None.
        """
        if lat is None or lon is None:
            # Use default from env if provided
            try:
                value = os.getenv("YANDEX_SEARCH_REGION")
                return int(value) if value else None
            except Exception:
                return None

        # Simple bounding boxes for RU hubs
        try:
            if 55.3 <= lat <= 56.2 and 36.5 <= lon <= 38.3:
                return 213  # Moscow
            if 59.7 <= lat <= 60.3 and 29.6 <= lon <= 30.7:
                return 2  # Saint Petersburg
            # Russia general
            return 225
        except Exception:
            return None


