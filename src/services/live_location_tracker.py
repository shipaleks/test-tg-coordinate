"""Live location tracking service for managing user location streams."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from telegram import Bot

from .openai_client import get_openai_client

logger = logging.getLogger(__name__)


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

    def __post_init__(self):
        if self.fact_history is None:
            self.fact_history = []


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
            await self._stop_session(user_id)

            # Create new session data
            session_data = LiveLocationData(
                user_id=user_id,
                chat_id=chat_id,
                latitude=latitude,
                longitude=longitude,
                last_update=datetime.now(),
                live_period=live_period,
                fact_interval_minutes=fact_interval_minutes,
            )

            # Start the fact sending task
            task = asyncio.create_task(self._fact_sending_loop(session_data, bot))
            session_data.task = task

            # Store the session
            self._active_sessions[user_id] = session_data

            logger.info(
                f"Started live location tracking for user {user_id} for {live_period}s, facts every {fact_interval_minutes} min"
            )

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
            if session.task and not session.task.done():
                session.task.cancel()
                try:
                    await session.task
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
            # Wait for the specified interval before sending first fact
            interval_seconds = session_data.fact_interval_minutes * 60
            await asyncio.sleep(interval_seconds)

            while True:
                # Check if session is still active and not expired before sending fact
                current_time = datetime.now()
                time_since_update = current_time - session_data.last_update

                # Stop if no updates for longer than live_period + 1 minute buffer
                if time_since_update > timedelta(seconds=session_data.live_period + 60):
                    logger.info(
                        f"Live location expired for user {session_data.user_id}"
                    )
                    break

                # Send fact at current coordinates
                try:
                    # Increment fact counter
                    session_data.fact_count += 1

                    openai_client = get_openai_client()
                    response = await openai_client.get_nearby_fact(
                        session_data.latitude,
                        session_data.longitude,
                        is_live_location=True,
                        previous_facts=session_data.fact_history,
                    )

                    # Parse the response to extract place and fact
                    lines = response.split("\n")
                    place = "рядом с вами"
                    fact = response  # Default to full response if parsing fails

                    # Try to parse structured response
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
                    formatted_response = (
                        f"🔴 *Факт #{session_data.fact_count}*\n\n"
                        f"📍 *Место:* {place}\n\n"
                        f"💡 *Факт:* {fact}"
                    )

                    # Save fact to history to avoid repetition
                    session_data.fact_history.append(f"{place}: {fact}")

                    # Send the fact
                    await bot.send_message(
                        chat_id=session_data.chat_id,
                        text=formatted_response,
                        parse_mode="Markdown",
                    )

                    # Try to parse coordinates and send location for navigation using search keywords (background fact)
                    coordinates = await openai_client.parse_coordinates_from_response(
                        response
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
                                address=f"Достопримечательность: {place}",
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
                    error_response = (
                        f"🔴 *Факт #{session_data.fact_count}*\n\n"
                        "😔 *Упс!*\n\n"
                        "Не удалось найти интересную информацию о текущем месте."
                    )

                    try:
                        await bot.send_message(
                            chat_id=session_data.chat_id,
                            text=error_response,
                            parse_mode="Markdown",
                        )
                    except Exception as send_error:
                        logger.error(f"Failed to send error message: {send_error}")

                # Wait for the next interval
                await asyncio.sleep(interval_seconds)

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


# Global tracker instance
_live_location_tracker: LiveLocationTracker | None = None


def get_live_location_tracker() -> LiveLocationTracker:
    """Get or create the global live location tracker instance."""
    global _live_location_tracker
    if _live_location_tracker is None:
        _live_location_tracker = LiveLocationTracker()
    return _live_location_tracker
