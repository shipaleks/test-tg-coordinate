# Исправления для деплоя в Railway

## Проблема: Event Loop уже запущен

### Симптомы:
```
RuntimeError: This event loop is already running
```

### Причина:
Railway запускает контейнеры в среде где уже активен event loop. Использование `asyncio.run(main())` приводит к конфликту.

### Решение:
Убрать `asyncio.run()` и использовать синхронные методы `python-telegram-bot`:

#### ❌ Было (вызывает краш):
```python
async def main() -> None:
    application = create_application()
    
    if webhook_url:
        await application.run_webhook(...)
    else:
        await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())  # ← Проблема!
```

#### ✅ Стало (работает в Railway):
```python
def main() -> None:  # Синхронная функция
    # Create application
    application = Application.builder().token(bot_token).build()
    
    # Add handlers...
    
    if webhook_url:
        application.run_webhook(...)  # Синхронный вызов
    else:
        application.run_polling()    # Синхронный вызов

if __name__ == "__main__":
    main()  # Прямой вызов
```

### Объяснение:
- `application.run_webhook()` и `application.run_polling()` сами управляют event loop
- В контейнерной среде это работает корректно
- `asyncio.run()` создает новый event loop, что конфликтует с существующим

## Проверка режима в Railway

### Убедиться что используется webhook:
1. Установить переменную `WEBHOOK_URL` в Railway dashboard
2. Проверить логи: должно быть `"Starting webhook on port 8000"`
3. НЕ должно быть `"Starting polling mode"`

### Переменные окружения для Railway:
```bash
TELEGRAM_BOT_TOKEN=your_bot_token
OPENAI_API_KEY=your_openai_key  
WEBHOOK_URL=https://your-app.railway.app
PORT=8000  # Railway автоматически назначает порт
```

## Статус:
✅ **Исправлено в commit [1e147ba]**
✅ **Готово к продакшн деплою** 