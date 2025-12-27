"""Live location tracking service for managing user location streams."""

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from telegram import Bot, InputMediaPhoto

from ..utils.formatting_utils import (
    extract_place_names_from_history as _extract_place_names,
)
from ..utils.formatting_utils import (
    extract_sources_from_answer as _extract_live_sources,
)
from ..utils.formatting_utils import is_duplicate_place as _is_duplicate_place
from ..utils.formatting_utils import (
    remove_bare_links_from_text as _remove_bare_links_from_text,
)
from ..utils.formatting_utils import strip_sources_section as _strip_live_sources
from .claude_client import get_claude_client as get_openai_client
from .firebase_stats import increment_fact_counters as fb_increment_fact

# Avoid importing handlers at module import time to prevent circular deps.
# We'll import get_localized_message lazily inside functions.

# Maximum retry attempts when AI returns a duplicate place
MAX_DUPLICATE_RETRIES = 2

logger = logging.getLogger(__name__)


async def send_live_fact_with_images(bot, chat_id, formatted_response, search_keywords, place, lat: float | None = None, lon: float | None = None, sources: list[tuple[str, str]] | None = None):
    """Send live fact message with Wikipedia images if available.
    
    Args:
        bot: Telegram bot instance
        chat_id: Chat ID to send to
        formatted_response: Formatted text response
        search_keywords: Keywords to search images for
        place: Place name for caption
    """
    try:
        # Try to get Wikipedia images
        openai_client = get_openai_client()
        # Provide coords via local names for optional introspection inside pipeline
        latitude = lat
        longitude = lon
        image_urls = await openai_client.get_wikipedia_images(
            search_keywords,
            max_images=4,  # Max 4 for media group
            lat=lat,
            lon=lon,
            place_hint=place,
            sources=sources,
            fact_text=formatted_response  # Pass full fact text for better relevance
        )



        if image_urls:
            # Try sending all images with text as media group
            try:
                logger.info(f"Attempting to send live fact with {len(image_urls)} images for {place}")
                logger.debug(f"Live formatted response length: {len(formatted_response)} chars")

                # Use full response as caption but ensure Markdown is safe
                caption_text = formatted_response

                # Debug logging for Markdown issues
                logger.debug(f"Caption text for debugging (first 200 chars): {caption_text[:200]}")
                logger.debug(f"Caption length: {len(caption_text)}")

                # For better UX, prefer keeping sources with images if they fit
                # Maximum safe caption length for Telegram
                max_caption_length = 1024

                if len(caption_text) <= max_caption_length:
                    # Caption fits in Telegram limit, send as media group with caption
                    media_list = []
                    for i, image_url in enumerate(image_urls):
                        if i == 0:
                            # First image gets the full fact as caption with Markdown
                            media_list.append(InputMediaPhoto(media=image_url, caption=caption_text, parse_mode="Markdown"))
                        else:
                            # Other images get no caption
                            media_list.append(InputMediaPhoto(media=image_url))

                    if len(media_list) == 1:
                        await bot.send_photo(chat_id=chat_id, photo=image_urls[0], caption=caption_text)
                    else:
                        await bot.send_media_group(chat_id=chat_id, media=media_list)
                    logger.info(f"Successfully sent {len(image_urls)} live images with caption in media group for {place}")
                else:
                    # Caption too long → first photo with shortened caption + rest without captions
                    # Safely truncate without breaking Markdown entities
                    max_len = 900  # Leave more room for safety
                    if len(caption_text) > max_len:
                        # First, try to find a safe breaking point before any sources section
                        sources_start = caption_text.find("\n\n🔗")
                        if sources_start > 0 and sources_start < max_len:
                            # Cut before sources section
                            short_caption = caption_text[:sources_start].rstrip() + "..."
                        else:
                            # Find a good breaking point (paragraph or sentence) before max_len
                            break_point = max_len
                            # Look for paragraph break first
                            for i in range(max_len-1, max(0, max_len-300), -1):
                                if caption_text[i:i+2] == '\n\n':
                                    break_point = i
                                    break
                            # If no paragraph break, look for sentence end
                            if break_point == max_len:
                                for i in range(max_len-1, max(0, max_len-200), -1):
                                    if caption_text[i] in '.!?' and i+1 < len(caption_text) and caption_text[i+1] in ' \n':
                                        break_point = i + 1
                                        break
                            # Last resort: break at space
                            if break_point == max_len:
                                for i in range(max_len-1, max(0, max_len-100), -1):
                                    if caption_text[i] in ' \n':
                                        break_point = i
                                        break
                            short_caption = caption_text[:break_point].rstrip() + "..."
                    else:
                        short_caption = caption_text
                    media_list = []
                    for i, image_url in enumerate(image_urls):
                        if i == 0:
                            media_list.append(InputMediaPhoto(media=image_url, caption=short_caption, parse_mode="Markdown"))
                        else:
                            media_list.append(InputMediaPhoto(media=image_url))
                    await bot.send_media_group(chat_id=chat_id, media=media_list)
                    logger.info(f"Successfully sent long live text + {len(image_urls)} images as media group for {place}")

                    # If we truncated and there were sources, send them as a separate message
                    sources_start_pos = caption_text.find("\n\n🔗")
                    if len(caption_text) > max_len and sources and sources_start_pos > 0:
                        try:
                            # Reconstruct sources section
                            from ..handlers.location import (
                                get_localized_message as _get_msg,
                            )
                            from ..utils.formatting_utils import (
                                sanitize_url as _sanitize_url,
                            )

                            # Get user_id from chat_id by extracting from the context
                            # For live location, chat_id is usually the user_id for private chats
                            user_id = chat_id if chat_id > 0 else 0

                            src_label = await _get_msg(user_id, 'sources_label')
                            bullets = []
                            for title, url in sources[:4]:
                                # Remove square brackets and escape other Markdown characters in title
                                safe_title = re.sub(r"[\[\]]", "", title)[:80]
                                # Escape Markdown special chars in title to prevent parsing errors
                                safe_title = safe_title.replace("*", "\\*").replace("_", "\\_").replace("`", "\\`").replace("(", "\\(").replace(")", "\\)")
                                safe_url = _sanitize_url(url)
                                bullets.append(f"- [{safe_title}]({safe_url})")
                            sources_msg = f"{src_label}\n" + "\n".join(bullets)

                            await bot.send_message(chat_id=chat_id, text=sources_msg, parse_mode="Markdown", disable_web_page_preview=True)
                            logger.info(f"Sent truncated sources in separate message for {place}")
                        except Exception as e:
                            logger.warning(f"Failed to send truncated sources: {e}")

                return

            except Exception as media_group_error:
                logger.error(f"Failed to send live fact text + media group: {media_group_error}")
                logger.error(f"Live fact error type: {type(media_group_error)}")
                try:
                    logger.error(f"Live image URLs that failed: {[img.media for img in media_list]}")
                except Exception:
                    logger.error("Live image URLs that failed: unavailable")

                # Try with fewer images if we had multiple images
                if len(image_urls) > 2:
                    logger.info(f"Retrying live fact with fewer images (2 instead of {len(image_urls)})")
                    try:
                        # Retry with only first 2 images, ensure caption fits limit
                        short_caption = caption_text
                        if len(short_caption) > 1024:
                            max_len = 1020
                            break_point = max_len
                            for i in range(max_len-1, max_len-200, -1):
                                if short_caption[i] in ' \n':
                                    break_point = i
                                    break
                            short_caption = short_caption[:break_point].rstrip() + "..."

                        retry_media_list = []
                        for i, image_url in enumerate(image_urls[:2]):
                            if i == 0:
                                retry_media_list.append(InputMediaPhoto(media=image_url, caption=short_caption, parse_mode="Markdown"))
                            else:
                                retry_media_list.append(InputMediaPhoto(media=image_url))

                        await bot.send_media_group(chat_id=chat_id, media=retry_media_list)
                        logger.info(f"Successfully sent {len(retry_media_list)} live images on retry for {place}")
                        return
                    except Exception as retry_error:
                        logger.error(f"Live fact retry with fewer images also failed: {retry_error}")

                # Check if text was sent successfully by trying to send it again
                try:
                    # Import localization function to avoid circular imports
                    from ..handlers.location import get_localized_message
                    fallback_message = await get_localized_message(0, 'image_fallback')  # Use user_id=0 for generic message
                    try:
                        await bot.send_message(
                            chat_id=chat_id,
                            text=f"{fallback_message}{formatted_response}",
                            parse_mode="Markdown"
                        )
                    except Exception:
                        await bot.send_message(chat_id=chat_id, text=f"{fallback_message}{formatted_response}")
                    logger.info(f"Sent fallback live text-only message for {place}")
                    return
                except Exception as text_fallback_error:
                    logger.error(f"Failed to send live fact fallback text: {text_fallback_error}")

                # Last resort: try sending individual images
                try:
                    # Try to send individual images (up to 2 to avoid spam)
                    successful_images = 0
                    for image_url in image_urls[:2]:  # Limit to 2 images
                        try:
                            await bot.send_photo(
                                chat_id=chat_id,
                                photo=image_url,
                                caption=f"📸 {place}"
                            )
                            successful_images += 1
                        except Exception as individual_error:
                            logger.debug(f"Failed to send individual live fact image: {individual_error}")
                            continue

                    if successful_images > 0:
                        logger.info(f"Sent {successful_images} individual live images (no text) for {place}")
                    else:
                        logger.warning(f"All live image sending methods failed for {place}")
                    return

                except Exception as individual_fallback_error:
                    logger.error(f"Failed to send individual live fact images fallback: {individual_fallback_error}")

        # No images found or all fallbacks failed, send just the text
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=formatted_response,
                parse_mode="Markdown"
            )
        except Exception:
            await bot.send_message(chat_id=chat_id, text=formatted_response)
        logger.info(f"Sent live fact without images for {place}")

    except Exception as e:
        logger.warning(f"Failed to send live fact with images: {e}")
        # Final fallback to text-only message
        try:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=formatted_response,
                    parse_mode="Markdown"
                )
            except Exception:
                await bot.send_message(chat_id=chat_id, text=formatted_response)
        except Exception as fallback_error:
            logger.error(f"Failed to send fallback live fact message: {fallback_error}")


@dataclass
class LiveLocationData:
    """Data structure for tracking live location sessions."""

    user_id: int
    chat_id: int
    latitude: float
    longitude: float
    last_update: datetime
    live_period: int
    fact_interval_minutes: int = 10  # Default 10 minutes
    fact_count: int = 0  # Counter for facts sent
    fact_history: list = None  # History of sent facts to avoid repetition
    task: asyncio.Task | None = None
    monitor_task: asyncio.Task | None = None  # Health monitoring task
    session_start: datetime = None  # Track when session started
    stop_requested: bool = False  # Flag to signal stop request
    last_coordinate_update: datetime = None  # Track when Telegram last sent coordinate update
    is_generating_fact: bool = False  # Flag to indicate fact generation in progress

    def __post_init__(self):
        if self.fact_history is None:
            self.fact_history = []
        if self.session_start is None:
            self.session_start = datetime.now()
        if self.last_coordinate_update is None:
            self.last_coordinate_update = datetime.now()


class LiveLocationTracker:
    """Service for tracking and managing live location sessions."""

    def __init__(self):
        """Initialize the tracker."""
        self._active_sessions: dict[int, LiveLocationData] = {}
        self._lock = asyncio.Lock()

    async def start_live_location(
        self,
        user_id: int,
        chat_id: int,
        latitude: float,
        longitude: float,
        live_period: int,
        bot: Bot,
        fact_interval_minutes: int = 10,
    ) -> None:
        """Start tracking live location for a user.

        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID
            latitude: Initial latitude
            longitude: Initial longitude
            live_period: Live location period in seconds
            bot: Telegram bot instance
            fact_interval_minutes: How often to send facts (in minutes)
        """
        async with self._lock:
            # Stop existing session if any
            if user_id in self._active_sessions:
                logger.info(f"Stopping existing live location session for user {user_id}")
                await self._stop_session(user_id)
                # Give a moment for cleanup to complete
                await asyncio.sleep(0.05)

            # Create new session data
            session_data = LiveLocationData(
                user_id=user_id,
                chat_id=chat_id,
                latitude=latitude,
                longitude=longitude,
                last_update=datetime.now(),
                live_period=live_period,
                fact_interval_minutes=fact_interval_minutes,
                session_start=datetime.now(),
            )

            # Start the fact sending task
            try:
                # Eagerly store session before tasks so we can cancel on slow startups
                self._active_sessions[user_id] = session_data

                task = asyncio.create_task(self._fact_sending_loop(session_data, bot))
                session_data.task = task

                # Start health monitor task
                monitor_task = asyncio.create_task(self._monitor_session_health(session_data, bot))
                session_data.monitor_task = monitor_task

                logger.info(
                    f"Started live location tracking for user {user_id} for {live_period}s, facts every {fact_interval_minutes} min"
                )
            except Exception as e:
                logger.error(f"Failed to start live location task for user {user_id}: {e}")
                # Ensure cleanup on failure
                await self._stop_session(user_id)
                raise

    async def update_live_location(
        self,
        user_id: int,
        latitude: float,
        longitude: float,
    ) -> None:
        """Update coordinates for an active live location session.

        Args:
            user_id: Telegram user ID
            latitude: New latitude
            longitude: New longitude
        """
        # Do not write every update to Firestore to reduce noise and costs.
        # We record movement only at the moment we actually attempt to send a fact
        # inside the fact-sending loop.

        async with self._lock:
            if user_id in self._active_sessions:
                session = self._active_sessions[user_id]
                session.latitude = latitude
                session.longitude = longitude
                session.last_update = datetime.now()
                session.last_coordinate_update = datetime.now()  # Track coordinate updates from Telegram

                logger.info(
                    f"Updated live location for user {user_id}: {latitude}, {longitude}"
                )

    async def stop_live_location(self, user_id: int) -> None:
        """Stop live location tracking for a user.

        Args:
            user_id: Telegram user ID
        """
        # First, mark session for stopping without waiting for lock
        if user_id in self._active_sessions:
            session = self._active_sessions[user_id]
            session.stop_requested = True  # Signal to stop

        # Try to acquire lock with timeout to avoid hanging
        try:
            # Use wait_for for Python 3.9+ compatibility
            await asyncio.wait_for(
                self._stop_with_lock(user_id),
                timeout=1.0
            )
        except TimeoutError:
            logger.warning(f"Timeout stopping session for user {user_id}, forcing stop")
            # Force stop without lock
            if user_id in self._active_sessions:
                session = self._active_sessions.pop(user_id)
                if session.task and not session.task.done():
                    session.task.cancel()
                if hasattr(session, 'monitor_task') and session.monitor_task and not session.monitor_task.done():
                    session.monitor_task.cancel()
                logger.info(f"Force-stopped live location for user {user_id}")

    async def _stop_with_lock(self, user_id: int) -> None:
        """Stop session with lock acquired."""
        async with self._lock:
            await self._stop_session(user_id)

    async def _stop_session(self, user_id: int) -> None:
        """Internal method to stop a session (called with lock held)."""
        if user_id in self._active_sessions:
            session = self._active_sessions[user_id]
            # Remove session first so further updates are ignored immediately
            del self._active_sessions[user_id]

            # Cancel fact sending task
            if session.task and not session.task.done():
                session.task.cancel()
                try:
                    await session.task
                except asyncio.CancelledError:
                    pass

            # Cancel monitor task
            if hasattr(session, 'monitor_task') and session.monitor_task and not session.monitor_task.done():
                session.monitor_task.cancel()
                try:
                    await session.monitor_task
                except asyncio.CancelledError:
                    pass
            logger.info(f"Stopped live location tracking for user {user_id}")

    async def _fact_sending_loop(
        self, session_data: LiveLocationData, bot: Bot
    ) -> None:
        """Background task that sends facts at custom intervals.

        Args:
            session_data: Live location session data
            bot: Telegram bot instance
        """
        try:
            # Calculate session end time based on when it started
            session_end_time = session_data.session_start + timedelta(seconds=session_data.live_period)

            # Desired interval between facts
            desired_interval_seconds = session_data.fact_interval_minutes * 60

            # Initial wait: 30 seconds to give user time to start walking
            initial_sleep = 30
            for _ in range(initial_sleep):
                if session_data.stop_requested:
                    logger.info(f"Stop requested during initial wait for user {session_data.user_id}")
                    return
                await asyncio.sleep(1)

            while True:
                # Check if stop was requested
                if session_data.stop_requested:
                    logger.info(f"Stop requested for user {session_data.user_id}, exiting fact loop")
                    break

                current_time = datetime.now()

                # Check if session has exceeded its live_period
                if current_time >= session_end_time:
                    logger.info(
                        f"Live location session expired for user {session_data.user_id} "
                        f"(started: {session_data.session_start}, live_period: {session_data.live_period}s)"
                    )
                    # Send notification to user that session has ended
                    try:
                        from ..handlers.location import get_localized_message
                        stop_message = await get_localized_message(session_data.user_id, 'live_expired')
                        await bot.send_message(
                            chat_id=session_data.chat_id,
                            text=stop_message,
                            parse_mode="Markdown",
                        )
                    except Exception as notify_error:
                        logger.error(f"Failed to send session end notification: {notify_error}")
                    break

                # Check if we haven't received coordinate updates from Telegram
                # This indicates user stopped sharing live location
                # Use adaptive threshold: min 15 minutes, or interval + 10 minutes (whichever is larger)
                # This gives PLENTY of time for Telegram to send updates even if user is stationary
                coordinate_timeout_minutes = max(15, session_data.fact_interval_minutes + 10)
                time_since_coordinate_update = current_time - session_data.last_coordinate_update
                if time_since_coordinate_update > timedelta(minutes=coordinate_timeout_minutes):
                    logger.info(
                        f"Live location stopped updating for user {session_data.user_id} "
                        f"(last coordinate update: {session_data.last_coordinate_update}, {time_since_coordinate_update.total_seconds():.0f}s ago, threshold: {coordinate_timeout_minutes} min)"
                    )
                    # Send notification that we detected manual stop
                    try:
                        from ..handlers.location import get_localized_message
                        stop_message = await get_localized_message(session_data.user_id, 'live_manual_stop')
                        await bot.send_message(
                            chat_id=session_data.chat_id,
                            text=stop_message,
                            parse_mode="Markdown",
                        )
                    except Exception as notify_error:
                        logger.error(f"Failed to send manual stop notification: {notify_error}")
                    break

                # Send fact at current coordinates
                try:
                    send_start_time = datetime.now()
                    # DON'T increment counter yet - only increment when fact is actually sent

                    # Set flag to indicate generation in progress
                    session_data.is_generating_fact = True
                    # Update last_update timestamp BEFORE generation to prevent monitor from killing session
                    session_data.last_update = datetime.now()

                    openai_client = get_openai_client()

                    # First fact always uses reasoning=none for speed (regardless of user settings)
                    # Subsequent facts use user's preferred reasoning level
                    force_reasoning_none = (session_data.fact_count == 0)

                    # Extract previous place names for duplicate checking
                    previous_place_names = _extract_place_names(session_data.fact_history)

                    # Try to get a unique fact, with retries if duplicate detected
                    place = None
                    fact = None
                    search_keywords = ""
                    poi_lat = None
                    poi_lon = None
                    sources = []
                    sources_block = ""
                    response = None

                    for duplicate_retry in range(MAX_DUPLICATE_RETRIES + 1):
                        # Build previous_facts with stronger emphasis on place names
                        # Include explicit list of place names to avoid
                        extended_previous_facts = session_data.fact_history.copy()

                        # On retry, add explicit duplicate warning
                        if duplicate_retry > 0:
                            logger.info(f"Duplicate retry {duplicate_retry}/{MAX_DUPLICATE_RETRIES} for user {session_data.user_id}")
                            # Add strong instruction to avoid the duplicate place
                            avoid_places = ", ".join([f'"{p}"' for p in previous_place_names[-5:]])
                            extended_previous_facts.append(
                                f"DUPLICATE DETECTED! You MUST find a COMPLETELY DIFFERENT place. "
                                f"DO NOT mention these places again: {avoid_places}"
                            )

                        response = await openai_client.get_nearby_fact(
                            session_data.latitude,
                            session_data.longitude,
                            is_live_location=True,
                            previous_facts=extended_previous_facts,
                            user_id=session_data.user_id,
                            force_reasoning_none=force_reasoning_none,
                        )

                        # Check if no POI was found
                        if response and "[[NO_POI_FOUND]]" in response:
                            logger.info(f"No POI found for live location (attempt skipped) for user {session_data.user_id}")
                            break  # Exit retry loop, will skip to next interval

                        # Parse the response to extract place and fact
                        from ..handlers.location import get_localized_message
                        place = await get_localized_message(session_data.user_id, 'near_you')  # Default location
                        fact = response  # Default to full response if parsing fails
                        search_keywords = ""
                        poi_lat = None
                        poi_lon = None
                        sources = []
                        sources_block = ""

                        # Try to parse structured response from <answer> tags first
                        answer_match = re.search(r"<answer>(.*?)(?:</answer>|$)", response, re.DOTALL)
                        if answer_match:
                            answer_content = answer_match.group(1).strip()

                            # Extract location from answer content
                            location_match = re.search(r"Location:\s*(.+?)(?:\n|$)", answer_content)
                            if location_match:
                                place = location_match.group(1).strip()

                            # Extract precise POI coordinates if provided
                            coord_match = re.search(r"Coordinates:\s*([\-\d\.]+)\s*,\s*([\-\d\.]+)", answer_content)
                            if coord_match:
                                try:
                                    poi_lat = float(coord_match.group(1))
                                    poi_lon = float(coord_match.group(2))
                                except Exception:
                                    pass

                            # Extract search keywords from answer content
                            search_match = re.search(r"Search:\s*(.+?)(?:\n|$)", answer_content)
                            if search_match:
                                search_keywords = search_match.group(1).strip()

                            # Extract fact from answer content
                            fact_match = re.search(r"Interesting fact:\s*(.*?)(?=\n(?:Sources|Источники)\s*:|$)", answer_content, re.DOTALL)
                            if fact_match:
                                fact = _strip_live_sources(fact_match.group(1).strip())
                                fact = _remove_bare_links_from_text(fact)

                            # Build sources block
                            sources = _extract_live_sources(answer_content)
                            if sources:
                                from ..handlers.location import (
                                    get_localized_message as _get_msg,
                                )
                                from ..utils.formatting_utils import (
                                    sanitize_url as _sanitize_url,
                                )
                                src_label = await _get_msg(session_data.user_id, 'sources_label')
                                bullets = []
                                for title, url in sources[:4]:
                                    safe_title = re.sub(r"[\[\]]", "", title)[:80]
                                    safe_title = safe_title.replace("*", "\\*").replace("_", "\\_").replace("`", "\\`").replace("(", "\\(").replace(")", "\\)")
                                    safe_url = _sanitize_url(url)
                                    bullets.append(f"- [{safe_title}]({safe_url})")
                                sources_block = f"\n\n{src_label}\n" + "\n".join(bullets)

                        # Legacy fallback for old format responses
                        else:
                            lines = response.split("\n")
                            for i, line in enumerate(lines):
                                if line.startswith("Локация:"):
                                    place = line.replace("Локация:", "").strip()
                                elif line.startswith("Интересный факт:"):
                                    fact_lines = []
                                    fact_lines.append(line.replace("Интересный факт:", "").strip())
                                    for j in range(i + 1, len(lines)):
                                        if lines[j].strip():
                                            fact_lines.append(lines[j].strip())
                                    fact = " ".join(fact_lines)
                                    break

                        # CHECK FOR DUPLICATE: compare against previous places
                        if _is_duplicate_place(place, previous_place_names):
                            logger.warning(
                                f"Duplicate place detected for user {session_data.user_id}: '{place}' "
                                f"(previous: {previous_place_names[-3:]})"
                            )
                            if duplicate_retry < MAX_DUPLICATE_RETRIES:
                                # Will retry with stronger instructions
                                continue
                            else:
                                # Max retries reached, skip this fact
                                logger.error(
                                    f"Max duplicate retries reached for user {session_data.user_id}, "
                                    f"skipping this interval"
                                )
                                place = None  # Signal to skip
                                break
                        else:
                            # Unique place found, exit retry loop
                            logger.info(f"Unique place found for user {session_data.user_id}: '{place}'")
                            break

                    # Check if we should skip this iteration (NO_POI_FOUND or max duplicate retries)
                    if response and "[[NO_POI_FOUND]]" in response:
                        continue  # Skip to next interval

                    if place is None:
                        # Max duplicate retries reached, skip this interval
                        continue

                    # Increment counter ONLY when we have a real fact to send
                    session_data.fact_count += 1

                    # Format the response with live location indicator and fact number
                    from ..handlers.location import (
                        _escape_markdown,
                        get_localized_message,
                    )
                    escaped_place = _escape_markdown(place)
                    escaped_fact = _escape_markdown(fact)
                    formatted_response = await get_localized_message(session_data.user_id, 'live_fact_format', number=session_data.fact_count, place=escaped_place, fact=escaped_fact)

                    # Add sources to the main message if available
                    if sources_block:
                        formatted_response = f"{formatted_response}{sources_block}"

                    # Save fact to history to avoid repetition
                    session_data.fact_history.append(f"{place}: {fact}")

                    # Send the fact with images using extracted search keywords
                    if search_keywords:
                        await send_live_fact_with_images(
                            bot,
                            session_data.chat_id,
                            formatted_response,
                            search_keywords,
                            place,
                            lat=poi_lat,  # Use POI coordinates for image search
                            lon=poi_lon,
                            sources=sources,
                        )
                    else:
                        # Legacy fallback: try to extract search keywords from old format
                        legacy_search_match = re.search(r"Поиск:\s*(.+?)(?:\n|$)", response)
                        if legacy_search_match:
                            legacy_search_keywords = legacy_search_match.group(1).strip()
                            await send_live_fact_with_images(
                                bot,
                                session_data.chat_id,
                                formatted_response,
                                legacy_search_keywords,
                                place,
                                lat=poi_lat,  # Use POI coordinates for image search
                                lon=poi_lon,
                                sources=sources,
                            )
                        else:
                            # No search keywords, send just text
                            await bot.send_message(
                                chat_id=session_data.chat_id,
                                text=formatted_response,
                                parse_mode="Markdown",
                            )

                    # Use POI coordinates for navigation venue if available
                    if poi_lat is not None and poi_lon is not None:
                        venue_lat, venue_lon = poi_lat, poi_lon
                    else:
                        # Try to parse coordinates from response as fallback
                        # Keep user coordinates for 5km validation (prevents hallucinated distant coordinates)
                        try:
                            coordinates = await openai_client.parse_coordinates_from_response(
                                response, session_data.latitude, session_data.longitude
                            )
                            if coordinates:
                                venue_lat, venue_lon = coordinates
                            else:
                                venue_lat, venue_lon = None, None
                        except Exception:
                            venue_lat, venue_lon = None, None

                    # Validate: if POI coords are suspiciously close to user's location, they're likely wrong
                    # Claude sometimes returns user coordinates instead of POI coordinates
                    # Threshold: 0.002 degrees ≈ 200 meters (at equator, less at higher latitudes)
                    try:
                        too_close_to_user = False
                        if venue_lat is not None and venue_lon is not None:
                            dy = abs(venue_lat - session_data.latitude)
                            dx = abs(venue_lon - session_data.longitude)
                            # Expanded threshold from 1e-6 (0.11m) to 0.002° (~200m) to catch nearby coords
                            too_close_to_user = (dy < 0.002 and dx < 0.002)
                            if too_close_to_user:
                                logger.warning(
                                    f"Venue coordinates too close to user location "
                                    f"(venue: {venue_lat}, {venue_lon}; user: {session_data.latitude}, {session_data.longitude}; "
                                    f"delta: {dy:.6f}, {dx:.6f}). Will try Nominatim fallback."
                                )
                        if too_close_to_user and search_keywords:
                            logger.info(f"Attempting Nominatim lookup with search keywords: {search_keywords}")
                            nomi = await openai_client.get_coordinates_from_search_keywords(search_keywords, session_data.latitude, session_data.longitude)
                            if nomi:
                                venue_lat, venue_lon = nomi
                                logger.info(f"Successfully adjusted venue via Nominatim from Search: {venue_lat}, {venue_lon}")
                            else:
                                logger.warning("Nominatim lookup failed, venue will not be sent")
                                venue_lat, venue_lon = None, None
                        elif too_close_to_user and not search_keywords:
                            logger.warning("Venue too close to user but no search keywords available, venue will not be sent")
                            venue_lat, venue_lon = None, None
                    except Exception as e:
                        logger.error(f"Error validating venue coordinates: {e}")
                        pass

                    if venue_lat is not None and venue_lon is not None:
                        try:
                            # Send venue with location for navigation
                            await bot.send_venue(
                                chat_id=session_data.chat_id,
                                latitude=venue_lat,
                                longitude=venue_lon,
                                title=place,
                                address=await get_localized_message(session_data.user_id, 'attraction_address', place=place),
                            )
                            logger.info(
                                f"Sent venue location for background fact navigation: {place} at {venue_lat}, {venue_lon}"
                            )
                        except Exception as venue_error:
                            logger.warning(
                                f"Failed to send venue for background fact: {venue_error}"
                            )
                            # Fallback to simple location
                            try:
                                await bot.send_location(
                                    chat_id=session_data.chat_id,
                                    latitude=venue_lat,
                                    longitude=venue_lon,
                                )
                                logger.info(
                                    f"Sent location as fallback for background fact: {venue_lat}, {venue_lon}"
                                )
                            except Exception as loc_error:
                                logger.error(
                                    f"Failed to send location for background fact: {loc_error}"
                                )

                    # Best-effort: increment fact counters after successful send
                    try:
                        await fb_increment_fact(session_data.user_id, 1)
                    except Exception:
                        pass

                    # Update last_update timestamp to keep session alive
                    # Even if coordinates didn't change, we successfully sent a fact
                    session_data.last_update = datetime.now()
                    # Clear generation flag
                    session_data.is_generating_fact = False

                    logger.info(
                        f"Sent live location fact #{session_data.fact_count} to user {session_data.user_id}"
                    )

                except Exception as e:
                    logger.error(
                        f"Error sending live location fact to user {session_data.user_id}: {e}"
                    )

                    # Increment counter for error message too (so user sees progress even on errors)
                    session_data.fact_count += 1

                    # Update last_update even on error to prevent monitor from killing session
                    session_data.last_update = datetime.now()
                    # Clear generation flag
                    session_data.is_generating_fact = False

                    # Send error message with fact number
                    from ..handlers.location import get_localized_message
                    error_fact = await get_localized_message(session_data.user_id, 'error_no_info')
                    error_response = await get_localized_message(session_data.user_id, 'live_fact_format',
                                                         number=session_data.fact_count,
                                                         place="",
                                                         fact=error_fact)

                    try:
                        await bot.send_message(
                            chat_id=session_data.chat_id,
                            text=error_response,
                            parse_mode="Markdown",
                        )
                    except Exception as send_error:
                        logger.error(f"Failed to send error message: {send_error}")

                # Wait for the next interval, compensating for generation time
                elapsed = (datetime.now() - send_start_time).total_seconds()
                sleep_time = max(desired_interval_seconds - elapsed, 15)

                # Sleep in 1-second intervals to check for stop request
                for _ in range(int(sleep_time)):
                    if session_data.stop_requested:
                        logger.info(f"Stop requested during sleep for user {session_data.user_id}")
                        return
                    await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info(f"Live location task cancelled for user {session_data.user_id}")
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error in live location loop for user {session_data.user_id}: {e}"
            )
        finally:
            # Clean up session when task ends
            async with self._lock:
                if session_data.user_id in self._active_sessions:
                    del self._active_sessions[session_data.user_id]

    def get_active_sessions_count(self) -> int:
        """Get the number of active live location sessions."""
        return len(self._active_sessions)

    def is_user_tracking(self, user_id: int) -> bool:
        """Check if a user has an active live location session."""
        return user_id in self._active_sessions


    async def _monitor_session_health(
        self, session_data: LiveLocationData, bot: Bot
    ) -> None:
        """Monitor session health and detect when user stops sharing.

        This task runs in parallel with fact sending and checks more frequently
        if the user has stopped sharing their live location.
        """
        try:
            while True:
                # Check every 30 seconds
                await asyncio.sleep(30)

                current_time = datetime.now()

                # Check if session has exceeded its live_period
                session_end_time = session_data.session_start + timedelta(seconds=session_data.live_period)
                if current_time >= session_end_time:
                    # Let the main loop handle expiration
                    break

                # ADAPTIVE TIMEOUT: Give enough time for fact generation (can take 15+ minutes with GPT-5.1 reasoning)
                # Formula: (interval * 3) + 30 minutes for generation overhead
                # Minimum: 40 minutes to avoid false positives
                adaptive_timeout_minutes = max(
                    (session_data.fact_interval_minutes * 3) + 30,
                    40
                )

                # Skip check if currently generating fact (prevents false positive during long AI generation)
                if session_data.is_generating_fact:
                    logger.debug(f"Health monitor: skipping check for user {session_data.user_id} (fact generation in progress)")
                    continue

                # Check if we haven't received updates in adaptive timeout period
                time_since_update = current_time - session_data.last_update
                if time_since_update > timedelta(minutes=adaptive_timeout_minutes):
                    logger.warning(
                        f"Health monitor detected stalled session for user {session_data.user_id} "
                        f"(last update: {time_since_update.total_seconds():.0f}s ago, timeout: {adaptive_timeout_minutes} min)"
                    )

                    # Send notification to user about session timeout
                    try:
                        from ..handlers.location import get_localized_message
                        timeout_message = await get_localized_message(session_data.user_id, 'live_manual_stop')
                        await bot.send_message(
                            chat_id=session_data.chat_id,
                            text=timeout_message,
                            parse_mode="Markdown",
                        )
                    except Exception as notify_error:
                        logger.error(f"Health monitor: failed to send timeout notification: {notify_error}")

                    # Cancel the main fact sending task
                    if session_data.task and not session_data.task.done():
                        session_data.task.cancel()
                    break

        except asyncio.CancelledError:
            logger.debug(f"Health monitor cancelled for user {session_data.user_id}")
        except Exception as e:
            logger.error(f"Error in health monitor for user {session_data.user_id}: {e}")


# Global tracker instance
_live_location_tracker: LiveLocationTracker | None = None


def get_live_location_tracker() -> LiveLocationTracker:
    """Get or create the global live location tracker instance."""
    global _live_location_tracker
    if _live_location_tracker is None:
        _live_location_tracker = LiveLocationTracker()
    return _live_location_tracker
