# План оптимизации Telegram-бота для работы с несколькими пользователями на Railway

## Краткое резюме проблемы

Telegram-бот "Экскурсобот" испытывает проблемы с производительностью при одновременном использовании несколькими пользователями:
- Бот начинает тормозить и не отвечать на команды
- Факты не присылаются вовремя
- Деплой на Railway (план Hobby)

## Анализ выявленных узких мест

### 1. **Блокирующие вызовы к OpenAI API**
- Каждый запрос к OpenAI может занимать 3-10 секунд
- Во время ожидания ответа от API другие пользователи не могут получить обработку
- Отсутствует ограничение на количество одновременных запросов

### 2. **Проблемы с архитектурой базы данных**
- Используется синхронная обёртка (`PostgresSyncWrapper`) для асинхронной базы данных
- Создаются отдельные потоки через `ThreadPoolExecutor` для каждого DB-запроса
- Это добавляет накладные расходы и может привести к исчерпанию пула потоков

### 3. **Отсутствие управления конкурентностью**
- Нет ограничения на количество одновременных сессий живой геолокации
- Каждая сессия создаёт отдельные background tasks
- При большом количестве пользователей создаётся слишком много параллельных задач

### 4. **Ограничения Railway Hobby плана**
- Ограниченные CPU и память
- Возможные лимиты на количество одновременных соединений
- Отсутствие автомасштабирования

## Детальный план оптимизации

### Фаза 1: Критические изменения (1-2 дня)

#### 1.1 Добавление семафора для ограничения одновременных запросов к OpenAI

**Проблема:** Неограниченное количество одновременных запросов к OpenAI API блокирует обработку.

**Решение:** Добавить семафор для ограничения параллельных запросов.

**Изменения в `src/services/openai_client.py`:**

```python
class OpenAIClient:
    def __init__(self):
        # ... existing code ...
        # Добавить семафор для ограничения одновременных запросов
        self._api_semaphore = asyncio.Semaphore(3)  # Максимум 3 параллельных запроса
    
    async def get_nearby_fact(self, lat: float, lon: float, **kwargs):
        async with self._api_semaphore:  # Ограничиваем доступ к API
            # ... existing implementation ...
```

**Статус:** [ ] Не выполнено

#### 1.2 Добавление очереди для обработки запросов

**Проблема:** При превышении лимита семафора запросы отклоняются.

**Решение:** Использовать очередь с приоритетами для обработки запросов.

**Новый файл `src/services/request_queue.py`:**

```python
import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable
import time

@dataclass(order=True)
class QueuedRequest:
    priority: int
    timestamp: float = field(default_factory=time.time)
    user_id: int = field(compare=False)
    callback: Callable = field(compare=False)
    args: tuple = field(compare=False)
    kwargs: dict = field(compare=False)

class RequestQueue:
    def __init__(self, max_concurrent: int = 3):
        self.queue = asyncio.PriorityQueue()
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.workers = []
        
    async def add_request(self, user_id: int, callback: Callable, 
                         *args, priority: int = 1, **kwargs):
        request = QueuedRequest(
            priority=priority,
            user_id=user_id,
            callback=callback,
            args=args,
            kwargs=kwargs
        )
        await self.queue.put(request)
    
    async def worker(self):
        while True:
            request = await self.queue.get()
            async with self.semaphore:
                try:
                    await request.callback(*request.args, **request.kwargs)
                except Exception as e:
                    logger.error(f"Error processing request for user {request.user_id}: {e}")
            self.queue.task_done()
    
    def start_workers(self, num_workers: int = 5):
        for _ in range(num_workers):
            worker = asyncio.create_task(self.worker())
            self.workers.append(worker)
```

**Статус:** [ ] Не выполнено

### Фаза 2: Оптимизация базы данных (2-3 дня)

#### 2.1 Переход на полностью асинхронные операции с БД

**Проблема:** Синхронная обёртка создаёт дополнительные потоки и накладные расходы.

**Решение:** Убрать `PostgresSyncWrapper` и использовать только асинхронные вызовы.

**Изменения:**
- Удалить `src/services/postgres_wrapper.py`
- Обновить все вызовы БД на асинхронные в handlers
- Использовать connection pooling для PostgreSQL

**Статус:** [ ] Не выполнено

#### 2.2 Добавление индексов в базу данных

**SQL миграция:**

```sql
-- Индексы для быстрого поиска
CREATE INDEX idx_donations_user_id ON donations(user_id);
CREATE INDEX idx_user_preferences_user_id ON user_preferences(user_id);
CREATE INDEX idx_donations_created_at ON donations(created_at);

-- Составной индекс для статистики
CREATE INDEX idx_donations_user_created ON donations(user_id, created_at);
```

**Статус:** [ ] Не выполнено

### Фаза 3: Оптимизация живой геолокации (2-3 дня)

#### 3.1 Ограничение количества активных сессий

**Изменения в `src/services/live_location_tracker.py`:**

```python
class LiveLocationTracker:
    def __init__(self):
        self._active_sessions: Dict[int, LiveLocationData] = {}
        self._lock = asyncio.Lock()
        # Ограничение на количество активных сессий
        self._max_sessions = 50
        self._session_semaphore = asyncio.Semaphore(10)  # Макс 10 одновременных обновлений
    
    async def start_live_location(self, user_id: int, ...):
        async with self._lock:
            if len(self._active_sessions) >= self._max_sessions:
                # Отправить сообщение о перегрузке
                await bot.send_message(
                    chat_id=chat_id,
                    text="⚠️ Сервер перегружен. Попробуйте позже."
                )
                return
```

**Статус:** [ ] Не выполнено

#### 3.2 Batch-обработка обновлений локации

**Решение:** Группировать обновления локаций и обрабатывать их пакетами.

```python
class BatchLocationProcessor:
    def __init__(self, batch_size: int = 5, batch_timeout: float = 1.0):
        self.pending_updates = []
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.lock = asyncio.Lock()
        
    async def add_update(self, update):
        async with self.lock:
            self.pending_updates.append(update)
            if len(self.pending_updates) >= self.batch_size:
                await self.process_batch()
    
    async def process_batch(self):
        # Обработать все обновления одним вызовом
        updates = self.pending_updates[:self.batch_size]
        self.pending_updates = self.pending_updates[self.batch_size:]
        
        # Параллельная обработка
        tasks = [self.process_single(u) for u in updates]
        await asyncio.gather(*tasks)
```

**Статус:** [ ] Не выполнено

### Фаза 4: Инфраструктурные улучшения (3-4 дня)

#### 4.1 Настройка Redis для кэширования

**docker-compose.yml для локальной разработки:**

```yaml
version: '3.8'
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  redis_data:
```

**Интеграция Redis в `requirements.txt`:**
```
redis>=5.0.0
```

**Новый сервис `src/services/cache.py`:**

```python
import redis.asyncio as redis
import json
from typing import Optional

class CacheService:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = redis.from_url(redis_url)
        
    async def get_fact_cache(self, lat: float, lon: float) -> Optional[str]:
        key = f"fact:{lat:.3f}:{lon:.3f}"
        value = await self.redis.get(key)
        return value.decode() if value else None
    
    async def set_fact_cache(self, lat: float, lon: float, fact: str, ttl: int = 3600):
        key = f"fact:{lat:.3f}:{lon:.3f}"
        await self.redis.set(key, fact, ex=ttl)
```

**Статус:** [ ] Не выполнено

#### 4.2 Переход на Railway Pro план или альтернативы

**Варианты:**

1. **Railway Pro план**
   - Больше CPU и памяти
   - Автомасштабирование
   - Приоритетная поддержка

2. **Альтернативные платформы:**
   - **Render.com** - автомасштабирование, встроенный Redis
   - **Fly.io** - глобальное распределение, edge computing
   - **DigitalOcean App Platform** - простое масштабирование

**Статус:** [ ] Не выполнено

### Фаза 5: Мониторинг и наблюдаемость (1-2 дня)

#### 5.1 Добавление метрик производительности

**Новый файл `src/services/metrics.py`:**

```python
import time
from dataclasses import dataclass, field
from typing import Dict
import asyncio

@dataclass
class PerformanceMetrics:
    request_count: int = 0
    error_count: int = 0
    avg_response_time: float = 0.0
    active_sessions: int = 0
    queue_size: int = 0
    
class MetricsCollector:
    def __init__(self):
        self.metrics = PerformanceMetrics()
        self.response_times = []
        self.lock = asyncio.Lock()
        
    async def record_request(self, duration: float, error: bool = False):
        async with self.lock:
            self.metrics.request_count += 1
            if error:
                self.metrics.error_count += 1
            self.response_times.append(duration)
            # Хранить только последние 100 измерений
            if len(self.response_times) > 100:
                self.response_times.pop(0)
            self.metrics.avg_response_time = sum(self.response_times) / len(self.response_times)
```

**Статус:** [ ] Не выполнено

#### 5.2 Логирование с структурированными данными

**Обновление логирования:**

```python
import structlog

logger = structlog.get_logger()

# Использование
logger.info("fact_requested", 
    user_id=user_id,
    lat=lat,
    lon=lon,
    duration=duration,
    cache_hit=cache_hit
)
```

**Статус:** [ ] Не выполнено

## Чеклист по внедрению изменений

### Критические изменения (Приоритет 1)
- [ ] Добавить семафор для ограничения запросов к OpenAI API
- [ ] Реализовать очередь запросов с приоритетами
- [ ] Добавить обработку ошибок при перегрузке

### Оптимизация БД (Приоритет 2)
- [ ] Удалить синхронную обёртку PostgresSyncWrapper
- [ ] Перейти на полностью асинхронные операции с БД
- [ ] Добавить индексы в базу данных
- [ ] Настроить connection pooling

### Оптимизация геолокации (Приоритет 3)
- [ ] Ограничить количество активных сессий
- [ ] Реализовать batch-обработку обновлений
- [ ] Добавить throttling для частых обновлений

### Инфраструктура (Приоритет 4)
- [ ] Настроить Redis для кэширования
- [ ] Оценить необходимость перехода на другой план/платформу
- [ ] Настроить автомасштабирование (если доступно)

### Мониторинг (Приоритет 5)
- [ ] Добавить сбор метрик производительности
- [ ] Настроить структурированное логирование
- [ ] Создать дашборд для мониторинга

## Ожидаемые результаты

После внедрения всех изменений:

1. **Производительность:**
   - Поддержка 50+ одновременных пользователей
   - Время отклика < 3 секунд для 95% запросов
   - Отсутствие блокировок при высокой нагрузке

2. **Надёжность:**
   - Graceful degradation при перегрузке
   - Автоматическое восстановление после сбоев
   - Защита от DDoS через rate limiting

3. **Масштабируемость:**
   - Готовность к горизонтальному масштабированию
   - Эффективное использование ресурсов
   - Возможность обработки 1000+ запросов в минуту

## Временные оценки

- **Фаза 1 (критические изменения):** 1-2 дня
- **Фаза 2 (оптимизация БД):** 2-3 дня  
- **Фаза 3 (оптимизация геолокации):** 2-3 дня
- **Фаза 4 (инфраструктура):** 3-4 дня
- **Фаза 5 (мониторинг):** 1-2 дня

**Общее время:** 9-14 дней

## Рекомендации по порядку внедрения

1. Начать с Фазы 1 - это даст немедленное улучшение
2. Параллельно можно начать Фазу 5 для сбора метрик
3. Фазы 2 и 3 можно выполнять параллельно разными разработчиками
4. Фаза 4 - после стабилизации основных изменений

## Альтернативные решения для быстрого результата

Если нужно срочное решение:

1. **Временно увеличить интервалы обновления** для живой геолокации (с 10 до 15-20 минут)
2. **Добавить простое rate limiting** на уровне хендлеров
3. **Использовать webhook вместо polling** (уже используется)
4. **Временно отключить картинки** для снижения нагрузки

## Заключение

Основная проблема бота - отсутствие механизмов управления конкурентным доступом к ресурсоемким операциям (OpenAI API, база данных). Предложенный план позволит систематически устранить узкие места и подготовить систему к масштабированию.
