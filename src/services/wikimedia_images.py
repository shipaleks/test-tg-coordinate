"""Wikipedia/Wikimedia Commons image retrieval pipeline."""

import logging
import os
from urllib.parse import quote

import aiohttp

logger = logging.getLogger(__name__)


class WikimediaImagesMixin:
    """Wikimedia image-search methods mixed into ClaudeClient.

    Relies on caches initialized in ClaudeClient.__init__ (_qid_cache,
    _p18_cache, _fileinfo_cache, _image_cache_ttl_seconds).
    """

    async def get_wikipedia_images(
        self,
        search_keywords: str,
        max_images: int = 5,
        *,
        lat: float | None = None,
        lon: float | None = None,
        place_hint: str | None = None,
        sources: list[tuple[str, str]] | None = None,
        fact_text: str | None = None,
    ) -> list[str]:
        """Get images relevant to the fact.

        This method maintains backward compatibility while providing image search.
        """
        # Primary: Yandex Search API if credentials are configured
        try:
            yandex_api_key = os.getenv("YANDEX_API_KEY")
            yandex_folder_id = os.getenv("YANDEX_FOLDER_ID")
            if yandex_api_key and yandex_folder_id:
                logger.info(
                    f"Attempting Yandex image search for: {place_hint or search_keywords}"
                )
                from .yandex_image_search import YandexImageSearch

                async with YandexImageSearch(
                    yandex_api_key, yandex_folder_id
                ) as yandex:
                    base_query = (
                        place_hint or search_keywords or ""
                    ).strip() or search_keywords
                    variants = yandex.build_query_variants(
                        base_query=base_query,
                        fact_text=fact_text,
                        place_name=place_hint,
                    ) or [base_query]
                    region = YandexImageSearch.detect_region(lat, lon)

                    collected: list[str] = []
                    for q in variants:
                        images = await yandex.search_images(
                            query=q, max_images=max(2, max_images), region=region
                        )
                        if images:
                            for u in images:
                                if u not in collected:
                                    collected.append(u)
                        if len(collected) >= max_images:
                            break
                    if collected:
                        logger.info(f"Yandex returned {len(collected)} images")
                        return collected[:max_images]
        except Exception as e:
            logger.warning(f"Yandex image search failed: {e}")

        # Fallback to Wikipedia/Wikimedia Commons
        clean_keywords = (
            (search_keywords or "").replace(" + ", " ").replace("+", " ").strip()
        )

        if clean_keywords and lat is None and lon is None and not place_hint:
            try:
                quick = await self._search_wikipedia_images(
                    clean_keywords, "en", max_images
                )
                if quick:
                    return quick
            except Exception:
                pass

        # Try Wikimedia Commons geosearch if we have coordinates
        if lat is not None and lon is not None:
            try:
                results = await self._commons_geosearch(lat, lon, max_images)
                if results:
                    return results
            except Exception as e:
                logger.debug(f"Commons geosearch failed: {e}")

        # Final fallback to Wikipedia search
        if clean_keywords:
            for lang in ["en", "ru", "fr"]:
                try:
                    results = await self._search_wikipedia_images(
                        clean_keywords, lang, max_images
                    )
                    if results:
                        return results
                except Exception:
                    continue

        return []

    async def _commons_geosearch(
        self, lat: float, lon: float, max_images: int = 5
    ) -> list[str]:
        """Search Wikimedia Commons for images near coordinates."""
        url = "https://commons.wikimedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "geosearch",
            "gscoord": f"{lat}|{lon}",
            "gsradius": 500,
            "gslimit": max_images * 2,
            "format": "json",
        }
        headers = {"User-Agent": "BotVoyage/2.0 (Educational Project)"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, params=params, headers=headers, timeout=5
                ) as response:
                    if response.status != 200:
                        return []
                    data = await response.json()

                    results = []
                    for item in data.get("query", {}).get("geosearch", []):
                        title = item.get("title", "")
                        if title.startswith("File:"):
                            filename = title[5:]
                            image_url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(filename)}?width=800"
                            results.append(image_url)
                            if len(results) >= max_images:
                                break

                    return results
        except Exception as e:
            logger.debug(f"Commons geosearch error: {e}")
            return []

    async def _search_wikipedia_images(
        self, search_term: str, lang: str, max_images: int = 5
    ) -> list[str]:
        """Search for images on Wikipedia."""
        try:
            search_url = f"https://{lang}.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "list": "search",
                "srsearch": search_term,
                "format": "json",
            }
            headers = {"User-Agent": "BotVoyage/2.0 (Educational Project)"}

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    search_url, params=params, headers=headers, timeout=5
                ) as response:
                    if response.status != 200:
                        return []

                    search_data = await response.json()
                    search_results = search_data.get("query", {}).get("search", [])

                    if not search_results:
                        return []

                    all_images = []

                    for result in search_results[:5]:
                        page_title = result.get("title")
                        if not page_title:
                            continue

                        media_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/media-list/{quote(page_title)}"

                        try:
                            async with session.get(
                                media_url, headers=headers, timeout=5
                            ) as media_response:
                                if media_response.status != 200:
                                    continue

                                media_data = await media_response.json()
                                items = media_data.get("items", [])

                                for item in items:
                                    if item.get("type") != "image":
                                        continue

                                    title = item.get("title", "").lower()

                                    skip_patterns = [
                                        "commons-logo",
                                        "edit-icon",
                                        "wikimedia",
                                        "stub",
                                        "ambox",
                                        "flag",
                                    ]
                                    if any(p in title for p in skip_patterns):
                                        continue

                                    clean_title = item["title"]
                                    if clean_title.startswith("File:"):
                                        clean_title = clean_title[5:]

                                    image_url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(f'File:{clean_title}')}?width=800"
                                    all_images.append(image_url)

                                    if len(all_images) >= max_images:
                                        return all_images
                        except Exception:
                            continue

                    return all_images[:max_images]

        except Exception as e:
            logger.debug(f"Wikipedia search error: {e}")
            return []

    async def get_wikipedia_image(self, search_keywords: str) -> str | None:
        """Get single image from Wikipedia (backward compatibility)."""
        images = await self.get_wikipedia_images(search_keywords, max_images=1)
        return images[0] if images else None
