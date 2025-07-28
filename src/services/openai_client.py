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
                "Ваша задача — пошагово проанализировать координаты и предоставить интересный факт о местности.\n\n"
                "Процесс рассуждения:\n"
                "1. Сначала внимательно проанализируйте координаты и определите точное местоположение\n"
                "2. Подумайте о географических особенностях этой области\n"
                "3. Вспомните исторические события, архитектурные особенности или культурные факты\n"
                "4. Выберите наиболее интересный и достоверный факт\n"
                "5. Убедитесь, что информация точна и не выдумана\n\n"
                "Важно: полагайтесь только на достоверные знания из обучения. "
                "Если не уверены в факте — лучше скажите, что не можете предоставить достоверную информацию. "
                "Весь ответ должен быть на русском языке."
            )

            user_prompt = (
                f"Проанализируйте координаты: {lat}, {lon}\n\n"
                "Пожалуйста, следуйте процессу рассуждения:\n\n"
                "Шаг 1: Определите географическое местоположение по координатам. Что это за город, район, страна?\n\n"
                "Шаг 2: Найдите топонимы в радиусе 300 метров (улицы, здания, памятники, парки, исторические места).\n\n"
                "Шаг 3: Проанализируйте, какие интересные исторические, архитектурные или культурные факты "
                "вы знаете об этой области или ближайших достопримечательностях.\n\n"
                "Шаг 4: Выберите наиболее интересный и достоверный факт, который будет познавательным для туриста.\n\n"
                "Финальный ответ в формате:\n"
                "Локация: [Конкретное название места]\n"
                "Интересный факт: [Увлекательный и достоверный факт]"
            )

            # Try o4-mini first, fallback to gpt-4.1 if not available or empty response
            response = None
            try:
                response = await self.client.chat.completions.create(
                    model="o4-mini",  # Using o4-mini for faster and more efficient responses
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_completion_tokens=3000,  # o4-mini uses max_completion_tokens like o3
                )
                
                logger.info(f"o4-mini response: {response}")
                content = response.choices[0].message.content if response.choices else None
                
                # Check if o4-mini returned empty content and fallback if needed
                if not content:
                    logger.warning(f"o4-mini returned empty content, falling back to gpt-4.1")
                    raise ValueError("Empty content from o4-mini")
                    
            except Exception as e:
                logger.warning(f"o4-mini failed ({e}), falling back to gpt-4.1")
                response = await self.client.chat.completions.create(
                    model="gpt-4.1",  # Fallback to gpt-4.1
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=400,
                    temperature=0.7,
                )
                logger.info(f"gpt-4.1 fallback response: {response}")
                content = response.choices[0].message.content if response.choices else None

            if not content:
                logger.error(f"Empty content even after fallback: {response}")
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
