"""Test live location silence detection (when user stops sharing)."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from src.services.live_location_tracker import LiveLocationTracker


@pytest.mark.asyncio
async def test_live_location_stops_on_silence():
    """Test that live location session stops when updates stop coming."""
    tracker = LiveLocationTracker()
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    bot.send_venue = AsyncMock()

    # Start a live location session
    await tracker.start_live_location(
        user_id=123,
        chat_id=456,
        latitude=48.8566,
        longitude=2.3522,
        live_period=3600,  # 1 hour
        bot=bot,
        fact_interval_minutes=5  # Every 5 minutes
    )

    # Verify session started
    assert tracker.is_user_tracking(123)

    # Wait a bit
    await asyncio.sleep(0.5)

    # Simulate some location updates
    await tracker.update_live_location(123, 48.8567, 2.3523)
    await asyncio.sleep(0.5)
    await tracker.update_live_location(123, 48.8568, 2.3524)

    # Now simulate silence - manually set last_update to 4 minutes ago
    session = tracker._active_sessions[123]
    session.last_update = datetime.now() - timedelta(minutes=4)

    # Wait for the health monitor to detect silence (runs every 30 seconds)
    # In test, we'll wait up to 35 seconds
    max_wait = 35
    for i in range(max_wait):
        if not tracker.is_user_tracking(123):
            break
        await asyncio.sleep(1)

    # Session should be stopped
    assert not tracker.is_user_tracking(123)

    # Check that manual stop message was sent
    bot.send_message.assert_called()
    call_args = bot.send_message.call_args
    assert "live_manual_stop" in str(call_args) or "stopped sharing" in call_args[1]["text"].lower()


@pytest.mark.asyncio
async def test_health_monitor_runs_independently():
    """Test that health monitor runs independently of fact sending."""
    tracker = LiveLocationTracker()
    bot = AsyncMock()

    # Mock OpenAI client to control fact generation
    from unittest.mock import patch
    with patch('src.services.live_location_tracker.get_openai_client') as mock_openai:
        mock_client = AsyncMock()
        mock_openai.return_value = mock_client
        mock_client.get_nearby_fact = AsyncMock(return_value="Test fact")
        mock_client.parse_coordinates_from_response = AsyncMock(return_value=None)
        mock_client.get_wikipedia_images = AsyncMock(return_value=[])

        # Start session with long fact interval
        await tracker.start_live_location(
            user_id=456,
            chat_id=789,
            latitude=48.8566,
            longitude=2.3522,
            live_period=3600,
            bot=bot,
            fact_interval_minutes=60  # Facts every hour
        )

        # Verify session started
        assert tracker.is_user_tracking(456)

        # Simulate silence after 1 minute
        await asyncio.sleep(1)
        session = tracker._active_sessions[456]
        session.last_update = datetime.now() - timedelta(minutes=4)

        # Health monitor should stop session within 35 seconds
        # even though next fact isn't due for 59 more minutes
        max_wait = 35
        for i in range(max_wait):
            if not tracker.is_user_tracking(456):
                break
            await asyncio.sleep(1)

        # Session should be stopped by health monitor
        assert not tracker.is_user_tracking(456)

        # Stop any remaining tasks
        await tracker.stop_live_location(456)


@pytest.mark.asyncio
async def test_normal_operation_not_affected():
    """Test that normal operation continues when updates are received."""
    tracker = LiveLocationTracker()
    bot = AsyncMock()

    await tracker.start_live_location(
        user_id=789,
        chat_id=101,
        latitude=48.8566,
        longitude=2.3522,
        live_period=300,  # 5 minutes
        bot=bot,
        fact_interval_minutes=1  # Every minute
    )

    # Simulate regular updates every 30 seconds
    for i in range(4):
        await asyncio.sleep(0.5)
        await tracker.update_live_location(789, 48.8566 + i*0.0001, 2.3522)

    # Session should still be active
    assert tracker.is_user_tracking(789)

    # Clean up
    await tracker.stop_live_location(789)
    assert not tracker.is_user_tracking(789)
