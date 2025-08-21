## Firebase: хранение пользователей, счётчиков и истории перемещений

Цель: добавить простую базу для трёх задач:
- Уникальные пользователи (по Telegram `user_id`)
- Счётчик фактов: сколько фактов получил конкретный пользователь и сколько фактов отправлено всего
- История перемещений (координаты + время), в первую очередь для «живых» локаций

Ниже — пошаговая настройка Firebase и план внедрения в код без выполнения самих правок.

### 1) Выбор технологии Firebase
- Рекомендуется использовать Firestore (в Native mode), а не Realtime Database:
  - **Причины**: атомарные инкременты (`FieldValue.increment`), простые транзакции, TTL-политики, хорошие индексы «из коробки»
  - Регион выберите ближе к основным пользователям (например, `europe-west1`), чтобы снизить задержки и соблюдать локальные требования к данным

### 2) Создание проекта и включение Firestore
1. Создайте проект на `https://console.firebase.google.com` (или выберите существующий)
2. Перейдите в Firestore → Create database → режим Native → укажите регион (например, `europe-west1`)
3. Правила доступа (Rules) временно можно оставить «закрытыми». Так как бот — серверное приложение, оно будет писать через Admin SDK, который по умолчанию обходит правила. Для порядка всё равно зададим максимально строгие правила (см. раздел «Безопасность»)

### 3) Сервисный аккаунт и секреты
1. В Google Cloud Console откройте IAM & Admin → Service Accounts
2. Создайте сервисный аккаунт (роль: `Cloud Datastore User` или `Firebase Admin`/`Owner` для простоты на старте)
3. Сгенерируйте JSON‑ключ
4. Передавайте ключ боту через переменные окружения (в Railway или локально), без хранения файла в репозитории. Есть три удобных варианта:

Вариант A (base64, надёжно для многострочных ключей):
```bash
# локально
cat firebase-key.json | base64 | pbcopy
# в Railway добавьте переменную: FIREBASE_CREDENTIALS_B64 = <вставьте base64>
```

Вариант B (целиком JSON в одну переменную — проще, если UI поддерживает многострочные значения):
- Создайте переменную `FIREBASE_CREDENTIALS_JSON` и вставьте СОДЕРЖИМОЕ JSON‑файла целиком (со всеми кавычками и `\n` внутри `private_key`).

Вариант C (разложить на поля — если не хочется держать один большой секрет):
- `FIREBASE_PROJECT_ID`, `FIREBASE_CLIENT_EMAIL`, `FIREBASE_PRIVATE_KEY` (важно экранировать переводы строк в `private_key` как `\n`).

Пример инициализации в Python, поддерживающий все три варианта:
```python
import os, json, base64
import firebase_admin
from firebase_admin import credentials
from google.cloud import firestore

_firestore = None

def get_firestore():
    global _firestore
    if _firestore is not None:
        return _firestore

    json_raw = os.getenv("FIREBASE_CREDENTIALS_JSON")
    b64 = os.getenv("FIREBASE_CREDENTIALS_B64")

    if json_raw:
        info = json.loads(json_raw)
        cred = credentials.Certificate(info)
    elif b64:
        info = json.loads(base64.b64decode(b64).decode("utf-8"))
        cred = credentials.Certificate(info)
    else:
        project_id = os.getenv("FIREBASE_PROJECT_ID")
        client_email = os.getenv("FIREBASE_CLIENT_EMAIL")
        private_key = os.getenv("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n")
        if not (project_id and client_email and private_key):
            raise RuntimeError("No Firebase credentials provided")
        info = {
            "type": "service_account",
            "project_id": project_id,
            "client_email": client_email,
            "private_key": private_key,
        }
        cred = credentials.Certificate(info)

    firebase_admin.initialize_app(cred)
    _firestore = firestore.Client()
    return _firestore
```

### 4) Зависимость в Python
- Добавьте в зависимости (позже в коде): `firebase-admin` (например, `firebase-admin==6.*`). Установка: `pip install firebase-admin`

### 5) Модель данных в Firestore

Коллекции и документы:
- `users/{user_id}` — профиль пользователя
  - `username`: string | null
  - `first_name`: string | null
  - `facts_count`: number (сколько фактов получил пользователь)
  - `created_at`: timestamp (серверное время при первом появлении)
  - `last_seen_at`: timestamp (последнее событие)

- `users/{user_id}/movements/{auto_id}` — перемещения пользователя (субколлекция)
  - `ts`: timestamp (время получения координат)
  - `lat`: number
  - `lon`: number
  - `session_id`: string (идентификатор сессии «живой» локации; можно брать из существующей логики или генерировать на старте)

- `metrics/counters` — агрегированные счётчики (1 документ)
  - `total_users`: number (уникальные пользователи)
  - `total_facts`: number (всего отправленных фактов всем)

Замечания по схеме:
- Для `total_users` инкремент выполняется только при создании нового документа `users/{user_id}` (см. раздел «Транзакции»)
- Историю перемещений лучше хранить в саб‑коллекции у пользователя — это упростит запросы «по одному пользователю» и снизит стоимость индексов
- При большом объёме данных включите TTL‑политику на документы `movements` (например, хранить 90 дней). В Firestore можно включить TTL по полю (например, `expires_at`) в настройках базы

### 6) Индексы
- Базовые индексы создаются автоматически
- При необходимости исторических выборок можно сделать композитный индекс по `ts` (обычно не требуется для простых запросов «последние N точек»). Индекс‑assistant в консоли подскажет нужные индексы, если запрос потребует их

### 7) Безопасность (Firestore Rules)
Так как бот пишет через Admin SDK, правила будут «обходиться» сервером. Тем не менее, лучше закрыть публичный доступ:

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      allow read, write: if false; // всё запрещено для клиентов
    }
  }
}
```

Таким образом, любые прямые клиентские чтения/записи будут запрещены.

### 8) План интеграции в код (высокоуровневый)

Создать сервис и точки интеграции, не меняя остальной код архитектурно:

1) Инициализация клиента
- `src/services/firebase_client.py` (новый файл):
  - Функция `init_firebase_from_env()` — инициализирует Admin SDK либо из `FIREBASE_CREDENTIALS_B64`, либо из набора `FIREBASE_PROJECT_ID/FIREBASE_CLIENT_EMAIL/FIREBASE_PRIVATE_KEY`
  - Ленивый синглтон `get_firestore()` возвращает инстанс Firestore

2) Низкоуровневые операции (новый модуль `src/services/firebase_stats.py`):
- `ensure_user(user_id, username, first_name)`
  - Транзакция: если `users/{user_id}` не существует → создать с `facts_count=0`, выставить `created_at`, `last_seen_at`, и атомарно `metrics/counters.total_users += 1`
  - Если существует → только обновить `last_seen_at`
- `increment_fact_counters(user_id, delta=1)`
  - Атомарный инкремент `users/{user_id}.facts_count += delta` и `metrics/counters.total_facts += delta`
- `record_movement(user_id, lat, lon, ts, session_id)`
  - Добавить документ в `users/{user_id}/movements`
  - Опционально: фильтр-дедупликация — писать точку, если прошло ≥15–30 сек или смещение > 10–20 м
- `get_stats_for_user(user_id)` → вернуть `facts_count` пользователя
- `get_global_stats()` → вернуть `total_users`, `total_facts`

3) Точки встраивания в существующий код:
- При `/start` (`start_command`): вызывать `ensure_user(...)`
- При каждом входящем событии с координатами:
  - В `handlers/location.py` (статическая локация) и в `LiveLocationTracker._fact_sending_loop` (живые обновления) сразу после успешной отправки факта → `increment_fact_counters(user_id)`
  - При обработке «живой» геолокации (каждое обновление координат) → `record_movement(...)` c семплированием (не спамить Firestore каждую секунду)
- Команда `/stat` (только для тестов):
  - Ответить: «твой `facts_count`», «общие `total_facts`», «`total_users`». Брать значения из `users/{user_id}` и `metrics/counters`

4) Семплирование перемещений
- Рекомендация: писать одну точку не чаще 1 раза в 20–30 секунд и/или при изменении координаты больше чем на 10–20 метров
- Это снизит стоимость и объём хранения без потери смысла «маршрута»

5) Отказоустойчивость
- Все операции делать «неблокирующими» для UX бота: ошибки Firestore логировать и пропускать, без падения основного потока фактов
- Для инкрементов использовать транзакции/батчи, где нужно, и `FieldValue.increment` для конкурентной записи

### 9) Команда `/stat` — формат ответа
- «Ты получил фактов: N» — `users/{user_id}.facts_count`
- «Всего фактов: M» — `metrics/counters.total_facts`
- «Пользователей: U» — `metrics/counters.total_users`

Важно: не считать пользователей через `COUNT(*)` по коллекции — это дорого и медленно. Держим агрегат в `metrics/counters` и обновляем только при создании нового пользователя (транзакция).

### 10) Транзакции: шаблон
Для «создать пользователя, если нет, и увеличить счётчик пользователей» используйте транзакцию Firestore:
1. Прочитать `users/{user_id}` и `metrics/counters`
2. Если пользователя нет — создать документ и выполнить `total_users += 1`
3. Если есть — пропустить инкремент `total_users`

Это исключит двойной учёт при гонках и при повторном `/start`.

### 11) Локальная разработка и эмулятор (опционально)
- Можно использовать Firebase Emulator Suite (Firestore) для разработки без затрат
- Запустить эмулятор, установить переменную `FIRESTORE_EMULATOR_HOST=localhost:8080`

### 12) Конфиденциальность и хранение данных
- Храните только необходимые поля (id, username, first_name)
- Добавьте срок хранения для `movements` (TTL 90 дней, например)
- По запросу пользователя обеспечить удаление его данных (`users/{user_id}` и саб‑коллекцию `movements`)

### 13) Стоимость (приблизительно)
- Firestore тарифицирует документы (записи/чтения/хранение). С семплированием перемещений каждые 20–30 сек стоимость умеренная
- Атомарные инкременты и точечные чтения `/stat` дешевы

### 14) Чек‑лист внедрения
1. Создать проект Firebase, включить Firestore (Native, регион)
2. Создать сервисный аккаунт, сгенерировать JSON‑ключ
3. Загрузить ключ в Railway как `FIREBASE_CREDENTIALS_B64` (или разнести по переменным)
4. Установить `firebase-admin` в зависимости
5. Добавить `firebase_client.py` и `firebase_stats.py` со вспомогательными функциями
6. Вызвать `ensure_user()` в `/start`
7. Вызывать `record_movement()` на обновлениях координат (с семплированием)
8. Вызывать `increment_fact_counters()` после каждой успешной отправки факта
9. Реализовать `/stat` с выводом трёх значений
10. Включить TTL для `movements` (если нужно)
11. Задать строгие Firestore Rules (deny all)

Эта схема минимально инвазивна, хорошо масштабируется и даёт понятные агрегаты для `/stat` без дорогих запросов.


