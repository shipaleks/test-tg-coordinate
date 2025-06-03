# Live Location Support (v1.1) 🔴

## Обзор

NearbyFactBot v1.1 добавляет поддержку **живой локации** (live location) с автоматической отправкой фактов каждые 10 минут во время sharing location.

## Новая функциональность

### 🔴 Live Location Tracking
- **Автоматические факты**: каждые 10 минут пока активна трансляция
- **Обновление координат**: бот отслеживает изменения позиции в реальном времени
- **Управление сессиями**: несколько пользователей могут одновременно sharing location
- **Автоматическое завершение**: сессия останавливается при окончании live_period

### 📱 Пользовательский опыт

#### Запуск Live Location:
1. 📎 → "Location" → **"Share Live Location"**
2. Выбрать продолжительность (15 мин, 1 час, 8 часов)
3. Получить подтверждение: *"🔴 Live Location Started"*
4. Получить начальный факт: *"🔴 Initial Fact"*

#### Во время трансляции:
- Факты приходят каждые 10 минут: *"🔴 Live Location Update"*
- Координаты обновляются автоматически при движении
- Можно остановить в любой момент

#### Завершение:
- Остановить sharing → *"✅ Live Location Stopped"*
- Автоматическое завершение по истечении времени

## Техническая реализация

### Архитектура

```
┌─────────────────┐    ┌────────────────────┐    ┌─────────────────┐
│  Telegram API   │───▶│  Location Handler  │───▶│ Live Tracker    │
│  (live location)│    │  (static + live)   │    │ (sessions mgmt) │
└─────────────────┘    └────────────────────┘    └─────────────────┘
                                │                          │
                                ▼                          ▼
                       ┌────────────────────┐    ┌─────────────────┐
                       │   OpenAI Client    │    │ Background Tasks│
                       │   (fact generator) │    │ (10min intervals)│
                       └────────────────────┘    └─────────────────┘
```

### Ключевые компоненты

#### 1. `LiveLocationTracker` Service
- **Хранение сессий**: `Dict[user_id, LiveLocationData]`
- **Координация задач**: Управление background tasks
- **Thread safety**: AsyncLock для concurrent access

#### 2. Location Handlers
- **`handle_location()`**: Статические + запуск live sessions
- **`handle_edited_location()`**: Обновления координат в real-time
- **`handle_stop_live_location()`**: Graceful завершение

#### 3. Background Tasks
- **`_fact_sending_loop()`**: AsyncIO task для каждой сессии
- **10-minute intervals**: `asyncio.sleep(600)`
- **Expiry detection**: Автоматическое завершение по timeout

### Управление памятью

```python
@dataclass
class LiveLocationData:
    user_id: int
    chat_id: int
    latitude: float
    longitude: float
    last_update: datetime
    live_period: int
    task: Optional[asyncio.Task] = None
```

### Session Lifecycle

1. **Start**: `start_live_location()` → создание session + task
2. **Update**: `update_live_location()` → обновление координат
3. **Monitor**: background task проверяет expiry
4. **Stop**: `stop_live_location()` → cleanup session + cancel task

## Обработка ошибок

### Сценарии ошибок:
- **OpenAI API timeout**: отправляется fallback message
- **Telegram API errors**: логируется, но сессия продолжается
- **Task cancellation**: graceful cleanup через CancelledError
- **Session expiry**: автоматическое завершение + уведомление

### Error Messages:
```
🔴 Live Location Update
😔 Упс!
Не удалось найти интересную информацию о текущем месте.
```

## Тестирование

### Unit Tests
- **test_live_location_tracker.py**: Core service логика
- **test_location_handler.py**: Integration с handlers
- **Mock strategies**: AsyncMock для OpenAI + Bot APIs
- **Session lifecycle**: Start/Update/Stop scenarios

### Тестовые сценарии:
- ✅ Single user session
- ✅ Multiple concurrent sessions
- ✅ Session expiry detection
- ✅ Coordinate updates
- ✅ Task cancellation
- ✅ Error handling

## Performance Considerations

### Масштабируемость:
- **Memory usage**: O(n) где n = active sessions
- **CPU usage**: Minimal (mostly I/O bound)
- **API limits**: 1 OpenAI call per user per 10 minutes

### Optimization:
- **Lazy initialization**: Tracker создается on-demand
- **Async processing**: Non-blocking background tasks
- **Graceful cleanup**: Proper task cancellation

## Развертывание

### Environment Variables:
```bash
TELEGRAM_BOT_TOKEN=your_bot_token
OPENAI_API_KEY=your_openai_key
WEBHOOK_URL=https://yourapp.railway.app/webhook  # for production
```

### Railway Deployment:
- **Stateless design**: Нет persistent storage
- **Memory limits**: ~50MB per 100 concurrent sessions
- **Restart resilience**: Sessions восстанавливаются after restart

## Мониторинг

### Logging:
```python
logger.info(f"Started live location tracking for user {user_id} for {live_period}s")
logger.info(f"Updated live location for user {user_id}: {lat}, {lon}")
logger.info(f"Live location expired for user {user_id}")
```

### Metrics to track:
- Active sessions count
- Facts sent per hour
- Session duration distribution
- Error rates by type

## Roadmap (v1.2)

- [ ] **Persistent sessions**: Restore after bot restart
- [ ] **Custom intervals**: User-configurable fact frequency
- [ ] **Location history**: Track movement patterns
- [ ] **Geofencing**: Facts for entering/leaving areas
- [ ] **Multiple languages**: i18n support 