"""OpenAI client for generating location-based facts."""

import logging
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
            user_language = "ru"  # Default to Russian
            if user_id:
                try:
                    donors_db = get_donors_db()
                    is_premium_user = donors_db.is_premium_user(user_id)
                    user_language = donors_db.get_user_language(user_id)
                except Exception as e:
                    logger.warning(f"Failed to check user preferences for user {user_id}: {e}")
            
            # Choose appropriate system prompt based on location type  
            if is_live_location:
                # Detailed system prompt for live locations (o4-mini/o3)
                system_prompt = f"""You are tasked with analyzing geographical coordinates and providing an interesting fact about the location. Follow these instructions carefully:

IMPORTANT: You must respond entirely in {user_language}. All your analysis, reasoning, and final answer must be in {user_language}.

Follow this step-by-step reasoning process:

Step 1: Determine the geographical location based on the coordinates. Identify the city, district, and country.

Step 2: Find nearby toponyms (streets, buildings, monuments, parks, memorial plaques). Prioritize the closest ones!

Step 3: Analyze what interesting historical, architectural, or cultural facts you know about this area or nearby attractions.

Step 4: Choose a fact nearby, considering the following priorities:
   A) PRIORITY: Something in the immediate vicinity
   B) Acceptable: Nearby places (short walk)
   C) Acceptable: In the same part of the city
   D) In large cities, there is ALWAYS something interesting nearby — keep searching!

Use this search strategy:
• First, look for obvious landmarks: streets, squares, parks, buildings
• Then think about the history of the area, architecture, culture
• If the place seems ordinary, look for details: monuments, historic buildings, cultural features
• As a last resort, talk about the architectural style, urban planning, or history of the area

Adopt the Atlas Obscura style:
• Look for unusual stories, architectural details, cultural features
• Hidden facts and non-obvious connections are more interesting than banal information
• IMPORTANT: Use only reliable information, do not make things up
• Approximate dates are acceptable if they make the story more lively
• If you're not sure about specific details, provide an engaging general context
• ALWAYS find something amazing — refusal is not acceptable

Your goal is to create a DETAILED and ENGAGING fact (approximately 100-120 words). Include:
- Unusual historical details or little-known events (only credible ones)
- Architectural secrets, hidden elements, non-obvious features
- Intriguing connections with famous personalities or events
- Cultural peculiarities, local legends, urban stories
- If the place is ordinary, find something unexpected and amazing about it
- IMPORTANT: Do not invent facts — use only what you are sure about
- DO NOT SPECIFY exact distances in meters — just talk about the place

Remember: ALL your response must be in {user_language}."""
            else:
                # Concise system prompt for static locations (GPT-4.1)
                system_prompt = f"""You are an AI assistant tasked with analyzing geographical coordinates and finding the nearest interesting place along with a brief, engaging fact about it. Your goal is to provide users with unexpected and intriguing information about locations near the given coordinates.

IMPORTANT: You must respond entirely in {user_language}. All your analysis and final answer must be in {user_language}.

When searching for an interesting place, prioritize locations in this order:
1. BEST: Objects in the immediate vicinity
2. GOOD: Nearby places (short walking distance)
3. ACCEPTABLE: In the same part of the city
4. Remember: In large cities, there's almost always something interesting nearby!

Follow this Atlas Obscura-inspired strategy when searching for interesting places:
• Look for streets, squares, buildings, or parks with unusual histories
• Seek out hidden architectural details or little-known historical events
• IMPORTANT: Only use factual information - do not invent or embellish facts
• If the location seems ordinary, find something surprising about it
• When in doubt, provide general interesting context rather than specific details
• ALWAYS find an unexpected and interesting fact

Your goal is to provide a brief but ENGAGING fact (60-80 words) that includes:
- Unusual historical details or little-known events (only verified facts)
- Intriguing architectural features or cultural information
- Non-obvious connections or surprising details
- IMPORTANT: Do not invent facts - it's better to give general context than made-up specifics
- DO NOT mention exact distances in meters - simply describe the place

Remember: ALL your response must be in {user_language}."""

            # Handle previous facts for both live and static locations
            previous_facts_text = ""
            if previous_facts:
                previous_facts_text = (
                    "\n\nYou have already mentioned these places:\n"
                    + "\n".join([f"- {fact}" for fact in previous_facts[-5:]])
                    + "\n\nFind a DIFFERENT place near the same coordinates, do not repeat already mentioned locations."
                )

            if is_live_location:
                # Detailed prompt for live location (o4-mini/o3)
                user_prompt = f"""Analyze these coordinates: {lat}, {lon}

You will be provided with previous facts that have already been mentioned about this location or nearby areas in the following format:
{previous_facts_text}

Make sure to choose a fact that has not been mentioned in the previous facts. If all obvious facts have been covered, dig deeper to find more obscure or specific information about the location or its surroundings.

Present your final answer in this format:
<answer>
Location: [Specific name of the place]
Search: [Keywords for accurate search: ORIGINAL name in local language + city + country. For example: 'Louvre Museum Paris France' or 'Красная площадь Москва Россия']
Interesting fact: [Detailed fact with historical details, approximately 100-120 words]
</answer>

Remember, your final output should only include the content within the <answer> tags. Do not include any of your thought process or the steps you took to arrive at your answer."""
            else:
                # Concise prompt for static location (gpt-4.1)
                user_prompt = f"""Here are the coordinates to analyze:
<coordinates>
Latitude: {lat}
Longitude: {lon}
</coordinates>

Before providing your answer, consider any previous facts that have been shared about nearby locations. This will help you avoid repetition and ensure you're providing new, interesting information. Here are the previous facts (if any):
<previous_facts>
{previous_facts_text if previous_facts_text else "None"}
</previous_facts>

Format your final answer as follows:
<answer>
Location: [Specific name of the place]
Search: [Keywords for precise search: ORIGINAL name in local language + city + country. For example: 'Louvre Museum Paris France' or 'Red Square Moscow Russia']
Interesting fact: [Brief but engaging fact, 60-80 words]
</answer>

Remember to think creatively and find truly engaging and unexpected information about the location you choose. Good luck!"""

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
                    response = await self.client.chat.completions.create(
                        model=model_to_use,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        max_completion_tokens=max_tokens_limit,
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
                        max_tokens=800,
                        temperature=0.7,
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
            # Extract content from <answer> tags first
            answer_match = re.search(r"<answer>(.*?)</answer>", response, re.DOTALL)
            if answer_match:
                answer_content = answer_match.group(1).strip()
                
                # Extract search keywords from answer content
                search_match = re.search(r"Search:\s*(.+?)(?:\n|$)", answer_content)
                if search_match:
                    search_keywords = search_match.group(1).strip()
                    logger.info(f"Found search keywords from <answer> tags: {search_keywords}")

                    # Use new keyword-based search
                    coords = await self.get_coordinates_from_search_keywords(search_keywords)
                    if coords:
                        return coords

                # Fallback: extract location name from answer content
                location_match = re.search(r"Location:\s*(.+?)(?:\n|$)", answer_content)
                if location_match:
                    place_name = location_match.group(1).strip()
                    logger.info(f"No search keywords found, using location name from <answer>: {place_name}")

                    # Use location name as search keywords
                    coords = await self.get_coordinates_from_search_keywords(place_name)
                    if coords:
                        return coords
            
            # Legacy fallback for old format responses (will be removed eventually)
            else:
                # First, try to extract search keywords from old format
                search_match = re.search(r"Поиск:\s*(.+?)(?:\n|$)", response)
                if search_match:
                    search_keywords = search_match.group(1).strip()
                    logger.info(f"Found search keywords from legacy format: {search_keywords}")

                    # Use new keyword-based search
                    coords = await self.get_coordinates_from_search_keywords(search_keywords)
                    if coords:
                        return coords

                # Fallback: try to extract location name if no search keywords
                place_match = re.search(r"Локация:\s*(.+?)(?:\n|$)", response)
                if place_match:
                    place_name = place_match.group(1).strip()
                    logger.info(f"No search keywords found, using location name from legacy: {place_name}")

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
                        # Return up to max_images best images with multiple URL formats
                        selected_images = []
                        for score, image_title in all_potential_images[:max_images * 2]:  # Try more images to account for failures
                            if len(selected_images) >= max_images:
                                break
                            
                            # Clean image title - remove File: prefix if present
                            clean_title = image_title[5:] if image_title.startswith('File:') else image_title
                            
                            # Use the most reliable URL format for Telegram
                            # This format works better and handles redirects properly
                            image_url = f"https://commons.wikimedia.org/wiki/Special:Redirect/file/{quote(clean_title)}?width=800"
                            selected_images.append(image_url)
                            logger.debug(f"Selected image: {image_title} (score: {score}) -> {image_url}")
                        
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


# Global client instance - will be initialized lazily
_openai_client: OpenAIClient | None = None


def get_openai_client() -> OpenAIClient:
    """Get or create the global OpenAI client instance."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAIClient()
    return _openai_client
