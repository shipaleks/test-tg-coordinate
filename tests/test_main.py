"""Tests for main application functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest
from src.main import start_command, info_command, remove_keyboard_command
from telegram import Chat, Message, Update, User


@pytest.fixture
def mock_update():
    """Create a mock update for command testing."""
    # Create mock user
    user = MagicMock(spec=User)
    user.id = 123456

    # Create mock chat
    chat = MagicMock(spec=Chat)
    chat.id = 123456

    # Create mock message
    message = MagicMock(spec=Message)
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
    return context


def test_start_command(mock_update, mock_context):
    """Test start command sends welcome message with location keyboard."""

    async def _test():
        # Call start command
        await start_command(mock_update, mock_context)

        # Verify reply was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args

        # Check that welcome text contains key information
        text = call_args[0][0]  # First positional argument
        assert "🗺️" in text
        assert "Добро пожаловать" in text
        assert "Обычная локация" in text
        assert "Живая локация" in text
        assert "Примеры использования" in text

        # Check that markdown is used
        assert call_args[1]["parse_mode"] == "Markdown"

        # Check that reply_markup (keyboard) is present
        assert "reply_markup" in call_args[1]
        reply_markup = call_args[1]["reply_markup"]
        
        # Verify keyboard structure
        assert reply_markup.resize_keyboard is True
        assert reply_markup.one_time_keyboard is False
        
        # Check keyboard buttons
        keyboard = reply_markup.keyboard
        assert len(keyboard) == 2  # Two rows
        assert len(keyboard[0]) == 1  # First row has 1 button (location)
        assert len(keyboard[1]) == 2  # Second row has 2 buttons (info, remove)
        
        # Check location button
        location_button = keyboard[0][0]
        assert location_button.text == "📍 Поделиться локацией"
        assert location_button.request_location is True
        
        # Check other buttons
        info_button = keyboard[1][0]
        remove_button = keyboard[1][1]
        assert info_button.text == "ℹ️ Информация"
        assert remove_button.text == "❌ Убрать кнопки"

    anyio.run(_test)


def test_info_command(mock_update, mock_context):
    """Test info command sends help information."""

    async def _test():
        # Call info command
        await info_command(mock_update, mock_context)

        # Verify reply was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args

        # Check that info text contains key information
        text = call_args[0][0]  # First positional argument
        assert "ℹ️ *Как пользоваться ботом:*" in text
        assert "Обычная локация" in text
        assert "Живая локация" in text
        assert "/start" in text
        assert "личных чатах" in text

        # Check that markdown is used
        assert call_args[1]["parse_mode"] == "Markdown"

    anyio.run(_test)


def test_remove_keyboard_command(mock_update, mock_context):
    """Test remove keyboard command removes the keyboard."""

    async def _test():
        # Call remove keyboard command
        await remove_keyboard_command(mock_update, mock_context)

        # Verify reply was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args

        # Check that confirmation text is sent
        text = call_args[0][0]  # First positional argument
        assert "✅ Кнопки убраны" in text
        assert "/start" in text

        # Check that ReplyKeyboardRemove is used
        assert "reply_markup" in call_args[1]
        reply_markup = call_args[1]["reply_markup"]
        # Should be ReplyKeyboardRemove instance
        assert hasattr(reply_markup, 'remove_keyboard')
        assert reply_markup.remove_keyboard is True

    anyio.run(_test) 