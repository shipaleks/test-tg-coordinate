"""Tests for OpenAI client."""

from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest
from src.services.openai_client import OpenAIClient


@pytest.fixture
def openai_client():
    """Create OpenAI client for testing."""
    return OpenAIClient(api_key="test-key")


def test_get_nearby_fact_success(openai_client):
    """Test successful fact generation."""

    async def _test():
        # Mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            "МЕСТО: Дом Пашкова\n"
            "ФАКТ: В этом здании в 1920 году тайно встречались революционеры."
        )

        # Create async mock that returns the mock response
        mock_create = AsyncMock(return_value=mock_response)

        with patch.object(openai_client.client.chat.completions, "create", mock_create):
            fact = await openai_client.get_nearby_fact(55.751244, 37.618423)

            assert "МЕСТО: Дом Пашкова" in fact
            assert (
                "ФАКТ: В этом здании в 1920 году тайно встречались революционеры."
                in fact
            )

    anyio.run(_test)


def test_get_nearby_fact_empty_response(openai_client):
    """Test handling of empty response from OpenAI."""

    async def _test():
        # Mock empty response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None

        mock_create = AsyncMock(return_value=mock_response)

        with patch.object(openai_client.client.chat.completions, "create", mock_create):
            with pytest.raises(ValueError, match="Empty response from OpenAI"):
                await openai_client.get_nearby_fact(55.751244, 37.618423)

    anyio.run(_test)


def test_get_nearby_fact_api_error(openai_client):
    """Test handling of API errors."""

    async def _test():
        mock_create = AsyncMock(side_effect=Exception("API Error"))

        with patch.object(openai_client.client.chat.completions, "create", mock_create):
            with pytest.raises(Exception, match="API Error"):
                await openai_client.get_nearby_fact(55.751244, 37.618423)

    anyio.run(_test)


def test_get_nearby_fact_prompt_format(openai_client):
    """Test that the prompt is formatted correctly."""

    async def _test():
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "МЕСТО: Test\nФАКТ: Test fact"

        mock_create = AsyncMock(return_value=mock_response)

        with patch.object(openai_client.client.chat.completions, "create", mock_create):
            await openai_client.get_nearby_fact(55.751244, 37.618423)

            # Check that create was called with correct parameters
            mock_create.assert_called_once()
            call_args = mock_create.call_args

            assert call_args[1]["model"] == "gpt-4.1-mini"
            assert call_args[1]["max_tokens"] == 250
            assert call_args[1]["temperature"] == 0.8

            messages = call_args[1]["messages"]
            assert len(messages) == 2
            assert messages[0]["role"] == "system"
            assert "профессиональный экскурсовод" in messages[0]["content"]
            assert messages[1]["role"] == "user"
            assert "55.751244,37.618423" in messages[1]["content"]
            assert "МЕСТО:" in messages[1]["content"]
            assert "ФАКТ:" in messages[1]["content"]

    anyio.run(_test)
