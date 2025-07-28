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

    async def get_nearby_fact(self, lat: float, lon: float, is_live_location: bool = False) -> str:
        """Get an interesting fact about a location.

        Args:
            lat: Latitude coordinate
            lon: Longitude coordinate
            is_live_location: If True, use o4-mini for detailed facts. If False, use gpt-4.1 for speed.

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

            if is_live_location:
                # Detailed prompt for live location (o4-mini)
                user_prompt = (
                    f"Проанализируйте координаты: {lat}, {lon}\n\n"
                    "Пожалуйста, следуйте процессу рассуждения:\n\n"
                    "Шаг 1: Определите географическое местоположение по координатам. Что это за город, район, страна?\n\n"
                    "Шаг 2: Найдите топонимы в радиусе 300 метров (улицы, здания, памятники, парки, исторические места).\n\n"
                    "Шаг 3: Проанализируйте, какие интересные исторические, архитектурные или культурные факты "
                    "вы знаете об этой области или ближайших достопримечательностях.\n\n"
                    "Шаг 4: Выберите наиболее интересный и достоверный факт, который будет познавательным для туриста.\n\n"
                    "ВАЖНО: Создайте ПОДРОБНЫЙ и РАЗВЕРНУТЫЙ факт (примерно 100-120 слов). Включите:\n"
                    "- Исторический контекст и даты\n"
                    "- Интересные детали и подробности\n"
                    "- Связи с известными личностями или событиями\n"
                    "- Архитектурные особенности или культурное значение\n\n"
                    "Финальный ответ в формате:\n"
                    "Локация: [Конкретное название места]\n"
                    "Интересный факт: [Развернутый факт с историческими подробностями, примерно 100-120 слов]"
                )
            else:
                # Concise prompt for static location (gpt-4.1)
                user_prompt = (
                    f"Проанализируйте координаты: {lat}, {lon}\n\n"
                    "Определите ближайшую достопримечательность или интересное место в радиусе 300 метров "
                    "и предоставьте краткий, но увлекательный факт.\n\n"
                    "ВАЖНО: Факт должен быть КРАТКИМ (60-80 слов) но интересным. Включите:\n"
                    "- Основную историческую информацию\n"
                    "- Одну яркую деталь или дату\n"
                    "- Что делает это место особенным\n\n"
                    "Финальный ответ в формате:\n"
                    "Локация: [Конкретное название места]\n"
                    "Интересный факт: [Краткий, но увлекательный факт, 60-80 слов]"
                )

            # Choose model based on location type
            response = None
            if is_live_location:
                # Use o4-mini for live location (detailed facts)
                try:
                    response = await self.client.chat.completions.create(
                        model="o4-mini",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        max_completion_tokens=2000,  # Moderate limit for detailed but not too long facts
                    )
                    logger.info(f"o4-mini (live location) response: {response}")
                    content = response.choices[0].message.content if response.choices else None
                    
                    if not content:
                        logger.warning(f"o4-mini returned empty content, falling back to gpt-4.1")
                        raise ValueError("Empty content from o4-mini")
                        
                except Exception as e:
                    logger.warning(f"o4-mini failed ({e}), falling back to gpt-4.1 for live location")
                    response = await self.client.chat.completions.create(
                        model="gpt-4.1",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        max_tokens=800,
                        temperature=0.7,
                    )
                    logger.info(f"gpt-4.1 fallback for live location: {response}")
                    content = response.choices[0].message.content if response.choices else None
            else:
                # Use gpt-4.1 for static location (fast, concise facts)
                try:
                    response = await self.client.chat.completions.create(
                        model="gpt-4.1",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        max_tokens=400,  # Smaller limit for concise facts
                        temperature=0.7,
                    )
                    logger.info(f"gpt-4.1 (static location) response: {response}")
                    content = response.choices[0].message.content if response.choices else None
                    
                    if not content:
                        logger.warning(f"gpt-4.1 returned empty content for static location")
                        raise ValueError("Empty content from gpt-4.1")
                        
                except Exception as e:
                    logger.error(f"gpt-4.1 failed for static location: {e}")
                    raise

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
