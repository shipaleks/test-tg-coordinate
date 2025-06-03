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
                "Вы — профессиональный экскурсовод с глубокими знаниями различных мест по всему миру. "
                "Ваша задача — предоставить интересный и неочевидный факт о топониме в пределах 300 метров от заданной точки. "
                "Представьте, что вы физически находитесь в этом месте и обладаете обширными знаниями об этой области. "
                "Не выдумывайте и не фабрикуйте информацию. Если не можете вспомнить действительно интересный факт, "
                "просто укажите локацию и скажите, что у вас нет необычных фактов о ближайших окрестностях. "
                "Весь ваш ответ должен быть на русском языке. "
                "Помните: не ищите в интернете и не используйте внешние ресурсы. "
                "Полагайтесь только на знания, которыми вы были обучены."
            )

            user_prompt = (
                f"Координаты локации: {lat}, {lon}\n\n"
                "1. Определите любые топонимы (названные места, достопримечательности, улицы и т.д.) в пределах примерно 300 метров от этой точки. "
                "Если в пределах 300 метров нет заметных топонимов, укажите этот факт.\n"
                "2. Выберите один из определенных топонимов (или саму локацию, если поблизости нет топонимов) "
                "и вспомните интересный, неочевидный факт о нем. "
                "Этот факт должен быть чем-то малоизвестным, но правдивым и интригующим.\n\n"
                "Предоставьте ваш ответ в следующем формате:\n"
                "Локация: [Название места или ближайшего узнаваемого объекта]\n"
                "Интересный факт: [Ваш интересный факт о ближайшем топониме или самой локации]"
            )

            response = await self.client.chat.completions.create(
                model="gpt-4.1",  # Using gpt-4.1 as specified in PRD
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
