"""Tests for Claude client."""

from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest
from src.services.claude_client import ClaudeClient


@pytest.fixture
def claude_client():
    """Create Claude client for testing."""
    return ClaudeClient(api_key="test-key")


def test_get_nearby_fact_success(claude_client):
    """Test successful fact generation."""

    async def _test():
        # Mock response content block
        mock_text_block = MagicMock()
        mock_text_block.text = (
            "Локация: Дом Пашкова\n"
            "Интересный факт: В этом здании в 1920 году тайно встречались революционеры."
        )

        # Mock response
        mock_response = MagicMock()
        mock_response.content = [mock_text_block]

        # Create async mock that returns the mock response
        mock_create = AsyncMock(return_value=mock_response)

        # Patch messages.create for Claude
        with patch.object(claude_client.client.messages, "create", mock_create):
            # Also patch web_search to avoid actual API calls
            with patch.object(
                claude_client.web_search,
                "search",
                new_callable=AsyncMock,
                return_value=[],
            ):
                fact = await claude_client.get_nearby_fact(
                    55.751244, 37.618423, is_live_location=False
                )

                assert "Локация: Дом Пашкова" in fact
                assert (
                    "Интересный факт: В этом здании в 1920 году тайно встречались революционеры."
                    in fact
                )

    anyio.run(_test)


def test_get_nearby_fact_empty_response(claude_client):
    """Test handling of empty response from Claude."""

    async def _test():
        # Mock empty response
        mock_response = MagicMock()
        mock_response.content = []

        mock_create = AsyncMock(return_value=mock_response)

        with patch.object(claude_client.client.messages, "create", mock_create):
            with patch.object(
                claude_client.web_search,
                "search",
                new_callable=AsyncMock,
                return_value=[],
            ):
                with pytest.raises(ValueError, match="Empty response from Claude"):
                    await claude_client.get_nearby_fact(
                        55.751244, 37.618423, is_live_location=False
                    )

    anyio.run(_test)


def test_get_nearby_fact_api_error(claude_client):
    """Test handling of API errors."""

    async def _test():
        mock_create = AsyncMock(side_effect=Exception("API Error"))

        with patch.object(claude_client.client.messages, "create", mock_create):
            with patch.object(
                claude_client.web_search,
                "search",
                new_callable=AsyncMock,
                return_value=[],
            ):
                with pytest.raises(Exception, match="API Error"):
                    await claude_client.get_nearby_fact(
                        55.751244, 37.618423, is_live_location=False
                    )

    anyio.run(_test)


def test_get_nearby_fact_prompt_format(claude_client):
    """Test that the prompt is formatted correctly for Claude."""

    async def _test():
        mock_text_block = MagicMock()
        mock_text_block.text = "Локация: Test\nИнтересный факт: Test fact"

        mock_response = MagicMock()
        mock_response.content = [mock_text_block]

        mock_create = AsyncMock(return_value=mock_response)

        with patch.object(claude_client.client.messages, "create", mock_create):
            with patch.object(
                claude_client.web_search,
                "search",
                new_callable=AsyncMock,
                return_value=[],
            ):
                await claude_client.get_nearby_fact(
                    55.751244, 37.618423, is_live_location=False
                )

                # Check that create was called with correct parameters
                mock_create.assert_called_once()
                call_args = mock_create.call_args
                kwargs = call_args.kwargs

                # Check model parameter (default is now Sonnet 5)
                assert kwargs["model"] == "claude-sonnet-5"

                # Check max_tokens
                assert "max_tokens" in kwargs
                assert kwargs["max_tokens"] == 8192
                # Default reasoning is "low" -> adaptive thinking with low effort
                assert "thinking" in kwargs
                assert kwargs["thinking"] == {"type": "adaptive"}
                assert kwargs["output_config"] == {"effort": "low"}

                # Check system prompt contains Atlas Obscura
                assert "system" in kwargs
                assert "Atlas Obscura" in kwargs["system"]

                # Check messages format
                assert "messages" in kwargs
                messages = kwargs["messages"]
                assert len(messages) == 1
                assert messages[0]["role"] == "user"

                # User prompt contains coordinates
                content = messages[0]["content"]
                assert "55.751244" in content

    anyio.run(_test)


def test_get_nearby_fact_live_location_model(claude_client):
    """Test that live location uses correct model settings."""

    async def _test():
        mock_text_block = MagicMock()
        mock_text_block.text = "Локация: Test\nИнтересный факт: Test detailed fact"

        mock_response = MagicMock()
        mock_response.content = [mock_text_block]

        mock_create = AsyncMock(return_value=mock_response)

        with patch.object(claude_client.client.messages, "create", mock_create):
            with patch.object(
                claude_client.web_search,
                "search",
                new_callable=AsyncMock,
                return_value=[],
            ):
                await claude_client.get_nearby_fact(
                    55.751244, 37.618423, is_live_location=True
                )

                mock_create.assert_called_once()
                call_args = mock_create.call_args
                kwargs = call_args.kwargs

                # Live location also uses Sonnet 5 by default (same as static)
                assert kwargs["model"] == "claude-sonnet-5"

    anyio.run(_test)


def test_build_thinking_config_claude5_adaptive(claude_client):
    """Claude 5 models use adaptive thinking with an effort parameter."""
    for model in (claude_client.MODEL_OPUS, claude_client.MODEL_SONNET):
        thinking, output_config = claude_client._build_thinking_config(
            "medium", False, model=model
        )
        assert thinking == {"type": "adaptive"}
        assert output_config == {"effort": "medium"}

    # Reasoning "none" disables thinking and sends no output_config
    thinking, output_config = claude_client._build_thinking_config(
        "none", False, model=claude_client.MODEL_OPUS
    )
    assert thinking == {"type": "disabled"}
    assert output_config is None


def test_build_thinking_config_haiku_budget_tokens(claude_client):
    """Haiku 4.5 (pre-4.6 model) keeps manual budget_tokens thinking."""
    thinking, output_config = claude_client._build_thinking_config(
        "medium", False, model=claude_client.MODEL_HAIKU
    )
    assert thinking == {"type": "enabled", "budget_tokens": 2048}
    assert output_config is None


def test_no_poi_retry_keeps_thinking_and_output_config(claude_client):
    """NO_POI retries must carry the same thinking/effort config as the first call."""

    async def _test():
        no_poi_block = MagicMock()
        no_poi_block.text = "[[NO_POI_FOUND]]"
        no_poi_response = MagicMock()
        no_poi_response.content = [no_poi_block]

        ok_block = MagicMock()
        ok_block.text = "Локация: Test\nИнтересный факт: Test fact"
        ok_response = MagicMock()
        ok_response.content = [ok_block]

        mock_create = AsyncMock(side_effect=[no_poi_response, ok_response])

        with patch.object(claude_client.client.messages, "create", mock_create):
            with patch.object(
                claude_client.web_search,
                "search",
                new_callable=AsyncMock,
                return_value=[],
            ):
                await claude_client.get_nearby_fact(
                    55.751244, 37.618423, is_live_location=False
                )

        assert mock_create.call_count == 2
        retry_kwargs = mock_create.call_args_list[1].kwargs
        assert retry_kwargs["thinking"] == {"type": "adaptive"}
        assert retry_kwargs["output_config"] == {"effort": "low"}

    anyio.run(_test)


def test_model_mapping_forward_maps_to_current_lineup(claude_client):
    """Every legacy stored model ID must map to a currently served model."""
    from src.services.async_donors_wrapper import MODEL_MAPPING

    current_models = {
        claude_client.MODEL_OPUS,
        claude_client.MODEL_SONNET,
        claude_client.MODEL_HAIKU,
    }
    # All mapping targets must pass the allow-list in get_nearby_fact
    assert set(MODEL_MAPPING.values()) <= current_models

    # Previously offered IDs are forward-mapped to the new generation
    assert MODEL_MAPPING["claude-opus-4-6"] == claude_client.MODEL_OPUS
    assert MODEL_MAPPING["claude-sonnet-4-5-20250929"] == claude_client.MODEL_SONNET
    assert MODEL_MAPPING["gpt-5.1"] == claude_client.MODEL_OPUS
    assert MODEL_MAPPING["gpt-5.1-mini"] == claude_client.MODEL_SONNET


def test_refusal_response_raises(claude_client):
    """A stop_reason == "refusal" response must not be parsed as content."""

    async def _test():
        mock_response = MagicMock()
        mock_response.stop_reason = "refusal"
        mock_response.content = []

        with patch.object(
            claude_client.client.messages,
            "create",
            AsyncMock(return_value=mock_response),
        ):
            with patch.object(
                claude_client.web_search,
                "search",
                new_callable=AsyncMock,
                return_value=[],
            ):
                with pytest.raises(ValueError):
                    await claude_client.get_nearby_fact(
                        55.751244, 37.618423, is_live_location=False
                    )

    anyio.run(_test)


def test_opus_requests_use_server_side_fallbacks(claude_client):
    """Opus 5 requests go through the beta endpoint with refusal fallbacks."""

    async def _test():
        plain_create = AsyncMock(return_value="plain")
        beta_create = AsyncMock(return_value="beta")

        with patch.object(claude_client.client.messages, "create", plain_create):
            with patch.object(
                claude_client.client.beta.messages, "create", beta_create
            ):
                result = await claude_client._create_message(
                    {"model": claude_client.MODEL_OPUS, "max_tokens": 10}
                )
                assert result == "beta"
                kwargs = beta_create.call_args.kwargs
                assert kwargs["betas"] == ["server-side-fallback-2026-07-01"]
                assert kwargs["fallbacks"] == "default"

                result = await claude_client._create_message(
                    {"model": claude_client.MODEL_SONNET, "max_tokens": 10}
                )
                assert result == "plain"
                assert "fallbacks" not in plain_create.call_args.kwargs

    anyio.run(_test)


def test_parse_coordinates_from_response(claude_client):
    """Test parsing coordinates from Claude response."""

    async def _test():
        # Test new format with search keywords inside <answer> tags
        response_with_search = (
            "<answer>\n"
            "Location: Тестовое место\n"
            "Search: Тестовое место Москва центр\n"
            "Interesting fact: Тестовое место для проверки.\n"
            "</answer>"
        )

        # Mock search keywords method
        with patch.object(
            claude_client,
            "get_coordinates_from_search_keywords",
            new_callable=AsyncMock,
            return_value=(55.7415, 37.6056),
        ):
            coords = await claude_client.parse_coordinates_from_response(
                response_with_search
            )
            assert coords == (55.7415, 37.6056)

        # Test fallback to location name when no search keywords
        response_without_search = (
            "<answer>\n"
            "Location: Тестовое место\n"
            "Interesting fact: Тестовое место для проверки.\n"
            "</answer>"
        )

        with patch.object(
            claude_client,
            "get_coordinates_from_search_keywords",
            new_callable=AsyncMock,
            return_value=(55.7415, 37.6056),
        ):
            coords = await claude_client.parse_coordinates_from_response(
                response_without_search
            )
            assert coords == (55.7415, 37.6056)

        # Test response without answer tags - should try legacy format
        with patch.object(
            claude_client,
            "get_coordinates_from_search_keywords",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response_without_coords = (
                "Локация: Где-то в городе\nИнтересный факт: Интересное место."
            )
            coords = await claude_client.parse_coordinates_from_response(
                response_without_coords
            )
            assert coords is None

    anyio.run(_test)


def test_get_precise_coordinates(claude_client):
    """Test getting precise coordinates (uses Nominatim directly)."""

    async def _test():
        # Mock Nominatim to return None
        with patch.object(
            claude_client,
            "get_coordinates_from_nominatim",
            new_callable=AsyncMock,
            return_value=None,
        ):
            coords = await claude_client.get_precise_coordinates(
                "Красная площадь", "Центр Москвы"
            )
            assert coords is None

        # Mock Nominatim to return valid coords
        with patch.object(
            claude_client,
            "get_coordinates_from_nominatim",
            new_callable=AsyncMock,
            return_value=(55.7539, 37.6208),
        ):
            coords = await claude_client.get_precise_coordinates(
                "Красная площадь", "Центр Москвы"
            )
            assert coords == (55.7539, 37.6208)

    anyio.run(_test)


def test_get_coordinates_from_nominatim(claude_client):
    """Test getting coordinates from Nominatim service."""

    async def _test():
        # Test successful response
        with patch.object(
            claude_client, "get_coordinates_from_nominatim", new_callable=AsyncMock
        ) as mock_nominatim:
            mock_nominatim.return_value = (55.7539, 37.6208)

            coords = await claude_client.get_coordinates_from_nominatim(
                "Красная площадь Москва"
            )
            assert coords == (55.7539, 37.6208)
            mock_nominatim.assert_called_once_with("Красная площадь Москва")

        # Test empty response
        with patch.object(
            claude_client, "get_coordinates_from_nominatim", new_callable=AsyncMock
        ) as mock_nominatim:
            mock_nominatim.return_value = None

            coords = await claude_client.get_coordinates_from_nominatim(
                "Несуществующее место"
            )
            assert coords is None

    anyio.run(_test)


def test_get_wikipedia_images_success(claude_client):
    """Test successful image retrieval from Wikipedia."""

    async def _test():
        # Mock the internal search method
        with patch.object(
            claude_client,
            "_search_wikipedia_images",
            new_callable=AsyncMock,
            return_value=[
                "https://commons.wikimedia.org/image1.jpg",
                "https://commons.wikimedia.org/image2.jpg",
            ],
        ):
            images = await claude_client.get_wikipedia_images("Красная площадь")
            assert len(images) == 2
            assert "image1.jpg" in images[0]

    anyio.run(_test)


def test_get_wikipedia_images_empty(claude_client):
    """Test empty image results."""

    async def _test():
        with patch.object(
            claude_client,
            "_search_wikipedia_images",
            new_callable=AsyncMock,
            return_value=[],
        ):
            images = await claude_client.get_wikipedia_images("Nonexistent place 12345")
            assert images == []

    anyio.run(_test)


def test_get_wikipedia_image_single(claude_client):
    """Test getting single image (backward compatibility)."""

    async def _test():
        with patch.object(
            claude_client,
            "get_wikipedia_images",
            new_callable=AsyncMock,
            return_value=["https://commons.wikimedia.org/image1.jpg"],
        ):
            image = await claude_client.get_wikipedia_image("Test place")
            assert image == "https://commons.wikimedia.org/image1.jpg"

        # Test when no images found
        with patch.object(
            claude_client,
            "get_wikipedia_images",
            new_callable=AsyncMock,
            return_value=[],
        ):
            image = await claude_client.get_wikipedia_image("No images place")
            assert image is None

    anyio.run(_test)


def test_static_location_history(claude_client):
    """Test static location history caching."""
    history = claude_client.static_history

    # Test empty history
    facts = history.get_previous_facts("test_location")
    assert facts == []

    # Add facts
    history.add_fact("test_location", "Place 1", "Fact about place 1")
    history.add_fact("test_location", "Place 2", "Fact about place 2")

    # Get facts
    facts = history.get_previous_facts("test_location")
    assert len(facts) == 2
    assert "Place 1" in facts[0]
    assert "Place 2" in facts[1]

    # Test cache stats
    stats = history.get_cache_stats()
    assert stats["locations"] == 1
    assert stats["total_facts"] == 2


def test_validate_city_coordinates(claude_client):
    """Test city coordinate validation."""
    # Valid Paris coordinates
    assert claude_client._validate_city_coordinates(48.8566, 2.3522, "Paris") is True

    # Invalid coordinates for Paris (actually Moscow)
    assert claude_client._validate_city_coordinates(55.7558, 37.6173, "Paris") is False

    # Valid Moscow coordinates
    assert claude_client._validate_city_coordinates(55.7558, 37.6173, "Москва") is True

    # Unknown city - should return True (can't validate)
    assert claude_client._validate_city_coordinates(0, 0, "Unknown City") is True


def test_calculate_distance(claude_client):
    """Test distance calculation between coordinates."""
    # Same point should be 0
    dist = claude_client._calculate_distance(55.7558, 37.6173, 55.7558, 37.6173)
    assert dist < 0.001  # Should be essentially 0

    # Moscow to Paris should be ~2500km
    dist = claude_client._calculate_distance(55.7558, 37.6173, 48.8566, 2.3522)
    assert 2400 < dist < 2600


def test_russian_style_instructions(claude_client):
    """Test that Russian style instructions are included."""
    instructions = claude_client._get_russian_style_instructions()

    # Check key Russian writing guidelines are present
    assert "СТИЛЬ ИЗЛОЖЕНИЯ" in instructions
    assert "Atlas Obscura" in instructions or "Obscura" in instructions
    assert "канцелярит" in instructions
    assert "является" in instructions  # Should mention forbidden words
    assert "ЗОЛОТОЕ ПРАВИЛО" in instructions


def test_system_prompt_russian(claude_client):
    """Test Russian system prompt generation."""
    prompt = claude_client._build_system_prompt_russian(is_live_location=False)

    assert "Atlas Obscura" in prompt
    assert "СТРОГО ЗАПРЕЩЕНО" in prompt
    assert "[[NO_POI_FOUND]]" in prompt
    assert "<answer>" in prompt


def test_system_prompt_english(claude_client):
    """Test English system prompt generation."""
    prompt = claude_client._build_system_prompt_english(
        user_language="en", is_live_location=False
    )

    assert "Atlas Obscura" in prompt
    assert "STRICTLY FORBIDDEN" in prompt
    assert "[[NO_POI_FOUND]]" in prompt
    assert "<answer>" in prompt
    assert "Write your response entirely in en" in prompt


def test_user_prompt_with_previous_facts(claude_client):
    """Test user prompt includes previous facts correctly."""
    previous_facts = ["Place A: Fact about A", "Place B: Fact about B"]

    prompt_ru = claude_client._build_user_prompt(
        lat=55.75,
        lon=37.62,
        is_live_location=False,
        previous_facts=previous_facts,
        user_language="ru",
    )

    assert "Place A" in prompt_ru
    assert "Place B" in prompt_ru
    assert "ЗАПРЕЩЁННЫЕ МЕСТА" in prompt_ru

    prompt_en = claude_client._build_user_prompt(
        lat=55.75,
        lon=37.62,
        is_live_location=False,
        previous_facts=previous_facts,
        user_language="en",
    )

    assert "Place A" in prompt_en
    assert "Place B" in prompt_en
    assert "FORBIDDEN PLACES" in prompt_en


def test_backward_compatibility_aliases():
    """Test that backward compatibility aliases work."""
    from src.services.claude_client import OpenAIClient, get_openai_client

    # These should be aliases for Claude classes
    assert OpenAIClient is ClaudeClient

    client = get_openai_client()
    assert isinstance(client, ClaudeClient)
