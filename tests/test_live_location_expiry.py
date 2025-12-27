"""Test live location expiry handling."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.handlers.location import handle_location
from src.services.live_location_tracker import (
    LiveLocationData,
    get_live_location_tracker,
)
from telegram import Bot, Location, Message, Update, User


@pytest.mark.asyncio
async def test_live_location_expires_after_period():
    """Test that live location sessions expire after the specified period."""
    # Create mock objects
    bot = AsyncMock(spec=Bot)
    user = MagicMock(spec=User)
    user.id = 12345

    # Create tracker and manually add a session
    tracker = get_live_location_tracker()

    # Clear any existing sessions
    tracker._active_sessions.clear()

    # Create a session that started 65 minutes ago with 60 minute period
    session_data = LiveLocationData(
        user_id=user.id,
        chat_id=67890,
        latitude=55.7558,
        longitude=37.6173,
        last_update=datetime.now() - timedelta(minutes=65),
        live_period=3600,  # 60 minutes in seconds
        fact_interval_minutes=0.01,  # Very short interval for testing (0.6 seconds)
        session_start=datetime.now() - timedelta(minutes=65)  # Started 65 minutes ago
    )

    # Start the fact sending loop
    task = asyncio.create_task(tracker._fact_sending_loop(session_data, bot))
    session_data.task = task

    # Give the task a moment to run and check expiry
    await asyncio.sleep(1.0)  # Wait for the interval to pass

    # Task should have exited due to expiry
    assert task.done()

    # Bot should have sent expiry notification
    bot.send_message.assert_called_once()
    call_args = bot.send_message.call_args
    assert "session ended" in call_args.kwargs["text"] or "завершена" in call_args.kwargs["text"]

    # Clean up - task should already be done
    assert task.done()


@pytest.mark.asyncio
async def test_live_location_stop_signal():
    """Test that receiving a regular location while live tracking stops the session."""
    # Create mock objects
    bot = AsyncMock(spec=Bot)
    update = MagicMock(spec=Update)
    context = MagicMock()
    context.bot = bot

    # Mock user
    user = MagicMock(spec=User)
    user.id = 12345
    update.effective_user = user
    update.effective_chat.id = 67890

    # Mock message with regular location (no live_period)
    message = MagicMock(spec=Message)
    location = MagicMock(spec=Location)
    location.latitude = 55.7558
    location.longitude = 37.6173
    location.live_period = None  # This indicates a stop signal
    message.location = location
    message.message_id = 123
    message.reply_text = AsyncMock()
    update.message = message

    # Create tracker and add an active session
    tracker = get_live_location_tracker()
    tracker._active_sessions.clear()

    # Add an active session for this user
    session_data = LiveLocationData(
        user_id=user.id,
        chat_id=67890,
        latitude=55.7558,
        longitude=37.6173,
        last_update=datetime.now(),
        live_period=3600,
        fact_interval_minutes=10
    )
    tracker._active_sessions[user.id] = session_data

    # Handle the location (should detect stop signal)
    await handle_location(update, context)

    # Session should be removed
    assert user.id not in tracker._active_sessions

    # Stop message should be sent
    message.reply_text.assert_called_once()
    call_args = message.reply_text.call_args
    assert "stopped" in call_args.kwargs["text"] or "остановлена" in call_args.kwargs["text"]


@pytest.mark.asyncio
async def test_live_location_continues_within_period():
    """Test that live location continues sending facts within the period."""
    # Create mock objects
    bot = AsyncMock(spec=Bot)
    bot.send_message = AsyncMock()

    # Create a session that just started with 60 minute period
    session_data = LiveLocationData(
        user_id=12345,
        chat_id=67890,
        latitude=55.7558,
        longitude=37.6173,
        last_update=datetime.now(),
        live_period=3600,  # 60 minutes
        fact_interval_minutes=0.01,  # 0.6 seconds for testing
        session_start=datetime.now()
    )

    # Mock OpenAI response
    with patch('src.services.live_location_tracker.get_openai_client') as mock_client:
        mock_openai = AsyncMock()
        mock_openai.get_nearby_fact = AsyncMock(return_value="Test fact response")
        mock_openai.parse_coordinates_from_response = AsyncMock(return_value=None)
        mock_client.return_value = mock_openai

        # Start the fact sending loop
        tracker = get_live_location_tracker()
        task = asyncio.create_task(tracker._fact_sending_loop(session_data, bot))

        # Let it run for 1.5 seconds (should be enough for first fact at 0.6s interval)
        await asyncio.sleep(1.5)

        # Task should still be running (not expired)
        assert not task.done()

        # Cancel the task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should have attempted to send at least one fact
        assert mock_openai.get_nearby_fact.called
