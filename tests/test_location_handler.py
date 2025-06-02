"""Tests for location handler."""

from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest
from src.handlers.location import handle_location
from telegram import Chat, Location, Message, Update, User


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
def mock_context():
    """Create a mock context."""
    context = MagicMock()
    context.bot = MagicMock()
    context.bot.send_chat_action = AsyncMock()
    return context


def test_handle_location_success(mock_update, mock_context):
    """Test successful location handling."""

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
            assert call_args[1]["parse_mode"] == "Markdown"
            assert call_args[1]["reply_to_message_id"] == 1

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
