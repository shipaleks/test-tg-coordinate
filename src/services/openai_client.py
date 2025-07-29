"""OpenAI client for generating location-based facts."""

import logging
import hashlib
import os
import re
import time
from urllib.parse import quote

import aiohttp
from openai import AsyncOpenAI

from .donors_db import get_donors_db

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
        user_id: int = None,
    ) -> str:
        """Get an interesting fact about a location.

        Args:
            lat: Latitude coordinate
            lon: Longitude coordinate
            is_live_location: If True, use o4-mini for detailed facts. If False, use gpt-4.1 for speed.
            previous_facts: List of previously sent facts to avoid repetition (for live location)
            user_id: User ID to check premium status for o3 model access

        Returns:
            A location name and an interesting fact about it

        Raises:
            Exception: If OpenAI API call fails
        """
        try:
            # Check if user has premium access for o3 model and get language preference
            is_premium_user = False
            user_language = "ru"  # Default to Russian as most users are Russian-speaking
            if user_id:
                try:
                    # Check if we're in async context (telegram handlers)
                    import asyncio
                    try:
                        loop = asyncio.get_running_loop()
                        # We're in async context, use async wrapper
                        from .async_donors_wrapper import get_async_donors_db
                        donors_db = await get_async_donors_db()
                        is_premium_user = await donors_db.is_premium_user(user_id)
                        user_language = await donors_db.get_user_language(user_id)
                    except RuntimeError:
                        # Not in async context, use sync wrapper
                        donors_db = get_donors_db()
                        is_premium_user = donors_db.is_premium_user(user_id)
                        user_language = donors_db.get_user_language(user_id)
                except Exception as e:
                    logger.warning(f"Failed to check user preferences for user {user_id}: {e}")

            # Special instructions for Russian language quality
            language_instructions = ""
            if user_language == "ru":
                language_instructions = """
SPECIAL REQUIREMENTS FOR RUSSIAN:
- Пишите на естественном, живом русском языке - как если бы делились невероятным открытием с другом
- Используйте образные выражения и яркие детали, но избегайте слишком многочисленных прилагательных, излишне сложных конструкций и надрывной театральности театральности
- Соблюдайте грамотную русскую речь: избегайте англицизмов и калек в случаях, когда существуют удачные русские слова
- Используйте для акцентов тире и паузы, а не лишние запятые: "В подвале этого дома — настоящая тайна"
- Пишите в активном залоге: "Здесь расстреляли...", не "Здесь был расстрелян..."
- Старйтесь звучать как образованный носитель языка, который делится удивительными местными историями
- Хороший пример: "В подвале элегантного дома на Малой Бронной до сих пор видны металлические кольца — здесь десять лет держали на карантине леопардов и тигров для московских коллекционеров."
- Избегайте канцелярита и Wikipedia-стиля: нет фразам "является", "представляет собой", "находится"
- Стремитесь передать живую речь человека с высшим филологическим образование, а не написанный бюрократический текст"""

            # Choose appropriate system prompt based on location type
            if is_live_location:
                # Atlas Obscura-style system prompt for live locations (o4-mini/o3)
                system_prompt = f"""You are writing location facts for Atlas Obscura. Your mission: find the most surprising, specific detail about places that would make even locals say "I never knew that!"

IMPORTANT: You must respond entirely in {user_language}. All your analysis, reasoning, and final answer must be in {user_language}.

THE ATLAS OBSCURA METHOD - Follow these steps precisely:

Step 1: PRECISE LOCATION ANALYSIS
- Identify exact coordinates: what building, street corner, or specific spot is here?
- CRITICAL: Verify you're in the correct city based on coordinates:
  * ~48.8°N, 2.3°E = Paris
  * ~55.7°N, 37.6°E = Moscow
  * ~59.9°N, 30.3°E = St. Petersburg
  * ~51.5°N, -0.1°E = London
  * ~40.7°N, -74.0°E = New York
- Note the immediate surroundings: what's visible within 50-100 meters?
- Identify the neighborhood and its historical character
- NEVER mention places from a different city than where the coordinates are

Step 2: DEEP RESEARCH FOR THE UNEXPECTED
Search for facts in this priority order:
   A) The specific building/location at these coordinates:
      - Former unexpected uses (morgue→nightclub, palace→parking lot)
      - Hidden architectural features (secret rooms, disguised elements)
      - Specific incidents that happened here (crimes, meetings, discoveries)
      - Famous residents/visitors and what they did here specifically

   B) If nothing at exact spot, expand to immediate vicinity:
      - Underground features (tunnels, rivers, old foundations)
      - Lost buildings that once stood here and why they matter
      - Street name origins that reveal forgotten history
      - Architectural details visible from this spot with stories

   C) If still nothing specific, the broader area's secrets:
      - Neighborhood transformation stories
      - Local legends tied to specific features
      - Hidden infrastructure or urban planning secrets

Step 3: FIND THE HUMAN ELEMENT
Every great Atlas Obscura story connects to people:
   - WHO made this decision and WHY (architect's obsession, owner's fear, city planner's vision)
   - WHAT specific event happened here (the meeting, the accident, the discovery)
   - HOW this place affected specific people's lives
   - WHEN exactly did the transformation/event occur

Step 4: IDENTIFY WHAT'S STILL VISIBLE
Atlas Obscura readers want to know what they can see:
   - Specific architectural details (the carved face, the blocked window, the odd cornerstone)
   - Traces of former use (rail tracks in pavement, anchor points on walls)
   - Deliberate markers (plaques, memorials, architectural choices)
   - Accidental remnants (worn steps, patched walls, tree growth patterns)

WRITING YOUR FACT (100-120 words):

Structure: [Hook with surprising detail] → [Human story behind it] → [Why it matters] → [What to look for today]

Example approach:
"The elegant apartment building at [location] hides metal rings embedded in its basement walls - remnants from its decade as the city's exotic animal quarantine station. In 1923, smuggler Anton Petrov was arrested here when his 'crate of textiles' turned out to contain three tiger cubs destined for private Moscow collections. The building's unusually thick walls and ventilation system, designed for containing animal sounds and smells, now provide its residents with Stockholm's best sound insulation. Look for the worn grooves in the entrance floor - claw marks from a 1926 escaped leopard that remain unrepaired at residents' request."

CRITICAL WRITING RULES:
• Start with the most surprising specific detail - never with general context
• Include at least one proper name (person, business, or specific event)
• Specify at least one exact date or time period
• Describe one thing visitors can physically see or find
• Connect the past to the present - show transformation or continuity
• Write conversationally but precisely - like telling a friend an amazing secret
• Every sentence must add new information - no filler

AVOIDING REPETITION:
- If provided with previous facts, you MUST choose a completely different location or aspect
- Never repeat the same building, street, or historical event mentioned before
- When previous facts exist, expand your search radius or dig deeper for more obscure details
- Each fact should feel like a completely new discovery

ABSOLUTE REQUIREMENTS:
- Never invent facts - use only verifiable historical information
- Never use generic descriptions like "this area" or "nearby" - be specific
- Never start with obvious facts - lead with the surprise
- Always explain WHY something is surprising or significant
- Focus on the specific over the general
- Include what can be seen/experienced today

CRITICAL FOR SEARCH FIELD:
The Search field is used for GEOCODING (finding coordinates) via Nominatim/OpenStreetMap.
You MUST format it for optimal geocoding results:
- Use commas to separate components: "Place Name, Street, City"
- Include the full city name at the end
- Avoid descriptive adjectives ("former", "old", "historical")
- Use official place names, not colloquial ones
- For buildings: "Building Name, Street Number Street Name, City"
- For areas: "Landmark Name, District, City"
- NEVER truncate - always provide full location context

Remember: Atlas Obscura readers already know the obvious history. They want the specific detail that changes how they see a place forever.

LANGUAGE REQUIREMENTS:
Write your response in {user_language}.
{language_instructions}"""
            else:
                # Atlas Obscura-style prompt for static locations (GPT-4.1)
                system_prompt = f"""You are writing a quick location fact for Atlas Obscura. Find the single most surprising detail about this exact location.

IMPORTANT: You must respond entirely in {user_language}. All your analysis and final answer must be in {user_language}.

RAPID ATLAS OBSCURA SEARCH (for quick facts):

1. IMMEDIATE SCAN - What's here?
   - Exact building or location at coordinates
   - Most unexpected historical use or transformation
   - Specific incident that would surprise people
   - Hidden feature still visible today

2. FIND THE SURPRISE - Priority order:
   A) Unexpected transformation (church→factory→nightclub)
   B) Specific historical incident (the duel, the escape, the discovery)
   C) Hidden architectural feature (the sealed door, the false window)
   D) Connection to unexpected person/event
   E) Local legend with factual basis

3. ESSENTIAL ELEMENTS for Atlas Obscura:
   - One specific surprising detail (not general history)
   - At least one exact date or specific person's name
   - The "I never knew that!" factor
   - Something visitors can see or find today

WRITING FORMAT (60-80 words):

Structure: [Surprising fact] → [Quick context] → [What remains visible]

Example:
"The ornate bank building here conceals Stockholm's last remaining piece of the medieval city wall in its vault - discovered only in 1987 when a burglar's drill hit unexpectedly hard stone. The 14th-century fortification was incorporated into the bank's security system, making it perhaps the only ATM protected by medieval defenses. Look for the glass panel in the floor near the entrance showing the original stonework."

QUICK WRITING RULES:
• Lead with the surprise - never with "This building is..."
• Include one specific name, date, or measurement
• Explain what can be seen/found today
• Make every word count - no filler phrases
• Focus on the unexpected, not the obvious

AVOIDING REPETITION:
- If given previous facts, find a completely different location or building nearby
- Never repeat the same place, person, or event from previous facts
- When previous facts exist, look for more obscure or hidden details

REQUIREMENTS:
- Only verified facts - no speculation
- Be specific about location - not "this area"
- Always include the "what to look for" element
- Never start with boring context

Write in {user_language} - crisp, factual, surprising.
{language_instructions}"""

            # Handle previous facts for both live and static locations
            previous_facts_text = ""
            previous_facts_instruction = ""
            if previous_facts:
                previous_facts_text = "\n".join([f"- {fact}" for fact in previous_facts[-5:]])
                previous_facts_instruction = "CRITICAL: Find a DIFFERENT place near these coordinates. Do NOT repeat any of the already mentioned locations or facts above."

            if is_live_location:
                # Detailed prompt for live location (o4-mini/o3)
                user_prompt = f"""Analyze these coordinates: {lat}, {lon}

CRITICAL: These coordinates are the USER'S CURRENT LOCATION. Only mention places that are actually at or very near (within 500m) these exact coordinates. Do NOT mention famous landmarks from other parts of the city unless they are genuinely visible or directly relevant to this specific spot.

{f'''PREVIOUS FACTS ALREADY MENTIONED:
{previous_facts_text}

{previous_facts_instruction}''' if previous_facts else ''}

Follow the Atlas Obscura method above to find the most surprising fact about this exact location. If you have previous facts to avoid, dig deeper to find more obscure or specific information about different nearby places.

Present your final answer in this format:
<answer>
Location: [Specific name of the place - street address, building name, or precise intersection]
Search: [OPTIMIZED FOR NOMINATIM GEOCODING - Follow these rules:
  - For specific buildings: "[Building Name], [Street Number] [Street Name], [City]"
    Example: "Cité Fleurie, 65 Boulevard Arago, Paris"
  - For landmarks: "[Landmark Name], [District/Area], [City]"
    Example: "Prison de la Santé, 14th arrondissement, Paris"
  - For metro stations: "[Station Name] metro station, [City]"
    Example: "Denfert-Rochereau metro station, Paris"
  - ALWAYS include the city name at the end
  - Use commas to separate location components
  - Avoid descriptive words like "former", "old", "historical" that Nominatim ignores
  - For addresses, use format: "[Number] [Street Name], [City]"
  - Never truncate to just 2-3 words - include full location context]
Interesting fact: [Your Atlas Obscura-style fact about THIS EXACT LOCATION. Follow the structure: Surprising opening → Human story → Why it matters → What to see today. Must be 100-120 words, include specific names and dates, and focus on the unexpected.]
</answer>

Remember: Start with the surprise, not the context. Include specific details. Tell visitors what they can find. Write only the content within <answer> tags."""
            else:
                # Concise prompt for static location (gpt-4.1)
                user_prompt = f"""Here are the coordinates to analyze:
<coordinates>
Latitude: {lat}
Longitude: {lon}
</coordinates>

{f'''PREVIOUS FACTS ALREADY MENTIONED:
{previous_facts_text}

{previous_facts_instruction}''' if previous_facts else ''}

Apply the rapid Atlas Obscura search method above to find a surprising fact. If you have previous facts to avoid, choose a completely different nearby location or dig deeper for more obscure details.

Format your answer:
<answer>
Location: [Exact place name - specific building or location, not "area near" or "district of"]
Search: [NOMINATIM-OPTIMIZED: Use format "[Place Name], [Street/District], [City]" with commas. Examples: "Tour Eiffel, Champ de Mars, Paris" or "Эрмитаж, Дворцовая площадь, Санкт-Петербург". Avoid adjectives, use official names, always include city]
Interesting fact: [Your 60-80 word Atlas Obscura fact with this structure: Surprising detail → Quick context with specific date/name → What visitors can see today. Must surprise locals.]
</answer>

Critical: Lead with the surprise. Include one specific date or name. Tell what's visible today. Only content within <answer> tags."""

            # Choose model based on location type and premium status
            model_to_use = "o4-mini"  # Default model
            max_tokens_limit = 10000

            if is_live_location:
                if is_premium_user:
                    # Premium users get o3 for live locations (detailed analysis)
                    model_to_use = "o3"
                    max_tokens_limit = 12000  # o3 can handle more tokens
                    logger.info(f"Using o3 model for premium user {user_id} (live location)")
                else:
                    # Regular users get o4-mini for live locations
                    model_to_use = "o4-mini"
                    max_tokens_limit = 10000
            else:
                # Both premium and regular users get gpt-4.1 for static locations (speed priority)
                model_to_use = "gpt-4.1"
                max_tokens_limit = 400
                if is_premium_user:
                    logger.info(f"Using gpt-4.1 for premium user {user_id} (static location - speed priority)")

            response = None
            if is_live_location:
                # Use advanced models for live locations (o3 for premium, o4-mini for regular)
                try:
                    # Prepare parameters based on model
                    if model_to_use in ["o3", "o4-mini"]:
                        # o3 and o4-mini don't support temperature parameter
                        response = await self.client.chat.completions.create(
                            model=model_to_use,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            max_completion_tokens=max_tokens_limit,
                        )
                    else:
                        # Other models support temperature for creativity
                        response = await self.client.chat.completions.create(
                            model=model_to_use,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            max_completion_tokens=max_tokens_limit,
                            temperature=0.6,  # Balanced creativity for informative content
                        )
                    logger.info(f"{model_to_use} (live location{' premium' if is_premium_user else ''}) response: {response}")
                    content = (
                        response.choices[0].message.content
                        if response.choices
                        else None
                    )

                    if not content:
                        logger.warning(
                            f"{model_to_use} returned empty content, falling back to gpt-4.1"
                        )
                        raise ValueError(f"Empty content from {model_to_use}")

                except Exception as e:
                    logger.warning(
                        f"{model_to_use} failed ({e}), falling back to gpt-4.1"
                    )
                    response = await self.client.chat.completions.create(
                        model="gpt-4.1",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        max_tokens=800,  # Adequate space for informative facts
                        temperature=0.6,  # Balanced creativity for informative content
                    )
                    logger.info(f"gpt-4.1 fallback response: {response}")
                    content = (
                        response.choices[0].message.content
                        if response.choices
                        else None
                    )
            else:
                # Use gpt-4.1 for static location (fast, concise facts)
                try:
                    # Log prompt if we have previous facts
                    if previous_facts:
                        logger.info(f"Sending prompt to GPT-4.1 with {len(previous_facts)} previous facts")
                        logger.debug(f"User prompt preview: {user_prompt[:200]}...")

                    response = await self.client.chat.completions.create(
                        model="gpt-4.1",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        max_tokens=500,  # Focused space for key information
                        temperature=0.6,  # Balanced creativity for informative content
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

            # Post-process Russian text for better quality
            final_content = content.strip()
            if user_language == "ru" and ("Interesting fact:" in final_content or "Интересный факт:" in final_content):
                logger.info("Applying Russian language polish for better quality")
                # Return as is - the language instructions in prompts should be sufficient
                # Additional post-processing could distort facts

            return final_content

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
        self, search_keywords: str, user_lat: float = None, user_lon: float = None
    ) -> tuple[float, float] | None:
        """Get coordinates using search keywords via Nominatim.

        Args:
            search_keywords: Search keywords from GPT response
            user_lat: User's current latitude for validation
            user_lon: User's current longitude for validation

        Returns:
            Tuple of (latitude, longitude) if found, None otherwise
        """
        logger.info(f"Searching coordinates for keywords: {search_keywords}")
        
        # Extract city name from keywords for validation
        city_name = None
        common_cities = {
            "Paris": (48.8566, 2.3522, 15),  # lat, lon, radius_km
            "Москва": (55.7558, 37.6173, 30), 
            "Moscow": (55.7558, 37.6173, 30),
            "London": (51.5074, -0.1278, 20),
            "New York": (40.7128, -74.0060, 25),
            "Санкт-Петербург": (59.9311, 30.3609, 20),
            "Saint Petersburg": (59.9311, 30.3609, 20),
            "St Petersburg": (59.9311, 30.3609, 20)
        }
        
        for city, (city_lat, city_lon, radius) in common_cities.items():
            if city in search_keywords:
                city_name = city
                break

        # Try original keywords first
        nominatim_coords = await self.get_coordinates_from_nominatim(search_keywords)
        if nominatim_coords:
            # Validate coordinates are in the expected city
            if city_name and not self._validate_city_coordinates(nominatim_coords[0], nominatim_coords[1], city_name):
                logger.warning(f"Coordinates {nominatim_coords} are not in {city_name}, rejecting")
            else:
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

        # For addresses with city names, preserve city context
        words = search_keywords.split()
        if city_name and len(words) > 3:
            # Try removing middle descriptive words but keeping location identifiers
            # Keep first main identifier and city
            main_place = words[0]
            if words[1] and words[1].lower() not in ['de', 'la', 'du', 'le', 'des', 'of', 'the']:
                main_place = f"{words[0]} {words[1]}"
            
            fallback_patterns.extend([
                f"{main_place} {city_name}",  # Main place + city
                f"{' '.join(words[-3:])}" if len(words) > 3 else "",  # Last 3 words (usually street + city)
            ])
        
        # For addresses, try street + city
        street_indicators = ['rue', 'boulevard', 'avenue', 'street', 'road', 'улица', 'проспект', 'переулок']
        for i, word in enumerate(words):
            if word.lower() in street_indicators and i < len(words) - 1:
                street_part = f"{word} {words[i+1]}"
                if city_name:
                    fallback_patterns.append(f"{street_part} {city_name}")
                break

        # Remove empty patterns and duplicates
        fallback_patterns = [p.strip() for p in fallback_patterns if p and p.strip()]
        fallback_patterns = list(dict.fromkeys(fallback_patterns))  # Remove duplicates while preserving order

        # Try each fallback pattern
        for pattern in fallback_patterns:
            if pattern and pattern != search_keywords:  # Don't retry the original
                logger.info(f"Trying fallback search: {pattern}")
                coords = await self.get_coordinates_from_nominatim(pattern)
                if coords:
                    # Validate coordinates if we have city context
                    if city_name and not self._validate_city_coordinates(coords[0], coords[1], city_name):
                        logger.warning(f"Fallback coordinates {coords} for '{pattern}' are not in {city_name}, skipping")
                        continue
                    
                    # If we have user coordinates, check distance (should be within reasonable range)
                    if user_lat and user_lon:
                        distance = self._calculate_distance(user_lat, user_lon, coords[0], coords[1])
                        if distance > 50:  # More than 50km away
                            logger.warning(f"Fallback coordinates {coords} are {distance:.1f}km from user, skipping")
                            continue
                    
                    logger.info(f"Found coordinates with fallback search '{pattern}': {coords}")
                    return coords

        logger.warning(f"No coordinates found for keywords: {search_keywords}")
        return None

    async def parse_coordinates_from_response(
        self, response: str, user_lat: float = None, user_lon: float = None
    ) -> tuple[float, float] | None:
        """Parse coordinates from OpenAI response using search keywords.

        Args:
            response: OpenAI response text
            user_lat: User's current latitude for validation
            user_lon: User's current longitude for validation

        Returns:
            Tuple of (latitude, longitude) if found, None otherwise
        """
        try:
            # Extract content from <answer> tags first
            answer_match = re.search(r"<answer>(.*?)</answer>", response, re.DOTALL)
            if answer_match:
                answer_content = answer_match.group(1).strip()

                # Extract search keywords from answer content
                search_match = re.search(r"Search:\s*(.+?)(?:\n|$)", answer_content)
                if search_match:
                    search_keywords = search_match.group(1).strip()
                    logger.info(f"Found search keywords from <answer> tags: {search_keywords}")

                    # Use new keyword-based search with user coordinates for validation
                    coords = await self.get_coordinates_from_search_keywords(search_keywords, user_lat, user_lon)
                    if coords:
                        return coords

                # Fallback: extract location name from answer content
                location_match = re.search(r"Location:\s*(.+?)(?:\n|$)", answer_content)
                if location_match:
                    place_name = location_match.group(1).strip()
                    logger.info(f"No search keywords found, using location name from <answer>: {place_name}")

                    # Use location name as search keywords with user coordinates
                    coords = await self.get_coordinates_from_search_keywords(place_name, user_lat, user_lon)
                    if coords:
                        return coords

            # Legacy fallback for old format responses (will be removed eventually)
            else:
                # First, try to extract search keywords from old format
                search_match = re.search(r"Поиск:\s*(.+?)(?:\n|$)", response)
                if search_match:
                    search_keywords = search_match.group(1).strip()
                    logger.info(f"Found search keywords from legacy format: {search_keywords}")

                    # Use new keyword-based search with user coordinates for validation
                    coords = await self.get_coordinates_from_search_keywords(search_keywords, user_lat, user_lon)
                    if coords:
                        return coords

                # Fallback: try to extract location name if no search keywords
                place_match = re.search(r"Локация:\s*(.+?)(?:\n|$)", response)
                if place_match:
                    place_name = place_match.group(1).strip()
                    logger.info(f"No search keywords found, using location name from legacy: {place_name}")

                    # Use location name as search keywords with user coordinates
                    coords = await self.get_coordinates_from_search_keywords(place_name, user_lat, user_lon)
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
                        # Return up to max_images best images with multiple URL formats
                        selected_images = []
                        for score, image_title in all_potential_images[:max_images * 2]:  # Try more images to account for failures
                            if len(selected_images) >= max_images:
                                break

                            # Clean image title - remove File: prefix if present
                            clean_title = image_title[5:] if image_title.startswith('File:') else image_title

                            # Try multiple URL formats for better reliability
                            # Skip images with potentially problematic filenames
                            if any(char in clean_title for char in ['|', ':', ';', '<', '>', '"']):
                                logger.debug(f"Skipping image with problematic filename: {clean_title}")
                                continue

                            # Try to get actual image URL using Wikimedia API
                            actual_image_url = await self._get_actual_image_url(clean_title, session, lang)
                            if actual_image_url:
                                selected_images.append(actual_image_url)
                                logger.debug(f"Selected image: {image_title} (score: {score}) -> {actual_image_url}")
                            else:
                                logger.debug(f"Failed to get actual URL for image: {clean_title}")

                        return selected_images

        except Exception as e:
            logger.debug(f"Error searching Wikipedia {lang} for '{search_term}': {e}")
            return []

        return []

    def _get_md5_hash(self, filename: str) -> str | None:
        """Get MD5 hash of filename for direct Wikipedia Commons URL.

        Args:
            filename: Wikipedia Commons filename

        Returns:
            MD5 hash string if successful, None otherwise
        """
        try:
            # Wikipedia Commons uses MD5 hash of filename for directory structure
            md5_hash = hashlib.md5(filename.encode('utf-8')).hexdigest()
            return md5_hash
        except Exception as e:
            logger.debug(f"Failed to calculate MD5 hash for {filename}: {e}")
            return None

    async def _get_actual_image_url(self, filename: str, session: aiohttp.ClientSession, lang: str = 'commons') -> str | None:
        """Get actual direct image URL using Wikimedia API.

        Args:
            filename: Clean filename without File: prefix
            session: aiohttp session to reuse
            lang: Language code, defaults to 'commons'

        Returns:
            Direct image URL if found, None otherwise
        """
        try:
            # Use Commons API to get the actual image info
            api_url = "https://commons.wikimedia.org/w/api.php"
            params = {
                'action': 'query',
                'format': 'json',
                'titles': f'File:{filename}',
                'prop': 'imageinfo',
                'iiprop': 'url',
                'iiurlwidth': '800'  # Request thumbnail width of 800px
            }

            headers = {"User-Agent": "NearbyFactBot/1.0 (Educational Project)"}

            async with session.get(api_url, params=params, headers=headers, timeout=5) as response:
                if response.status != 200:
                    logger.debug(f"API request failed for {filename}: status {response.status}")
                    return None

                data = await response.json()
                pages = data.get('query', {}).get('pages', {})

                for page_data in pages.values():
                    imageinfo = page_data.get('imageinfo', [])
                    if imageinfo:
                        # Try to get thumbnail URL first (better for Telegram)
                        thumb_url = imageinfo[0].get('thumburl')
                        if thumb_url:
                            logger.debug(f"Found thumbnail URL for {filename}: {thumb_url}")
                            return thumb_url

                        # Fallback to original URL
                        original_url = imageinfo[0].get('url')
                        if original_url:
                            logger.debug(f"Found original URL for {filename}: {original_url}")
                            return original_url

                logger.debug(f"No image info found for {filename}")
                return None

        except Exception as e:
            logger.debug(f"Error getting actual image URL for {filename}: {e}")
            return None

    async def get_wikipedia_image(self, search_keywords: str) -> str | None:
        """Get single image from Wikipedia using search keywords (backward compatibility).

        Args:
            search_keywords: Search keywords from GPT response

        Returns:
            Image URL if found, None otherwise
        """
        images = await self.get_wikipedia_images(search_keywords, max_images=1)
        return images[0] if images else None

    async def get_nearby_fact_with_history(self, lat: float, lon: float, cache_key: str | None = None, user_id: int = None) -> str:
        """Get fact for static location with history tracking to avoid repetition.

        Args:
            lat: Latitude coordinate
            lon: Longitude coordinate
            cache_key: Cache key for the location (coordinates or search keywords)
            user_id: User ID to check premium status for o3 model access

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
        fact_response = await self.get_nearby_fact(lat, lon, is_live_location=False, previous_facts=previous_facts, user_id=user_id)

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
    
    def _validate_city_coordinates(self, lat: float, lon: float, city_name: str) -> bool:
        """Validate that coordinates are within expected city bounds.
        
        Args:
            lat: Latitude to check
            lon: Longitude to check  
            city_name: Name of the city to validate against
            
        Returns:
            True if coordinates are within city bounds, False otherwise
        """
        city_bounds = {
            "Paris": (48.8566, 2.3522, 15),  # center_lat, center_lon, radius_km
            "Москва": (55.7558, 37.6173, 30), 
            "Moscow": (55.7558, 37.6173, 30),
            "London": (51.5074, -0.1278, 20),
            "New York": (40.7128, -74.0060, 25),
            "Санкт-Петербург": (59.9311, 30.3609, 20),
            "Saint Petersburg": (59.9311, 30.3609, 20),
            "St Petersburg": (59.9311, 30.3609, 20)
        }
        
        if city_name not in city_bounds:
            return True  # Can't validate unknown cities
            
        center_lat, center_lon, radius_km = city_bounds[city_name]
        distance = self._calculate_distance(lat, lon, center_lat, center_lon)
        
        return distance <= radius_km
    
    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two coordinates in kilometers.
        
        Args:
            lat1, lon1: First coordinate
            lat2, lon2: Second coordinate
            
        Returns:
            Distance in kilometers
        """
        from math import radians, cos, sin, asin, sqrt
        
        # Convert to radians
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        r = 6371  # Earth radius in kilometers
        
        return r * c


# Global client instance - will be initialized lazily
_openai_client: OpenAIClient | None = None


def get_openai_client() -> OpenAIClient:
    """Get or create the global OpenAI client instance."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAIClient()
    return _openai_client
