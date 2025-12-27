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


def extract_bare_links(text: str) -> list[str]:
    """Extract bare domains or domain+path from text and normalize to https URLs."""
    try:
        urls = []
        # Match domains optionally with a simple path, avoid already http(s) links
        for m in re.finditer(r"(?<!https?://)([a-z0-9.-]+\.[a-z]{2,})(/[\w\-/%]+)?", text, re.IGNORECASE):
            domain = m.group(1)
            path = m.group(2) or ""
            url = f"https://{domain}{path}"
            urls.append(url)
        # Deduplicate
        uniq = []
        seen = set()
        for u in urls:
            if u not in seen:
                uniq.append(u)
                seen.add(u)
        return uniq
    except Exception:
        return []


def remove_bare_links_from_text(text: str) -> str:
    """Remove bare domains in parentheses or as standalone tokens from text."""
    try:
        # Remove (example.com) or (example.com/path)
        text = re.sub(r"\((?<!https?://)([a-z0-9.-]+\.[a-z]{2,}(/[\w\-/%]+)?)\)", "", text, flags=re.IGNORECASE)
        return text
    except Exception:
        return text


def normalize_place_name(place: str) -> str:
    """Normalize a place name for duplicate detection.
    
    This function removes common prefixes, suffixes, articles, and punctuation
    to allow comparison of place names that may be written differently:
    - "Église Saint-Eustache" → "saint eustache"
    - "Church of Saint-Eustache, Paris" → "saint eustache"
    - "The Saint-Eustache church" → "saint eustache church"
    """
    if not place:
        return ""

    normalized = place.lower().strip()

    # First, remove city names at the end (common pattern: "Place Name, Paris")
    # Do this BEFORE removing prefixes to preserve the main place name
    normalized = re.sub(r",\s*[a-zA-Zа-яА-Яéèêëàâùûôîïç\s]+$", "", normalized)

    # Common translations/equivalents for well-known landmarks
    # These are bidirectional mappings to handle cross-language duplicates
    landmark_normalizations = {
        # Eiffel Tower variations
        r"tour\s+eiffel": "eiffel",
        r"eiffel\s+tower": "eiffel",
        r"эйфелева\s+башня": "eiffel",
        # Louvre variations
        r"musée\s+du\s+louvre": "louvre",
        r"louvre\s+museum": "louvre",
        r"the\s+louvre": "louvre",
        r"музей\s+лувр": "louvre",
        # Notre-Dame variations
        r"notre[- ]dame\s+de\s+paris": "notre dame",
        r"cathédrale\s+notre[- ]dame": "notre dame",
        r"notre[- ]dame\s+cathedral": "notre dame",
        r"собор\s+парижской\s+богоматери": "notre dame",
        # Arc de Triomphe
        r"arc\s+de\s+triomphe": "arc triomphe",
        r"триумфальная\s+арка": "arc triomphe",
    }

    for pattern, replacement in landmark_normalizations.items():
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)

    # Remove common prefixes/articles in multiple languages
    prefixes_to_remove = [
        # French
        r"^l'", r"^la\s+", r"^le\s+", r"^les\s+", r"^du\s+", r"^de\s+la\s+", r"^de\s+l'",
        r"^église\s+", r"^cathédrale\s+", r"^basilique\s+", r"^musée\s+", r"^palais\s+",
        r"^place\s+", r"^rue\s+", r"^avenue\s+", r"^boulevard\s+",
        # English
        r"^the\s+", r"^a\s+", r"^an\s+",
        r"^church\s+of\s+", r"^cathedral\s+of\s+", r"^basilica\s+of\s+",
        r"^museum\s+of\s+", r"^palace\s+of\s+",
        r"^saint\s+", r"^st\.?\s+",
        # Russian
        r"^церковь\s+", r"^собор\s+", r"^храм\s+", r"^музей\s+", r"^дворец\s+",
        r"^площадь\s+", r"^улица\s+", r"^проспект\s+", r"^бульвар\s+",
        # German
        r"^die\s+", r"^der\s+", r"^das\s+",
        r"^kirche\s+", r"^dom\s+", r"^schloss\s+",
        # Spanish
        r"^el\s+", r"^la\s+", r"^los\s+", r"^las\s+",
        r"^iglesia\s+de\s+", r"^catedral\s+de\s+",
        # Italian
        r"^il\s+", r"^lo\s+", r"^la\s+", r"^i\s+", r"^gli\s+", r"^le\s+",
        r"^chiesa\s+di\s+", r"^basilica\s+di\s+",
    ]

    for prefix in prefixes_to_remove:
        normalized = re.sub(prefix, "", normalized, flags=re.IGNORECASE)

    # Replace special characters with spaces
    normalized = re.sub(r"[-–—_/\\]", " ", normalized)

    # Remove punctuation
    normalized = re.sub(r"[.,;:!?'\"()[\]{}]", "", normalized)

    # Collapse multiple spaces
    normalized = re.sub(r"\s+", " ", normalized).strip()

    # If result is too short (e.g., just a number), use original with basic cleanup
    if len(normalized) < 3:
        # Fallback: basic cleanup without aggressive prefix removal
        normalized = place.lower().strip()
        normalized = re.sub(r",\s*[a-zA-Zа-яА-Яéèêëàâùûôîïç\s]+$", "", normalized)
        normalized = re.sub(r"[-–—_/\\]", " ", normalized)
        normalized = re.sub(r"[.,;:!?'\"()[\]{}]", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()

    return normalized


def is_duplicate_place(new_place: str, previous_places: list[str], threshold: float = 0.7) -> bool:
    """Check if a place name is a duplicate of any previous places.
    
    Uses normalized comparison and substring matching.
    
    Args:
        new_place: The new place name to check
        previous_places: List of previously mentioned place names
        threshold: Similarity threshold (not currently used, for future fuzzy matching)
    
    Returns:
        True if this appears to be a duplicate
    """
    if not new_place or not previous_places:
        return False

    new_normalized = normalize_place_name(new_place)
    if not new_normalized:
        return False

    # Split into tokens for comparison
    new_tokens = set(new_normalized.split())

    for prev in previous_places:
        prev_normalized = normalize_place_name(prev)
        if not prev_normalized:
            continue

        # Exact match after normalization
        if new_normalized == prev_normalized:
            return True

        prev_tokens = set(prev_normalized.split())

        # Check for significant overlap (more than 70% of tokens match)
        if new_tokens and prev_tokens:
            common_tokens = new_tokens & prev_tokens
            # If either set is mostly contained in the other
            overlap_ratio_new = len(common_tokens) / len(new_tokens)
            overlap_ratio_prev = len(common_tokens) / len(prev_tokens)

            if overlap_ratio_new >= threshold or overlap_ratio_prev >= threshold:
                return True

        # Check if one is substring of another (handles cases like "Saint-Eustache" vs "Église Saint-Eustache")
        if new_normalized in prev_normalized or prev_normalized in new_normalized:
            return True

    return False


def extract_place_names_from_history(fact_history: list[str]) -> list[str]:
    """Extract just the place names from fact history entries.
    
    Fact history format: "Place Name: fact text..."
    
    Args:
        fact_history: List of strings in format "Place: Fact"
    
    Returns:
        List of place names only
    """
    places = []
    for entry in fact_history:
        if ": " in entry:
            place = entry.split(": ", 1)[0].strip()
            if place:
                places.append(place)
    return places


