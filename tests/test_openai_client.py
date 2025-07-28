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
            "Локация: Дом Пашкова\n"
            "Интересный факт: В этом здании в 1920 году тайно встречались революционеры."
        )

        # Create async mock that returns the mock response
        mock_create = AsyncMock(return_value=mock_response)

        with patch.object(openai_client.client.chat.completions, "create", mock_create):
            fact = await openai_client.get_nearby_fact(55.751244, 37.618423)

            assert "Локация: Дом Пашкова" in fact
            assert (
                "Интересный факт: В этом здании в 1920 году тайно встречались революционеры."
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
        mock_response.choices[
            0
        ].message.content = "Локация: Test\nИнтересный факт: Test fact"

        mock_create = AsyncMock(return_value=mock_response)

        with patch.object(openai_client.client.chat.completions, "create", mock_create):
            await openai_client.get_nearby_fact(55.751244, 37.618423)

            # Check that create was called with correct parameters
            mock_create.assert_called_once()
            call_args = mock_create.call_args

            # Check that either o4-mini or gpt-4.1 was used
            model_used = call_args[1]["model"]
            assert model_used in ["o4-mini", "gpt-4.1"]
            
            # If gpt-4.1 is used as fallback, it should have temperature and max_tokens
            if model_used == "gpt-4.1":
                assert call_args[1]["temperature"] == 0.7
                assert call_args[1]["max_tokens"] == 400
            # o4-mini uses max_completion_tokens and no temperature (like o3)
            elif model_used == "o4-mini":
                assert "temperature" not in call_args[1]
                assert call_args[1]["max_completion_tokens"] == 3000
                assert "max_tokens" not in call_args[1]

            messages = call_args[1]["messages"]
            assert len(messages) == 2
            assert messages[0]["role"] == "system"
            assert "экскурсовод" in messages[0]["content"]
            assert "рассуждения" in messages[0]["content"]
            assert messages[1]["role"] == "user"
            assert "55.751244, 37.618423" in messages[1]["content"]
            assert "Шаг 1:" in messages[1]["content"]
            assert "Локация:" in messages[1]["content"]
            assert "Интересный факт:" in messages[1]["content"]

    anyio.run(_test)
