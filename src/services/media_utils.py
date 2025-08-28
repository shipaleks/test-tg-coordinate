"""Utilities for downloading and preparing images for Telegram uploads."""

from __future__ import annotations

import asyncio
import logging
from io import BytesIO
from typing import Iterable, List, Tuple

import aiohttp
from telegram import BufferedInputFile


logger = logging.getLogger(__name__)


async def _fetch_one_image(
    session: aiohttp.ClientSession,
    url: str,
    *,
    timeout_seconds: float = 10.0,
    max_bytes: int = 7_000_000,
) -> tuple[BufferedInputFile, str] | None:
    """Download one image URL and wrap it as InputFile.

    Returns (InputFile, source_url) on success, otherwise None.
    """
    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with session.get(url, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            content_type = resp.headers.get("Content-Type", "").lower()
            if not content_type.startswith("image/"):
                return None

            total_read = 0
            chunks: list[bytes] = []
            async for chunk in resp.content.iter_chunked(64 * 1024):
                total_read += len(chunk)
                if total_read > max_bytes:
                    return None
                chunks.append(chunk)
            data = b"".join(chunks)

            # Best-effort filename from URL or content-type
            filename = "image"
            try:
                # Extract simple name from URL path
                tail = url.split("?")[0].rstrip("/").split("/")[-1]
                if tail:
                    filename = tail[:100]
            except Exception:
                pass

            if "." not in filename:
                # Add extension from mime
                ext = {
                    "image/jpeg": ".jpg",
                    "image/jpg": ".jpg",
                    "image/png": ".png",
                    "image/webp": ".webp",
                }.get(content_type, ".jpg")
                filename = filename + ext

            file_obj = BytesIO(data)
            file_obj.name = filename
            return BufferedInputFile(file_obj.getvalue(), filename=filename), url
    except Exception as e:
        try:
            logger.debug(f"Image download failed for {url}: {e}")
        except Exception:
            pass
        return None


async def download_images_for_telegram(
    urls: Iterable[str],
    *,
    max_images: int = 4,
    concurrency: int = 4,
    timeout_seconds: float = 10.0,
    max_bytes: int = 7_000_000,
) -> List[Tuple[BufferedInputFile, str]]:
    """Download up to max_images from urls and return as InputFile tuples.

    Returns a list of (InputFile, source_url).
    """
    selected: list[tuple[BufferedInputFile, str]] = []
    # Process in order; run a small pool concurrently
    urls_list = [u for u in urls if isinstance(u, str) and u.startswith("http")]
    if not urls_list:
        return selected

    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Iterate in windows to preserve ordering
        for i in range(0, len(urls_list), concurrency):
            if len(selected) >= max_images:
                break
            window = urls_list[i : i + concurrency]
            tasks = [
                _fetch_one_image(
                    session,
                    url,
                    timeout_seconds=timeout_seconds,
                    max_bytes=max_bytes,
                )
                for url in window
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, tuple) and len(res) == 2:
                    selected.append(res)  # type: ignore[arg-type]
                    if len(selected) >= max_images:
                        break
    return selected


