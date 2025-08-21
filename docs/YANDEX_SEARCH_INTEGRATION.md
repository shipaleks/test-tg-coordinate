# Интеграция Yandex Search API для поиска изображений

## Оглавление
1. [Обзор](#обзор)
2. [Текущая система поиска изображений](#текущая-система)
3. [Почему Yandex Search API](#почему-yandex-search-api)
4. [Настройка Yandex Cloud](#настройка-yandex-cloud)
5. [Архитектура интеграции](#архитектура-интеграции)
6. [Пошаговое внедрение](#пошаговое-внедрение)
7. [Тестирование](#тестирование)
8. [Миграция](#миграция)
9. [Мониторинг и оптимизация](#мониторинг-и-оптимизация)

## Обзор

Этот документ описывает процесс перехода с текущей системы поиска изображений (Wikimedia Commons) на Yandex Search API для улучшения релевантности изображений, отправляемых пользователям вместе с фактами о местах.

### Цели интеграции
- Повысить релевантность изображений к фактам
- Использовать бесплатную квоту Yandex Cloud
- Получать 2-8 качественных изображений для каждого факта
- Сохранить асинхронную архитектуру бота

## Текущая система

### Как работает сейчас
1. **ImageSearchEngine** (`src/services/image_search.py`) использует Wikimedia Commons API
2. Несколько стратегий поиска:
   - Поиск по людям (если упоминаются в факте)
   - Поиск по зданиям и достопримечательностям
   - Извлечение изображений из источников (Wikidata)
   - Геопоиск по координатам
3. Проблемы:
   - Ограниченная база изображений
   - Часто нерелевантные результаты
   - Сложная логика фильтрации

### Точки интеграции
- `OpenAIClient.get_wikipedia_images()` - основной метод получения изображений
- `send_fact_with_images()` в `location.py` - отправка фактов с изображениями
- `send_live_fact_with_images()` в `live_location_tracker.py` - для живой локации

## Почему Yandex Search API

### Преимущества
1. **Более широкая база изображений** - не ограничена Wikimedia
2. **Лучшая релевантность** - использует поисковые алгоритмы Яндекса
3. **Поддержка русского языка** - лучше понимает русскоязычные запросы
4. **Бесплатная квота** - доступна в рамках Yandex Cloud
5. **Гибкие параметры поиска** - регион, фильтры, количество результатов

### Ограничения
- Требует настройки Yandex Cloud
- Лимиты на количество запросов
- Необходимость фильтрации результатов

## Настройка Yandex Cloud

### Шаг 1: Регистрация и создание проекта

1. Перейдите на [console.cloud.yandex.ru](https://console.cloud.yandex.ru/)
2. Зарегистрируйтесь или войдите с Яндекс ID
3. Создайте новое облако:
   ```
   Название: ExcursoBot Cloud
   Описание: Облако для телеграм-бота экскурсий
   ```
4. Внутри облака создайте каталог:
   ```
   Название: production
   Описание: Продакшн окружение бота
   ```

### Шаг 2: Настройка платежного аккаунта

1. В консоли перейдите в "Биллинг"
2. Создайте платежный аккаунт (если нет)
3. Убедитесь, что статус `ACTIVE` или `TRIAL_ACTIVE`
4. Проверьте доступную бесплатную квоту

### Шаг 3: Создание сервисного аккаунта

1. В консоли выберите ваш каталог
2. Перейдите в "Сервисные аккаунты" (IAM → Сервисные аккаунты)
3. Нажмите "Создать сервисный аккаунт":
   ```
   Имя: excursobot-search-api
   Описание: Сервисный аккаунт для поиска изображений
   ```
4. После создания назначьте роль:
   - Нажмите на созданный аккаунт
   - Вкладка "Роли" → "Назначить роль"
   - Выберите роль: `search-api.executor`

### Шаг 4: Создание API ключа

1. В настройках сервисного аккаунта перейдите в "Ключи"
2. Нажмите "Создать новый ключ" → "Создать API-ключ"
3. Параметры ключа:
   ```
   Описание: Production API key for image search
   Область действия: yc.search-api.execute
   ```
4. **ВАЖНО**: Скопируйте и сохраните ключ! Он показывается только один раз
5. Формат ключа: `AQVNxxxxxx...` (начинается с AQV)

### Шаг 5: Получение Folder ID

1. В консоли выберите ваш каталог
2. Скопируйте Folder ID (формат: `b1gxxxxxx`)
3. Сохраните для использования в запросах

## Архитектура интеграции

### Новый модуль: YandexImageSearch

Создадим новый сервис, который будет работать параллельно с существующим:

```python
# src/services/yandex_image_search.py
import aiohttp
import asyncio
import logging
import json
from typing import List, Tuple, Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)

class YandexImageSearch:
    """Yandex Search API client for image search."""
    
    def __init__(self, api_key: str, folder_id: str):
        self.api_key = api_key
        self.folder_id = folder_id
        self.base_url = "https://searchapi.api.cloud.yandex.net/v2/image/search"
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    async def search_images(
        self,
        query: str,
        max_images: int = 8,
        region: Optional[int] = None
    ) -> List[str]:
        """
        Search images using Yandex Search API.
        
        Args:
            query: Search query
            max_images: Maximum number of images to return (1-20)
            region: Region ID (213 for Moscow, etc.)
            
        Returns:
            List of image URLs
        """
        # Implementation details below
```

### Интеграция с существующим кодом

Модифицируем `OpenAIClient.get_wikipedia_images()` для использования Yandex API как основного источника:

```python
async def get_wikipedia_images(self, search_keywords: str, max_images: int = 5, **kwargs):
    """Enhanced image search with Yandex as primary source."""
    
    # Try Yandex Search first
    if os.getenv("YANDEX_API_KEY") and os.getenv("YANDEX_FOLDER_ID"):
        try:
            from .yandex_image_search import YandexImageSearch
            async with YandexImageSearch(
                api_key=os.getenv("YANDEX_API_KEY"),
                folder_id=os.getenv("YANDEX_FOLDER_ID")
            ) as yandex:
                images = await yandex.search_images(
                    query=search_keywords,
                    max_images=max_images
                )
                if images:
                    return images
        except Exception as e:
            logger.warning(f"Yandex search failed: {e}")
    
    # Fallback to existing Wikimedia search
    # ... existing code ...
```

## Пошаговое внедрение

### TODO: Настройка окружения

- [ ] Зарегистрироваться в Yandex Cloud
- [ ] Создать облако и каталог
- [ ] Настроить платежный аккаунт
- [ ] Создать сервисный аккаунт с ролью `search-api.executor`
- [ ] Сгенерировать API ключ
- [ ] Сохранить Folder ID

### TODO: Разработка

- [ ] Создать файл `src/services/yandex_image_search.py`
- [ ] Реализовать класс `YandexImageSearch` с методами:
  - [ ] `search_images()` - основной метод поиска
  - [ ] `_build_query()` - формирование оптимального запроса
  - [ ] `_filter_results()` - фильтрация результатов
  - [ ] `_parse_response()` - парсинг ответа API
- [ ] Добавить обработку ошибок и retry логику
- [ ] Реализовать кеширование результатов

### TODO: Интеграция

- [ ] Добавить переменные окружения:
  ```
  YANDEX_API_KEY=AQVNxxxxxx...
  YANDEX_FOLDER_ID=b1gxxxxxx
  YANDEX_SEARCH_REGION=213  # Optional: Moscow by default
  ```
- [ ] Модифицировать `OpenAIClient.get_wikipedia_images()`
- [ ] Добавить логирование для отладки
- [ ] Реализовать fallback на Wikimedia при ошибках

### TODO: Оптимизация запросов

- [ ] Анализировать факты для извлечения ключевых слов
- [ ] Формировать запросы с учетом:
  - [ ] Названия места
  - [ ] Типа объекта (музей, памятник, здание)
  - [ ] Исторического периода
  - [ ] Упомянутых персон
- [ ] Добавлять контекст местоположения в запрос

### TODO: Фильтрация результатов

- [ ] Исключать нерелевантные изображения:
  - [ ] Логотипы и иконки
  - [ ] Схемы и карты (если не запрошены)
  - [ ] Низкокачественные изображения
  - [ ] Дубликаты
- [ ] Приоритизировать:
  - [ ] Фотографии высокого качества
  - [ ] Актуальные изображения
  - [ ] Изображения с правильным соотношением сторон

## Детальная реализация

### 1. Полная реализация YandexImageSearch

```python
# src/services/yandex_image_search.py
import aiohttp
import asyncio
import logging
import json
import os
from typing import List, Tuple, Optional, Dict
from urllib.parse import quote
import hashlib
import time

logger = logging.getLogger(__name__)

class YandexImageSearch:
    """Yandex Search API v2 client for image search."""
    
    def __init__(self, api_key: str, folder_id: str):
        self.api_key = api_key
        self.folder_id = folder_id
        self.base_url = "https://searchapi.api.cloud.yandex.net/v2/image/search"
        self.session = None
        self._cache = {}  # Simple in-memory cache
        self._cache_ttl = 3600  # 1 hour
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    def _get_cache_key(self, query: str, region: Optional[int]) -> str:
        """Generate cache key for query."""
        key_data = f"{query}:{region}"
        return hashlib.md5(key_data.encode()).hexdigest()
        
    def _is_cache_valid(self, cache_entry: Dict) -> bool:
        """Check if cache entry is still valid."""
        return time.time() - cache_entry['timestamp'] < self._cache_ttl
        
    async def search_images(
        self,
        query: str,
        max_images: int = 8,
        region: Optional[int] = None,
        safe_search: bool = True
    ) -> List[str]:
        """
        Search images using Yandex Search API v2.
        
        Args:
            query: Search query in any language
            max_images: Maximum number of images (1-20)
            region: Region ID (213=Moscow, 2=SPb, 225=Russia)
            safe_search: Enable safe search filter
            
        Returns:
            List of image URLs
        """
        # Check cache first
        cache_key = self._get_cache_key(query, region)
        if cache_key in self._cache:
            cache_entry = self._cache[cache_key]
            if self._is_cache_valid(cache_entry):
                logger.debug(f"Returning cached results for: {query}")
                return cache_entry['images'][:max_images]
        
        # Prepare request
        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "folderId": self.folder_id,
            "query": {
                "text": query,
                "type": "IMAGE",
                "familyMode": "MODERATE" if safe_search else "NONE",
                "page": 0
            }
        }
        
        if region:
            payload["query"]["region"] = region
            
        try:
            # Make API request
            async with self.session.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                response.raise_for_status()
                data = await response.json()
                
            # Parse response
            images = self._parse_response(data, max_images)
            
            # Cache results
            self._cache[cache_key] = {
                'images': images,
                'timestamp': time.time()
            }
            
            # Clean old cache entries
            self._cleanup_cache()
            
            logger.info(f"Yandex search found {len(images)} images for: {query}")
            return images
            
        except aiohttp.ClientError as e:
            logger.error(f"Yandex API request failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in Yandex search: {e}")
            raise
            
    def _parse_response(self, data: Dict, max_images: int) -> List[str]:
        """Parse API response and extract image URLs."""
        images = []
        
        items = data.get('items', [])
        for item in items[:max_images * 2]:  # Get more for filtering
            if item.get('type') != 'IMAGE':
                continue
                
            # Get image URL
            image_url = item.get('url')
            if not image_url:
                continue
                
            # Basic quality filters
            if self._is_quality_image(item):
                images.append(image_url)
                
            if len(images) >= max_images:
                break
                
        return images
        
    def _is_quality_image(self, item: Dict) -> bool:
        """Filter out low quality or irrelevant images."""
        # Get image metadata if available
        snippet = item.get('snippet', {})
        title = snippet.get('title', '').lower()
        
        # Skip logos, icons, etc.
        skip_keywords = [
            'logo', 'icon', 'логотип', 'иконка',
            'схема', 'карта', 'map', 'diagram',
            'banner', 'баннер'
        ]
        
        for keyword in skip_keywords:
            if keyword in title:
                return False
                
        # Check image dimensions if available
        image_data = item.get('image', {})
        width = image_data.get('width', 0)
        height = image_data.get('height', 0)
        
        # Skip very small images
        if width > 0 and height > 0:
            if width < 400 or height < 300:
                return False
                
        return True
        
    def _cleanup_cache(self):
        """Remove expired cache entries."""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self._cache.items()
            if current_time - entry['timestamp'] > self._cache_ttl
        ]
        for key in expired_keys:
            del self._cache[key]
            
    async def build_optimized_query(
        self,
        fact_text: str,
        place_name: str,
        place_type: Optional[str] = None
    ) -> str:
        """
        Build optimized search query from fact components.
        
        Args:
            fact_text: Full fact text
            place_name: Name of the place
            place_type: Type of place (museum, monument, etc.)
            
        Returns:
            Optimized search query
        """
        # Start with place name
        query_parts = [place_name]
        
        # Add place type if known
        if place_type:
            # Translate common types to Russian for better results
            type_translations = {
                'museum': 'музей',
                'monument': 'памятник',
                'church': 'церковь храм',
                'park': 'парк',
                'theater': 'театр',
                'bridge': 'мост',
                'station': 'вокзал',
                'palace': 'дворец'
            }
            translated_type = type_translations.get(place_type.lower(), place_type)
            query_parts.append(translated_type)
            
        # Extract year or period from fact
        import re
        year_match = re.search(r'\b(1\d{3}|20\d{2})\b', fact_text)
        if year_match:
            query_parts.append(year_match.group(1))
            
        # Build final query
        query = ' '.join(query_parts)
        
        # Limit query length
        if len(query) > 100:
            query = query[:100].rsplit(' ', 1)[0]
            
        return query
```

### 2. Модификация OpenAIClient

```python
# Добавить в src/services/openai_client.py

async def get_wikipedia_images(self, search_keywords: str, max_images: int = 5, 
                              lat: float | None = None, lon: float | None = None, 
                              place_hint: str | None = None, sources: list[tuple[str, str]] | None = None, 
                              fact_text: str | None = None) -> list[str]:
    """Get images using Yandex Search API with Wikimedia fallback."""
    
    # Try Yandex Search API first
    yandex_api_key = os.getenv("YANDEX_API_KEY")
    yandex_folder_id = os.getenv("YANDEX_FOLDER_ID")
    
    if yandex_api_key and yandex_folder_id:
        try:
            from .yandex_image_search import YandexImageSearch
            
            async with YandexImageSearch(yandex_api_key, yandex_folder_id) as yandex:
                # Build optimized query
                query = search_keywords
                if place_hint and fact_text:
                    query = await yandex.build_optimized_query(
                        fact_text=fact_text,
                        place_name=place_hint
                    )
                
                # Determine region based on coordinates
                region = None
                if lat and lon:
                    # Simple region detection (can be enhanced)
                    if 55.5 < lat < 56 and 37.3 < lon < 37.9:
                        region = 213  # Moscow
                    elif 59.8 < lat < 60.2 and 30.1 < lon < 30.5:
                        region = 2  # St. Petersburg
                    else:
                        region = 225  # Russia (general)
                
                # Search images
                images = await yandex.search_images(
                    query=query,
                    max_images=max_images,
                    region=region
                )
                
                if images:
                    logger.info(f"Yandex search returned {len(images)} images")
                    return images
                    
        except Exception as e:
            logger.warning(f"Yandex search failed, falling back to Wikimedia: {e}")
    
    # Fallback to existing Wikimedia search
    if (place_hint or fact_text) and lat is not None and lon is not None:
        from .image_search import ImageSearchEngine
        
        try:
            async with ImageSearchEngine() as engine:
                fact_content = fact_text or search_keywords
                place_name = place_hint or search_keywords
                coordinates = (lat, lon)
                sources_list = sources or []
                
                images = await engine.search_images(
                    fact_text=fact_content,
                    place_name=place_name,
                    coordinates=coordinates,
                    sources=sources_list,
                    max_images=max_images
                )
                
                if images:
                    logger.info(f"Wikimedia search found {len(images)} images")
                    return images
                    
        except Exception as e:
            logger.warning(f"Wikimedia search also failed: {e}")
    
    # Final fallback - empty list
    return []
```

### 3. Переменные окружения

Добавить в `.env`:

```bash
# Yandex Search API
YANDEX_API_KEY=AQVNxxxxxx...  # Ваш API ключ
YANDEX_FOLDER_ID=b1gxxxxxx    # ID вашего каталога
YANDEX_SEARCH_REGION=213       # Опционально: регион по умолчанию (213=Москва)
```

## Тестирование

### 1. Unit тесты для YandexImageSearch

```python
# tests/test_yandex_image_search.py
import pytest
import asyncio
from unittest.mock import Mock, patch
from src.services.yandex_image_search import YandexImageSearch

@pytest.mark.asyncio
async def test_search_images_success():
    """Test successful image search."""
    api_key = "test_key"
    folder_id = "test_folder"
    
    async with YandexImageSearch(api_key, folder_id) as yandex:
        with patch.object(yandex.session, 'post') as mock_post:
            # Mock response
            mock_response = Mock()
            mock_response.status = 200
            mock_response.json = asyncio.coroutine(lambda: {
                'items': [
                    {
                        'type': 'IMAGE',
                        'url': 'https://example.com/image1.jpg',
                        'image': {'width': 800, 'height': 600}
                    },
                    {
                        'type': 'IMAGE',
                        'url': 'https://example.com/image2.jpg',
                        'image': {'width': 1024, 'height': 768}
                    }
                ]
            })
            mock_post.return_value.__aenter__.return_value = mock_response
            
            # Test search
            images = await yandex.search_images("Красная площадь", max_images=2)
            
            assert len(images) == 2
            assert all(url.startswith('https://') for url in images)

@pytest.mark.asyncio
async def test_query_optimization():
    """Test query building optimization."""
    async with YandexImageSearch("key", "folder") as yandex:
        query = await yandex.build_optimized_query(
            fact_text="Эрмитаж был основан в 1764 году Екатериной II",
            place_name="Эрмитаж",
            place_type="museum"
        )
        
        assert "Эрмитаж" in query
        assert "музей" in query
        assert "1764" in query
```

### 2. Интеграционные тесты

```python
# tests/test_image_search_integration.py
import pytest
import os
from src.services.openai_client import OpenAIClient

@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("YANDEX_API_KEY"),
    reason="Yandex API key not configured"
)
async def test_real_yandex_search():
    """Test real Yandex API integration."""
    client = OpenAIClient()
    
    images = await client.get_wikipedia_images(
        search_keywords="Кремль Москва",
        max_images=3,
        lat=55.752,
        lon=37.617,
        place_hint="Московский Кремль"
    )
    
    assert len(images) > 0
    assert all(url.startswith('http') for url in images)
```

### 3. Тестовый скрипт

```python
# test_yandex_manual.py
import asyncio
import os
from dotenv import load_dotenv
from src.services.yandex_image_search import YandexImageSearch

async def test_search():
    load_dotenv()
    
    api_key = os.getenv("YANDEX_API_KEY")
    folder_id = os.getenv("YANDEX_FOLDER_ID")
    
    if not api_key or not folder_id:
        print("Error: Yandex credentials not found in .env")
        return
        
    test_queries = [
        "Эрмитаж Санкт-Петербург",
        "Красная площадь Москва",
        "Петергоф фонтаны",
        "Большой театр"
    ]
    
    async with YandexImageSearch(api_key, folder_id) as yandex:
        for query in test_queries:
            print(f"\nSearching for: {query}")
            try:
                images = await yandex.search_images(query, max_images=3)
                print(f"Found {len(images)} images:")
                for i, url in enumerate(images, 1):
                    print(f"  {i}. {url}")
            except Exception as e:
                print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_search())
```

## Миграция

### Поэтапный переход

1. **Фаза 1: Параллельная работа**
   - Yandex API как основной источник
   - Wikimedia как fallback
   - Логирование для сравнения качества

2. **Фаза 2: A/B тестирование**
   - 50% пользователей - Yandex
   - 50% пользователей - Wikimedia
   - Сбор метрик и обратной связи

3. **Фаза 3: Полный переход**
   - Yandex для всех пользователей
   - Wikimedia только как аварийный fallback

### Откат

В случае проблем достаточно удалить переменные окружения:
```bash
unset YANDEX_API_KEY
unset YANDEX_FOLDER_ID
```

## Мониторинг и оптимизация

### Метрики для отслеживания

1. **Производительность**
   - Время ответа API
   - Процент успешных запросов
   - Количество fallback на Wikimedia

2. **Качество**
   - Количество найденных изображений
   - Релевантность (можно добавить обратную связь)

3. **Использование квоты**
   - Количество запросов в день
   - Оставшаяся квота

### Логирование

```python
# Добавить в yandex_image_search.py
class YandexSearchMetrics:
    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.total_images_found = 0
        self.response_times = []
        
    def log_request(self, success: bool, images_count: int, response_time: float):
        self.total_requests += 1
        if success:
            self.successful_requests += 1
            self.total_images_found += images_count
        else:
            self.failed_requests += 1
        self.response_times.append(response_time)
        
    def get_stats(self):
        avg_response_time = sum(self.response_times) / len(self.response_times) if self.response_times else 0
        return {
            'total_requests': self.total_requests,
            'success_rate': self.successful_requests / self.total_requests if self.total_requests else 0,
            'avg_images_per_request': self.total_images_found / self.successful_requests if self.successful_requests else 0,
            'avg_response_time': avg_response_time
        }
```

### Оптимизация запросов

1. **Кеширование**
   - Кеш популярных мест
   - TTL 1-24 часа в зависимости от места

2. **Батчинг**
   - Группировка запросов для похожих мест
   - Переиспользование результатов

3. **Умные запросы**
   - Анализ факта для извлечения ключевых слов
   - Использование синонимов и вариаций

## Дополнительные возможности

### 1. Расширенная фильтрация

```python
def advanced_filter(self, item: Dict, fact_context: Dict) -> bool:
    """Advanced filtering based on fact context."""
    # Check time period relevance
    if 'historical_period' in fact_context:
        # Filter modern photos for historical facts
        pass
        
    # Check image source credibility
    source_domain = self._extract_domain(item.get('url', ''))
    trusted_sources = ['wikipedia.org', 'museum.ru', ...]
    
    # Prefer images from trusted sources
    if source_domain in trusted_sources:
        return True
```

### 2. Многоязычные запросы

```python
async def multilingual_search(self, place_name: str, languages: List[str]) -> List[str]:
    """Search in multiple languages and merge results."""
    all_images = []
    
    for lang in languages:
        translated_query = await self.translate_query(place_name, lang)
        images = await self.search_images(translated_query)
        all_images.extend(images)
        
    # Remove duplicates and return
    return list(dict.fromkeys(all_images))
```

### 3. Контекстный поиск

```python
def build_contextual_query(self, fact_data: Dict) -> str:
    """Build query with rich context."""
    components = []
    
    # Main subject
    components.append(fact_data['place_name'])
    
    # Time context
    if 'year' in fact_data:
        components.append(f"{fact_data['year']} год")
        
    # Event context
    if 'event' in fact_data:
        components.append(fact_data['event'])
        
    # Architectural style
    if 'style' in fact_data:
        components.append(f"стиль {fact_data['style']}")
        
    return ' '.join(components)
```

## Заключение

Интеграция Yandex Search API позволит значительно улучшить качество изображений, отправляемых пользователям. Ключевые преимущества:

1. **Более релевантные изображения** благодаря продвинутым алгоритмам Яндекса
2. **Поддержка русского языка** на уровне поисковой системы
3. **Бесплатная квота** в рамках Yandex Cloud
4. **Гибкая настройка** поиска с учетом региона и контекста

При правильной реализации пользователи получат визуально привлекательные и релевантные изображения для каждого факта о местах.
