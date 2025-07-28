# NearbyFactBot v1.2.2 🗺️

Telegram-бот для получения интересных фактов о местах. Отправьте локацию — получите удивительную историю!

## ✨ Новое в v1.2.2

### 🔢 **Нумерация фактов**
- Live location факты теперь нумеруются: "🔴 Факт #1", "🔴 Факт #2" и т.д.
- Убрано неестественное "Начальный факт"
- Лучше видно прогресс во время прогулки

### 📍 Упрощенный интерфейс (v1.2.1)
- **Кнопка локации** — мгновенная отправка геопозиции
- **Подробная инструкция** — как использовать live location
- **Убрана лишняя кнопка** — Telegram сам умеет скрывать клавиатуру

### Как использовать:

**📍 Быстрая отправка:**
- Кнопка «📍 Поделиться локацией» → мгновенный факт

**🔴 Живая локация (прогулки):**
- Скрепка 📎 → Location → Share Live Location
- Выберите время → настройте интервал → получайте факты автоматически

## 🚀 Возможности

### 📍 Статическая локация
- Мгновенный интересный факт о месте
- Быстрая и качественная обработка координат с o4-mini

### 🔴 Живая локация (Live Location)
- **Настраиваемые интервалы**: 5, 10, 30, 60 минут  
- **Нумерованные факты**: видите прогресс путешествия
- **Автоматические факты** во время движения
- **Обновление координат** в реальном времени
- Идеально для туристических прогулок по городу

## 🎯 Почему живая локация?

Идеально для туристических прогулок — узнавайте о местах автоматически, не отвлекаясь от экскурсии!

**Пример использования:**
```
📎 → Location → Share Live Location (1 час)
🔴 Выбираете интервал: каждые 10 минут  
🔴 Факт #1 → 🔴 Факт #2 → 🔴 Факт #3...
🗺️ Получаете нумерованные факты во время прогулки!
```

## 🛠️ Технический стек

- **Python 3.12** + python-telegram-bot
- **OpenAI o4-mini** для генерации фактов
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

**Покрытие**: 13 тестов, включая упрощенную функциональность клавиатуры

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

### v1.2.2 (текущая)
- ✅ **Нумерация фактов** — 🔴 Факт #1, #2, #3...
- ✅ **Убрано "Начальный факт"** — более естественно
- ✅ **Счетчик в данных сессии** — fact_count в LiveLocationData

### v1.2.1
- ✅ **Упрощенный интерфейс** — убрана лишняя кнопка
- ✅ **Исправлены инструкции** — live location через скрепку
- ✅ **Краткие тексты** — меньше информационного шума

### v1.2  
- ✅ **Кнопка локации** — ReplyKeyboardMarkup
- ✅ **Информационная система** — встроенная справка

### v1.1  
- ✅ **Live Location** — автоматические факты каждые N минут
- ✅ **Настраиваемые интервалы** — 5, 10, 30, 60 минут
- ✅ **Полная русификация** — включая OpenAI промпты

### v1.0
- ✅ **MVP** — статические локации + факты o3
- ✅ **Production deployment** — Railway + webhook

## 🌟 User Experience

### Упрощенный интерфейс v1.2.1:
```
Стартовая клавиатура:
┌─────────────────────────────┐
│  📍 Поделиться локацией      │  ← кнопка request_location
├─────────────────────────────┤
│  ℹ️ Подробная инструкция    │  ← как использовать live location
└─────────────────────────────┘
```

**Результат**: фокус на главной функциональности, меньше отвлекающих элементов

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
- ✅ **Полное тестирование** — 13 unit tests
- ✅ **CI/CD Pipeline** — GitHub Actions
- ✅ **Comprehensive docs** — техническая документация
- ✅ **User-friendly UX** — простой и понятный интерфейс

**NearbyFactBot v1.2.2 — готов к использованию!** 🚀 