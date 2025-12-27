"""Tests for main module."""

from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest
from src.main import info_command, start_command
from telegram import Chat, Message, Update, User


@pytest.fixture
def mock_update():
    """Create a mock update."""
    user = MagicMock(spec=User)
    user.id = 123456
    user.first_name = "Test User"
    user.username = "testuser"
    user.language_code = "en"

    chat = MagicMock(spec=Chat)
    chat.id = 123456

    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock()

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.effective_chat = chat
    update.message = message

    return update


@pytest.fixture
def mock_context():
    """Create a mock context."""
    context = MagicMock()
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.send_photo = AsyncMock()
    return context


def test_start_command(mock_update, mock_context):
    """Test start command sends welcome message with simplified location keyboard."""

    async def _test():
        # Call start command
        # We need to mock get_async_donors_db to avoid real DB calls
        with patch("src.main.get_async_donors_db") as mock_get_db, \
             patch("src.main.fb_ensure_user", new_callable=AsyncMock):

            mock_db = MagicMock()
            mock_db.has_language_set = AsyncMock(return_value=False) # New user
            mock_get_db.return_value = mock_db

            await start_command(mock_update, mock_context)

            # Verify "Processing" message was sent
            assert mock_update.message.reply_text.called

            # Since has_language_set is False, it should show language selection
            # Verify language selection message was sent
            # This uses context.bot.send_message or update.message.reply_text?
            # In main.py: show_language_selection uses update.message.reply_text

            # Check calls to reply_text
            calls = mock_update.message.reply_text.call_args_list
            assert len(calls) >= 1

            # Check if language selection text is in one of the calls
            found_lang_msg = False
            for call in calls:
                args, _ = call
                if "Выберите ваш язык" in args[0] or "Language" in args[0]:
                    found_lang_msg = True
                    break
            assert found_lang_msg

    anyio.run(_test)


def test_info_command(mock_update, mock_context):
    """Test info command sends detailed help information."""

    async def _test():
        with patch("src.main.get_async_donors_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.get_user_language = AsyncMock(return_value="ru")
            mock_get_db.return_value = mock_db

            # Call info command
            await info_command(mock_update, mock_context)

            # Verify messages were sent
            # info_command sends messages via context.bot.send_message and send_photo

            assert mock_context.bot.send_message.called

            # Check for key phrases in the sent messages (both text and photo captions)

            # Collect text messages
            calls_text = mock_context.bot.send_message.call_args_list
            texts = [call.kwargs.get('text', '') or (call.args[1] if len(call.args) > 1 else '') for call in calls_text]

            # Collect photo captions
            calls_photo = mock_context.bot.send_photo.call_args_list
            captions = [call.kwargs.get('caption', '') for call in calls_photo]

            combined_text = " ".join(texts + captions)

            assert "Что такое живая локация" in combined_text
            # It sends steps sequentially
            assert "Шаг 1/3" in combined_text

    anyio.run(_test)
