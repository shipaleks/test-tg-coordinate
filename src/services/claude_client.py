"""Claude client for generating location-based facts using Anthropic API."""

import asyncio
import logging
import os
import re
import time

import aiohttp
from anthropic import AsyncAnthropic

from .prompts import PromptBuilderMixin
from .web_search import get_web_search_service
from .wikimedia_images import WikimediaImagesMixin

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
            sorted_items = sorted(self._cache.items(), key=lambda x: x[1]["timestamp"])
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


class ClaudeClient(PromptBuilderMixin, WikimediaImagesMixin):
    """Client for interacting with Anthropic Claude API to generate location facts."""

    # Model constants
    MODEL_OPUS = "claude-opus-5"
    MODEL_SONNET = "claude-sonnet-5"
    MODEL_HAIKU = "claude-haiku-4-5-20251001"

    def __init__(self, api_key: str | None = None):
        """Initialize Claude client.

        Args:
            api_key: Anthropic API key. If None, will use ANTHROPIC_API_KEY env var.
        """
        self.client = AsyncAnthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))
        self.web_search = get_web_search_service()
        self.static_history = StaticLocationHistory()
        # Lightweight caches for Wikimedia pipeline
        self._qid_cache: dict[str, tuple[str, float]] = {}
        self._p18_cache: dict[str, tuple[str, float]] = {}
        self._fileinfo_cache: dict[str, tuple[dict, float]] = {}
        self._image_cache_ttl_seconds = 24 * 3600
        # Semaphore to limit concurrent API requests
        self._api_semaphore = asyncio.Semaphore(3)

    def _parse_int_env(self, key: str) -> int | None:
        value = os.getenv(key)
        if value is None or value == "":
            return None
        try:
            return int(value)
        except ValueError:
            logger.warning(f"Invalid int for {key}: {value}")
            return None

    def _get_thinking_budget(self, reasoning_level: str | None) -> int | None:
        if not reasoning_level:
            return None

        level_key = reasoning_level.upper()
        env_keys = [
            f"CLAUDE_THINKING_BUDGET_TOKENS_{level_key}",
            f"ANTHROPIC_THINKING_BUDGET_TOKENS_{level_key}",
            "CLAUDE_THINKING_BUDGET_TOKENS",
            "ANTHROPIC_THINKING_BUDGET_TOKENS",
        ]
        for key in env_keys:
            value = self._parse_int_env(key)
            if value is not None:
                return value
        return None

    def _build_thinking_config(
        self,
        reasoning_level: str | None,
        force_reasoning_none: bool,
        model: str | None = None,
    ) -> tuple[dict | None, dict | None]:
        """Build thinking config and optional output_config for the API call.

        Returns:
            Tuple of (thinking_config, output_config). output_config is only set
            for Opus 4.6 adaptive thinking with effort control.
        """
        if force_reasoning_none or not reasoning_level or reasoning_level == "none":
            return {"type": "disabled"}, None

        # Claude 5 models (Opus 5, Sonnet 5) reject budget_tokens: they use
        # adaptive thinking with an effort parameter instead.
        if model in (self.MODEL_OPUS, self.MODEL_SONNET):
            effort_mapping = {
                "low": "low",
                "medium": "medium",
                "high": "high",
            }
            effort = effort_mapping.get(reasoning_level, "high")
            return {"type": "adaptive"}, {"effort": effort}

        # Pre-4.6 models (Haiku 4.5) use budget_tokens
        default_budgets = {
            "low": 1024,
            "medium": 2048,
            "high": 4096,
        }
        budget = self._get_thinking_budget(reasoning_level)
        if budget is None:
            budget = default_budgets.get(reasoning_level, 1024)

        if budget < 1024:
            logger.warning(
                f"Thinking budget too low ({budget}); clamping to 1024 minimum"
            )
            budget = 1024

        return {"type": "enabled", "budget_tokens": budget}, None

    def _is_thinking_error(self, error: Exception) -> bool:
        message = str(error).lower()
        return ("thinking" in message or "output_config" in message) and (
            "budget" in message
            or "adaptive" in message
            or "type" in message
            or "effort" in message
        )

    async def _create_message(self, request_kwargs: dict):
        """Send a message request.

        Opus 5 requests opt into server-side refusal fallbacks: if safety
        classifiers decline the request, the API re-runs it on Anthropic's
        recommended fallback model instead of returning the refusal.
        """
        if request_kwargs.get("model") == self.MODEL_OPUS:
            return await self.client.beta.messages.create(
                **request_kwargs,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        return await self.client.messages.create(**request_kwargs)

    async def _create_message_with_thinking_fallback(self, request_kwargs: dict):
        try:
            return await self._create_message(request_kwargs)
        except Exception as e:
            if self._is_thinking_error(e):
                current = request_kwargs.get("thinking", {})
                if current.get("type") != "disabled":
                    logger.warning(
                        "Thinking error from Claude API; retrying with thinking disabled"
                    )
                    retry_kwargs = dict(request_kwargs)
                    retry_kwargs["thinking"] = {"type": "disabled"}
                    retry_kwargs.pop("output_config", None)
                    return await self._create_message(retry_kwargs)
            raise

    def _check_response_stop_reason(self, response) -> bool:
        """Inspect stop_reason; returns True when the response was refused.

        Claude 5 safety classifiers can decline a request with a normal
        HTTP 200 and stop_reason == "refusal" (content empty or partial),
        so this must be checked before parsing content.
        """
        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            logger.warning(f"Claude refused the request (stop_details={details})")
            return True
        if stop_reason == "max_tokens":
            logger.warning(
                "Claude hit max_tokens; response may be truncated "
                "(thinking shares the max_tokens budget)"
            )
        return False

    async def get_nearby_fact(
        self,
        lat: float,
        lon: float,
        is_live_location: bool = False,
        previous_facts: list = None,
        user_id: int = None,
        force_reasoning_none: bool = False,  # Disables thinking for this request
    ) -> str:
        """Get an interesting fact about a location.

        Args:
            lat: Latitude coordinate
            lon: Longitude coordinate
            is_live_location: If True, generate more detailed fact
            previous_facts: List of previously sent facts to avoid repetition
            user_id: User ID to check premium status and language
            force_reasoning_none: If True, thinking is disabled for this request

        Returns:
            A location name and an interesting fact about it

        Raises:
            Exception: If Claude API call fails
        """
        try:
            # Get user preferences
            user_language = "ru"  # Default to Russian
            user_model = self.MODEL_SONNET  # Default model (Sonnet 5)
            user_reasoning = "low"  # Default reasoning level

            if user_id:
                try:
                    from .async_donors_wrapper import get_async_donors_db

                    donors_db = await get_async_donors_db()
                    user_language = await donors_db.get_user_language(user_id)

                    # Check user model preference
                    stored_model = await donors_db.get_user_model(user_id)
                    if stored_model:
                        # Use stored model if it matches our known models
                        if stored_model in [
                            self.MODEL_OPUS,
                            self.MODEL_SONNET,
                            self.MODEL_HAIKU,
                        ]:
                            user_model = stored_model

                    # Check user reasoning preference
                    stored_reasoning = await donors_db.get_user_reasoning(user_id)
                    if stored_reasoning:
                        user_reasoning = stored_reasoning
                except Exception as e:
                    logger.warning(f"Failed to get user preferences: {e}")

            # Perform web search for context
            web_search_results = ""
            try:
                # First, get location name via reverse geocoding to search for specific places
                location_name = None
                try:
                    coords = await self.get_coordinates_from_nominatim(
                        f"{lat},{lon}", user_lat=lat, user_lon=lon
                    )
                    if coords and len(coords) > 2:
                        # coords[2] contains address details
                        location_name = coords[2]
                except Exception as e:
                    logger.warning(f"Reverse geocoding failed: {e}")

                # Get country info for local language search
                country = None
                city = None
                suburb = ""
                road = ""

                import httpx

                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(
                        "https://nominatim.openstreetmap.org/reverse",
                        params={
                            "lat": lat,
                            "lon": lon,
                            "format": "json",
                            "addressdetails": 1,
                        },
                        headers={"User-Agent": "NearbyFactBot/1.0"},
                    )
                    if response.status_code == 200:
                        data = response.json()
                        address = data.get("address", {})
                        country = address.get("country", "")
                        city = (
                            address.get("city")
                            or address.get("town")
                            or address.get("village")
                            or ""
                        )
                        suburb = address.get("suburb", "")
                        road = address.get("road", "")

                        # Update location_name if not set
                        if not location_name and road and city:
                            location_name = f"{road}, {city}"

                # Determine local language based on country
                local_queries_map = {
                    "France": (
                        "fr",
                        "histoire",
                        "bâtiment historique",
                        "lieux insolites",
                    ),
                    "Deutschland": (
                        "de",
                        "Geschichte",
                        "historisches Gebäude",
                        "ungewöhnliche Orte",
                    ),
                    "Germany": (
                        "de",
                        "Geschichte",
                        "historisches Gebäude",
                        "ungewöhnliche Orte",
                    ),
                    "España": (
                        "es",
                        "historia",
                        "edificio histórico",
                        "lugares inusuales",
                    ),
                    "Spain": (
                        "es",
                        "historia",
                        "edificio histórico",
                        "lugares inusuales",
                    ),
                    "Italia": ("it", "storia", "edificio storico", "luoghi insoliti"),
                    "Italy": ("it", "storia", "edificio storico", "luoghi insoliti"),
                    "Россия": (
                        "ru",
                        "история",
                        "историческое здание",
                        "необычные места",
                    ),
                    "Russia": (
                        "ru",
                        "история",
                        "историческое здание",
                        "необычные места",
                    ),
                }

                local_terms = None
                if country:
                    local_terms = local_queries_map.get(country)
                    if not local_terms:
                        # Try partial match
                        for country_name, terms in local_queries_map.items():
                            if country_name.lower() in country.lower():
                                local_terms = terms
                                break

                # Build search queries based on location name or coordinates
                search_queries = []

                if location_name:
                    # Extract city and specific location
                    # Parse location_name which is like "24 rue de la Glacière, Paris, France"
                    parts = [p.strip() for p in location_name.split(",")]

                    if len(parts) >= 2:
                        street = parts[0]  # "24 rue de la Glacière"
                        city_name = parts[1] if len(parts) > 1 else city  # "Paris"

                        # Search in English
                        search_queries = [
                            f'"{street}" {city_name} history facts',
                            f'"{street}" {city_name} historical building',
                        ]

                        # Add local language searches for better "local knowledge"
                        if local_terms:
                            lang_code, hist_term, building_term, unusual_term = (
                                local_terms
                            )
                            search_queries.extend(
                                [
                                    f'"{street}" {city_name} {hist_term}',
                                    f'"{street}" {city_name} {building_term}',
                                ]
                            )

                        logger.info(
                            f"Search with local language: {local_terms[0] if local_terms else 'en'}"
                        )
                    else:
                        # Fallback to city-based search
                        search_queries = [
                            f"{location_name} history interesting facts",
                            f"{location_name} hidden gems unusual",
                        ]
                else:
                    # Build queries with specific location info from Nominatim
                    if road and city:
                        search_queries = [
                            f'"{road}" {city} history facts',
                            f'"{road}" {city} interesting places',
                        ]

                        # Add local language queries
                        if local_terms:
                            lang_code, hist_term, building_term, unusual_term = (
                                local_terms
                            )
                            search_queries.append(f'"{road}" {city} {hist_term}')

                        search_queries.append(f"{city} {suburb} unusual hidden places")
                    elif city:
                        search_queries = [
                            f"{city} {suburb} interesting facts history",
                            f"{city} unusual places hidden gems",
                        ]

                        if local_terms:
                            lang_code, hist_term, building_term, unusual_term = (
                                local_terms
                            )
                            search_queries.append(f"{city} {unusual_term}")
                    else:
                        # Last resort: coordinate-based search
                        search_queries = [
                            f"Paris unusual places {lat} {lon}",
                            f"historical sites near {lat},{lon}",
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
                else:
                    logger.warning(
                        "Web search returned 0 results - will use fallback mode without strict verification"
                    )
            except Exception as e:
                logger.warning(
                    f"Web search failed: {e} - will use fallback mode without strict verification"
                )

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
            thinking_config, output_config = self._build_thinking_config(
                user_reasoning, force_reasoning_none, model=user_model
            )
            thinking_type = (
                thinking_config.get("type")
                if isinstance(thinking_config, dict)
                else "default"
            )
            logger.info(
                "Calling Claude API "
                f"(model={user_model}, reasoning={user_reasoning}, thinking={thinking_type})"
            )

            async with self._api_semaphore:
                request_kwargs = {
                    "model": user_model,
                    "max_tokens": 8192,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                }
                if thinking_config is not None:
                    request_kwargs["thinking"] = thinking_config
                if output_config is not None:
                    request_kwargs["output_config"] = output_config
                response = await self._create_message_with_thinking_fallback(
                    request_kwargs
                )

            if self._check_response_stop_reason(response):
                raise ValueError("Claude refused the request")

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

                # Adaptive radius expansion: 1500m → 2500m → 3500m for live locations
                radius_steps = [1500]
                if is_live_location:
                    radius_steps.extend([2500, 3500])

                for radius in radius_steps:
                    expanded_prompt = (
                        user_prompt
                        + f"\n\nПРИМЕЧАНИЕ: Расширь радиус поиска до {radius}м. Найди ЛЮБОЙ интересный исторический объект поблизости."
                        if user_language == "ru"
                        else user_prompt
                        + f"\n\nNOTE: Expand search radius to {radius}m. Find ANY interesting historical object nearby."
                    )

                    # Prepare retry parameters (reuse thinking config if applicable)
                    retry_kwargs = {
                        "model": user_model,
                        "max_tokens": 8192,
                        "system": system_prompt,
                        "messages": [{"role": "user", "content": expanded_prompt}],
                    }
                    if thinking_config is not None:
                        retry_kwargs["thinking"] = thinking_config
                    if output_config is not None:
                        retry_kwargs["output_config"] = output_config

                    async with self._api_semaphore:
                        retry_response = (
                            await self._create_message_with_thinking_fallback(
                                retry_kwargs
                            )
                        )

                    # A refused retry is not fatal: keep the NO_POI content and
                    # let the handler show its friendly "nothing found" message.
                    if self._check_response_stop_reason(retry_response):
                        continue

                    if retry_response.content:
                        retry_content = ""
                        for block in retry_response.content:
                            if hasattr(block, "text"):
                                retry_content += block.text
                        if retry_content and "[[NO_POI_FOUND]]" not in retry_content:
                            content = retry_content
                            break

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
                        "city": (
                            street_parts[-1].strip()
                            if len(street_parts) > 1
                            else "Paris"
                        ),
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

                                    display_name = result.get(
                                        "display_name", ""
                                    ).lower()
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

        for city, (_city_lat, _city_lon, _radius) in common_cities.items():
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

                    logger.info(
                        f"Found coordinates with fallback '{pattern}': {coords}"
                    )
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
                    r"Coordinates:\s*([\d.]+),\s*([\d.]+)", answer_content
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
                                logger.info(
                                    f"Using coordinates directly from Claude: {lat}, {lon}"
                                )
                                return (lat, lon)
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Failed to parse Coordinates field: {e}")

                # PRIORITY 2: Fallback to Search: keywords via Nominatim
                search_match = re.search(r"Search:\s*(.+?)(?:\n|$)", answer_content)
                if search_match:
                    search_keywords = search_match.group(1).strip()
                    logger.info(
                        f"Fallback: using search keywords via Nominatim: {search_keywords}"
                    )

                    coords = await self.get_coordinates_from_search_keywords(
                        search_keywords, user_lat, user_lon
                    )
                    if coords:
                        return coords

                # PRIORITY 3: Fallback to Location: name via Nominatim
                location_match = re.search(r"Location:\s*(.+?)(?:\n|$)", answer_content)
                if location_match:
                    place_name = location_match.group(1).strip()
                    logger.info(
                        f"Fallback: using location name via Nominatim: {place_name}"
                    )

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

            logger.debug(
                "No coordinates, search keywords, or location name found in response"
            )
            return None

        except (ValueError, AttributeError) as e:
            logger.warning(f"Error parsing coordinates: {e}")
            return None

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
                logger.info(
                    f"Found {len(previous_facts)} previous facts for {cache_key}"
                )

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
