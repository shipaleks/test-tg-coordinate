"""OpenAI client for generating location-based facts."""

import logging
import os

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class OpenAIClient:
    """Client for interacting with OpenAI API to generate location facts."""

    def __init__(self, api_key: str | None = None):
        """Initialize OpenAI client.

        Args:
            api_key: OpenAI API key. If None, will use OPENAI_API_KEY env var.
        """
        self.client = AsyncOpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))

    async def get_nearby_fact(self, lat: float, lon: float) -> str:
        """Get an interesting fact about a location.

        Args:
            lat: Latitude coordinate
            lon: Longitude coordinate

        Returns:
            A location name and an interesting fact about it

        Raises:
            Exception: If OpenAI API call fails
        """
        try:
            system_prompt = (
                "You are a professional tour guide with deep knowledge of various locations around the world. "
                "Your task is to provide an interesting and non-obvious fact about a toponym within 300 meters of the given location. "
                "Imagine you are physically present at this location and have extensive knowledge of the area. "
                "Do not invent or fabricate information. If you cannot think of a genuine interesting fact, "
                "simply state the location and that you don't have any unusual facts about the immediate vicinity. "
                "Your entire response should be in Russian language. "
                "Remember, do not search the internet or use external resources. "
                "Rely only on the knowledge you have been trained with."
            )

            user_prompt = (
                f"Location coordinates: {lat}, {lon}\n\n"
                "1. Identify any toponyms (named places, landmarks, streets, etc.) within approximately 300 meters of this location. "
                "If there are no notable toponyms within 300 meters, state this fact.\n"
                "2. Choose one of the identified toponyms (or the location itself if no nearby toponyms exist) "
                "and think of an interesting, non-obvious fact about it. "
                "This fact should be something that is not commonly known but is true and intriguing.\n\n"
                "Provide your response in the following format:\n"
                "Локация: [Name of the location or nearest identifiable place]\n"
                "Интересный факт: [Your interesting fact about a nearby toponym or the location itself]"
            )

            response = await self.client.chat.completions.create(
                model="gpt-4.1-mini",  # Using gpt-4.1-mini as specified in PRD
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=300,  # Increased for detailed responses
                temperature=0.7,  # Balanced for accuracy and creativity
            )

            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from OpenAI")

            logger.info(f"Generated fact for location {lat},{lon}")
            return content.strip()

        except Exception as e:
            logger.error(f"Failed to generate fact for {lat},{lon}: {e}")
            raise


# Global client instance - will be initialized lazily
_openai_client: OpenAIClient | None = None


def get_openai_client() -> OpenAIClient:
    """Get or create the global OpenAI client instance."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAIClient()
    return _openai_client
