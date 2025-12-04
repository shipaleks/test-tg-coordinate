# 🚀 Полная настройка Koyeb для Bot Voyage

## 📋 Чек-лист перед деплоем

- [ ] GitHub репозиторий подключён к Koyeb
- [ ] Telegram бот создан (@BotFather)
- [ ] OpenAI API key получен
- [ ] (Опционально) Firebase проект создан

---

## 1️⃣ Создание сервиса в Koyeb

### Шаг 1: Deploy настройки

1. **Service type**: Web Service
2. **Builder**: Dockerfile
3. **Branch**: `main`
4. **Dockerfile path**: `Dockerfile` (в корне)

### Шаг 2: Instance settings

- **Instance type**: Free (или Eco для production)
- **Regions**: Выберите ближайший к вашим пользователям
  - `fra` - Frankfurt (хорошо для Европы)
  - `was` - Washington (хорошо для США)

### Шаг 3: Port настройка

⚠️ **КРИТИЧНО:**
- **Port**: `8000`
- **Protocol**: HTTP
- Koyeb автоматически создаст публичный URL

---

## 2️⃣ Environment Variables (Переменные окружения)

### ✅ ОБЯЗАТЕЛЬНЫЕ переменные

```bash
# Telegram Bot Token (от @BotFather)
TELEGRAM_BOT_TOKEN=<your_token>

# OpenAI API Key
OPENAI_API_KEY=sk-proj-...

# Webhook URL (ВАЖНО: БЕЗ /telegram на конце!)
WEBHOOK_URL=https://your-app-name.koyeb.app

# Port (должен совпадать с EXPOSE в Dockerfile)
PORT=8000
```

⚠️ **ВАЖНО**: `WEBHOOK_URL` должен быть **БЕЗ** `/telegram` на конце!
- ✅ Правильно: `https://bot-voyage.koyeb.app`
- ❌ Неправильно: `https://bot-voyage.koyeb.app/telegram`

### 🔥 Firestore (РЕКОМЕНДУЕТСЯ для production)

```bash
# Enable Firestore database
USE_FIRESTORE_DB=true

# Google Cloud Project ID
GOOGLE_CLOUD_PROJECT=your-project-id
```

**Firebase Service Account** (выберите один из способов):

**Способ 1: JSON в переменной** (проще)
```bash
GOOGLE_APPLICATION_CREDENTIALS_JSON={
  "type": "service_account",
  "project_id": "your-project",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "firebase-adminsdk-...@your-project.iam.gserviceaccount.com",
  "client_id": "...",
  ...
}
```

**Способ 2: Путь к файлу** (сложнее на Koyeb)
```bash
# Если храните credentials.json в volume
GOOGLE_APPLICATION_CREDENTIALS=/data/firebase-credentials.json
```

### ⚡ Опциональные переменные

```bash
# Yandex Search для изображений (улучшает качество)
YANDEX_API_KEY=your_yandex_key
YANDEX_FOLDER_ID=your_folder_id

# PostgreSQL (вместо Firestore, если предпочитаете)
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# Кэшированные Telegram file_id для инструкций (ускоряет отправку)
HOWTO_STEP1_FILE_ID=AgACAgIAAxkBAAI...
HOWTO_STEP2_FILE_ID=AgACAgIAAxkBAAI...
HOWTO_STEP3_FILE_ID=AgACAgIAAxkBAAI...
```

---

## 3️⃣ Health Check настройка

### В Koyeb UI

**Service → Settings → Health Checks**:

```
✅ Enable health checks: ON

Health check settings:
- Protocol: HTTP
- Path: /health
- Port: 8000
- Initial delay: 40 seconds  ← ВАЖНО! Дать время на старт
- Interval: 30 seconds
- Timeout: 10 seconds
- Grace period: 300 seconds
- Restart limit: 3
```

⚠️ **КРИТИЧНО**: 
- **Initial delay должен быть >= 40 секунд** - приложение долго стартует
- Если меньше, Koyeb будет убивать instance до того как он запустится

### Альтернатива: HTTP Response проверка

Если health check не работает, попробуйте:
- **Path**: `/`
- **Expected response**: `200`

---

## 4️⃣ Deployment Type

### Выберите стратегию деплоя

**Рекомендуется**: Rolling Deployment
- Zero downtime
- Новая версия стартует до остановки старой
- Если новая версия падает, старая продолжает работать

**Настройки**:
- Max unavailable: 0
- Max surge: 1

---

## 5️⃣ Проверка после деплоя

### Шаг 1: Проверить логи

Откройте **Koyeb → Service → Runtime Logs**

**Должны увидеть**:
```
✅ Starting Bot Voyage...
✅ Added healthcheck endpoints: /, /health, /healthz
✅ Starting webhook on port 8000
✅ Application started successfully
```

**НЕ должно быть**:
```
❌ Instance is stopping
❌ Failed to initialize
❌ Webhook setup failed
```

### Шаг 2: Проверить healthcheck

```bash
# Замените your-app-name на ваше имя
curl https://your-app-name.koyeb.app/health

# Должен вернуть: OK
```

### Шаг 3: Проверить Telegram webhook

```bash
# Замените YOUR_BOT_TOKEN на ваш токен
curl https://api.telegram.org/botYOUR_BOT_TOKEN/getWebhookInfo
```

**Ожидаемый ответ**:
```json
{
  "ok": true,
  "result": {
    "url": "https://your-app-name.koyeb.app/telegram",
    "has_custom_certificate": false,
    "pending_update_count": 0,
    "last_error_date": 0,
    "max_connections": 40
  }
}
```

⚠️ Если `pending_update_count > 0` или `last_error_date` не равен 0:
- Проблема с webhook
- Проверьте WEBHOOK_URL и PORT

### Шаг 4: Тестировать бота

1. Откройте бота в Telegram
2. `/start` → выберите язык
3. **Подождите 10-15 минут** (убедитесь что instance не падает!)
4. Отправьте геолокацию 📍
5. ✅ Должен прийти факт с изображениями

---

## 🐛 Troubleshooting

### Проблема 1: "Build failed"

**Симптомы**:
```
#2 [internal] load metadata for docker.io/library/python:3.12-slim
[STUCK HERE]
```

**Решение**:
1. Проверьте что Dockerfile в корне репозитория
2. Убедитесь что GitHub подключён правильно
3. Попробуйте пересоздать сервис в Koyeb

### Проблема 2: "Instance is stopping"

**Симптомы**:
```
Instance is stopping.
Application is stopping.
```

**Решение**:
1. ✅ Healthcheck должен быть настроен в Koyeb UI
2. ✅ Initial delay >= 40 секунд
3. ✅ Path должен быть `/health` или `/`
4. Проверьте переменные окружения

### Проблема 3: "Webhook not set"

**Симптомы**:
```json
{
  "ok": true,
  "result": {
    "url": "",  // ← пусто!
    "pending_update_count": 0
  }
}
```

**Решение**:
```bash
# Установить webhook вручную
curl -X POST https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-app-name.koyeb.app/telegram"}'
```

### Проблема 4: "OpenAI API errors"

**Симптомы** в логах:
```
Failed to generate fact
OpenAI API error
```

**Решение**:
1. Проверьте `OPENAI_API_KEY` - правильный ли ключ
2. Проверьте баланс на OpenAI аккаунте
3. Убедитесь что у вас доступ к GPT-5.1 моделям

### Проблема 5: "Firebase not configured"

**Симптомы**:
```
firebase not configured or error
ensure_user skipped
```

**Решение** (опции):

**A) Настроить Firebase** (рекомендуется):
1. Создайте Firebase проект
2. Создайте service account
3. Добавьте JSON в `GOOGLE_APPLICATION_CREDENTIALS_JSON`
4. Установите `USE_FIRESTORE_DB=true`

**B) Использовать PostgreSQL**:
1. Создайте PostgreSQL БД в Koyeb
2. Добавьте `DATABASE_URL` в переменные
3. Удалите `USE_FIRESTORE_DB`

**C) Игнорировать** (работает, но без статистики):
- Firebase опциональный
- Бот будет работать без него
- Но не будет статистики и счётчиков

---

## 6️⃣ Оптимизация для production

### Автоматический деплой

**GitHub → Koyeb**:
1. В Koyeb включите: Auto-deploy on Git push
2. Каждый `git push` будет автоматически деплоиться
3. Rollback через Koyeb UI если что-то сломалось

### Логирование

```bash
# Уровень логов (опционально)
LOG_LEVEL=INFO

# Можно увеличить для отладки
LOG_LEVEL=DEBUG
```

### Scaling (если нужно)

Для большого количества пользователей:
- **Horizontal scaling**: несколько instances
- **Instance type**: Eco или выше
- **Regions**: Multiple для лучшей доступности

---

## 7️⃣ Мониторинг

### Внутренний мониторинг Koyeb

**Метрики** (доступны в UI):
- CPU usage
- Memory usage
- Request count
- Response time
- Error rate

### Внешний мониторинг (рекомендуется)

**UptimeRobot** (бесплатный):
1. Создайте монитор: `https://your-app-name.koyeb.app/health`
2. Interval: 5 minutes
3. Email/Telegram уведомления при падении

**Telegram webhook monitoring**:
```bash
# Скрипт для проверки webhook (запускать периодически)
curl https://api.telegram.org/botYOUR_BOT_TOKEN/getWebhookInfo
```

---

## 🔄 Migration с Railway на Koyeb

Если переезжаете с Railway:

### Различия:

| Аспект | Railway | Koyeb |
|--------|---------|-------|
| **Healthcheck** | Автоматический | Требует настройки |
| **Volumes** | Проще | Сложнее |
| **Port** | Динамический `$PORT` | Фиксированный |
| **ENV vars** | UI или railway.json | Только UI |
| **Logs** | Лучше | Базовые |

### Миграция данных:

1. **Экспортируйте БД** из Railway
2. **Импортируйте** в Koyeb PostgreSQL или Firebase
3. **Обновите** `DATABASE_URL` или настройте Firestore

---

## 📊 Recommended Setup для production

```yaml
# Koyeb Service Config (conceptual)
name: bot-voyage
type: web
instance: eco  # или free для тестирования
regions: [fra]  # Europe
autoscaling:
  min: 1
  max: 1  # Telegram webhook не поддерживает множественные instances
env:
  - TELEGRAM_BOT_TOKEN: [secret]
  - OPENAI_API_KEY: [secret]
  - WEBHOOK_URL: https://bot-voyage.koyeb.app
  - PORT: 8000
  - USE_FIRESTORE_DB: true
  - GOOGLE_CLOUD_PROJECT: your-project
  - GOOGLE_APPLICATION_CREDENTIALS_JSON: [secret]
health_check:
  path: /health
  port: 8000
  protocol: http
  initial_delay: 40
  interval: 30
  timeout: 10
```

---

## ✅ Финальный чек-лист

### Перед деплоем:
- [x] Healthcheck endpoint в коде (`src/main.py`)
- [x] Упрощённый Dockerfile
- [x] Зафиксированные версии (`requirements.txt`)
- [ ] Все ENV vars установлены в Koyeb
- [ ] Healthcheck настроен в Koyeb UI

### После деплоя:
- [ ] Логи показывают успешный старт
- [ ] `/health` возвращает `200 OK`
- [ ] Webhook установлен корректно
- [ ] Instance не падает через 15 минут
- [ ] Бот отвечает на `/start`
- [ ] Бот возвращает факты на геолокацию

### Production ready:
- [ ] Мониторинг настроен (UptimeRobot)
- [ ] Backup БД настроен
- [ ] Auto-deploy на Git push включён
- [ ] Документация обновлена

---

## 🆘 Если что-то не работает

### 1. Логи показывают ошибки?

Скопируйте **полные логи** из Koyeb и проверьте:
- Какой этап падает (build, start, runtime)?
- Какая конкретная ошибка?

### 2. Healthcheck не проходит?

```bash
# Прямая проверка
curl -v https://your-app-name.koyeb.app/health

# Должен вернуть:
< HTTP/1.1 200 OK
OK
```

Если 404 или timeout:
- Проверьте что приложение запустилось
- Проверьте логи на ошибки
- Убедитесь что порт 8000

### 3. Instance всё равно падает?

**Увеличьте initial delay**:
- Было: 40 секунд
- Попробуйте: 60 секунд

Приложению нужно время чтобы:
- Установить зависимости
- Инициализировать БД
- Настроить webhook
- Запустить HTTP сервер

### 4. Нужна помощь?

Соберите информацию:
1. Полные логи из Koyeb (Build + Runtime)
2. `getWebhookInfo` output
3. `curl` результат для `/health`
4. Список ENV переменных (без секретов!)

---

## 🎯 Ожидаемый результат

После правильной настройки:

**Логи** (первые 2 минуты):
```
Starting Bot Voyage...
PostgreSQL detected, checking for migration...
Added healthcheck endpoints: /, /health, /healthz  ← ВАЖНО!
Starting webhook on port 8000
Webhook setup completed
Application started successfully
```

**Healthcheck**:
```bash
$ curl https://your-app.koyeb.app/health
OK
```

**Uptime**:
- Instance работает стабильно 24/7
- Никаких `Instance is stopping` в логах
- Бот всегда отвечает на запросы

**Пользовательский опыт**:
- ✅ Быстрые ответы (<5 секунд)
- ✅ Качественные факты от GPT-5.1
- ✅ Изображения загружаются
- ✅ Live location работает стабильно

---

## 📚 Полезные ссылки

- [Koyeb Documentation](https://www.koyeb.com/docs)
- [Koyeb Health Checks Guide](https://www.koyeb.com/docs/deploy/health-checks)
- [Koyeb Status Page](https://status.koyeb.com/)
- [Telegram Bot API - Webhooks](https://core.telegram.org/bots/webhooks)
- [OpenAI GPT-5.1 Docs](https://platform.openai.com/docs/guides/latest-model)

---

**Создано**: 15 ноября 2025  
**Версия**: v1.3.1  
**Статус**: ✅ Готово к деплою

