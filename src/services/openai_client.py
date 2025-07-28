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

    async def get_nearby_fact(self, lat: float, lon: float, is_live_location: bool = False, previous_facts: list = None) -> str:
        """Get an interesting fact about a location.

        Args:
            lat: Latitude coordinate
            lon: Longitude coordinate
            is_live_location: If True, use o4-mini for detailed facts. If False, use gpt-4.1 for speed.
            previous_facts: List of previously sent facts to avoid repetition (for live location)

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
                "ПРИНЦИПЫ ДОСТОВЕРНОСТИ:\n"
                "• ПРИОРИТЕТ: Стремитесь к максимальной точности и достоверности\n"
                "• НЕ ВЫДУМЫВАЙТЕ: Полагайтесь только на знания из обучения\n"
                "• ПРОВЕРЯЙТЕ: Убедитесь в правдивости каждого факта перед его изложением\n"
                "• ИЕРАРХИЯ ВЫБОРА:\n"
                "  1. Конкретные факты о ближайших достопримечательностях (в радиусе 300м)\n"
                "  2. Исторические факты о районе/квартале\n"
                "  3. Общая информация о городе или регионе\n"
                "  4. Только если ничего достоверного не знаете — честно скажите об ограниченности знаний\n\n"
                "ВАЖНО: Лучше предоставить достоверный общий факт о городе, чем выдуманный детальный. "
                "Весь ответ должен быть на русском языке."
            )

            # Handle previous facts for live location
            previous_facts_text = ""
            if is_live_location and previous_facts:
                previous_facts_text = (
                    f"\n\nРАНЕЕ РАССКАЗАННЫЕ ФАКТЫ (НЕ ПОВТОРЯЙТЕ):\n" +
                    "\n".join([f"- {fact}" for fact in previous_facts[-5:]])  # Last 5 facts
                    + "\n\nВыберите ДРУГУЮ тему или аспект этого места!\n"
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
                    f"Шаг 4: Выберите факт по иерархии достоверности:{previous_facts_text}\n"
                    "   А) Есть ли достоверные факты о конкретных зданиях/памятниках в радиусе 300м?\n"
                    "   Б) Если не нашли точных — какие достоверные факты знаете о районе?\n"
                    "   В) Если и о районе мало — какие проверенные факты о городе/регионе?\n"
                    "   Г) Если сомневаетесь в точности — лучше честно скажите об ограниченности знаний\n\n"
                    "ВАЖНО: Создайте ПОДРОБНЫЙ и РАЗВЕРНУТЫЙ факт (примерно 100-120 слов), но ТОЛЬКО из достоверных знаний. Включите:\n"
                    "- Исторический контекст и даты (только если уверены в точности)\n"
                    "- Интересные детали и подробности (только проверенные)\n"
                    "- Связи с известными личностями или событиями (только достоверные)\n"
                    "- Архитектурные особенности или культурное значение (только если точно знаете)\n\n"
                    "Финальный ответ в формате:\n"
                    "Локация: [Конкретное название места]\n"
                    "Интересный факт: [Развернутый факт с историческими подробностями, примерно 100-120 слов]"
                )
            else:
                # Concise prompt for static location (gpt-4.1)
                user_prompt = (
                    f"Проанализируйте координаты: {lat}, {lon}\n\n"
                    "Определите ближайшую достопримечательность или интересное место и предоставьте краткий факт.\n\n"
                    "ВЫБИРАЙТЕ ПО ИЕРАРХИИ ДОСТОВЕРНОСТИ:\n"
                    "1. Конкретные факты о ближайших объектах (300м)\n"
                    "2. Достоверные факты о районе\n"
                    "3. Проверенная информация о городе\n"
                    "4. Если не уверены — скажите об ограниченности знаний\n\n"
                    "ВАЖНО: Факт должен быть КРАТКИМ (60-80 слов) но ДОСТОВЕРНЫМ. Включите только:\n"
                    "- Проверенную историческую информацию\n"
                    "- Точные детали или даты (если уверены)\n"
                    "- Достоверные особенности места\n\n"
                    "Финальный ответ в формате:\n"
                    "Локация: [Конкретное название места]\n"
                    "Интересный факт: [Краткий, но достоверный факт, 60-80 слов]"
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
                        max_completion_tokens=10000,  # Large limit for o4-mini extensive reasoning + detailed response
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
