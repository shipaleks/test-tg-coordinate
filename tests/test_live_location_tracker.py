"""Tests for live location tracker."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest
from src.services.live_location_tracker import LiveLocationData, LiveLocationTracker
from telegram import Bot


@pytest.fixture
def tracker():
    """Create a live location tracker for testing."""
    return LiveLocationTracker()


@pytest.fixture
def mock_bot():
    """Create a mock Telegram bot."""
    bot = MagicMock(spec=Bot)
    bot.send_message = AsyncMock()
    return bot


def test_start_live_location(tracker, mock_bot):
    """Test starting a live location session."""

    async def _test():
        user_id = 123456
        chat_id = 123456
        lat, lon = 55.7558, 37.6173
        live_period = 3600  # 1 hour

        with patch(
            "src.services.live_location_tracker.get_openai_client"
        ) as mock_get_client:
            # Mock OpenAI client
            mock_client = MagicMock()
            mock_client.get_nearby_fact = AsyncMock(
                return_value="Локация: Test\nИнтересный факт: Test fact"
            )
            mock_get_client.return_value = mock_client

            # Start live location
            await tracker.start_live_location(
                user_id=user_id,
                chat_id=chat_id,
                latitude=lat,
                longitude=lon,
                live_period=live_period,
                bot=mock_bot,
            )

            # Check that session was created
            assert tracker.is_user_tracking(user_id)
            assert tracker.get_active_sessions_count() == 1

            # Stop the session to clean up
            await tracker.stop_live_location(user_id)

    anyio.run(_test)


def test_update_live_location(tracker, mock_bot):
    """Test updating live location coordinates."""

    async def _test():
        user_id = 123456
        chat_id = 123456
        lat, lon = 55.7558, 37.6173
        live_period = 3600

        with patch(
            "src.services.live_location_tracker.get_openai_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_nearby_fact = AsyncMock(
                return_value="Локация: Test\nИнтересный факт: Test fact"
            )
            mock_get_client.return_value = mock_client

            # Start live location
            await tracker.start_live_location(
                user_id=user_id,
                chat_id=chat_id,
                latitude=lat,
                longitude=lon,
                live_period=live_period,
                bot=mock_bot,
            )

            # Update coordinates
            new_lat, new_lon = 55.7600, 37.6200
            await tracker.update_live_location(user_id, new_lat, new_lon)

            # Verify coordinates were updated
            session = tracker._active_sessions[user_id]
            assert session.latitude == new_lat
            assert session.longitude == new_lon

            # Stop the session
            await tracker.stop_live_location(user_id)

    anyio.run(_test)


def test_stop_live_location(tracker, mock_bot):
    """Test stopping a live location session."""

    async def _test():
        user_id = 123456
        chat_id = 123456
        lat, lon = 55.7558, 37.6173
        live_period = 3600

        with patch(
            "src.services.live_location_tracker.get_openai_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_nearby_fact = AsyncMock(
                return_value="Локация: Test\nИнтересный факт: Test fact"
            )
            mock_get_client.return_value = mock_client

            # Start live location
            await tracker.start_live_location(
                user_id=user_id,
                chat_id=chat_id,
                latitude=lat,
                longitude=lon,
                live_period=live_period,
                bot=mock_bot,
            )

            assert tracker.is_user_tracking(user_id)

            # Stop live location
            await tracker.stop_live_location(user_id)

            # Verify session was removed
            assert not tracker.is_user_tracking(user_id)
            assert tracker.get_active_sessions_count() == 0

    anyio.run(_test)


def test_multiple_sessions(tracker, mock_bot):
    """Test managing multiple live location sessions."""

    async def _test():
        user1_id = 123456
        user2_id = 789012
        chat_id = 123456
        lat, lon = 55.7558, 37.6173
        live_period = 3600

        with patch(
            "src.services.live_location_tracker.get_openai_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_nearby_fact = AsyncMock(
                return_value="Локация: Test\nИнтересный факт: Test fact"
            )
            mock_get_client.return_value = mock_client

            # Start sessions for two users
            await tracker.start_live_location(
                user_id=user1_id,
                chat_id=chat_id,
                latitude=lat,
                longitude=lon,
                live_period=live_period,
                bot=mock_bot,
            )

            await tracker.start_live_location(
                user_id=user2_id,
                chat_id=chat_id,
                latitude=lat + 0.01,
                longitude=lon + 0.01,
                live_period=live_period,
                bot=mock_bot,
            )

            # Check both sessions are active
            assert tracker.get_active_sessions_count() == 2
            assert tracker.is_user_tracking(user1_id)
            assert tracker.is_user_tracking(user2_id)

            # Stop one session
            await tracker.stop_live_location(user1_id)

            # Check only one session remains
            assert tracker.get_active_sessions_count() == 1
            assert not tracker.is_user_tracking(user1_id)
            assert tracker.is_user_tracking(user2_id)

            # Stop remaining session
            await tracker.stop_live_location(user2_id)

            # Check no sessions remain
            assert tracker.get_active_sessions_count() == 0

    anyio.run(_test)


def test_fact_sending_loop_quick(tracker, mock_bot):
    """Test the fact sending loop with a very short interval for testing."""

    async def _test():
        user_id = 123456
        chat_id = 123456
        lat, lon = 55.7558, 37.6173
        live_period = 3600

        # Create session data
        session_data = LiveLocationData(
            user_id=user_id,
            chat_id=chat_id,
            latitude=lat,
            longitude=lon,
            last_update=datetime.now(),
            live_period=live_period,
        )

        with patch(
            "src.services.live_location_tracker.get_openai_client"
        ) as mock_get_client:
            with patch("asyncio.sleep") as mock_sleep:
                # Mock OpenAI client
                mock_client = MagicMock()
                mock_client.get_nearby_fact = AsyncMock(
                    return_value="Локация: Test Location\nИнтересный факт: Amazing test fact"
                )
                mock_get_client.return_value = mock_client

                # Mock sleep to return immediately but track calls
                mock_sleep.return_value = asyncio.Future()
                mock_sleep.return_value.set_result(None)

                # Start the fact sending loop
                task = asyncio.create_task(
                    tracker._fact_sending_loop(session_data, mock_bot)
                )

                # Let it run for a short time then cancel
                await asyncio.sleep(0.1)
                task.cancel()

                try:
                    await task
                except asyncio.CancelledError:
                    pass

                # Verify sleep was called (initial 10-minute wait)
                mock_sleep.assert_called()

    anyio.run(_test)


def test_session_expiry():
    """Test that sessions expire after live_period."""

    async def _test():
        # Create expired session data
        session_data = LiveLocationData(
            user_id=123456,
            chat_id=123456,
            latitude=55.7558,
            longitude=37.6173,
            last_update=datetime.now() - timedelta(hours=2),  # 2 hours ago
            live_period=3600,  # 1 hour period, so this should be expired
        )

        tracker = LiveLocationTracker()
        mock_bot = MagicMock(spec=Bot)
        mock_bot.send_message = AsyncMock()

        with patch("src.services.live_location_tracker.get_openai_client"):
            with patch("asyncio.sleep") as mock_sleep:
                # Mock to return immediately on first sleep call
                mock_sleep.return_value = asyncio.Future()
                mock_sleep.return_value.set_result(None)

                # Start the fact sending loop
                task = asyncio.create_task(
                    tracker._fact_sending_loop(session_data, mock_bot)
                )

                # Wait for task to complete (should exit due to expiry)
                await asyncio.sleep(0.1)

                # Task should complete on its own due to expiry
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                # Verify no facts were sent due to expiry
                mock_bot.send_message.assert_not_called()

    anyio.run(_test)
