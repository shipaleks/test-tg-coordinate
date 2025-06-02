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
            system_prompt = (
                "Ты - профессиональный экскурсовод с научной степенью по истории. "
                "Твоя специализация - рассказывать малоизвестные, но удивительные факты о местах. "
                "Ты избегаешь банальностей и общеизвестной информации, фокусируясь на деталях, "
                "которые заставят людей воскликнуть 'Невероятно, я не знал!'. "
                "Все факты должны быть исторически точными и проверяемыми."
            )

            user_prompt = (
                f"Расскажи один малоизвестный, но очень интересный факт о любом месте "
                f"в радиусе 1 км от координат {lat},{lon}. "
                "Факт должен быть: "
                "1) Неочевидным и удивительным "
                "2) Исторически достоверным "
                "3) Связан с конкретным местом, зданием или событием "
                "Ответ: 2-3 предложения, максимум 100 слов."
            )

            response = await self.client.chat.completions.create(
                model="gpt-4.1-mini",  # Using gpt-4.1-mini as specified in PRD
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=200,  # Increased for Russian text
                temperature=0.8,  # Slightly higher for more creative responses
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
