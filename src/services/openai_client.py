"""OpenAI client for generating location-based facts."""

import logging
import os
import re

import aiohttp
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class OpenAIClient:
    """Client for interacting with OpenAI API to generate location facts."""

    def __init__(self, api_key: str | None = None):
        """Initialize OpenAI client.

        Args:
            api_key: OpenAI API key. If None, will use OPENAI_API_KEY env var.
        """
        self.client = AsyncOpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))

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
                "ПРИНЦИПЫ ДОСТОВЕРНОСТИ:\n"
                "• ПРИОРИТЕТ: Стремитесь к максимальной точности и достоверности\n"
                "• НЕ ВЫДУМЫВАЙТЕ: Полагайтесь только на знания из обучения\n"
                "• ПРОВЕРЯЙТЕ: Убедитесь в правдивости каждого факта перед его изложением\n"
                "• СТРОГАЯ ИЕРАРХИЯ БЛИЗОСТИ:\n"
                "  1. ПРИОРИТЕТ: места в радиусе до 300 метров (5-7 минут пешком)\n"
                "  2. Допустимо: до 500-700м (10-12 минут пешком)\n"
                "  3. МАКСИМУМ: до 1км (15 минут пешком)\n"
                "  4. ЛУЧШЕ честно сказать 'поблизости ничего особенного' чем выбрать слишком далёкое место\n\n"
                "⚠️ В больших городах (Париж, Лондон, Москва) ВСЕГДА есть что-то интересное рядом — ищите внимательнее!\n\n"
                "КАЧЕСТВО ФАКТОВ:\n"
                "Стремитесь к уровню качества фактов как в Atlas Obscura — необычные, неочевидные, "
                "но достоверные детали о местах. Ищите скрытые истории, архитектурные секреты, "
                "малоизвестные исторические события, культурные особенности.\n\n"
                "🚨 КРИТИЧЕСКОЕ ПРЕДУПРЕЖДЕНИЕ: НЕ ВЫДУМЫВАЙТЕ ФАКТЫ!\n"
                "• Лучше сказать 'информации недостаточно', чем придумать детали\n"
                "• Каждое название, дата, имя должны быть из реальных знаний\n"
                "• Если сомневаетесь в точности — не включайте этот факт\n\n"
                "Весь ответ должен быть на русском языке."
            )

            # Handle previous facts for live location
            previous_facts_text = ""
            if is_live_location and previous_facts:
                previous_facts_text = (
                    "\n\nРАНЕЕ РАССКАЗАННЫЕ ФАКТЫ (НЕ ПОВТОРЯЙТЕ):\n"
                    + "\n".join(
                        [f"- {fact}" for fact in previous_facts[-5:]]
                    )  # Last 5 facts
                    + "\n\nВыберите ДРУГУЮ тему или аспект этого места!\n"
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
                    "   А) ПРИОРИТЕТ: что-то в радиусе до 300м? (5-7 минут пешком)\n"
                    "   Б) Допустимо: до 500-700м (10-12 минут пешком)\n"
                    "   В) МАКСИМУМ: до 1км (15 минут пешком)\n"
                    "   Г) В Париже/Лондоне/Москве ВСЕГДА есть что-то рядом — ищите лучше!\n\n"
                    "🚫 НЕ ВЫБИРАЙТЕ: далёкие достопримечательности, другие районы, общие факты о городе\n\n"
                "⚠️ КРИТИЧЕСКИ ВАЖНО - ДОСТОВЕРНОСТЬ:\n"
                "• ТОЛЬКО реально существующие места и здания\n"
                "• ТОЛЬКО проверенные исторические факты из вашего обучения\n"
                "• НЕ ВЫДУМЫВАЙТЕ названия зданий, даты, имена, события\n"
                "• Если не знаете точно — лучше скажите 'информации недостаточно'\n"
                "• ПРОВЕРЬТЕ каждую деталь перед ответом\n\n"
                    "ВАЖНО: Создайте ПОДРОБНЫЙ и РАЗВЕРНУТЫЙ факт (примерно 100-120 слов), но ТОЛЬКО из достоверных знаний. Включите:\n"
                    "- Исторический контекст и даты (только если уверены в точности)\n"
                    "- Интересные детали и подробности (только проверенные)\n"
                    "- Связи с известными личностями или событиями (только достоверные)\n"
                    "- Архитектурные особенности или культурное значение (только если точно знаете)\n\n"
                    "Финальный ответ в формате:\n"
                    "Локация: [Конкретное название места]\n"
                    "Поиск: [Ключевые слова для точного поиска: ОРИГИНАЛЬНОЕ название на местном языке + город + страна. Например: 'Louvre Museum Paris France' или 'Красная площадь Москва Россия']\n"
                    "Интересный факт: [Развернутый факт с историческими подробностями, примерно 100-120 слов]"
                )
            else:
                # Concise prompt for static location (gpt-4.1)
                user_prompt = (
                    f"Проанализируйте координаты: {lat}, {lon}\n\n"
                    "Определите ближайшую достопримечательность или интересное место и предоставьте краткий факт.\n\n"
                    "СТРОГАЯ ИЕРАРХИЯ БЛИЗОСТИ:\n"
                    "1. ПРИОРИТЕТ: объекты в радиусе до 300м (5-7 минут пешком)\n"
                    "2. Допустимо: до 500-700м (10-12 минут пешком)\n"
                    "3. МАКСИМУМ: до 1км (15 минут пешком)\n"
                    "4. В больших городах всегда есть что-то рядом!\n\n"
                    "🚫 НЕ ВЫБИРАЙТЕ далёкие достопримечательности!\n\n"
                    "⚠️ КРИТИЧЕСКИ ВАЖНО - ДОСТОВЕРНОСТЬ:\n"
                    "• ТОЛЬКО реально существующие места и здания\n"
                    "• ТОЛЬКО проверенные исторические факты из вашего обучения\n"
                    "• НЕ ВЫДУМЫВАЙТЕ названия зданий, даты, имена, события\n"
                    "• Если не знаете точно — лучше скажите 'информации недостаточно'\n"
                    "• ПРОВЕРЬТЕ каждую деталь перед ответом\n\n"
                    "ВАЖНО: Факт должен быть КРАТКИМ (60-80 слов) но ДОСТОВЕРНЫМ. Включите только:\n"
                    "- Проверенную историческую информацию\n"
                    "- Точные детали или даты (если уверены)\n"
                    "- Достоверные особенности места\n\n"
                    "Финальный ответ в формате:\n"
                    "Локация: [Конкретное название места]\n"
                    "Поиск: [Ключевые слова для точного поиска: ОРИГИНАЛЬНОЕ название на местном языке + город + страна. Например: 'Louvre Museum Paris France' или 'Красная площадь Москва Россия']\n"
                    "Интересный факт: [Краткий, но достоверный факт, 60-80 слов]"
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

        # Try Nominatim first (faster and often more accurate for landmarks)
        nominatim_coords = await self.get_coordinates_from_nominatim(search_keywords)
        if nominatim_coords:
            logger.info(f"Found Nominatim coordinates: {nominatim_coords}")
            return nominatim_coords

        # Try variations of search keywords if Nominatim fails
        logger.info(f"Nominatim failed for: {search_keywords}")

        # Try simpler search - just the main place name
        if " + " in search_keywords or "+" in search_keywords:
            # Extract first part before + sign
            simple_keywords = search_keywords.split("+")[0].strip()
            logger.info(f"Trying simplified search: {simple_keywords}")
            simple_coords = await self.get_coordinates_from_nominatim(simple_keywords)
            if simple_coords:
                logger.info(f"Found coordinates with simplified search: {simple_coords}")
                return simple_coords

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


# Global client instance - will be initialized lazily
_openai_client: OpenAIClient | None = None


def get_openai_client() -> OpenAIClient:
    """Get or create the global OpenAI client instance."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAIClient()
    return _openai_client
