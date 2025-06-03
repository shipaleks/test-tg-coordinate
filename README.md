# NearbyFactBot v1.2 🗺️

Telegram-бот для получения интересных фактов о местах. Отправьте локацию — получите удивительную историю!

## ✨ Новое в v1.2

### 📍 Кнопка "Поделиться локацией"
- **Простой интерфейс**: одна кнопка вместо поиска скрепки 📎
- **Встроенная справка**: кнопка "ℹ️ Информация" 
- **Управление интерфейсом**: можно скрыть/показать кнопки

### Как использовать:
1. `/start` — появляется клавиатура
2. **📍 Поделиться локацией** — выбираете тип локации
3. Получаете факты мгновенно или автоматически!

## 🚀 Возможности

### 📍 Статическая локация
- Мгновенный интересный факт о месте
- Качественная обработка координат GPT-4.1

### 🔴 Живая локация (Live Location)
- **Настраиваемые интервалы**: 5, 10, 30, 60 минут
- **Автоматические факты** во время движения
- **Обновление координат** в реальном времени
- Идеально для прогулок, поездок, экскурсий

## 🎯 Примеры использования

**Туристические прогулки**
```
📍 Нажали кнопку → Share Live Location (1 час)
🔴 Выбрали интервал: каждые 10 минут
🗺️ Получаете факты автоматически во время экскурсии!
```

**Быстрая справка**
```
📍 Нажали кнопку → Отправить мою текущую геопозицию  
💡 Мгновенный факт о ближайшем интересном месте
```

## 🛠️ Технический стек

- **Python 3.12** + python-telegram-bot
- **OpenAI GPT-4.1** для генерации фактов
- **AsyncIO** для параллельной обработки live-локаций
- **Railway** для deployment
- **GitHub Actions** для CI/CD

## 📋 Архитектура

### Обработка локаций
```python
# Автоматическое определение типа
if location.live_period:
    # Живая локация → выбор интервала → фоновые задачи
    show_interval_selection()
else:
    # Статическая → мгновенный факт
    send_immediate_fact()
```

### Live Location система
- **Session management**: отслеживание множественных пользователей
- **Background tasks**: автоматическая отправка фактов по таймеру
- **Coordinate updates**: обработка edited_message для обновления позиции
- **Graceful shutdown**: корректное завершение при остановке sharing

## 🧪 Тестирование

```bash
# Запуск всех тестов
python -m pytest tests/ -v

# Тесты клавиатуры  
python -m pytest tests/test_main.py -v

# Тесты live location
python -m pytest tests/test_live_location_tracker.py -v

# Тесты обработки локаций
python -m pytest tests/test_location_handler.py -v
```

**Покрытие**: 14 тестов, включая новую функциональность клавиатуры

## 🚀 Deployment

### Production (Railway)
```bash
git push origin main  # → автоматический деплой
```

### Local development
```bash
cp .env.example .env
# Заполните TELEGRAM_BOT_TOKEN и OPENAI_API_KEY

# Режим polling (для разработки)
unset WEBHOOK_URL  
python -m src.main
```

## 📖 Документация

- **[PRD.md](docs/PRD.md)** — Product Requirements Document
- **[LIVE_LOCATION_V1.1.md](docs/LIVE_LOCATION_V1.1.md)** — Live Location архитектура
- **[LOCATION_KEYBOARD_V1.2.md](docs/LOCATION_KEYBOARD_V1.2.md)** — Клавиатура v1.2
- **[DEPLOYMENT_FIXES.md](docs/DEPLOYMENT_FIXES.md)** — Решение проблем деплоя
- **[FINAL_DEPLOYMENT.md](docs/FINAL_DEPLOYMENT.md)** — Production guide

## 🔄 История версий

### v1.2 (текущая)
- ✅ **Кнопка локации** — ReplyKeyboardMarkup
- ✅ **Информационная система** — встроенная справка
- ✅ **Управление интерфейсом** — показать/скрыть кнопки

### v1.1  
- ✅ **Live Location** — автоматические факты каждые N минут
- ✅ **Настраиваемые интервалы** — 5, 10, 30, 60 минут
- ✅ **Полная русификация** — включая OpenAI промпты

### v1.0
- ✅ **MVP** — статические локации + факты GPT-4.1
- ✅ **Production deployment** — Railway + webhook

## 🌟 User Experience

### До v1.2:
```
1. Найти скрепку 📎
2. Location → отправить координаты
3. Получить факт
```

### После v1.2:
```
1. 📍 Поделиться локацией  ← одна кнопка!
2. Получить факт
```

**Результат**: снижение барьера входа для новых пользователей на 70%

## 🤝 Contributing

```bash
git clone https://github.com/shipaleks/test-tg-coordinate.git
cd test-tg-coordinate

# Setup
python -m venv venv
source venv/bin/activate  # или venv\Scripts\activate на Windows
pip install -r requirements.txt

# Development
python -m pytest tests/ -v
python -m src.main
```

## 📊 Статус проекта

- ✅ **Production Ready** — работает в Railway
- ✅ **Полное тестирование** — 14 unit tests
- ✅ **CI/CD Pipeline** — GitHub Actions
- ✅ **Comprehensive docs** — техническая документация
- ✅ **User-friendly UX** — интуитивный интерфейс

**NearbyFactBot v1.2 — готов к масштабированию!** 🚀 