"""Tests for location handler."""

from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest
from src.handlers.location import (
    handle_edited_location,
    handle_interval_callback,
    handle_location,
)
from telegram import CallbackQuery, Chat, Location, Message, Update, User


@pytest.fixture
def mock_update():
    """Create a mock update with location data."""
    # Create mock user
    user = MagicMock(spec=User)
    user.id = 123456

    # Create mock chat
    chat = MagicMock(spec=Chat)
    chat.id = 123456

    # Create mock location
    location = MagicMock(spec=Location)
    location.latitude = 55.751244
    location.longitude = 37.618423
    location.live_period = None  # Default to static location

    # Create mock message
    message = MagicMock(spec=Message)
    message.location = location
    message.message_id = 1
    message.reply_text = AsyncMock()

    # Create mock update
    update = MagicMock(spec=Update)
    update.message = message
    update.effective_user = user
    update.effective_chat = chat

    return update


@pytest.fixture
def mock_live_update():
    """Create a mock update with live location data."""
    # Create mock user
    user = MagicMock(spec=User)
    user.id = 123456

    # Create mock chat
    chat = MagicMock(spec=Chat)
    chat.id = 123456

    # Create mock location with live period
    location = MagicMock(spec=Location)
    location.latitude = 55.751244
    location.longitude = 37.618423
    location.live_period = 3600  # 1 hour

    # Create mock message
    message = MagicMock(spec=Message)
    message.location = location
    message.message_id = 1
    message.reply_text = AsyncMock()

    # Create mock update
    update = MagicMock(spec=Update)
    update.message = message
    update.effective_user = user
    update.effective_chat = chat

    return update


@pytest.fixture
def mock_callback_query():
    """Create a mock callback query for interval selection."""
    user = MagicMock(spec=User)
    user.id = 123456

    chat = MagicMock(spec=Chat)
    chat.id = 123456

    query = MagicMock(spec=CallbackQuery)
    query.data = "interval_10_55.751244_37.618423_3600"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()

    update = MagicMock(spec=Update)
    update.callback_query = query
    update.effective_user = user
    update.effective_chat = chat

    return update


@pytest.fixture
def mock_edited_update():
    """Create a mock update with edited location data."""
    # Create mock user
    user = MagicMock(spec=User)
    user.id = 123456

    # Create mock chat
    chat = MagicMock(spec=Chat)
    chat.id = 123456

    # Create mock location
    location = MagicMock(spec=Location)
    location.latitude = 55.760000
    location.longitude = 37.620000

    # Create mock edited message
    edited_message = MagicMock(spec=Message)
    edited_message.location = location
    edited_message.message_id = 1

    # Create mock update
    update = MagicMock(spec=Update)
    update.edited_message = edited_message
    update.effective_user = user
    update.effective_chat = chat

    return update


@pytest.fixture
def mock_context():
    """Create a mock context."""
    context = MagicMock()
    context.bot = MagicMock()
    context.bot.send_chat_action = AsyncMock()
    context.bot.send_message = AsyncMock()
    return context


def test_handle_location_static_success(mock_update, mock_context):
    """Test successful static location handling."""

    async def _test():
        with patch("src.handlers.location.get_openai_client") as mock_get_client:
            # Mock OpenAI client
            mock_client = MagicMock()
            mock_client.get_nearby_fact = AsyncMock(
                return_value=(
                    "Локация: Красная площадь\n"
                    "Интересный факт: Красная площадь получила своё название не от цвета стен Кремля, "
                    "а от старорусского слова 'красный', означавшего 'красивый'."
                )
            )
            mock_get_client.return_value = mock_client

            # Call handler
            await handle_location(mock_update, mock_context)

            # Verify typing action was sent
            mock_context.bot.send_chat_action.assert_called_once_with(
                chat_id=123456, action="typing"
            )

            # Verify OpenAI was called with correct coordinates
            mock_client.get_nearby_fact.assert_called_once_with(55.751244, 37.618423)

            # Verify reply was sent
            mock_update.message.reply_text.assert_called_once()
            call_args = mock_update.message.reply_text.call_args
            assert "📍 *Место:* Красная площадь" in call_args[1]["text"]
            assert "💡 *Факт:* Красная площадь" in call_args[1]["text"]
            # Should NOT have live location indicators for static location
            assert "🔴" not in call_args[1]["text"]
            assert call_args[1]["parse_mode"] == "Markdown"

    anyio.run(_test)


def test_handle_location_live_shows_interval_selection(mock_live_update, mock_context):
    """Test that live location shows interval selection buttons."""

    async def _test():
        # Call handler
        await handle_location(mock_live_update, mock_context)

        # Verify interval selection message was sent
        mock_live_update.message.reply_text.assert_called_once()
        call_args = mock_live_update.message.reply_text.call_args

        # Check that interval selection message contains Russian text
        assert "🔴 *Живая локация получена!*" in call_args[1]["text"]
        assert "60 минут" in call_args[1]["text"]  # 3600 seconds = 60 minutes
        assert "Как часто присылать интересные факты?" in call_args[1]["text"]

        # Check that reply_markup (keyboard) is present
        assert "reply_markup" in call_args[1]
        assert call_args[1]["parse_mode"] == "Markdown"

    anyio.run(_test)


def test_handle_interval_callback_success(mock_callback_query, mock_context):
    """Test successful interval callback handling."""

    async def _test():
        with patch("src.handlers.location.get_openai_client") as mock_get_client:
            with patch(
                "src.handlers.location.get_live_location_tracker"
            ) as mock_get_tracker:
                # Mock OpenAI client
                mock_client = MagicMock()
                mock_client.get_nearby_fact = AsyncMock(
                    return_value="Локация: Красная площадь\nИнтересный факт: Интересный факт о месте"
                )
                mock_get_client.return_value = mock_client

                # Mock live location tracker
                mock_tracker = MagicMock()
                mock_tracker.start_live_location = AsyncMock()
                mock_get_tracker.return_value = mock_tracker

                # Call handler
                await handle_interval_callback(mock_callback_query, mock_context)

                # Verify callback was answered
                mock_callback_query.callback_query.answer.assert_called_once()

                # Verify live location was started with correct interval
                mock_tracker.start_live_location.assert_called_once_with(
                    user_id=123456,
                    chat_id=123456,
                    latitude=55.751244,
                    longitude=37.618423,
                    live_period=3600,
                    bot=mock_context.bot,
                    fact_interval_minutes=10,
                )

                # Verify confirmation message was sent (Russian)
                mock_callback_query.callback_query.edit_message_text.assert_called_once()
                edit_call_args = (
                    mock_callback_query.callback_query.edit_message_text.call_args
                )
                assert "🔴 *Живая локация активирована!*" in edit_call_args[1]["text"]
                assert "10 минут" in edit_call_args[1]["text"]

                # Verify initial fact was sent
                mock_context.bot.send_message.assert_called_once()
                fact_call_args = mock_context.bot.send_message.call_args
                assert "🔴 *Факт #1*" in fact_call_args[1]["text"]

    anyio.run(_test)


def test_handle_edited_location_success(mock_edited_update, mock_context):
    """Test successful edited location (live location update) handling."""

    async def _test():
        with patch(
            "src.handlers.location.get_live_location_tracker"
        ) as mock_get_tracker:
            # Mock live location tracker
            mock_tracker = MagicMock()
            mock_tracker.update_live_location = AsyncMock()
            mock_get_tracker.return_value = mock_tracker

            # Call handler
            await handle_edited_location(mock_edited_update, mock_context)

            # Verify coordinates were updated
            mock_tracker.update_live_location.assert_called_once_with(
                123456, 55.760000, 37.620000
            )

    anyio.run(_test)


def test_handle_location_no_location_data(mock_context):
    """Test handling when no location data is present."""

    async def _test():
        # Create update without location
        update = MagicMock(spec=Update)
        update.message = MagicMock(spec=Message)
        update.message.location = None

        # Call handler - should return early without error
        await handle_location(update, mock_context)

        # Verify no actions were taken
        mock_context.bot.send_chat_action.assert_not_called()

    anyio.run(_test)


def test_handle_edited_location_no_data(mock_context):
    """Test handling edited location when no data is present."""

    async def _test():
        # Create update without edited location
        update = MagicMock(spec=Update)
        update.edited_message = MagicMock(spec=Message)
        update.edited_message.location = None

        # Call handler - should return early without error
        await handle_edited_location(update, mock_context)

        # Verify no actions were taken (no tracker calls)
        # We can't easily mock the tracker here, but the function should exit early

    anyio.run(_test)


def test_handle_location_openai_error(mock_update, mock_context):
    """Test handling of OpenAI errors."""

    async def _test():
        with patch("src.handlers.location.get_openai_client") as mock_get_client:
            # Mock OpenAI client to raise error
            mock_client = MagicMock()
            mock_client.get_nearby_fact = AsyncMock(
                side_effect=Exception("OpenAI API error")
            )
            mock_get_client.return_value = mock_client

            # Call handler
            await handle_location(mock_update, mock_context)

            # Verify error message was sent
            mock_update.message.reply_text.assert_called_once()
            call_args = mock_update.message.reply_text.call_args
            assert "😔 *Упс!*" in call_args[1]["text"]
            assert "Не удалось найти" in call_args[1]["text"]
            assert call_args[1]["parse_mode"] == "Markdown"

    anyio.run(_test)


def test_handle_location_parsing_fallback(mock_update, mock_context):
    """Test that unparseable responses are still handled gracefully."""

    async def _test():
        with patch("src.handlers.location.get_openai_client") as mock_get_client:
            # Mock OpenAI client with unparseable response
            mock_client = MagicMock()
            mock_client.get_nearby_fact = AsyncMock(
                return_value="This is an unparseable response without proper formatting"
            )
            mock_get_client.return_value = mock_client

            # Call handler
            await handle_location(mock_update, mock_context)

            # Verify reply was sent with fallback formatting
            mock_update.message.reply_text.assert_called_once()
            call_args = mock_update.message.reply_text.call_args
            assert "📍 *Место:* рядом с вами" in call_args[1]["text"]
            assert (
                "💡 *Факт:* This is an unparseable response without proper formatting"
                in call_args[1]["text"]
            )

    anyio.run(_test)
