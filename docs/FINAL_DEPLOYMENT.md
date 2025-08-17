# Финальный деплой NearbyFactBot v1.3 в Railway

## ✅ Исправления применены

- **Event Loop Fix**: Убран `asyncio.run()` вызывающий краш в Railway
- **Live Location v1.1**: Полностью реализован и протестирован  
- **GPT-5 + web_search**: Принудительное онлайн‑верифицирование фактов и координат

## 🚀 Шаги для деплоя

### 1. Railway Project Setup
```bash
# Уже создан проект, подключен к GitHub репозиторию
# https://github.com/shipaleks/test-tg-coordinate.git
```

### 2. Environment Variables в Railway Dashboard
```bash
TELEGRAM_BOT_TOKEN=ваш_реальный_токен_от_@BotFather
OPENAI_API_KEY=ваш_openai_api_key  
WEBHOOK_URL=https://your-app.railway.app
PORT=8000
```

### 3. Автоматический деплой
- ✅ GitHub Actions настроен
- ✅ Push в main → автоматический деплой
- ✅ Исправление уже запущено (commit 2685978)

### 4. Проверка деплоя

#### Логи должны показывать:
```
INFO - Starting NearbyFactBot...
INFO - Starting webhook on port 8000
INFO - Application started
```

#### НЕ должно быть:
```
❌ RuntimeError: This event loop is already running
❌ Starting polling mode (должен быть webhook!)
```

### 5. Тестирование функций

#### Static Location:
1. Отправить локацию → получить факт за ≤3 секунды

#### Live Location v1.1:
1. Share Live Location → подтверждение + начальный факт
2. Каждые 10 минут → новые факты
3. Stop sharing → уведомление о завершении

## 🔧 Troubleshooting

### Если краш с event loop:
- ✅ **Исправлено** в commit 2685978
- Проверить что используется webhook mode, не polling

### Если 401 Unauthorized:
- Проверить `TELEGRAM_BOT_TOKEN` в Railway dashboard
- Токен должен быть от @BotFather

### Если 403 Forbidden от OpenAI:
- Проверьте `OPENAI_API_KEY`
- Убедитесь, что ключу доступна модель GPT‑5 (reasoning) и инструмент `web_search`

### Если бот не отвечает:
- Проверьте, что `WEBHOOK_URL` правильный
- Убедитесь, что Railway приложение доступно по URL
- Проверьте логи: модель должна вызываться как `gpt-5` c `tool_choice=web_search`

## 📊 Monitoring

### Важные метрики:
- **Uptime**: >99% после исправления event loop
- **Response time**: <3 секунды для статических фактов  
- **Live sessions**: Могут работать часами без проблем

### Логи для мониторинга:
```
INFO - Started live location tracking for user X for Ys
INFO - Sent live location fact to user X
INFO - Live location expired for user X
```

## 🎉 Готово к продакшену!

```
✅ Event Loop Issues - RESOLVED
✅ Live Location v1.1 - IMPLEMENTED  
✅ GPT-5 + web_search - DEPLOYED
✅ Comprehensive Testing - COMPLETED
✅ Documentation - COMPLETE
✅ CI/CD Pipeline - ACTIVE
```

**Статус**: NearbyFactBot v1.1 готов к реальному использованию в production! 🚀 