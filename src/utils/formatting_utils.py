"""Shared formatting utilities for parsing model output and building sections."""

import re


def extract_sources_from_answer(answer_content: str) -> list[tuple[str, str]]:
    """Parse Sources/Источники section into (title, url) pairs.

    Handles bullets like "- Title — URL" or "- Title - URL" and mixed headers
    like "Sources/Источники:" or "Источники/Sources:".
    """
    try:
        match = re.search(
            r"(?:^|\n)(Sources(?:/Источники)?|Источники(?:/Sources)?)\s*:\s*(.*?)$",
            answer_content,
            re.DOTALL | re.IGNORECASE,
        )
        if not match:
            return []
        section = match.group(2).strip()
        pairs: list[tuple[str, str]] = []
        for line in section.splitlines():
            line = line.strip()
            if not line.startswith("-"):
                continue
            item = line.lstrip("- ").strip()
            # Split on em dash or hyphen
            split = re.split(r"\s+[—-]\s+", item, maxsplit=1)
            if len(split) == 2:
                title, url = split[0].strip(), split[1].strip()
                url_match = re.search(r"https?://\S+", url)
                if url_match:
                    url = url_match.group(0)
                if title and url:
                    pairs.append((title, url))
            else:
                url_match = re.search(r"https?://\S+", item)
                if url_match:
                    url = url_match.group(0)
                    domain = re.sub(r"^https?://(www\.)?", "", url).split('/')[0]
                    pairs.append((domain, url))
        return pairs
    except Exception:
        return []


def strip_sources_section(text: str) -> str:
    """Remove any trailing Sources/Источники section from a text block."""
    try:
        cut = re.split(
            r"\n(?:Sources(?:/Источники)?|Источники(?:/Sources)?)\s*:.*",
            text,
            maxsplit=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return cut[0].rstrip()
    except Exception:
        return text


def sanitize_url(url: str) -> str:
    """Percent-encode characters that break Telegram Markdown links."""
    try:
        return (
            url.replace(" ", "%20").replace("(", "%28").replace(")", "%29")
        )
    except Exception:
        return url


def escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def label_to_html(label: str) -> str:
    """Convert patterns like "🔗 *Источники:*" to "🔗 <b>Источники:</b>""" 
    return re.sub(r"\*(.+?)\*", r"<b>\\1</b>", label)


