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
            fact = await openai_client.get_nearby_fact(
                55.751244, 37.618423, is_live_location=False
            )

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
            with pytest.raises(ValueError, match="Empty content from gpt-4.1"):
                await openai_client.get_nearby_fact(
                    55.751244, 37.618423, is_live_location=False
                )

    anyio.run(_test)


def test_get_nearby_fact_api_error(openai_client):
    """Test handling of API errors."""

    async def _test():
        mock_create = AsyncMock(side_effect=Exception("API Error"))

        with patch.object(openai_client.client.chat.completions, "create", mock_create):
            with pytest.raises(Exception, match="API Error"):
                await openai_client.get_nearby_fact(
                    55.751244, 37.618423, is_live_location=False
                )

    anyio.run(_test)


def test_get_nearby_fact_prompt_format(openai_client):
    """Test that the prompt is formatted correctly."""

    async def _test():
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            "Локация: Test\nИнтересный факт: Test fact"
        )

        mock_create = AsyncMock(return_value=mock_response)

        with patch.object(openai_client.client.chat.completions, "create", mock_create):
            await openai_client.get_nearby_fact(
                55.751244, 37.618423, is_live_location=False
            )

            # Check that create was called with correct parameters
            mock_create.assert_called_once()
            call_args = mock_create.call_args

            # For static location (is_live_location=False), should use gpt-4.1
            model_used = call_args[1]["model"]
            assert model_used == "gpt-4.1"
            assert call_args[1]["temperature"] == 0.7
            assert call_args[1]["max_tokens"] == 400
            assert "max_completion_tokens" not in call_args[1]

            messages = call_args[1]["messages"]
            assert len(messages) == 2
            assert messages[0]["role"] == "system"
            assert "экскурсовод" in messages[0]["content"]
            assert "рассуждения" in messages[0]["content"]
            assert messages[1]["role"] == "user"
            assert "55.751244, 37.618423" in messages[1]["content"]
            # Static location should not have detailed steps, but should be concise
            assert "Краткий но УВЛЕКАТЕЛЬНЫЙ факт (60-80 слов)" in messages[1]["content"]
            assert "Локация:" in messages[1]["content"]
            assert "Интересный факт:" in messages[1]["content"]

    anyio.run(_test)


def test_get_nearby_fact_live_location_model(openai_client):
    """Test that live location uses o4-mini model."""

    async def _test():
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            "Локация: Test\nИнтересный факт: Test detailed fact"
        )

        mock_create = AsyncMock(return_value=mock_response)

        with patch.object(openai_client.client.chat.completions, "create", mock_create):
            await openai_client.get_nearby_fact(
                55.751244, 37.618423, is_live_location=True
            )

            # Check that create was called with correct parameters
            mock_create.assert_called_once()
            call_args = mock_create.call_args

            # For live location (is_live_location=True), should use o4-mini
            model_used = call_args[1]["model"]
            assert model_used == "o4-mini"
            assert "temperature" not in call_args[1]
            assert call_args[1]["max_completion_tokens"] == 10000
            assert "max_tokens" not in call_args[1]

            messages = call_args[1]["messages"]
            assert len(messages) == 2
            assert messages[0]["role"] == "system"
            assert "экскурсовод" in messages[0]["content"]
            assert "рассуждения" in messages[0]["content"]
            assert messages[1]["role"] == "user"
            assert "55.751244, 37.618423" in messages[1]["content"]
            assert (
                "Шаг 1:" in messages[1]["content"]
            )  # Should have detailed steps for live location

    anyio.run(_test)


def test_parse_coordinates_from_response(openai_client):
    """Test parsing coordinates from OpenAI response."""

    async def _test():
        # Test new format with search keywords
        response_with_search = (
            "Локация: Тестовое место\n"
            "Поиск: Тестовое место Москва центр\n"
            "Интересный факт: Тестовое место для проверки."
        )
        
        # Mock search keywords method
        with patch.object(
            openai_client,
            "get_coordinates_from_search_keywords",
            new_callable=AsyncMock,
            return_value=(55.7415, 37.6056),
        ):
            coords = await openai_client.parse_coordinates_from_response(
                response_with_search
            )
            assert coords == (55.7415, 37.6056)
            
        # Test fallback to location name when no search keywords
        response_without_search = (
            "Локация: Тестовое место\n"
            "Интересный факт: Тестовое место для проверки."
        )
        
        with patch.object(
            openai_client,
            "get_coordinates_from_search_keywords",
            new_callable=AsyncMock,
            return_value=(55.7415, 37.6056),
        ):
            coords = await openai_client.parse_coordinates_from_response(
                response_without_search
            )
            assert coords == (55.7415, 37.6056)

        # Test response without coordinates - will try to search for precise coordinates
        # Mock both fallback methods to return None
        with patch.object(
            openai_client,
            "get_precise_coordinates",
            new_callable=AsyncMock,
            return_value=None,
        ), patch.object(
            openai_client,
            "get_coordinates_from_nominatim",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response_without_coords = (
                "Локация: Где-то в городе\n" "Интересный факт: Интересное место."
            )
            coords = await openai_client.parse_coordinates_from_response(
                response_without_coords
            )
            assert coords is None

        # Test invalid coordinates (out of range) - should try to search for precise coordinates
        with patch.object(
            openai_client,
            "get_precise_coordinates",
            new_callable=AsyncMock,
            return_value=None,
        ), patch.object(
            openai_client,
            "get_coordinates_from_nominatim",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response_invalid_coords = (
                "Локация: Невалидное место\n"
                "Координаты: 95.0, 200.0\n"
                "Интересный факт: Факт."
            )
            coords = await openai_client.parse_coordinates_from_response(
                response_invalid_coords
            )
            assert coords is None

        # Test malformed coordinates - should try to search for precise coordinates
        with patch.object(
            openai_client,
            "get_precise_coordinates",
            new_callable=AsyncMock,
            return_value=None,
        ), patch.object(
            openai_client,
            "get_coordinates_from_nominatim",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response_bad_coords = (
                "Локация: Плохое место\n"
                "Координаты: не числа\n"
                "Интересный факт: Факт."
            )
            coords = await openai_client.parse_coordinates_from_response(
                response_bad_coords
            )
            assert coords is None

    anyio.run(_test)


def test_get_precise_coordinates(openai_client):
    """Test getting precise coordinates using web search (deprecated - always returns None)."""

    async def _test():
        # WebSearch is deprecated, so this method should always return None
        coords = await openai_client.get_precise_coordinates(
            "Красная площадь", "Центр Москвы"
        )
        assert coords is None

        # Test with any other input - should still return None
        coords = await openai_client.get_precise_coordinates(
            "Несуществующее место", "Где-то"
        )
        assert coords is None

    anyio.run(_test)


def test_get_coordinates_from_nominatim(openai_client):
    """Test getting coordinates from Nominatim service."""

    async def _test():
        # Test successful response
        with patch.object(
            openai_client, "get_coordinates_from_nominatim", new_callable=AsyncMock
        ) as mock_nominatim:
            mock_nominatim.return_value = (55.7539, 37.6208)

            coords = await openai_client.get_coordinates_from_nominatim(
                "Красная площадь Москва"
            )
            assert coords == (55.7539, 37.6208)
            mock_nominatim.assert_called_once_with("Красная площадь Москва")

        # Test no results
        with patch.object(
            openai_client, "get_coordinates_from_nominatim", new_callable=AsyncMock
        ) as mock_nominatim:
            mock_nominatim.return_value = None

            coords = await openai_client.get_coordinates_from_nominatim(
                "Несуществующее место"
            )
            assert coords is None

    anyio.run(_test)


def test_coordinates_precision_detection(openai_client):
    """Test detection of imprecise coordinates."""
    
    # Test precise coordinates that are far from suspicious patterns (should return False)
    assert not openai_client._coordinates_look_imprecise(55.7415, 37.6056)  # Different area
    
    # Test imprecise coordinates - too few decimal places
    assert openai_client._coordinates_look_imprecise(55.75, 37.62)
    
    # Test suspicious round numbers
    assert openai_client._coordinates_look_imprecise(55.8, 37.6)
    
    # Test suspicious patterns (Moscow center)
    assert openai_client._coordinates_look_imprecise(55.7558, 37.6173)
    
    # Test Null Island
    assert openai_client._coordinates_look_imprecise(0.0, 0.0)


def test_coordinates_precision_comparison(openai_client):
    """Test comparison of coordinate precision."""
    
    # More precise vs less precise
    precise_coords = (55.753915, 37.620795)  # 6 decimal places each
    imprecise_coords = (55.75, 37.62)  # 2 decimal places each
    
    assert openai_client._coordinates_are_more_precise(precise_coords, imprecise_coords)
    assert not openai_client._coordinates_are_more_precise(imprecise_coords, precise_coords)
    
    # Same precision
    coords1 = (55.7539, 37.6208)  # 4 decimal places each
    coords2 = (55.7541, 37.6207)  # 4 decimal places each (avoid trailing zeros)
    
    assert not openai_client._coordinates_are_more_precise(coords1, coords2)
    assert not openai_client._coordinates_are_more_precise(coords2, coords1)


def test_get_coordinates_from_search_keywords(openai_client):
    """Test getting coordinates from search keywords."""

    async def _test():
        # Test successful Nominatim search
        with patch.object(
            openai_client,
            "get_coordinates_from_nominatim",
            new_callable=AsyncMock,
            return_value=(55.7539, 37.6208),
        ):
            coords = await openai_client.get_coordinates_from_search_keywords(
                "Красная площадь Москва"
            )
            assert coords == (55.7539, 37.6208)

        # Test metro station fallback search
        with patch.object(
            openai_client,
            "get_coordinates_from_nominatim",
            new_callable=AsyncMock,
            side_effect=[None, (48.8356, 2.3454)],  # Original fails, fallback succeeds
        ) as mock_nominatim:
            coords = await openai_client.get_coordinates_from_search_keywords(
                "Censier–Daubenton Metro Paris France"
            )
            assert coords == (48.8356, 2.3454)
            # Verify fallback was called with simplified metro station format
            assert mock_nominatim.call_count == 2
            calls = [call.args[0] for call in mock_nominatim.call_args_list]
            assert "Censier–Daubenton Metro Paris France" in calls
            assert any("Censier–Daubenton" in call and "station" in call for call in calls)

        # Test complex place name fallback search  
        with patch.object(
            openai_client,
            "get_coordinates_from_nominatim",
            new_callable=AsyncMock,
            side_effect=[None, (55.7540, 37.6209)],  # First call fails, second succeeds
        ):
            coords = await openai_client.get_coordinates_from_search_keywords(
                "Complex Place Name + Paris + Detail"
            )
            assert coords == (55.7540, 37.6209)

        # Test when all methods fail
        with patch.object(
            openai_client,
            "get_coordinates_from_nominatim",
            new_callable=AsyncMock,
            return_value=None,
        ):
            coords = await openai_client.get_coordinates_from_search_keywords(
                "Несуществующее место"
            )
            assert coords is None

    anyio.run(_test)


def test_get_wikipedia_image(openai_client):
    """Test getting images from Wikipedia."""

    async def _test():
        # Test with a well-known landmark that should have an image
        with patch('aiohttp.ClientSession') as mock_session:
            # Mock Wikipedia search response (now using legacy API format)
            mock_search_response = MagicMock()
            mock_search_response.status = 200
            mock_search_response.json = AsyncMock(return_value={
                'query': {
                    'search': [
                        {'title': 'Eiffel Tower', 'snippet': 'Famous tower in Paris'}
                    ]
                }
            })
            
            # Mock Wikipedia media response  
            mock_media_response = MagicMock()
            mock_media_response.status = 200
            mock_media_response.json = AsyncMock(return_value={
                'items': [
                    {'type': 'image', 'title': 'File:Eiffel_Tower.jpg'},
                    {'type': 'image', 'title': 'File:Commons-logo.png'}  # Should be skipped
                ]
            })
            
            # Mock session context manager
            mock_session_instance = MagicMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_session_instance)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)
            
            # Mock get requests
            mock_session_instance.get.return_value.__aenter__ = AsyncMock()
            mock_session_instance.get.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_session_instance.get.return_value.__aenter__.side_effect = [
                mock_search_response, mock_media_response
            ]
            
            # Test the function
            image_url = await openai_client.get_wikipedia_image("Eiffel Tower Paris France")
            
            # Should return the image URL (URL encoded)
            assert image_url == "https://commons.wikimedia.org/wiki/Special:FilePath/File%3AEiffel_Tower.jpg"
            
        # Test with search keywords that won't be found
        with patch('aiohttp.ClientSession') as mock_session:
            mock_search_response = MagicMock()
            mock_search_response.status = 200
            mock_search_response.json = AsyncMock(return_value={
                'query': {'search': []}
            })
            
            mock_session_instance = MagicMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_session_instance)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_session_instance.get.return_value.__aenter__ = AsyncMock(return_value=mock_search_response)
            mock_session_instance.get.return_value.__aexit__ = AsyncMock(return_value=None)
            
            image_url = await openai_client.get_wikipedia_image("NonexistentPlace")
            assert image_url is None

    anyio.run(_test)
