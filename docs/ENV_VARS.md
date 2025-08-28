# Переменные окружения

Проект читает переменные из окружения (Cloud Run) и из файла `.env` локально (через `python-dotenv`).

## Обязательные
- TELEGRAM_BOT_TOKEN: токен бота от @BotFather
- OPENAI_API_KEY: API ключ OpenAI
- WEBHOOK_URL: публичный URL сервиса (Cloud Run URL)
- PORT: порт прослушивания HTTP (для Cloud Run — 8080)

## Рекомендуемые (безопасность)
- TELEGRAM_WEBHOOK_SECRET_TOKEN: секрет для проверки вебхука Telegram

## Firebase (3 способа)
Логика в `src/services/firebase_client.py` поддерживает три варианта:
1) FIREBASE_CREDENTIALS_JSON: полный JSON сервис-аккаунта как строка
2) FIREBASE_CREDENTIALS_B64: base64 от содержимого JSON сервис-аккаунта
3) FIREBASE_PROJECT_ID + FIREBASE_CLIENT_EMAIL + FIREBASE_PRIVATE_KEY (c `\n` в ключе)

Рекомендуется использовать вариант 2 (B64) в сочетании с Secret Manager.

## Postgres (опционально)
- DATABASE_URL: строка подключения (например, `postgresql+asyncpg://user:pass@host:5432/dbname`)

---

# Где хранить переменные в Google Cloud Run

### Вариант A: Через Secret Manager (рекомендовано)
1. Создайте секреты (пример для macOS):
```bash
# сервис-аккаунт Firebase
base64 < firebase-key.json | tr -d '\n' | pbcopy  # B64 в буфере обмена
# затем вставьте значение при создании секрета в GCP

# OpenAI
printf "%s" "$OPENAI_API_KEY" | gcloud secrets create openai_api_key --data-file=-

# Telegram
printf "%s" "$TELEGRAM_BOT_TOKEN" | gcloud secrets create telegram_bot_token --data-file=-
```

2. Привяжите секреты к переменным окружения в Cloud Run:
- `FIREBASE_CREDENTIALS_B64` → секрет с base64 JSON сервис-аккаунта
- `OPENAI_API_KEY` → секрет `openai_api_key`
- `TELEGRAM_BOT_TOKEN` → секрет `telegram_bot_token`
- (опционально) `TELEGRAM_WEBHOOK_SECRET_TOKEN` → отдельный секрет

Можно сделать это в консоли Cloud Run → Редактировать → Переменные и секреты → «Сослаться на секрет».

3. Публичные значения (не секреты) задайте напрямую как env:
- `WEBHOOK_URL`, `PORT=8080`

### Вариант B: Прямо в переменные окружения
Можно задать все значения сразу в Cloud Run, но для ключей рекомендуется Secret Manager.

---

# Локальная разработка

1. Создайте `.env` (см. `.env.example`):
```
TELEGRAM_BOT_TOKEN=...
OPENAI_API_KEY=...
WEBHOOK_URL=  # оставьте пустым, чтобы работал polling
PORT=8080
# Firebase: выберите любой вариант из трёх ниже
FIREBASE_CREDENTIALS_B64=...
# либо
# FIREBASE_CREDENTIALS_JSON=...
# либо
# FIREBASE_PROJECT_ID=...
# FIREBASE_CLIENT_EMAIL=...
# FIREBASE_PRIVATE_KEY=-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n
# DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname
```

2. Запуск локально (polling):
```bash
python -m src.main
```

Cloud Run: см. `docs/CLOUD_RUN.md`.
