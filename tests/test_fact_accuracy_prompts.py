"""Test that prompts emphasize fact accuracy."""

import pytest
from src.services.openai_client import OpenAIClient


def test_live_location_prompt_contains_key_elements():
    """Test that live location prompt includes essential instructions."""
    client = OpenAIClient(api_key="test_key")
    
    # Get prompt for live location
    lat, lon = 48.8566, 2.3522  # Paris coordinates
    system_prompt, user_prompt = client._build_location_fact_prompt(
        lat, lon, 
        is_live_location=True, 
        user_language="ru",
        previous_facts=None,
        language_instructions=""
    )
    
    # Check core rules
    assert "YOU ARE A FACT WRITER, NOT A SEARCH ASSISTANT" in system_prompt
    assert "Atlas Obscura–style facts" in system_prompt
    assert "Verification:" in system_prompt
    assert "Use web_search at least twice" in system_prompt
    
    # Check forbidden items
    assert "STRICTLY FORBIDDEN:" in system_prompt
    assert "Meta-facts about coordinates" in system_prompt
    assert "Wrong dates, false attributions" in system_prompt
    
    # Check live location specific user prompt
    assert "CRITICAL: This is the user's CURRENT location" in user_prompt
    assert "DISTANCE PRIORITY:" in user_prompt
    assert "0-400m" in user_prompt


def test_static_location_prompt_contains_key_elements():
    """Test that static location prompt includes essential instructions."""
    client = OpenAIClient(api_key="test_key")
    
    # Get prompt for static location
    lat, lon = 55.7558, 37.6173  # Moscow coordinates
    system_prompt, user_prompt = client._build_location_fact_prompt(
        lat, lon, 
        is_live_location=False, 
        user_language="ru",
        previous_facts=None,
        language_instructions=""
    )
    
    # Check core rules (same as live)
    assert "YOU ARE A FACT WRITER" in system_prompt
    assert "Verification:" in system_prompt
    
    # Check static location specific user prompt
    assert "Here are the coordinates to analyze" in user_prompt
    assert "Apply the method above to find one concise, surprising, verified detail" in user_prompt
    # Static location allows [[NO_POI_FOUND]]
    assert "[[NO_POI_FOUND]]" in user_prompt


def test_prompt_language_integration():
    """Test that language instructions are integrated into the prompt."""
    client = OpenAIClient(api_key="test_key")
    
    lat, lon = 48.8566, 2.3522
    lang_instr = "SPECIAL RUSSIAN INSTRUCTIONS"
    
    system_prompt, _ = client._build_location_fact_prompt(
        lat, lon, 
        is_live_location=True, 
        user_language="ru",
        previous_facts=None,
        language_instructions=lang_instr
    )
    
    assert "LANGUAGE REQUIREMENTS:" in system_prompt
    assert "Write your response in ru" in system_prompt
    assert lang_instr in system_prompt


def test_previous_facts_duplicate_prevention():
    """Test that previous facts are included for duplicate prevention."""
    client = OpenAIClient(api_key="test_key")
    
    lat, lon = 48.8566, 2.3522
    previous_facts = [
        "Eiffel Tower: Built in 1889", 
        "Louvre Museum: Home of Mona Lisa"
    ]
    
    _, user_prompt = client._build_location_fact_prompt(
        lat, lon, 
        is_live_location=True, 
        user_language="en",
        previous_facts=previous_facts,
        language_instructions=""
    )
    
    assert "PREVIOUS FACTS ALREADY MENTIONED:" in user_prompt
    assert "Eiffel Tower" in user_prompt
    assert "Louvre Museum" in user_prompt
    assert "⛔ FORBIDDEN PLACES" in user_prompt
    assert "CRITICAL DUPLICATE PREVENTION:" in user_prompt
