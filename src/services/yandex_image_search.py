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
        # Prepare multiple payload variants to handle API enum/casing differences
        base_snake = {
            "folderId": self.folder_id,
            "query": {
                "query_text": query,
                "search_type": "SEARCH_TYPE_IMAGE",  # enum style
                "page": 0,
            },
        }
        alt_camel = {
            "folderId": self.folder_id,
            "query": {
                "queryText": query,
                "searchType": "SEARCH_TYPE_IMAGE",
                "page": 0,
            },
        }
        alt_numeric = {
            "folderId": self.folder_id,
            "query": {
                "query_text": query,
                "search_type": 2,  # assume IMAGE=2; harmless if wrong as we fallback
                "page": 0,
            },
        }
        payload_variants: List[Dict] = [base_snake, alt_camel, alt_numeric]
        if region is not None:
            for p in payload_variants:
                try:
                    if "query" in p:
                        p["query"]["region"] = region
                except Exception:
                    pass

        timeout = aiohttp.ClientTimeout(total=10)
        last_error_text = None
        data = None
        for variant in payload_variants:
            try:
                async with self.session.post(self.BASE_URL, headers=headers, json=variant, timeout=timeout) as resp:
                    content_type = resp.headers.get("Content-Type", "")
                    if resp.status != 200:
                        # Keep body for diagnostics and to decide retry
                        text = await resp.text()
                        last_error_text = text
                        # Retry only on 400 (validation) to try next variant
                        if resp.status == 400:
                            continue
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
                        try:
                            data = await resp.json()
                        except Exception:
                            logger.warning("YandexImageSearch: non-JSON response: %s", content_type)
                            data = None
                    if data is not None:
                        # High-level diagnostics to adjust parsing in production
                        try:
                            top_keys = list(data.keys())[:10] if isinstance(data, dict) else type(data).__name__
                            logger.info(f"Yandex response OK; top-level keys: {top_keys}")
                        except Exception:
                            pass
                        break
            except aiohttp.ClientError as e:
                logger.warning("YandexImageSearch request failed: %s", e)
                # Try next variant on client error
                continue

        if data is None:
            if last_error_text:
                logger.warning("YandexImageSearch exhausted payload variants; last error: %s", str(last_error_text)[:200])
            return []

        images = self._extract_images(data, max_images * 3)
        # Stronger dedup: collapse by base filename and prefer larger widths
        images = self._deduplicate_and_select(images, need=max_images)
        if images:
            self._cache_set(cache_key, images)
        return images[:max_images]

    def _extract_images(self, data: Dict, max_images: int) -> List[str]:
        """Extract image URLs from API response with defensive parsing."""
        images: List[str] = []

        # 0) Some deployments return a single "rawData" field with JSON or HTML/text
        raw = data.get("rawData")
        if isinstance(raw, str):
            # Try JSON first
            try:
                import json as _json
                raw_obj = _json.loads(raw)
                if isinstance(raw_obj, dict):
                    try:
                        logger.info(f"Yandex rawData JSON object; keys: {list(raw_obj.keys())[:10]}")
                    except Exception:
                        pass
                    images.extend(self._find_image_urls_anywhere(raw_obj, need=max_images))
            except Exception:
                # Not JSON; try base64-decode -> XML, then regex fallback
                try:
                    snippet = raw[:120].replace("\n", " ")
                    logger.info(f"Yandex rawData text; len={len(raw)}; head= {snippet}")
                except Exception:
                    pass
                # Attempt base64 decode → XML parse
                found: List[str] = []
                try:
                    import base64 as _b64
                    decoded = _b64.b64decode(raw, validate=False)
                    text = decoded.decode("utf-8", errors="ignore").strip()
                    if text.startswith("<?xml") or text.startswith("<"):
                        try:
                            import xml.etree.ElementTree as ET
                            root = ET.fromstring(text)
                            # Collect URLs from common tags/attributes
                            for elem in root.iter():
                                # Tag text content
                                if elem.text and self._looks_like_image_url(elem.text.strip()):
                                    found.append(elem.text.strip())
                                    if len(found) >= max_images:
                                        break
                                # Attributes that may hold URLs
                                for attr_name, attr_val in (elem.attrib or {}).items():
                                    if isinstance(attr_val, str) and self._looks_like_image_url(attr_val):
                                        found.append(attr_val)
                                        if len(found) >= max_images:
                                            break
                                if len(found) >= max_images:
                                    break
                        except Exception:
                            # Ignore XML parse errors
                            pass
                except Exception:
                    # Ignore base64 errors
                    pass
                # Fallback to regex over raw text if XML/base64 yielded nothing
                if len(found) < max_images:
                    found.extend(self._extract_image_urls_from_text(raw, need=max_images - len(found)))
                try:
                    logger.info(f"Yandex rawData text: regex found {len(found)} image URLs")
                except Exception:
                    pass
                images.extend(found)
            if len(images) >= max_images:
                return images[:max_images]

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

        # 3) Try other commonly seen containers
        if len(images) < max_images:
            for key in ("documents", "blocks", "groups", "images", "data"):
                seq = data.get(key)
                if isinstance(seq, list):
                    for item in seq:
                        if not isinstance(item, dict):
                            continue
                        url = item.get("url") or item.get("imageUrl") or item.get("previewUrl")
                        if not url:
                            img = item.get("image") or {}
                            if isinstance(img, dict):
                                url = img.get("url") or img.get("previewUrl")
                        if url and self._passes_basic_filters(item):
                            images.append(url)
                            if len(images) >= max_images:
                                break
                if len(images) >= max_images:
                    break

        # 4) Last resort: traverse structure and pick plausible image URLs
        if len(images) < max_images:
            try:
                fallback = self._find_image_urls_anywhere(data, need=max_images - len(images))
                images.extend(fallback)
            except Exception:
                pass

        # Deduplicate and filter wiki pages while preserving order
        deduped: List[str] = []
        seen = set()
        for u in images:
            # Final safety check: only accept valid image URLs
            if u and u not in seen and self._looks_like_image_url(u):
                seen.add(u)
                deduped.append(u)
        return deduped

    def _deduplicate_and_select(self, urls: List[str], need: int) -> List[str]:
        # Group by base filename
        def extract_base(u: str) -> tuple[str, int]:
            from urllib.parse import urlparse, parse_qs
            import re as _re
            # Try to extract canonical commons filename (without 'File:')
            filename = self._extract_commons_filename(u)
            if not filename:
                # Fallback: last segment
                from urllib.parse import unquote
                filename = unquote(u.split('/')[-1])
            # Strip query string remnants
            filename = filename.split('?')[0]
            # Remove size patterns like 120px-, 1600px-, etc from filename
            base = _re.sub(r"(^|[/_-])\d+px[-_/]", r"\\1", filename).lower()
            # Heuristic width from query param or filename
            width = 0
            try:
                q = parse_qs(urlparse(u).query)
                if 'width' in q:
                    width = int(q['width'][0])
            except Exception:
                pass
            if width == 0:
                m = _re.search(r"(\d{3,4})px", u)
                if m:
                    try:
                        width = int(m.group(1))
                    except Exception:
                        width = 0
            return base, width

        groups: dict[str, list[tuple[int, str]]] = {}
        for u in urls:
            base, width = extract_base(u)
            groups.setdefault(base, []).append((width, u))

        selected: List[str] = []
        # Sort each group by width desc, take first; then take groups in insertion order
        for base, items in groups.items():
            items.sort(key=lambda x: x[0], reverse=True)
            best = items[0][1]
            if best not in selected:
                selected.append(best)
            if len(selected) >= need:
                break
        return selected

    def build_query_variants(
        self,
        base_query: str,
        *,
        fact_text: Optional[str] = None,
        place_name: Optional[str] = None,
    ) -> List[str]:
        """Build multiple query variants to increase diversity of results.

        Strategy:
          - Start with place_name or base_query
          - Add detected place type (e.g., музей/museum, парк/park, мост/bridge)
          - Add area token from comma-separated place (e.g., district/city)
        """
        variants: List[str] = []

        seed = (place_name or base_query or "").strip()
        if seed:
            variants.append(seed)

        # Heuristic place type extraction from fact_text
        place_types = [
            ("музей", ["музей", "museum"]),
            ("парк", ["парк", "park"]),
            ("мост", ["мост", "bridge"]),
            ("церковь", ["церковь", "храм", "church"]),
            ("собор", ["собор", "cathedral"]),
            ("дворец", ["дворец", "palace"]),
            ("театр", ["театр", "theater"]),
            ("университет", ["университет", "university"]),
        ]
        type_token: Optional[str] = None
        if fact_text:
            low = fact_text.lower()
            for ru, keys in place_types:
                if any(k in low for k in keys):
                    type_token = ru
                    break
        if type_token and seed:
            variants.append(f"{seed} {type_token}")

        # Area/city token from comma-separated place
        if place_name and "," in place_name:
            try:
                parts = [p.strip() for p in place_name.split(",") if p.strip()]
                # add last part (often city/country)
                if len(parts) >= 2:
                    tail = parts[-1]
                    variants.append(f"{parts[0]} {tail}")
            except Exception:
                pass

        # De-duplicate while preserving order and cap to 3 variants
        out: List[str] = []
        seen = set()
        for v in variants:
            if v and v not in seen:
                seen.add(v)
                out.append(v)
            if len(out) >= 3:
                break
        return out

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

    def _find_image_urls_anywhere(self, node, need: int = 3, depth: int = 0, max_depth: int = 5) -> List[str]:
        urls: List[str] = []
        if depth > max_depth or need <= 0:
            return urls
        try:
            if isinstance(node, dict):
                # Prefer direct image-looking URLs
                for k, v in node.items():
                    if isinstance(v, str) and k.lower() in ("url", "imageurl", "previewurl"):
                        norm = self._normalize_wikimedia_url(v)
                        # Only accept if it looks like a valid image URL (not wiki page)
                        if self._looks_like_image_url(norm):
                            urls.append(norm)
                            if len(urls) >= need:
                                return urls
                # Recurse into children
                for v in node.values():
                    urls.extend(self._find_image_urls_anywhere(v, need - len(urls), depth + 1, max_depth))
                    if len(urls) >= need:
                        return urls
            elif isinstance(node, list):
                for it in node:
                    urls.extend(self._find_image_urls_anywhere(it, need - len(urls), depth + 1, max_depth))
                    if len(urls) >= need:
                        return urls
        except Exception:
            return urls
        return urls

    @staticmethod
    def _looks_like_image_url(url: str) -> bool:
        try:
            lower = url.lower()
            # Must be HTTP(S)
            if not lower.startswith("http"):
                return False
            
            # Special:FilePath URLs are always valid (Telegram can load them)
            if "special:filepath" in lower:
                return True
            
            # CRITICAL: Reject wiki page URLs (Telegram can't load these)
            if "/wiki/file:" in lower:
                return False
            
            # For other URLs, must end with image extension
            if any(ext in lower for ext in (".jpg", ".jpeg", ".png", ".webp")):
                return True
            
            return False
        except Exception:
            return False

    def _extract_image_urls_from_text(self, text: str, need: int = 5) -> List[str]:
        try:
            import re as _re
            # Find http(s) URLs ending with image extensions (basic heuristic)
            pattern = r"https?://[^\s'\"]+\.(?:jpg|jpeg|png|webp)"
            matches = _re.findall(pattern, text, flags=_re.IGNORECASE)
            # Preserve order and unique
            seen = set()
            out: List[str] = []
            for m in matches:
                norm = self._normalize_wikimedia_url(m)
                # Only accept valid image URLs (not wiki pages)
                if norm not in seen and self._looks_like_image_url(norm):
                    seen.add(norm)
                    out.append(norm)
                if len(out) >= need:
                    break
            return out
        except Exception:
            return []

    @staticmethod
    def _normalize_wikimedia_url(url: str) -> str:
        """Normalize Wikimedia thumbnail URLs to Special:FilePath for consistent delivery.

        Example input:
          https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Filename.jpg/120px-Filename.jpg
        Output:
          https://commons.wikimedia.org/wiki/Special:FilePath/File%3AFilename.jpg?width=1200
        """
        try:
            from urllib.parse import quote
            # Convert commons file pages to direct Special:FilePath
            if "commons.wikimedia.org/wiki/File:" in url or "commons.m.wikimedia.org/wiki/File:" in url:
                try:
                    filename = url.split("/wiki/File:", 1)[1]
                    filename = filename.split("?", 1)[0]
                    encoded = quote(f"File:{filename}")
                    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{encoded}?width=1200"
                except Exception:
                    return url
            # Normalize upload.wikimedia thumbs to Special:FilePath
            if "upload.wikimedia.org" in url and "/thumb/" in url:
                parts = url.split("/thumb/")
                if len(parts) < 2:
                    return url
                rest = parts[1]
                # rest like: a/ab/Filename.jpg/120px-Filename.jpg
                try:
                    segs = rest.split("/")
                    if len(segs) < 3:
                        return url
                    filename = segs[2]
                    if not filename:
                        return url
                    encoded = quote(f"File:{filename}")
                    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{encoded}?width=1200"
                except Exception:
                    return url
            # Normalize upload.wikimedia originals (non-thumb) to Special:FilePath
            if "upload.wikimedia.org" in url and "/wikipedia/commons/" in url and "/thumb/" not in url:
                try:
                    # Path like: /wikipedia/commons/a/ab/Filename.jpg
                    path = url.split("/wikipedia/commons/", 1)[1]
                    segs = path.split("/")
                    if len(segs) >= 3:
                        filename = segs[2]
                        if filename:
                            encoded = quote(f"File:{filename}")
                            return f"https://commons.wikimedia.org/wiki/Special:FilePath/{encoded}?width=1200"
                except Exception:
                    return url
            return url
        except Exception:
            return url

    @staticmethod
    def _extract_commons_filename(url: str) -> Optional[str]:
        """Extract canonical Wikimedia filename from various URL forms.

        Returns filename with extension, without 'File:' prefix, lowercased if possible.
        """
        try:
            from urllib.parse import unquote
            u = url
            if "Special:FilePath/" in u:
                part = u.split("Special:FilePath/", 1)[1]
                part = part.split("?", 1)[0]
                name = unquote(part)
                if name.lower().startswith("file:"):
                    name = name.split(":", 1)[1]
                return name
            if "/wiki/File:" in u:
                part = u.split("/wiki/File:", 1)[1]
                part = part.split("?", 1)[0]
                name = unquote(part)
                return name
            if "upload.wikimedia.org" in u and "/wikipedia/commons/" in u:
                # thumb or original
                if "/thumb/" in u:
                    rest = u.split("/thumb/", 1)[1]
                    segs = rest.split("/")
                    if len(segs) >= 3:
                        return segs[2]
                else:
                    rest = u.split("/wikipedia/commons/", 1)[1]
                    segs = rest.split("/")
                    if len(segs) >= 3:
                        return segs[2]
            return None
        except Exception:
            return None

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


