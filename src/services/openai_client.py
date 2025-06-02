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
            A short interesting fact about the location

        Raises:
            Exception: If OpenAI API call fails
        """
        try:
            prompt = (
                f"Give one unusual fact about any place within 1 km of {lat},{lon}; "
                "2 sentences, max 60 words."
            )

            response = await self.client.chat.completions.create(
                model="gpt-4.1-mini",  # Using gpt-4.1-mini as specified in PRD
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.7,
            )

            fact = response.choices[0].message.content
            if not fact:
                raise ValueError("Empty response from OpenAI")

            logger.info(f"Generated fact for location {lat},{lon}")
            return fact.strip()

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
