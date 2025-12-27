"""Test that prompts emphasize fact accuracy."""

from src.services.claude_client import ClaudeClient


def test_live_location_prompt_contains_key_elements():
    """Test that live location prompt includes essential instructions."""
    client = ClaudeClient(api_key="test_key")

    # Get Russian system prompt for live location
    system_prompt = client._build_system_prompt_russian(is_live_location=True)

    # Check core rules
    assert (
        "ТЫ — АВТОР ФАКТОВ" in system_prompt or "YOU ARE A FACT WRITER" in system_prompt
    )
    assert "Atlas Obscura" in system_prompt

    # Check forbidden items
    assert "СТРОГО ЗАПРЕЩЕНО:" in system_prompt or "STRICTLY FORBIDDEN" in system_prompt
    assert "[[NO_POI_FOUND]]" in system_prompt

    # Check format requirements
    assert "<answer>" in system_prompt


def test_static_location_prompt_contains_key_elements():
    """Test that static location prompt includes essential instructions."""
    client = ClaudeClient(api_key="test_key")

    # Get Russian system prompt for static location
    system_prompt = client._build_system_prompt_russian(is_live_location=False)

    # Check core rules
    assert (
        "ТЫ — АВТОР ФАКТОВ" in system_prompt or "YOU ARE A FACT WRITER" in system_prompt
    )

    # Check format requirements
    assert "<answer>" in system_prompt
    assert "Location:" in system_prompt
    assert "Coordinates:" in system_prompt


def test_english_prompt_contains_key_elements():
    """Test that English prompt includes essential instructions."""
    client = ClaudeClient(api_key="test_key")

    # Get English system prompt
    system_prompt = client._build_system_prompt_english(
        user_language="en", is_live_location=True
    )

    # Check core rules
    assert "YOU ARE A FACT WRITER" in system_prompt
    assert "Atlas Obscura" in system_prompt
    assert "STRICTLY FORBIDDEN:" in system_prompt

    # Check language instruction
    assert "Write your response entirely in en" in system_prompt


def test_user_prompt_live_location():
    """Test that live location user prompt includes correct elements."""
    client = ClaudeClient(api_key="test_key")

    lat, lon = 48.8566, 2.3522  # Paris
    user_prompt = client._build_user_prompt(
        lat, lon, is_live_location=True, previous_facts=None, user_language="en"
    )

    # Check coordinates are included
    assert "48.8566" in user_prompt
    assert "2.3522" in user_prompt

    # Check live location specific instructions
    assert "CURRENT location" in user_prompt
    assert "DISTANCE PRIORITY" in user_prompt


def test_user_prompt_static_location():
    """Test that static location user prompt includes correct elements."""
    client = ClaudeClient(api_key="test_key")

    lat, lon = 55.7558, 37.6173  # Moscow
    user_prompt = client._build_user_prompt(
        lat, lon, is_live_location=False, previous_facts=None, user_language="ru"
    )

    # Check coordinates are included
    assert "55.7558" in user_prompt
    assert "37.6173" in user_prompt

    # Check NO_POI_FOUND is mentioned for static
    assert "[[NO_POI_FOUND]]" in user_prompt


def test_previous_facts_duplicate_prevention():
    """Test that previous facts are included for duplicate prevention."""
    client = ClaudeClient(api_key="test_key")

    lat, lon = 48.8566, 2.3522
    previous_facts = [
        "Eiffel Tower: Built in 1889",
        "Louvre Museum: Home of Mona Lisa",
    ]

    user_prompt = client._build_user_prompt(
        lat,
        lon,
        is_live_location=True,
        previous_facts=previous_facts,
        user_language="en",
    )

    # Check previous facts are mentioned
    assert "Eiffel Tower" in user_prompt
    assert "Louvre Museum" in user_prompt
    assert "FORBIDDEN PLACES" in user_prompt


def test_russian_style_instructions_quality():
    """Test that Russian style instructions include quality guidelines."""
    client = ClaudeClient(api_key="test_key")

    instructions = client._get_russian_style_instructions()

    # Check key Russian writing guidelines
    assert "СТИЛЬ ИЗЛОЖЕНИЯ" in instructions
    assert "СТРУКТУРА ФАКТА" in instructions
    assert "ЯЗЫК И ГРАММАТИКА" in instructions
    assert "ЗОЛОТОЕ ПРАВИЛО" in instructions

    # Check forbidden words
    assert "канцелярит" in instructions
    assert "является" in instructions


def test_russian_prompt_uses_separate_style():
    """Test that Russian prompt uses dedicated Russian style instructions."""
    client = ClaudeClient(api_key="test_key")

    system_prompt = client._build_system_prompt_russian(is_live_location=False)

    # Should include Russian-specific style guide
    assert "СТИЛЬ ИЗЛОЖЕНИЯ" in system_prompt
    assert "Начинайте с самого удивительного факта" in system_prompt


def test_web_search_context_included():
    """Test that web search results can be included in prompt."""
    client = ClaudeClient(api_key="test_key")

    web_results = "Web search results:\n1. Example result about Paris"

    system_prompt = client._build_system_prompt_russian(
        is_live_location=False, web_search_results=web_results
    )

    assert "Example result about Paris" in system_prompt
    assert "РЕЗУЛЬТАТЫ ПОИСКА" in system_prompt
