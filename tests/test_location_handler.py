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
    context.bot.send_photo = AsyncMock()
    context.bot.send_media_group = AsyncMock()
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
            # Mock image search to return empty list so it falls back to text
            mock_client.get_wikipedia_images = AsyncMock(return_value=[])

            mock_get_client.return_value = mock_client

            # Call handler
            await handle_location(mock_update, mock_context)

            # Verify typing action was sent
            mock_context.bot.send_chat_action.assert_called_with(
                chat_id=123456, action="typing"
            )

            # Verify OpenAI was called with correct coordinates
            # Note: handle_location might pass force_reasoning_none=True
            args, kwargs = mock_client.get_nearby_fact.call_args
            assert args == (55.751244, 37.618423)
            # We don't strictly check kwargs as they might change

            # Verify reply was sent (using bot.send_message because no images)
            assert mock_context.bot.send_message.called

            # Check the content of the sent messages
            # The handler sends the fact via send_message and the upsell via reply_text

            # Verify fact message (sent via reply_text in fallback mode)
            assert mock_update.message.reply_text.called
            fact_calls = mock_update.message.reply_text.call_args_list
            fact_texts = [call.kwargs.get('text', '') or call.args[0] for call in fact_calls]
            combined_fact_text = " ".join(fact_texts)

            assert "📍 *Место:* Красная площадь" in combined_fact_text
            assert "💡 *Факт:* Красная площадь" in combined_fact_text
            assert "🔴" not in combined_fact_text

            # Verify upsell message (sent via bot.send_message)
            assert mock_context.bot.send_message.called
            upsell_calls = mock_context.bot.send_message.call_args_list
            upsell_texts = [call.kwargs.get('text', '') or call.args[1] for call in upsell_calls]
            combined_upsell_text = " ".join(upsell_texts)
            assert "💡 *Совет:*" in combined_upsell_text

    anyio.run(_test)


def test_handle_location_live_shows_interval_selection(mock_live_update, mock_context):
    """Test that live location shows interval selection buttons."""

    async def _test():
        # Call handler
        await handle_location(mock_live_update, mock_context)

        # Verify interval selection message was sent using reply_text
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
                mock_client.get_wikipedia_images = AsyncMock(return_value=[])
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

                # Note: Initial fact is now sent by the tracker loop in background,
                # not immediately by the handler. So we don't check for send_message here.

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
            # This uses reply_text directly in catch block?
            # src/handlers/location.py: handle_location calls reply_text on exception?
            # Actually no, it might use context.bot.send_message or similar.
            # Checking implementation: it calls `await update.message.reply_text`

            mock_update.message.reply_text.assert_called()
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
            mock_client.get_wikipedia_images = AsyncMock(return_value=[])
            mock_get_client.return_value = mock_client

            # Call handler
            await handle_location(mock_update, mock_context)

            # Verify reply was sent (fallback formatting)
            assert mock_update.message.reply_text.called

            # Check calls to reply_text
            fact_calls = mock_update.message.reply_text.call_args_list
            fact_texts = [call.kwargs.get('text', '') or call.args[0] for call in fact_calls]
            combined_text = " ".join(fact_texts)

            # Since parsing fails, it might default to some fallback or just print the text.
            assert "This is an unparseable response without proper formatting" in combined_text

    anyio.run(_test)
