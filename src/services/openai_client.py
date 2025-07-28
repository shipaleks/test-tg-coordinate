"""OpenAI client for generating location-based facts."""

import logging
import os
import re
import time
from urllib.parse import quote

import aiohttp
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class StaticLocationHistory:
    """Simple in-memory cache for static location facts to avoid repetition."""
    
    def __init__(self, max_entries: int = 1000, ttl_hours: int = 24):
        """Initialize the history cache.
        
        Args:
            max_entries: Maximum number of entries to keep in cache
            ttl_hours: Time to live for entries in hours
        """
        self._cache = {}  # {search_keywords: {"facts": [facts], "timestamp": time}}
        self._max_entries = max_entries
        self._ttl_seconds = ttl_hours * 3600
    
    def get_previous_facts(self, search_keywords: str) -> list[str]:
        """Get previous facts for a location.
        
        Args:
            search_keywords: Search keywords identifying the location
            
        Returns:
            List of previous facts (empty if none or expired)
        """
        self._cleanup_expired()
        
        entry = self._cache.get(search_keywords)
        if entry and (time.time() - entry["timestamp"]) < self._ttl_seconds:
            return entry["facts"][-5:]  # Return last 5 facts like live location
        return []
    
    def add_fact(self, search_keywords: str, place: str, fact: str):
        """Add a new fact to the history.
        
        Args:
            search_keywords: Search keywords identifying the location
            place: Place name
            fact: The fact text
        """
        self._cleanup_expired()
        
        if search_keywords not in self._cache:
            self._cache[search_keywords] = {"facts": [], "timestamp": time.time()}
        
        # Add fact in same format as live location
        fact_entry = f"{place}: {fact}"
        self._cache[search_keywords]["facts"].append(fact_entry)
        self._cache[search_keywords]["timestamp"] = time.time()
        
        # Keep only last 10 facts per location to prevent memory bloat
        if len(self._cache[search_keywords]["facts"]) > 10:
            self._cache[search_keywords]["facts"] = self._cache[search_keywords]["facts"][-10:]
        
        logger.debug(f"Added fact to static location history: {place}")
    
    def _cleanup_expired(self):
        """Remove expired entries and limit cache size."""
        current_time = time.time()
        
        # Remove expired entries
        expired_keys = [
            key for key, entry in self._cache.items()
            if (current_time - entry["timestamp"]) >= self._ttl_seconds
        ]
        for key in expired_keys:
            del self._cache[key]
        
        # Limit cache size
        if len(self._cache) > self._max_entries:
            # Remove oldest entries
            sorted_items = sorted(
                self._cache.items(), 
                key=lambda x: x[1]["timestamp"]
            )
            keys_to_remove = [item[0] for item in sorted_items[:len(self._cache) - self._max_entries]]
            for key in keys_to_remove:
                del self._cache[key]
    
    def get_cache_stats(self) -> dict:
        """Get cache statistics for debugging."""
        self._cleanup_expired()
        total_facts = sum(len(entry["facts"]) for entry in self._cache.values())
        return {
            "locations": len(self._cache),
            "total_facts": total_facts,
            "oldest_entry": min((entry["timestamp"] for entry in self._cache.values()), default=0)
        }


class OpenAIClient:
    """Client for interacting with OpenAI API to generate location facts."""

    def __init__(self, api_key: str | None = None):
        """Initialize OpenAI client.

        Args:
            api_key: OpenAI API key. If None, will use OPENAI_API_KEY env var.
        """
        self.client = AsyncOpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.static_history = StaticLocationHistory()

    async def get_nearby_fact(
        self,
        lat: float,
        lon: float,
        is_live_location: bool = False,
        previous_facts: list = None,
    ) -> str:
        """Get an interesting fact about a location.

        Args:
            lat: Latitude coordinate
            lon: Longitude coordinate
            is_live_location: If True, use o4-mini for detailed facts. If False, use gpt-4.1 for speed.
            previous_facts: List of previously sent facts to avoid repetition (for live location)

        Returns:
            A location name and an interesting fact about it

        Raises:
            Exception: If OpenAI API call fails
        """
        try:
            system_prompt = (
                "Вы — профессиональный экскурсовод с глубокими знаниями различных мест по всему миру. "
                "Ваша задача — пошагово проанализировать координаты и предоставить интересный факт о местности.\n\n"
                "Процесс рассуждения:\n"
                "1. Сначала внимательно проанализируйте координаты и определите точное местоположение\n"
                "2. Подумайте о географических особенностях этой области\n"
                "3. Вспомните исторические события, архитектурные особенности или культурные факты\n"
                "4. Выберите наиболее интересный и достоверный факт\n"
                "5. Убедитесь, что информация точна и не выдумана\n\n"
                "ПРИНЦИПЫ РАБОТЫ:\n"
                "• ПРИОРИТЕТ: Интересные, достоверные факты на основе ваших знаний\n"
                "• КАЧЕСТВО: Стремитесь к уровню Atlas Obscura — необычные детали\n"
                "• БЛИЗОСТЬ: Фокус на ближайших местах, но не отказывайтесь без веской причины\n"
                "• ИЕРАРХИЯ РАССТОЯНИЙ:\n"
                "  1. ЛУЧШЕ ВСЕГО: места до 300м (5-7 минут пешком)\n"
                "  2. ХОРОШО: до 500-700м (10-12 минут пешком)\n"
                "  3. ПРИЕМЛЕМО: до 1км (15 минут пешком)\n"
                "  4. Только если ничего ближе — до 1.5км с объяснением расстояния\n\n"
                "💡 В больших городах почти всегда есть что-то интересное рядом!\n\n"
                "ATLAS OBSCURA ПОДХОД:\n"
                "• Ищите скрытые истории, неочевидные детали, архитектурные секреты\n"
                "• Фокус на необычном: малоизвестные исторические события, культурные особенности\n"
                "• Интересные подробности важнее банальных общих фактов\n"
                "• НО: рассказывайте только то, в чем уверены - не изобретайте факты\n"
                "• Используйте приблизительные даты если точные неизвестны\n"
                "• Лучше увлекательная деталь, чем скучная общая информация\n"
                "• Если сомневаетесь в деталях - дайте общий интересный контекст\n"
                "• ВСЕГДА находите что-то неожиданное и интригующее\n\n"
                "Весь ответ должен быть на русском языке."
            )

            # Handle previous facts for both live and static locations
            previous_facts_text = ""
            if previous_facts:
                previous_facts_text = (
                    "\n\n🚫 РАНЕЕ РАССКАЗАННЫЕ ФАКТЫ (НЕ ПОВТОРЯЙТЕ):\n"
                    + "\n".join(
                        [f"- {fact}" for fact in previous_facts[-5:]]
                    )  # Last 5 facts
                    + "\n\n🎯 ВАЖНО: Найдите ДРУГОЕ МЕСТО в том же районе! Не повторяйте уже упомянутые локации.\n"
                    + "Ищите другие достопримечательности, здания, памятники, улицы в радиусе 200-500м.\n"
                )

            if is_live_location:
                # Detailed prompt for live location (o4-mini)
                user_prompt = (
                    f"Проанализируйте координаты: {lat}, {lon}\n\n"
                    "Пожалуйста, следуйте процессу рассуждения:\n\n"
                    "Шаг 1: Определите географическое местоположение по координатам. Что это за город, район, страна?\n\n"
                    "Шаг 2: Найдите топонимы в радиусе до 300 метров (улицы, здания, памятники, парки, мемориальные доски). Приоритет ближайшим!\n\n"
                    "Шаг 3: Проанализируйте, какие интересные исторические, архитектурные или культурные факты "
                    "вы знаете об этой области или ближайших достопримечательностях.\n\n"
                    f"Шаг 4: Выберите факт СТРОГО по близости:{previous_facts_text}\n"
                    + ("   🔄 У ВАС ЕСТЬ ПРЕДЫДУЩИЕ ФАКТЫ — найдите ДРУГОЕ место в том же районе!\n" if previous_facts else "")
                    + "   А) ПРИОРИТЕТ: что-то в радиусе до 300м? (5-7 минут пешком)\n"
                    "   Б) Допустимо: до 500-700м (10-12 минут пешком)\n"
                    "   В) МАКСИМУМ: до 1км (15 минут пешком)\n"
                    "   Г) В Париже/Лондоне/Москве ВСЕГДА есть что-то рядом — ищите лучше!\n\n"
                    "🎯 СТРАТЕГИЯ ПОИСКА" + (" (ищите ДРУГОЕ место!):" if previous_facts else ":") + "\n"
                    "• " + ("ИЗБЕГАЙТЕ уже упомянутых мест — найдите альтернативные достопримечательности\n• " if previous_facts else "")
                    + "Сначала ищите очевидные ориентиры: улицы, площади, парки, здания\n"
                    "• Затем думайте об истории района, архитектуре, культуре\n"
                    "• Если место кажется обычным — ищите детали: памятники, исторические здания, культурные особенности\n"
                    "• В крайнем случае расскажите об архитектурном стиле, городском планировании или истории района\n\n"
                    "💎 ATLAS OBSCURA СТИЛЬ:\n"
                    "• Ищите необычные истории, архитектурные детали, культурные особенности\n"    
                    "• Скрытые факты и неочевидные связи интереснее банальной информации\n"
                    "• НО ВАЖНО: используйте только достоверную информацию, не выдумывайте\n"
                    "• Приблизительные даты приемлемы, если делают рассказ живее\n"
                    "• Если не уверены в конкретных деталях — дайте общий увлекательный контекст\n"
                    "• ВСЕГДА находите что-то удивительное — отказ недопустим\n\n"
                    "ЦЕЛЬ: Создайте ПОДРОБНЫЙ и УВЛЕКАТЕЛЬНЫЙ факт (примерно 100-120 слов). Включите:\n"
                    "- Необычные исторические детали или малоизвестные события (только достоверные)\n"
                    "- Архитектурные секреты, скрытые элементы, неочевидные особенности\n"
                    "- Интригующие связи с известными личностями или событиями\n"
                    "- Культурные особенности, местные легенды, городские истории\n"
                    "- Если место обычное — найдите в нем что-то неожиданное и удивительное\n"
                    "- ВАЖНО: не изобретайте факты — используйте только то, в чем уверены\n\n"
                    "Финальный ответ в формате:\n"
                    "Локация: [Конкретное название места]\n"
                    "Поиск: [Ключевые слова для точного поиска: ОРИГИНАЛЬНОЕ название на местном языке + город + страна. Например: 'Louvre Museum Paris France' или 'Красная площадь Москва Россия']\n"
                    "Интересный факт: [Развернутый факт с историческими подробностями, примерно 100-120 слов]"
                )
            else:
                # Concise prompt for static location (gpt-4.1)
                user_prompt = (
                    f"Проанализируйте координаты: {lat}, {lon}\n\n"
                    "Найдите ближайшее интересное место и предоставьте краткий факт.\n\n"
                    "ИЕРАРХИЯ РАССТОЯНИЙ:\n"
                    "1. ЛУЧШЕ ВСЕГО: объекты до 300м (5-7 минут пешком)\n"
                    "2. ХОРОШО: до 500-700м (10-12 минут пешком)\n"
                    "3. ПРИЕМЛЕМО: до 1км (15 минут пешком)\n"
                    "4. В больших городах почти всегда есть что-то интересное рядом!\n\n"
                    "🎯 ATLAS OBSCURA СТРАТЕГИЯ:\n"
                    "• Ищите улицы, площади, здания, парки с необычными историями\n"
                    "• Скрытые детали архитектуры, малоизвестные исторические события\n"
                    "• НО: только достоверная информация — не выдумывайте факты\n"
                    "• Если место обычное — найдите в нем что-то удивительное\n"
                    "• При сомнениях — лучше общий интересный контекст, чем выдуманные детали\n"
                    "• ВСЕГДА находите неожиданный интересный факт\n\n"
                    "ЦЕЛЬ: Краткий но УВЛЕКАТЕЛЬНЫЙ факт (60-80 слов). Включите:\n"
                    "- Необычные исторические детали или малоизвестные события (только достоверные)\n"
                    "- Интригующие архитектурные особенности или культурные факты\n"
                    "- Неочевидные связи или удивительные подробности\n"
                    "- ВАЖНО: не изобретайте факты — лучше общий контекст, чем выдуманные детали\n\n"
                    "Финальный ответ в формате:\n"
                    "Локация: [Конкретное название места]\n"
                    "Поиск: [Ключевые слова для точного поиска: ОРИГИНАЛЬНОЕ название на местном языке + город + страна. Например: 'Louvre Museum Paris France' или 'Красная площадь Москва Россия']\n"
                    "Интересный факт: [Краткий, но увлекательный факт, 60-80 слов]"
                )

            # Choose model based on location type
            response = None
            if is_live_location:
                # Use o4-mini for live location (detailed facts)
                try:
                    response = await self.client.chat.completions.create(
                        model="o4-mini",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        max_completion_tokens=10000,  # Large limit for o4-mini extensive reasoning + detailed response
                    )
                    logger.info(f"o4-mini (live location) response: {response}")
                    content = (
                        response.choices[0].message.content
                        if response.choices
                        else None
                    )

                    if not content:
                        logger.warning(
                            "o4-mini returned empty content, falling back to gpt-4.1"
                        )
                        raise ValueError("Empty content from o4-mini")

                except Exception as e:
                    logger.warning(
                        f"o4-mini failed ({e}), falling back to gpt-4.1 for live location"
                    )
                    response = await self.client.chat.completions.create(
                        model="gpt-4.1",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        max_tokens=800,
                        temperature=0.7,
                    )
                    logger.info(f"gpt-4.1 fallback for live location: {response}")
                    content = (
                        response.choices[0].message.content
                        if response.choices
                        else None
                    )
            else:
                # Use gpt-4.1 for static location (fast, concise facts)
                try:
                    response = await self.client.chat.completions.create(
                        model="gpt-4.1",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        max_tokens=400,  # Smaller limit for concise facts
                        temperature=0.7,
                    )
                    logger.info(f"gpt-4.1 (static location) response: {response}")
                    content = (
                        response.choices[0].message.content
                        if response.choices
                        else None
                    )

                    if not content:
                        logger.warning(
                            "gpt-4.1 returned empty content for static location"
                        )
                        raise ValueError("Empty content from gpt-4.1")

                except Exception as e:
                    logger.error(f"gpt-4.1 failed for static location: {e}")
                    raise

            if not content:
                logger.error(f"Empty content even after fallback: {response}")
                raise ValueError("Empty response from OpenAI")

            logger.info(f"Generated fact for location {lat},{lon}")
            return content.strip()

        except Exception as e:
            logger.error(f"Failed to generate fact for {lat},{lon}: {e}")
            raise

    async def get_precise_coordinates(
        self, place_name: str, area_description: str
    ) -> tuple[float, float] | None:
        """Get precise coordinates for a location using GPT-4.1 with web search.

        Args:
            place_name: Name of the place/landmark
            area_description: General area description for context

        Returns:
            Tuple of (latitude, longitude) if found, None otherwise
        """
        try:

            # WebSearch tool is deprecated and no longer works
            logger.warning("WebSearch tool is deprecated, skipping web search")
            return None

        except Exception as e:
            logger.error(f"Failed to get precise coordinates for {place_name}: {e}")
            return None

    async def get_coordinates_from_nominatim(
        self, place_name: str
    ) -> tuple[float, float] | None:
        """Get coordinates using OpenStreetMap Nominatim service as fallback.

        Args:
            place_name: Name of the place to search

        Returns:
            Tuple of (latitude, longitude) if found, None otherwise
        """
        try:
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                "q": place_name,
                "format": "json",
                "limit": 1,
                "addressdetails": 1,
            }
            headers = {"User-Agent": "NearbyFactBot/1.0 (Educational Project)"}

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, params=params, headers=headers, timeout=5
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data:
                            lat = float(data[0]["lat"])
                            lon = float(data[0]["lon"])

                            if -90 <= lat <= 90 and -180 <= lon <= 180:
                                logger.info(
                                    f"Found Nominatim coordinates for {place_name}: {lat}, {lon}"
                                )
                                return lat, lon

            logger.debug(f"No coordinates found in Nominatim for: {place_name}")
            return None

        except Exception as e:
            logger.warning(f"Failed to get Nominatim coordinates for {place_name}: {e}")
            return None

    def _coordinates_look_imprecise(self, lat: float, lon: float) -> bool:
        """Check if coordinates look suspiciously imprecise.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            True if coordinates look imprecise (too rounded, common defaults, etc.)
        """
        # Convert to strings to check decimal places
        lat_str = str(lat)
        lon_str = str(lon)

        # Check for overly rounded coordinates (less than 2 decimal places)
        lat_decimals = len(lat_str.split('.')[-1]) if '.' in lat_str else 0
        lon_decimals = len(lon_str.split('.')[-1]) if '.' in lon_str else 0

        if lat_decimals < 2 or lon_decimals < 2:
            logger.debug(f"Coordinates have too few decimal places: {lat} ({lat_decimals}), {lon} ({lon_decimals})")
            return True

        # Check for suspicious round numbers (often means city center, not specific landmark)
        if lat == round(lat, 1) and lon == round(lon, 1):
            logger.debug(f"Coordinates are suspiciously round: {lat}, {lon}")
            return True

        # Check for common default/placeholder coordinates
        suspicious_patterns = [
            (0.0, 0.0),  # Null Island
            (55.7558, 37.6173),  # Generic Moscow center
            (55.75, 37.62),  # Rounded Moscow
            (59.9311, 30.3609),  # Generic SPb center
        ]

        for sus_lat, sus_lon in suspicious_patterns:
            if abs(lat - sus_lat) < 0.01 and abs(lon - sus_lon) < 0.01:
                logger.debug(f"Coordinates match suspicious pattern: {lat}, {lon}")
                return True

        return False

    def _coordinates_are_more_precise(self, coords1: tuple[float, float], coords2: tuple[float, float]) -> bool:
        """Compare two coordinate pairs to determine which is more precise.

        Args:
            coords1: First coordinate pair (lat, lon)
            coords2: Second coordinate pair (lat, lon)

        Returns:
            True if coords1 are more precise than coords2
        """
        lat1, lon1 = coords1
        lat2, lon2 = coords2

        # Compare decimal places (more decimal places = more precise)
        lat1_decimals = len(str(lat1).split('.')[-1]) if '.' in str(lat1) else 0
        lon1_decimals = len(str(lon1).split('.')[-1]) if '.' in str(lon1) else 0
        lat2_decimals = len(str(lat2).split('.')[-1]) if '.' in str(lat2) else 0
        lon2_decimals = len(str(lon2).split('.')[-1]) if '.' in str(lon2) else 0

        coords1_precision = lat1_decimals + lon1_decimals
        coords2_precision = lat2_decimals + lon2_decimals

        return coords1_precision > coords2_precision

    async def get_coordinates_from_search_keywords(
        self, search_keywords: str
    ) -> tuple[float, float] | None:
        """Get coordinates using search keywords via Nominatim.

        Args:
            search_keywords: Search keywords from GPT response

        Returns:
            Tuple of (latitude, longitude) if found, None otherwise
        """
        logger.info(f"Searching coordinates for keywords: {search_keywords}")

        # Try original keywords first
        nominatim_coords = await self.get_coordinates_from_nominatim(search_keywords)
        if nominatim_coords:
            logger.info(f"Found Nominatim coordinates: {nominatim_coords}")
            return nominatim_coords

        logger.info(f"Nominatim failed for original keywords: {search_keywords}")

        # Try multiple fallback patterns for better search coverage
        fallback_patterns = []
        
        # For metro/subway stations, try different formats
        if "metro" in search_keywords.lower() or "метро" in search_keywords.lower():
            # Extract station name and try different combinations
            station_name = search_keywords.replace("Metro", "").replace("metro", "").replace("метро", "").replace("станция", "").strip()
            if "Paris" in search_keywords:
                fallback_patterns.extend([
                    f"{station_name} station Paris",
                    f"{station_name} Paris metro",
                    f"{station_name} Paris",
                    station_name.split()[0] if station_name else ""  # First word only
                ])
            elif "France" in search_keywords:
                fallback_patterns.extend([
                    f"{station_name} station",
                    f"{station_name} metro",
                    station_name.split()[0] if station_name else ""
                ])
        
        # For places with + or complex formatting
        if " + " in search_keywords or "+" in search_keywords:
            parts = search_keywords.replace("+", " ").split()
            fallback_patterns.extend([
                " ".join(parts[:2]) if len(parts) >= 2 else parts[0],  # First two words
                parts[0] if parts else "",  # First word only
            ])
        
        # For long place names, try progressively shorter versions
        words = search_keywords.split()
        if len(words) > 2:
            fallback_patterns.extend([
                " ".join(words[:3]),  # First 3 words
                " ".join(words[:2]),  # First 2 words
                words[0]  # First word only
            ])
        
        # Remove empty patterns and duplicates
        fallback_patterns = [p.strip() for p in fallback_patterns if p and p.strip()]
        fallback_patterns = list(dict.fromkeys(fallback_patterns))  # Remove duplicates while preserving order
        
        # Try each fallback pattern
        for pattern in fallback_patterns:
            if pattern and pattern != search_keywords:  # Don't retry the original
                logger.info(f"Trying fallback search: {pattern}")
                coords = await self.get_coordinates_from_nominatim(pattern)
                if coords:
                    logger.info(f"Found coordinates with fallback search '{pattern}': {coords}")
                    return coords

        logger.warning(f"No coordinates found for keywords: {search_keywords}")
        return None

    async def parse_coordinates_from_response(
        self, response: str
    ) -> tuple[float, float] | None:
        """Parse coordinates from OpenAI response using search keywords.

        Args:
            response: OpenAI response text

        Returns:
            Tuple of (latitude, longitude) if found, None otherwise
        """
        try:
            # First, try to extract search keywords from new format
            search_match = re.search(r"Поиск:\s*(.+?)(?:\n|$)", response)
            if search_match:
                search_keywords = search_match.group(1).strip()
                logger.info(f"Found search keywords: {search_keywords}")

                # Use new keyword-based search
                coords = await self.get_coordinates_from_search_keywords(search_keywords)
                if coords:
                    return coords

            # Fallback: try to extract location name if no search keywords
            place_match = re.search(r"Локация:\s*(.+?)(?:\n|$)", response)
            if place_match:
                place_name = place_match.group(1).strip()
                logger.info(f"No search keywords found, using location name: {place_name}")

                # Use location name as search keywords
                coords = await self.get_coordinates_from_search_keywords(place_name)
                if coords:
                    return coords

            logger.debug("No search keywords or location name found in response")
            return None

        except (ValueError, AttributeError) as e:
            logger.warning(f"Error parsing coordinates: {e}")
            return None

    async def get_wikipedia_images(self, search_keywords: str, max_images: int = 5) -> list[str]:
        """Get multiple images from Wikipedia using search keywords.
        
        Args:
            search_keywords: Search keywords from GPT response
            max_images: Maximum number of images to return (default 5)
            
        Returns:
            List of image URLs (up to max_images)
        """
        # Languages to try (in order of preference)
        languages = ['en', 'ru', 'fr', 'de', 'es', 'it']
        
        # Clean up search keywords
        clean_keywords = search_keywords.replace(' + ', ' ').replace('+', ' ').strip()
        
        # Try different variations of search terms
        search_variations = [clean_keywords]
        
        # Add word combinations
        words = clean_keywords.split()
        if len(words) > 1:
            # Try first two words
            search_variations.append(' '.join(words[:2]))
            # Try first word only
            search_variations.append(words[0])
            # Try last word (often the most specific)
            search_variations.append(words[-1])
            # Try removing common words like "France", "Paris", etc.
            filtered_words = [w for w in words if w not in ['France', 'Paris', 'London', 'Moscow', 'Москва', 'Россия']]
            if filtered_words and len(filtered_words) != len(words):
                search_variations.append(' '.join(filtered_words))
        
        # Add specific variations for common patterns
        if any(word in clean_keywords.lower() for word in ['metro', 'station', 'метро', 'станция']):
            # For metro stations, try without "metro"/"метро" words
            metro_clean = clean_keywords.lower()
            for word in ['metro', 'station', 'метро', 'станция']:
                metro_clean = metro_clean.replace(word, '').strip()
            if metro_clean:
                search_variations.append(metro_clean)
        
        # Remove duplicates while preserving order
        search_variations = list(dict.fromkeys(search_variations))
        
        found_images = []
        
        for lang in languages:
            if len(found_images) >= max_images:
                break
                
            for search_term in search_variations:
                if not search_term or len(found_images) >= max_images:
                    continue
                    
                try:
                    logger.debug(f"Trying Wikipedia search: '{search_term}' in {lang}")
                    images = await self._search_wikipedia_images(search_term, lang, max_images - len(found_images))
                    if images:
                        # Filter out duplicates
                        for img in images:
                            if img not in found_images:
                                found_images.append(img)
                                if len(found_images) >= max_images:
                                    break
                        logger.info(f"Found {len(images)} Wikipedia images for '{search_term}' in {lang}")
                    else:
                        logger.debug(f"No images found for '{search_term}' in {lang}")
                except Exception as e:
                    logger.debug(f"Wikipedia search failed for '{search_term}' in {lang}: {e}")
                    continue
        
        if found_images:
            logger.info(f"Found {len(found_images)} Wikipedia images for: {search_keywords}")
        else:
            logger.info(f"No Wikipedia images found for: {search_keywords} (tried {len(search_variations)} variations across {len(languages)} languages)")
        
        return found_images

    async def _search_wikipedia_images(self, search_term: str, lang: str, max_images: int = 5) -> list[str]:
        """Search for images on specific Wikipedia language.
        
        Args:
            search_term: Term to search for
            lang: Language code (en, ru, fr, etc.)
            max_images: Maximum number of images to return
            
        Returns:
            List of image URLs (up to max_images)
        """
        try:
            # Use legacy API for search (REST API often returns 404)
            search_url = f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search&srsearch={quote(search_term)}&format=json"
            headers = {"User-Agent": "NearbyFactBot/1.0 (Educational Project)"}
            
            async with aiohttp.ClientSession() as session:
                # Search for pages using legacy API
                async with session.get(search_url, headers=headers, timeout=5) as response:
                    if response.status != 200:
                        logger.debug(f"Search failed for '{search_term}' in {lang}: status {response.status}")
                        return None
                    
                    search_data = await response.json()
                    search_results = search_data.get('query', {}).get('search', [])
                    
                    if not search_results:
                        logger.debug(f"No search results found for '{search_term}' in {lang}")
                        return []
                    
                    logger.debug(f"Found {len(search_results)} search results for '{search_term}' in {lang}")
                    
                    # Collect all potential images from multiple pages
                    all_potential_images = []
                    
                    # Try first few pages
                    for result in search_results[:5]:  # Try more pages
                        page_title = result.get('title')
                        if not page_title:
                            continue
                        
                        logger.debug(f"Trying page: {page_title}")
                        
                        # Get media list for this page using REST API (this part still works)
                        media_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/media-list/{quote(page_title)}"
                        
                        async with session.get(media_url, headers=headers, timeout=5) as media_response:
                            if media_response.status != 200:
                                continue
                                
                            media_data = await media_response.json()
                            items = media_data.get('items', [])
                            
                            logger.debug(f"Found {len(items)} media items for page '{page_title}'")
                            
                            # Look for good images
                            for item in items:
                                if item.get('type') != 'image':
                                    continue
                                
                                title = item.get('title', '').lower()
                                
                                # Skip common non-relevant images
                                skip_patterns = [
                                    'commons-logo', 'edit-icon', 'wikimedia', 'stub',
                                    'ambox', 'crystal', 'nuvola', 'dialog', 'system',
                                    'red_x', 'green_check', 'question_mark', 'infobox',
                                    'arrow', 'symbol', 'disambiguation', 'flag'
                                ]
                                
                                if any(pattern in title for pattern in skip_patterns):
                                    continue
                                
                                # Prefer images with good extensions and score them
                                score = 0
                                if any(ext in title for ext in ['.jpg', '.jpeg']):
                                    score += 3
                                elif any(ext in title for ext in ['.png', '.webp']):
                                    score += 2
                                
                                # Prefer images that contain keywords from search term
                                search_words = search_term.lower().split()
                                for word in search_words:
                                    if word in title and len(word) > 2:  # Avoid short words
                                        score += 1
                                
                                all_potential_images.append((score, item['title']))
                    
                    # Sort by score and return best images
                    all_potential_images.sort(reverse=True, key=lambda x: x[0])
                    
                    if all_potential_images:
                        # Return up to max_images best images with improved URLs
                        selected_images = []
                        for score, image_title in all_potential_images[:max_images]:
                            # Use different URL format that's more reliable for Telegram
                            # Add width parameter to ensure reasonable image size
                            image_url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(image_title)}?width=800"
                            selected_images.append(image_url)
                            logger.debug(f"Selected image: {image_title} (score: {score})")
                        
                        return selected_images
        
        except Exception as e:
            logger.debug(f"Error searching Wikipedia {lang} for '{search_term}': {e}")
            return []
        
        return []

    async def get_wikipedia_image(self, search_keywords: str) -> str | None:
        """Get single image from Wikipedia using search keywords (backward compatibility).
        
        Args:
            search_keywords: Search keywords from GPT response
            
        Returns:
            Image URL if found, None otherwise
        """
        images = await self.get_wikipedia_images(search_keywords, max_images=1)
        return images[0] if images else None

    async def get_nearby_fact_with_history(self, lat: float, lon: float, cache_key: str | None = None) -> str:
        """Get fact for static location with history tracking to avoid repetition.
        
        Args:
            lat: Latitude coordinate
            lon: Longitude coordinate  
            cache_key: Cache key for the location (coordinates or search keywords)
            
        Returns:
            A location name and an interesting fact about it
        """
        # Get previous facts for this location if we have a cache key
        previous_facts = []
        if cache_key:
            previous_facts = self.static_history.get_previous_facts(cache_key)
            if previous_facts:
                logger.info(f"Found {len(previous_facts)} previous facts for {cache_key}: {previous_facts}")
            else:
                logger.info(f"No previous facts found for {cache_key}")
        
        # Get fact using existing method but with previous facts
        logger.info(f"Calling get_nearby_fact with {len(previous_facts)} previous facts")
        if previous_facts:
            logger.info(f"Previous facts being sent to AI: {previous_facts}")
        fact_response = await self.get_nearby_fact(lat, lon, is_live_location=False, previous_facts=previous_facts)
        
        # Parse the response to extract place and fact for history
        if cache_key:
            lines = fact_response.split("\n")
            place = "рядом с вами"
            fact = fact_response
            
            # Try to parse structured response
            for i, line in enumerate(lines):
                if line.startswith("Локация:"):
                    place = line.replace("Локация:", "").strip()
                elif line.startswith("Интересный факт:"):
                    # Join all lines after Интересный факт: as the fact might be multiline
                    fact_lines = []
                    fact_lines.append(line.replace("Интересный факт:", "").strip())
                    for j in range(i + 1, len(lines)):
                        if lines[j].strip():
                            fact_lines.append(lines[j].strip())
                    fact = " ".join(fact_lines)
                    break
            
            # Add to history
            logger.info(f"Adding fact to history for {cache_key}: {place}")
            self.static_history.add_fact(cache_key, place, fact)
            
            # Log cache stats after adding
            stats = self.static_history.get_cache_stats()
            logger.info(f"Static location cache after add: {stats['locations']} locations, {stats['total_facts']} total facts")
        
        return fact_response


# Global client instance - will be initialized lazily
_openai_client: OpenAIClient | None = None


def get_openai_client() -> OpenAIClient:
    """Get or create the global OpenAI client instance."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAIClient()
    return _openai_client
