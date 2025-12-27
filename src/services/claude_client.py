"""Claude client for generating location-based facts using Anthropic API."""

import asyncio
import logging
import os
import re
import time
from urllib.parse import quote

import aiohttp
from anthropic import AsyncAnthropic

from .web_search import get_web_search_service

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
            self._cache[search_keywords]["facts"] = self._cache[search_keywords][
                "facts"
            ][-10:]

        logger.debug(f"Added fact to static location history: {place}")

    def _cleanup_expired(self):
        """Remove expired entries and limit cache size."""
        current_time = time.time()

        # Remove expired entries
        expired_keys = [
            key
            for key, entry in self._cache.items()
            if (current_time - entry["timestamp"]) >= self._ttl_seconds
        ]
        for key in expired_keys:
            del self._cache[key]

        # Limit cache size
        if len(self._cache) > self._max_entries:
            # Remove oldest entries
            sorted_items = sorted(
                self._cache.items(), key=lambda x: x[1]["timestamp"]
            )
            keys_to_remove = [
                item[0] for item in sorted_items[: len(self._cache) - self._max_entries]
            ]
            for key in keys_to_remove:
                del self._cache[key]

    def get_cache_stats(self) -> dict:
        """Get cache statistics for debugging."""
        self._cleanup_expired()
        total_facts = sum(len(entry["facts"]) for entry in self._cache.values())
        return {
            "locations": len(self._cache),
            "total_facts": total_facts,
            "oldest_entry": min(
                (entry["timestamp"] for entry in self._cache.values()), default=0
            ),
        }


class ClaudeClient:
    """Client for interacting with Anthropic Claude API to generate location facts."""

    # Model constants
    MODEL_OPUS = "claude-opus-4-5-20251101"
    MODEL_SONNET = "claude-sonnet-4-20250514"

    def __init__(self, api_key: str | None = None):
        """Initialize Claude client.

        Args:
            api_key: Anthropic API key. If None, will use ANTHROPIC_API_KEY env var.
        """
        self.client = AsyncAnthropic(
            api_key=api_key or os.getenv("ANTHROPIC_API_KEY")
        )
        self.web_search = get_web_search_service()
        self.static_history = StaticLocationHistory()
        # Lightweight caches for Wikimedia pipeline
        self._qid_cache: dict[str, tuple[str, float]] = {}
        self._p18_cache: dict[str, tuple[str, float]] = {}
        self._fileinfo_cache: dict[str, tuple[dict, float]] = {}
        self._image_cache_ttl_seconds = 24 * 3600
        # Semaphore to limit concurrent API requests
        self._api_semaphore = asyncio.Semaphore(3)

    def _get_russian_style_instructions(self) -> str:
        """Get detailed Russian language style instructions for Atlas Obscura quality."""
        return """
СПЕЦИАЛЬНЫЕ ТРЕБОВАНИЯ ДЛЯ РУССКОГО ЯЗЫКА (стиль Atlas Obscura):

СТИЛЬ ИЗЛОЖЕНИЯ:
- Пишите живым, образным языком — как будто рассказываете друзьям потрясающую историю за чашкой кофе
- Начинайте с самого удивительного факта, а не с общих слов о здании или районе
- Используйте конкретные детали: не "старинное здание", а "дом с горгульями 1902 года"
- Добавляйте сенсорные детали: что можно увидеть, потрогать, заметить именно сегодня

СТРУКТУРА ФАКТА:
1. Захватывающее начало — сразу удивительная деталь ("В подвале этого дома до сих пор видны кольца...")
2. Краткий исторический контекст — кто, когда, зачем (одно предложение с именем и датой)
3. Почему это важно/удивительно — связь с большой историей или неожиданный поворот
4. Что можно увидеть сегодня — конкретные детали для посетителя

ЯЗЫК И ГРАММАТИКА:
- Активный залог: "Здесь расстреляли...", а не "Здесь был расстрелян..."
- Тире для драматических пауз: "В этом доме — настоящая тайна"
- Избегайте канцелярита: никаких "является", "представляет собой", "находится"
- Точные даты и имена: "в 1924 году Маяковский", а не "в 20-х годах поэт"

ПРИМЕРЫ ХОРОШЕГО СТИЛЯ:
✓ "Под штукатуркой этого дома до сих пор скрыты пулевые отверстия — в октябре 1941 года здесь три дня держали оборону курсанты военного училища."
✓ "За невзрачной железной дверью в арке сохранился вход в систему подземных ходов Китай-города — их использовали купцы для тайной переправки контрабанды."
✗ "Это здание является памятником архитектуры и представляет собой образец неоклассицизма."
✗ "В данном месте находился известный ресторан."

ЗОЛОТОЕ ПРАВИЛО: Каждое предложение должно добавлять новую конкретную информацию, а не повторять уже сказанное другими словами.

ТОПОНИМЫ И ИМЕНА:
- Всегда используйте русские названия улиц, площадей, районов и достопримечательностей
- Имена собственные пишите в принятой русской транскрипции (например, «Жорж-Эжен Осман», «Пьер Кюри»)
- Не переключайтесь на другие языки внутри русского текста без необходимости"""

    def _build_system_prompt_russian(
        self, is_live_location: bool, web_search_results: str = ""
    ) -> str:
        """Build system prompt for Russian language - separate for quality."""

        web_context = ""
        if web_search_results:
            web_context = f"""

РЕЗУЛЬТАТЫ ПОИСКА В ИНТЕРНЕТЕ:
{web_search_results}

Используйте эти результаты для верификации фактов. Цитируйте источники в разделе "Источники"."""

        base_rules = f"""Ты — автор фактов для Atlas Obscura на русском языке. Твоя миссия: найти самую удивительную, конкретную, проверенную деталь о РЕАЛЬНОМ МЕСТЕ рядом с указанными координатами.

ТЫ — АВТОР ФАКТОВ, А НЕ ПОИСКОВЫЙ АССИСТЕНТ. Никогда не извиняйся, не проси разрешения, не объясняй трудности. Либо напиши полноценный факт, либо верни [[NO_POI_FOUND]].
{web_context}

МЕТОД РАБОТЫ:
1) Локация: Найди реальное здание/памятник/место (не пустую точку). Точный адрес с номером дома.
   **СТРОГОЕ ПРАВИЛО ДИСТАНЦИИ**: настоятельно предпочтительно в пределах 200м, приемлемо до 400м,
   абсолютный максимум 600м ТОЛЬКО если ничего ближе не существует.
2) Исследование: A) конкретное здание/место в точке B) непосредственная близость (<100м) C) ближайший район (100-400м) ТОЛЬКО если A/B не имеют интересных фактов.
3) Видно сегодня: конкретные детали, которые посетитель может увидеть (никаких воображаемых табличек/надписей/меток).

**ATLAS OBSCURA СТИЛЬ - ФОКУС НА НЕОБЫЧНОМ:**
- Ищи СКРЫТЫЕ, ЗАБЫТЫЕ, ПРОТИВОРЕЧАЩИЕ ИНТУИЦИИ детали, о которых местные жители НЕ знают
- НЕ пиши про известные туристические достопримечательности (Эйфелева башня, Лувр, Нотр-Дам)
- Ищи необычные дома, секретные проходы, забытые мемориалы, странные архитектурные детали
- ПЛАНКА КАЧЕСТВА: Заставит ли этот факт человека остановиться и посмотреть внимательнее? Если нет - копай глубже.

КРИТИЧЕСКОЕ ТРЕБОВАНИЕ - ВЕРИФИКАЦИЯ ФАКТОВ:
- КАЖДЫЙ факт ДОЛЖЕН быть подтвержден надежным источником из веб-поиска
- НЕ выдумывай детали, которых нет в источниках (даты, имена, события)
- Если источники противоречат друг другу - используй только общепризнанные факты
- НИКОГДА не пиши "сердца польских королей", "серебряные урны", "тайные подземелья" без ПРЯМОГО подтверждения в источниках
- Если не можешь найти достаточно фактов в источниках - лучше верни [[NO_POI_FOUND]]

КРИТИЧЕСКОЕ ТРЕБОВАНИЕ - ТОЧНОСТЬ КООРДИНАТ:
- Coordinates ДОЛЖНЫ быть координатами ОПИСЫВАЕМОГО места, НЕ координатами пользователя!
- Используй точные координаты из веб-поиска или карт (например, Google Maps, OpenStreetMap)
- Если координаты неточные или неизвестны - используй Search для геокодирования
- ПРОВЕРЬ: расстояние от пользователя должно быть <2км (иначе это явно неправильное место!)

СТРОГО ЗАПРЕЩЕНО:
- **ПОПСОВЫЕ ТУРИСТИЧЕСКИЕ МЕСТА**: Собор Парижской Богоматери, Пантеон, Эйфелева башня, Лувр, Триумфальная арка, Сакре-Кёр - НЕТ!
- Мета-факты о координатах как "безымянных"/"пустых"
- Упоминание технических инструментов (Nominatim, Overpass, геокодирование, панорамы, API)
- Факты о процессе поиска
- Неправильные даты, ложные атрибуции, выдуманные детали
- ЛЮБЫЕ извинения или просьбы о разрешении ("Извините", "могу проверить", "нужна проверка")
- Временные заглушки типа "рядом с вами" без конкретного адреса
- Факты, которые можно найти в любом туристическом путеводителе

ЗАПРЕЩЁННЫЕ ФРАЗЫ (НИКОГДА НЕ ИСПОЛЬЗОВАТЬ):
- "Извините — не удалось..."
- "Временно недоступен..."
- "Могу повторить проверку..."
- "Нужна быстрая проверка..."
- "мне нужно проверить..."

ЕСЛИ НЕ МОЖЕШЬ НАЙТИ ФАКТ: Верни ТОЛЬКО "[[NO_POI_FOUND]]" — ничего больше.

{self._get_russian_style_instructions()}"""

        if is_live_location:
            return base_rules + """

ФОРМАТ ОТВЕТА (живая локация, 100-120 слов):
<answer>
Location: [Точный адрес / название здания / перекрёсток]
Coordinates: [LAT, LON точки, которую описываешь, НЕ координаты пользователя! 6 знаков после запятой]
Search: [Запрос для геокодирования через Nominatim: "Название, Улица, Город"]
Interesting fact: [Удивительное начало → История с именами/датами → Почему важно → Что видно сегодня. Без URL в тексте.]
Источники:
- [Краткое название] — [URL]
- [Краткое название] — [URL]
</answer>"""
        else:
            return base_rules + """

ФОРМАТ ОТВЕТА (статичная локация, 60-80 слов):
<answer>
Location: [Точное название места — конкретное здание или локация]
Coordinates: [LAT, LON точки, которую описываешь, НЕ координаты пользователя! 6 знаков после запятой]
Search: [Запрос для Nominatim: "Название, Улица, Город"]
Interesting fact: [Удивительная деталь → Краткий контекст с датой/именем → Что видно сегодня. Без URL в тексте.]
Источники:
- [Краткое название] — [URL]
- [Краткое название] — [URL]
</answer>"""

    def _build_system_prompt_english(
        self,
        user_language: str,
        is_live_location: bool,
        web_search_results: str = "",
    ) -> str:
        """Build system prompt for non-Russian languages."""

        web_context = ""
        if web_search_results:
            web_context = f"""

WEB SEARCH RESULTS:
{web_search_results}

Use these results to verify facts. Cite sources in the Sources section."""

        base_rules = f"""You are an Atlas Obscura fact writer. Your mission: find the most surprising, specific, verified detail about a REAL PLACE near the given coordinates.

YOU ARE A FACT WRITER, NOT A SEARCH ASSISTANT. Never apologize, never ask permission, never explain difficulties. Either write a complete fact or return [[NO_POI_FOUND]].
{web_context}

LANGUAGE: Write your response entirely in {user_language}.

METHOD:
1) Location: Find a real building/monument/place (not empty point). Exact address with house number.
   **STRICT DISTANCE RULE**: strongly prefer within 200m, acceptable up to 400m,
   absolute max 600m ONLY if nothing closer exists.
2) Research: A) specific building/place at exact spot B) immediate vicinity (<100m) C) nearby area (100-400m) ONLY if A/B have no interesting facts.
3) Visible today: concrete details a visitor can see (no imaginary plaques/signatures/marks).

**ATLAS OBSCURA STYLE - FOCUS ON UNUSUAL:**
- Seek HIDDEN, FORGOTTEN, COUNTERINTUITIVE details that locals don't know
- DO NOT write about famous tourist landmarks (Eiffel Tower, Louvre, Notre-Dame)
- Look for unusual houses, secret passages, forgotten memorials, strange architectural details
- QUALITY BAR: Would this fact make someone stop walking and look closer? If not, dig deeper.

CRITICAL REQUIREMENT - FACT VERIFICATION:
- EVERY fact MUST be confirmed by reliable sources from web search
- DO NOT invent details not present in sources (dates, names, events)
- If sources contradict - use only universally accepted facts
- NEVER write "hearts of Polish kings", "silver urns", "secret tunnels" without DIRECT confirmation in sources
- If you cannot find enough facts in sources - better return [[NO_POI_FOUND]]

CRITICAL REQUIREMENT - COORDINATE ACCURACY:
- Coordinates MUST be coordinates of the DESCRIBED place, NOT user's coordinates!
- Use precise coordinates from web search or maps (e.g., Google Maps, OpenStreetMap)
- If coordinates are imprecise or unknown - use Search field for geocoding
- CHECK: distance from user should be <2km (otherwise it's clearly the wrong place!)

WRITING STYLE (Atlas Obscura):
- Start with the most surprising detail immediately - no generic introductions
- Include at least one specific name and exact date/year
- Each sentence must add NEW concrete information (no repetition)
- Focus on interesting, unusual, or historical details
- QUALITY BAR: Would this fact make someone stop walking and look closer?

STRICTLY FORBIDDEN:
- **TOURIST TRAP LANDMARKS**: Notre-Dame Cathedral, Pantheon, Eiffel Tower, Louvre, Arc de Triomphe, Sacré-Cœur - NO!
- Meta-facts about coordinates being "unnamed"/"empty"
- Mentioning technical tools (Nominatim, Overpass, reverse geocoding, API)
- Facts about the search process itself
- Wrong dates, false attributions, invented details
- ANY form of apologies or meta-commentary
- Temporary placeholders like "near you" without specific address
- Facts you can find in any tourist guidebook

IF YOU CANNOT FIND A FACT: Return ONLY "[[NO_POI_FOUND]]" - nothing else."""

        if is_live_location:
            return base_rules + f"""

OUTPUT FORMAT (live location, 100-120 words):
<answer>
Location: [Exact address / building name / intersection]
Coordinates: [LAT, LON of the point being described, NOT user location! 6 decimal places]
Search: [Nominatim query: "Name, Street, City"]
Interesting fact: [Surprising opening → Human story with names/dates → Why it matters → What to see today. No URLs in text.]
Sources:
- [Concise title] — [URL]
- [Concise title] — [URL]
</answer>

Write in {user_language}."""
        else:
            return base_rules + f"""

OUTPUT FORMAT (static location, 60-80 words):
<answer>
Location: [Exact place name - specific building or location]
Coordinates: [LAT, LON of the point being described, NOT user location! 6 decimal places]
Search: [Nominatim query: "Name, Street, City"]
Interesting fact: [Surprising detail → Quick context with date/name → What visitors can see today. No URLs in text.]
Sources:
- [Concise title] — [URL]
- [Concise title] — [URL]
</answer>

Write in {user_language}."""

    def _build_user_prompt(
        self,
        lat: float,
        lon: float,
        is_live_location: bool,
        previous_facts: list | None,
        user_language: str,
    ) -> str:
        """Build user prompt with coordinates and previous facts."""

        prev_block = ""
        if previous_facts:
            place_names = []
            fact_entries = []
            for entry in previous_facts[-5:]:
                if ": " in entry:
                    place_name = entry.split(": ", 1)[0].strip()
                    if place_name:
                        place_names.append(place_name)
                fact_entries.append(f"- {entry}")

            prev_text = "\n".join(fact_entries)

            if place_names:
                places_list = ", ".join([f'"{p}"' for p in place_names])
                if user_language == "ru":
                    prev_block = f"""

УЖЕ УПОМЯНУТЫЕ ФАКТЫ:
{prev_text}

⛔ ЗАПРЕЩЁННЫЕ МЕСТА (НЕ ИСПОЛЬЗОВАТЬ — найди ДРУГОЕ место!):
{places_list}

КРИТИЧНО: Выбери ПОЛНОСТЬЮ ДРУГОЕ место. НЕ упоминай те же здания/памятники/локации под другим названием."""
                else:
                    prev_block = f"""

PREVIOUS FACTS ALREADY MENTIONED:
{prev_text}

⛔ FORBIDDEN PLACES (DO NOT USE - find a DIFFERENT location!):
{places_list}

CRITICAL: Choose a COMPLETELY DIFFERENT place. Do NOT mention the same building/monument/location with a different name."""

        if is_live_location:
            if user_language == "ru":
                return f"""Проанализируй координаты: {lat}, {lon}

КРИТИЧНО: Это ТЕКУЩЕЕ местоположение пользователя. Упоминай только места, которые реально находятся рядом (≤500м) с этими точными координатами. НЕ притягивай знаменитые достопримечательности из других частей города.{prev_block}

ЖЁСТКИЕ ОГРАНИЧЕНИЯ:
- ПРИОРИТЕТ РАССТОЯНИЯ: Сначала проверь 0-400м, затем 400-800м, максимум 1200м. Всегда выбирай БЛИЖАЙШИЙ интересный объект.
- НИКОГДА не пиши мета-факты о самой координатной точке как "безымянной" или "пустой"
- Если в точке нет POI, ищи систематически: сначала непосредственная близость (0-100м), затем рядом (100-400м).

Найди самый удивительный проверенный факт об ЭТОМ КОНКРЕТНОМ месте."""
            else:
                return f"""Analyze coordinates: {lat}, {lon}

CRITICAL: This is the user's CURRENT location. Only mention places actually at or very near (≤500m) these exact coordinates. Do NOT pull famous landmarks from other parts of the city.{prev_block}

HARD CONSTRAINTS:
- DISTANCE PRIORITY: First check 0-400m, then 400-800m, max 1200m if needed. Always choose the CLOSEST interesting POI.
- NEVER write meta-facts about the coordinate being "unnamed" or "empty"
- If exact point has no POI, search systematically: immediate area first (0-100m), then nearby (100-400m).

Find the most surprising verified fact about THIS EXACT location."""
        else:
            if user_language == "ru":
                return f"""Координаты для анализа:
<coordinates>
Широта: {lat}
Долгота: {lon}
</coordinates>{prev_block}

Найди один краткий, удивительный, проверенный факт.

ЖЁСТКИЕ ОГРАНИЧЕНИЯ:
- ПРИОРИТЕТ РАССТОЯНИЯ: Сначала 0-400м, затем 400-800м, максимум 1200м.
- НИКОГДА не пиши о координатах как "безымянных" или "пустых"

Если не можешь найти реальное место (здание/POI) в радиусе 1200м с проверяемым фактом и источниками, выведи ровно этот токен на одной строке:
[[NO_POI_FOUND]]"""
            else:
                return f"""Coordinates to analyze:
<coordinates>
Latitude: {lat}
Longitude: {lon}
</coordinates>{prev_block}

Find one concise, surprising, verified fact.

HARD CONSTRAINTS:
- DISTANCE PRIORITY: First 0-400m, then 400-800m, max 1200m.
- NEVER write about coordinates being "unnamed" or "empty"

If you cannot find any real place (building/POI) within 1200m with a verifiable fact and sources, output exactly this token on a single line:
[[NO_POI_FOUND]]"""

    async def get_nearby_fact(
        self,
        lat: float,
        lon: float,
        is_live_location: bool = False,
        previous_facts: list = None,
        user_id: int = None,
        force_reasoning_none: bool = False,  # Kept for API compatibility, not used
    ) -> str:
        """Get an interesting fact about a location.

        Args:
            lat: Latitude coordinate
            lon: Longitude coordinate
            is_live_location: If True, generate more detailed fact
            previous_facts: List of previously sent facts to avoid repetition
            user_id: User ID to check premium status and language
            force_reasoning_none: Unused, kept for API compatibility

        Returns:
            A location name and an interesting fact about it

        Raises:
            Exception: If Claude API call fails
        """
        try:
            # Get user preferences
            user_language = "ru"  # Default to Russian
            user_model = self.MODEL_OPUS  # Default model

            if user_id:
                try:
                    from .async_donors_wrapper import get_async_donors_db
                    donors_db = await get_async_donors_db()
                    user_language = await donors_db.get_user_language(user_id)

                    # Check user model preference
                    stored_model = await donors_db.get_user_model(user_id)
                    if stored_model == "claude-sonnet-4-20250514":
                        user_model = self.MODEL_SONNET
                except Exception as e:
                    logger.warning(f"Failed to get user preferences: {e}")

            # Perform web search for context
            web_search_results = ""
            try:
                # Search for UNUSUAL, HIDDEN places (not tourist landmarks!)
                # Atlas Obscura style: forgotten, counterintuitive, locals don't know
                search_queries = [
                    f"hidden gems unusual places {lat},{lon}",
                    f"obscure historical sites secrets {lat} {lon}",
                    f"forgotten places Atlas Obscura {lat},{lon}",
                ]

                all_results = []
                for query in search_queries[:3]:
                    results = await self.web_search.search(query, count=2)
                    all_results.extend(results)

                if all_results:
                    web_search_results = self.web_search.format_results_for_prompt(
                        all_results[:5]
                    )
                    logger.info(f"Web search returned {len(all_results)} results")
            except Exception as e:
                logger.warning(f"Web search failed: {e}")

            # Build prompts based on language
            if user_language == "ru":
                system_prompt = self._build_system_prompt_russian(
                    is_live_location, web_search_results
                )
            else:
                system_prompt = self._build_system_prompt_english(
                    user_language, is_live_location, web_search_results
                )

            user_prompt = self._build_user_prompt(
                lat, lon, is_live_location, previous_facts, user_language
            )

            # Call Claude API
            logger.info(f"Calling Claude API (model={user_model})")

            async with self._api_semaphore:
                response = await self.client.messages.create(
                    model=user_model,
                    max_tokens=2048,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )

            # Extract content from response
            content = ""
            if response.content:
                for block in response.content:
                    if hasattr(block, "text"):
                        content += block.text

            if not content:
                logger.error("Claude returned empty response")
                raise ValueError("Empty response from Claude")

            # Handle NO_POI_FOUND - retry with different approach
            if "[[NO_POI_FOUND]]" in content:
                logger.info("NO_POI_FOUND detected, retrying with expanded search")

                # Try with expanded search prompt
                expanded_prompt = user_prompt + "\n\nПРИМЕЧАНИЕ: Расширь радиус поиска до 1500м. Найди ЛЮБОЙ интересный исторический объект поблизости." if user_language == "ru" else user_prompt + "\n\nNOTE: Expand search radius to 1500m. Find ANY interesting historical object nearby."

                async with self._api_semaphore:
                    retry_response = await self.client.messages.create(
                        model=user_model,
                        max_tokens=2048,
                        system=system_prompt,
                        messages=[{"role": "user", "content": expanded_prompt}],
                    )

                if retry_response.content:
                    retry_content = ""
                    for block in retry_response.content:
                        if hasattr(block, "text"):
                            retry_content += block.text
                    if retry_content and "[[NO_POI_FOUND]]" not in retry_content:
                        content = retry_content

            logger.info(f"Generated fact for location {lat},{lon}")
            return content.strip()

        except Exception as e:
            logger.error(f"Failed to generate fact for {lat},{lon}: {e}")
            raise

    async def get_precise_coordinates(
        self, place_name: str, area_description: str
    ) -> tuple[float, float] | None:
        """Get precise coordinates for a location.

        Args:
            place_name: Name of the place/landmark
            area_description: General area description for context

        Returns:
            Tuple of (latitude, longitude) if found, None otherwise
        """
        # Use Nominatim directly - more reliable than asking AI
        return await self.get_coordinates_from_nominatim(place_name)

    async def get_coordinates_from_nominatim(
        self, place_name: str, user_lat: float = None, user_lon: float = None
    ) -> tuple[float, float] | None:
        """Get coordinates using OpenStreetMap Nominatim service.

        Args:
            place_name: Name of the place to search
            user_lat: User's latitude to prioritize nearby results
            user_lon: User's longitude to prioritize nearby results

        Returns:
            Tuple of (latitude, longitude) if found, None otherwise
        """
        search_strategies = []

        base_params = {
            "format": "json",
            "limit": 5,
            "addressdetails": 1,
            "namedetails": 1,
        }

        if user_lat is not None and user_lon is not None:
            base_params.update(
                {
                    "viewbox": f"{user_lon-0.02},{user_lat-0.02},{user_lon+0.02},{user_lat+0.02}",
                    "bounded": "0",
                }
            )

        search_strategies.append(
            {
                **base_params,
                "q": place_name,
                "extratags": 1,
                "accept-language": "fr,en,ru",
            }
        )

        if "," in place_name:
            parts = [p.strip() for p in place_name.split(",")]
            if len(parts) >= 2:
                structured_params = {
                    "format": "json",
                    "limit": 5,
                    "addressdetails": 1,
                    "namedetails": 1,
                }

                if len(parts) == 3:
                    structured_params["amenity"] = parts[0]
                    structured_params["street"] = parts[1]
                    structured_params["city"] = parts[2]
                elif len(parts) == 2:
                    street_indicators = ["rue", "avenue", "boulevard", "street", "road"]
                    if any(
                        indicator in parts[0].lower() for indicator in street_indicators
                    ):
                        structured_params["street"] = parts[0]
                        structured_params["city"] = parts[1]
                    else:
                        structured_params["amenity"] = parts[0]
                        structured_params["city"] = parts[1]

                search_strategies.append(structured_params)

        street_match = re.search(r"(\d+)\s+(.+)", place_name)
        if street_match:
            number = street_match.group(1)
            rest = street_match.group(2)
            if "," in rest:
                street_parts = rest.split(",")
                search_strategies.append(
                    {
                        "format": "json",
                        "limit": 5,
                        "addressdetails": 1,
                        "street": f"{number} {street_parts[0].strip()}",
                        "city": street_parts[-1].strip()
                        if len(street_parts) > 1
                        else "Paris",
                    }
                )

        url = "https://nominatim.openstreetmap.org/search"
        headers = {"User-Agent": "BotVoyage/2.0 (Educational Project)"}

        async with aiohttp.ClientSession() as session:
            for i, params in enumerate(search_strategies):
                try:
                    logger.debug(
                        f"Trying Nominatim strategy {i+1}/{len(search_strategies)}"
                    )

                    async with session.get(
                        url, params=params, headers=headers, timeout=5
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data:
                                best_result = None
                                best_score = -1

                                for result in data:
                                    score = 0
                                    result_type = result.get("type", "")

                                    if result_type in [
                                        "building",
                                        "house",
                                        "amenity",
                                        "historic",
                                    ]:
                                        score += 3
                                    elif result_type in ["street", "road"]:
                                        score += 2
                                    elif result_type in ["suburb", "neighbourhood"]:
                                        score += 1

                                    display_name = result.get("display_name", "").lower()
                                    if (
                                        "paris" in place_name.lower()
                                        and "paris" in display_name
                                    ):
                                        score += 5
                                    elif (
                                        "москва" in place_name.lower()
                                        and "москва" in display_name
                                    ):
                                        score += 5

                                    importance = result.get("importance", 0)
                                    score += importance

                                    if score > best_score:
                                        best_score = score
                                        best_result = result

                                if best_result:
                                    lat = float(best_result["lat"])
                                    lon = float(best_result["lon"])

                                    if -90 <= lat <= 90 and -180 <= lon <= 180:
                                        logger.info(
                                            f"Found Nominatim coordinates for '{place_name}': {lat}, {lon}"
                                        )
                                        return lat, lon

                except Exception as e:
                    logger.debug(f"Strategy {i+1} failed: {e}")
                    continue

        logger.debug(f"No coordinates found in Nominatim for: {place_name}")
        return None

    async def get_coordinates_from_search_keywords(
        self, search_keywords: str, user_lat: float = None, user_lon: float = None
    ) -> tuple[float, float] | None:
        """Get coordinates using search keywords via Nominatim.

        Args:
            search_keywords: Search keywords from Claude response
            user_lat: User's current latitude for validation
            user_lon: User's current longitude for validation

        Returns:
            Tuple of (latitude, longitude) if found, None otherwise
        """
        logger.info(f"Searching coordinates for keywords: {search_keywords}")

        clean_keywords = search_keywords.replace('"', "").replace("'", "").strip()

        city_name = None
        common_cities = {
            "Paris": (48.8566, 2.3522, 15),
            "Москва": (55.7558, 37.6173, 30),
            "Moscow": (55.7558, 37.6173, 30),
            "London": (51.5074, -0.1278, 20),
            "New York": (40.7128, -74.0060, 25),
            "Санкт-Петербург": (59.9311, 30.3609, 20),
            "Saint Petersburg": (59.9311, 30.3609, 20),
            "St Petersburg": (59.9311, 30.3609, 20),
        }

        for city, (city_lat, city_lon, radius) in common_cities.items():
            if city in clean_keywords:
                city_name = city
                break

        nominatim_coords = await self.get_coordinates_from_nominatim(
            clean_keywords, user_lat, user_lon
        )
        if nominatim_coords:
            if city_name and not self._validate_city_coordinates(
                nominatim_coords[0], nominatim_coords[1], city_name
            ):
                logger.warning(
                    f"Coordinates {nominatim_coords} are not in {city_name}, rejecting"
                )
            else:
                logger.info(f"Found Nominatim coordinates: {nominatim_coords}")
                return nominatim_coords

        logger.info(f"Nominatim failed for original keywords: {search_keywords}")

        # Fallback patterns
        fallback_patterns = []

        if "," in search_keywords:
            parts = [p.strip() for p in search_keywords.split(",")]
            if len(parts) >= 2:
                street_indicators = [
                    "rue",
                    "avenue",
                    "boulevard",
                    "street",
                    "road",
                    "place",
                    "square",
                ]
                for i, part in enumerate(parts):
                    if any(
                        indicator in part.lower() for indicator in street_indicators
                    ):
                        if i < len(parts) - 1:
                            street_with_city = f"{part}, {parts[-1]}"
                            fallback_patterns.append(street_with_city)
                        if re.search(r"\d+", part):
                            fallback_patterns.append(part)
                        break

        fallback_patterns = [p.strip() for p in fallback_patterns if p and p.strip()]
        fallback_patterns = list(dict.fromkeys(fallback_patterns))

        for pattern in fallback_patterns:
            if pattern and pattern != search_keywords:
                logger.info(f"Trying fallback search: {pattern}")
                coords = await self.get_coordinates_from_nominatim(
                    pattern, user_lat, user_lon
                )
                if coords:
                    if user_lat and user_lon:
                        distance = self._calculate_distance(
                            user_lat, user_lon, coords[0], coords[1]
                        )
                        if distance > 50:
                            logger.warning(
                                f"Fallback coordinates {coords} are {distance:.1f}km away"
                            )
                            continue

                    logger.info(f"Found coordinates with fallback '{pattern}': {coords}")
                    return coords

        logger.warning(f"No coordinates found for keywords: {search_keywords}")
        return None

    async def parse_coordinates_from_response(
        self, response: str, user_lat: float = None, user_lon: float = None
    ) -> tuple[float, float] | None:
        """Parse coordinates from Claude response.

        Priority:
        1. Parse Coordinates: field directly from response (most accurate)
        2. Fallback to Search: keywords via Nominatim (less accurate)
        3. Fallback to Location: name via Nominatim (least accurate)

        Args:
            response: Claude response text
            user_lat: User's current latitude for validation
            user_lon: User's current longitude for validation

        Returns:
            Tuple of (latitude, longitude) if found, None otherwise
        """
        try:
            answer_match = re.search(r"<answer>(.*?)</answer>", response, re.DOTALL)
            if answer_match:
                answer_content = answer_match.group(1).strip()

                # PRIORITY 1: Parse Coordinates: field directly
                # This is what Claude explicitly provides - use it first!
                coordinates_match = re.search(
                    r"Coordinates:\s*([\d.]+),\s*([\d.]+)",
                    answer_content
                )
                if coordinates_match:
                    try:
                        lat = float(coordinates_match.group(1))
                        lon = float(coordinates_match.group(2))

                        # Validate coordinates are reasonable
                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                            # If user coordinates provided, check distance
                            if user_lat is not None and user_lon is not None:
                                distance = self._calculate_distance(
                                    user_lat, user_lon, lat, lon
                                )
                                # Reject if Claude's coordinates are more than 5km away
                                # (likely hallucination or wrong place)
                                if distance > 5:
                                    logger.warning(
                                        f"Coordinates from Claude ({lat}, {lon}) are {distance:.1f}km "
                                        f"from user ({user_lat}, {user_lon}), rejecting and using fallback"
                                    )
                                else:
                                    logger.info(
                                        f"Using coordinates directly from Claude: {lat}, {lon} "
                                        f"({distance:.1f}km from user)"
                                    )
                                    return (lat, lon)
                            else:
                                logger.info(f"Using coordinates directly from Claude: {lat}, {lon}")
                                return (lat, lon)
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Failed to parse Coordinates field: {e}")

                # PRIORITY 2: Fallback to Search: keywords via Nominatim
                search_match = re.search(r"Search:\s*(.+?)(?:\n|$)", answer_content)
                if search_match:
                    search_keywords = search_match.group(1).strip()
                    logger.info(f"Fallback: using search keywords via Nominatim: {search_keywords}")

                    coords = await self.get_coordinates_from_search_keywords(
                        search_keywords, user_lat, user_lon
                    )
                    if coords:
                        return coords

                # PRIORITY 3: Fallback to Location: name via Nominatim
                location_match = re.search(
                    r"Location:\s*(.+?)(?:\n|$)", answer_content
                )
                if location_match:
                    place_name = location_match.group(1).strip()
                    logger.info(f"Fallback: using location name via Nominatim: {place_name}")

                    coords = await self.get_coordinates_from_search_keywords(
                        place_name, user_lat, user_lon
                    )
                    if coords:
                        return coords
            else:
                # Legacy format fallback
                search_match = re.search(r"Поиск:\s*(.+?)(?:\n|$)", response)
                if search_match:
                    search_keywords = search_match.group(1).strip()
                    coords = await self.get_coordinates_from_search_keywords(
                        search_keywords, user_lat, user_lon
                    )
                    if coords:
                        return coords

                place_match = re.search(r"Локация:\s*(.+?)(?:\n|$)", response)
                if place_match:
                    place_name = place_match.group(1).strip()
                    coords = await self.get_coordinates_from_search_keywords(
                        place_name, user_lat, user_lon
                    )
                    if coords:
                        return coords

            logger.debug("No coordinates, search keywords, or location name found in response")
            return None

        except (ValueError, AttributeError) as e:
            logger.warning(f"Error parsing coordinates: {e}")
            return None

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
                logger.info(f"Attempting Yandex image search for: {place_hint or search_keywords}")
                from .yandex_image_search import YandexImageSearch

                async with YandexImageSearch(yandex_api_key, yandex_folder_id) as yandex:
                    base_query = (place_hint or search_keywords or "").strip() or search_keywords
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
        clean_keywords = (search_keywords or "").replace(" + ", " ").replace("+", " ").strip()

        if clean_keywords and lat is None and lon is None and not place_hint:
            try:
                quick = await self._search_wikipedia_images(clean_keywords, "en", max_images)
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

    async def get_nearby_fact_with_history(
        self,
        lat: float,
        lon: float,
        cache_key: str | None = None,
        user_id: int = None,
        force_reasoning_none: bool = False,
    ) -> str:
        """Get fact for static location with history tracking."""
        previous_facts = []
        if cache_key:
            previous_facts = self.static_history.get_previous_facts(cache_key)
            if previous_facts:
                logger.info(f"Found {len(previous_facts)} previous facts for {cache_key}")

        fact_response = await self.get_nearby_fact(
            lat,
            lon,
            is_live_location=False,
            previous_facts=previous_facts,
            user_id=user_id,
            force_reasoning_none=force_reasoning_none,
        )

        if cache_key:
            lines = fact_response.split("\n")
            place = "рядом с вами"
            fact = fact_response

            for i, line in enumerate(lines):
                if line.startswith("Локация:") or line.startswith("Location:"):
                    place = line.split(":", 1)[1].strip() if ":" in line else place
                elif line.startswith("Интересный факт:") or line.startswith(
                    "Interesting fact:"
                ):
                    fact_lines = [line.split(":", 1)[1].strip() if ":" in line else ""]
                    for j in range(i + 1, len(lines)):
                        if lines[j].strip() and not lines[j].startswith(
                            ("Источники", "Sources", "-")
                        ):
                            fact_lines.append(lines[j].strip())
                    fact = " ".join(fact_lines)
                    break

            logger.info(f"Adding fact to history for {cache_key}: {place}")
            self.static_history.add_fact(cache_key, place, fact)

        return fact_response

    def _validate_city_coordinates(
        self, lat: float, lon: float, city_name: str
    ) -> bool:
        """Validate that coordinates are within expected city bounds."""
        city_bounds = {
            "Paris": (48.8566, 2.3522, 15),
            "Москва": (55.7558, 37.6173, 30),
            "Moscow": (55.7558, 37.6173, 30),
            "London": (51.5074, -0.1278, 20),
            "New York": (40.7128, -74.0060, 25),
            "Санкт-Петербург": (59.9311, 30.3609, 20),
            "Saint Petersburg": (59.9311, 30.3609, 20),
            "St Petersburg": (59.9311, 30.3609, 20),
        }

        if city_name not in city_bounds:
            return True

        center_lat, center_lon, radius_km = city_bounds[city_name]
        distance = self._calculate_distance(lat, lon, center_lat, center_lon)

        return distance <= radius_km

    def _calculate_distance(
        self, lat1: float, lon1: float, lat2: float, lon2: float
    ) -> float:
        """Calculate distance between two coordinates in kilometers."""
        from math import asin, cos, radians, sin, sqrt

        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        r = 6371

        return r * c


# Global client instance
_claude_client: ClaudeClient | None = None


def get_claude_client() -> ClaudeClient:
    """Get or create the global Claude client instance."""
    global _claude_client
    if _claude_client is None:
        _claude_client = ClaudeClient()
    return _claude_client


# Backward compatibility aliases
OpenAIClient = ClaudeClient
get_openai_client = get_claude_client
