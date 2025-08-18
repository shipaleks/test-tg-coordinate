"""Live location tracking service for managing user location streams."""

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from telegram import Bot, InputMediaPhoto

from .openai_client import get_openai_client
from ..utils.formatting_utils import extract_sources_from_answer as _extract_live_sources
from ..utils.formatting_utils import strip_sources_section as _strip_live_sources
from ..utils.formatting_utils import remove_bare_links_from_text as _remove_bare_links_from_text
# Avoid importing handlers at module import time to prevent circular deps.
# We'll import get_localized_message lazily inside functions.

logger = logging.getLogger(__name__)


async def send_live_fact_with_images(bot, chat_id, formatted_response, search_keywords, place, lat: float | None = None, lon: float | None = None):
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
        image_urls = await openai_client.get_wikipedia_images(search_keywords, max_images=4)  # Max 4 for media group
        
        if image_urls:
            # Try sending all images with text as media group
            try:
                logger.info(f"Attempting to send live fact with {len(image_urls)} images for {place}")
                logger.debug(f"Live formatted response length: {len(formatted_response)} chars")
                
                if len(formatted_response) <= 1024:
                    # Caption fits in Telegram limit, send as media group with caption
                    media_list = []
                    for i, image_url in enumerate(image_urls):
                        if i == 0:
                            # First image gets the full fact as caption
                            media_list.append(InputMediaPhoto(media=image_url, caption=formatted_response, parse_mode="Markdown"))
                        else:
                            # Other images get no caption
                            media_list.append(InputMediaPhoto(media=image_url))

                    if len(media_list) == 1:
                        await bot.send_photo(chat_id=chat_id, photo=image_urls[0], caption=formatted_response, parse_mode="Markdown")
                    else:
                        await bot.send_media_group(chat_id=chat_id, media=media_list)
                    logger.info(f"Successfully sent {len(image_urls)} live images with caption in media group for {place}")
                else:
                    # Caption too long → first photo with shortened caption + rest without captions
                    short_caption = formatted_response[:1020]
                    media_list = []
                    for i, image_url in enumerate(image_urls):
                        if i == 0:
                            media_list.append(InputMediaPhoto(media=image_url, caption=short_caption, parse_mode="Markdown"))
                        else:
                            media_list.append(InputMediaPhoto(media=image_url))
                    await bot.send_media_group(chat_id=chat_id, media=media_list)
                    logger.info(f"Successfully sent long live text + {len(image_urls)} images as media group for {place}")
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
                        # Retry with only first 2 images
                        retry_media_list = []
                        for i, image_url in enumerate(image_urls[:2]):
                            if i == 0:
                                retry_media_list.append(InputMediaPhoto(media=image_url, caption=formatted_response, parse_mode="Markdown"))
                            else:
                                retry_media_list.append(InputMediaPhoto(media=image_url))
                        
                        await bot.send_media_group(
                            chat_id=chat_id,
                            media=retry_media_list
                        )
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

    def __post_init__(self):
        if self.fact_history is None:
            self.fact_history = []
        if self.session_start is None:
            self.session_start = datetime.now()


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
                task = asyncio.create_task(self._fact_sending_loop(session_data, bot))
                session_data.task = task
                
                # Start health monitor task
                monitor_task = asyncio.create_task(self._monitor_session_health(session_data, bot))
                # Store monitor task reference (we'll add this field)
                session_data.monitor_task = monitor_task
                
                # Store the session
                self._active_sessions[user_id] = session_data
                
                logger.info(
                    f"Started live location tracking for user {user_id} for {live_period}s, facts every {fact_interval_minutes} min"
                )
            except Exception as e:
                logger.error(f"Failed to start live location task for user {user_id}: {e}")
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
        async with self._lock:
            if user_id in self._active_sessions:
                session = self._active_sessions[user_id]
                session.latitude = latitude
                session.longitude = longitude
                session.last_update = datetime.now()

                logger.info(
                    f"Updated live location for user {user_id}: {latitude}, {longitude}"
                )

    async def stop_live_location(self, user_id: int) -> None:
        """Stop live location tracking for a user.

        Args:
            user_id: Telegram user ID
        """
        async with self._lock:
            await self._stop_session(user_id)

    async def _stop_session(self, user_id: int) -> None:
        """Internal method to stop a session (called with lock held)."""
        if user_id in self._active_sessions:
            session = self._active_sessions[user_id]
            
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

            del self._active_sessions[user_id]
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

            # Initial wait: account for ~3 minutes model latency so the next fact lands close to user interval
            initial_sleep = max(desired_interval_seconds - 180, 30)
            await asyncio.sleep(initial_sleep)

            while True:
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
                
                # Check if we haven't received updates in a while (user stopped sharing)
                # Telegram usually sends updates every ~30-60 seconds for live location
                # If no update for 3 minutes, user likely stopped sharing
                time_since_update = current_time - session_data.last_update
                if time_since_update > timedelta(minutes=3):
                    logger.info(
                        f"Live location stopped updating for user {session_data.user_id} "
                        f"(last update: {session_data.last_update}, {time_since_update.total_seconds():.0f}s ago)"
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
                    # Increment fact counter
                    session_data.fact_count += 1

                    openai_client = get_openai_client()
                    response = await openai_client.get_nearby_fact(
                        session_data.latitude,
                        session_data.longitude,
                        is_live_location=True,
                        previous_facts=session_data.fact_history,
                        user_id=session_data.user_id,
                    )

                    # Parse the response to extract place and fact
                    from ..handlers.location import get_localized_message
                    place = await get_localized_message(session_data.user_id, 'near_you')  # Default location
                    fact = response  # Default to full response if parsing fails
                    search_keywords = ""

                    # Try to parse structured response from <answer> tags first
                    answer_match = re.search(r"<answer>(.*?)</answer>", response, re.DOTALL)
                    if answer_match:
                        answer_content = answer_match.group(1).strip()
                        
                        # Extract location from answer content
                        location_match = re.search(r"Location:\s*(.+?)(?:\n|$)", answer_content)
                        if location_match:
                            place = location_match.group(1).strip()
                        
                        # Extract search keywords from answer content
                        search_match = re.search(r"Search:\s*(.+?)(?:\n|$)", answer_content)
                        if search_match:
                            search_keywords = search_match.group(1).strip()
                        
                        # Extract fact from answer content, stopping before Sources/Источники
                        fact_match = re.search(r"Interesting fact:\s*(.*?)(?=\n(?:Sources|Источники)\s*:|$)", answer_content, re.DOTALL)
                        if fact_match:
                            fact = _strip_live_sources(fact_match.group(1).strip())
                            fact = _remove_bare_links_from_text(fact)
                        # Build localized sources block from answer content (single, clean block)
                        sources = _extract_live_sources(answer_content)
                        sources_block = ""
                        if sources:
                            from ..handlers.location import get_localized_message as _get_msg
                            src_label = await _get_msg(session_data.user_id, 'sources_label')
                            bullets = []
                            for title, url in sources[:3]:
                                # No markdown here (we ship as caption or as text separately elsewhere)
                                bullets.append(f"- {title}")
                            sources_block = f"\n\n{src_label}\n" + "\n".join(bullets)
                    
                    # Legacy fallback for old format responses
                    else:
                        lines = response.split("\n")
                        
                        # Try to parse old structured response format
                        for i, line in enumerate(lines):
                            if line.startswith("Локация:"):
                                place = line.replace("Локация:", "").strip()
                            elif line.startswith("Интересный факт:"):
                                # Join all lines after Интересный факт: as the fact might be multiline
                                fact_lines = []
                                # Start from the current line, removing the prefix
                                fact_lines.append(
                                    line.replace("Интересный факт:", "").strip()
                                )
                                # Add all subsequent lines
                                for j in range(i + 1, len(lines)):
                                    if lines[j].strip():  # Only add non-empty lines
                                        fact_lines.append(lines[j].strip())
                                fact = " ".join(fact_lines)
                                break

                    # Format the response with live location indicator and fact number
                    # Import get_localized_message at top of function to avoid circular imports
                    from ..handlers.location import get_localized_message
                    formatted_response = await get_localized_message(session_data.user_id, 'live_fact_format', number=session_data.fact_count, place=place, fact=fact)
                    if 'sources_block' in locals() and sources_block:
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
                            lat=session_data.latitude,
                            lon=session_data.longitude,
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
                                lat=session_data.latitude,
                                lon=session_data.longitude,
                            )
                        else:
                            # No search keywords, send just text
                            await bot.send_message(
                                chat_id=session_data.chat_id,
                                text=formatted_response,
                                parse_mode="Markdown",
                            )

                    # Try to parse coordinates and send location for navigation using search keywords (background fact)
                    coordinates = await openai_client.parse_coordinates_from_response(
                        response, session_data.latitude, session_data.longitude
                    )
                    if coordinates:
                        venue_lat, venue_lon = coordinates
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

                    logger.info(
                        f"Sent live location fact #{session_data.fact_count} to user {session_data.user_id}"
                    )

                except Exception as e:
                    logger.error(
                        f"Error sending live location fact to user {session_data.user_id}: {e}"
                    )

                    # Send error message with fact number  
                    session_data.fact_count += 1
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
                await asyncio.sleep(sleep_time)

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
                
                # Check if we haven't received updates in 3 minutes
                time_since_update = current_time - session_data.last_update
                if time_since_update > timedelta(minutes=3):
                    logger.info(
                        f"Health monitor detected stopped live location for user {session_data.user_id} "
                        f"(last update: {time_since_update.total_seconds():.0f}s ago)"
                    )
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
