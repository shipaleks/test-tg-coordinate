### Формат локации, которую получает бот

Пользователь нажимает скрепку **📎 → Location**.  
Бот получает `update` c объектом `message.location`, который минимум содержит два float-поля:

| Поле       | Тип   | Описание                 |
|------------|-------|--------------------------|
| latitude   | float | Широта (–90…+90)         |
| longitude  | float | Долгота (–180…+180)      |

Дополнительно Telegram может передать:

* `horizontal_accuracy` — радиус неопределённости (м)  
* `live_period` — длительность трансляции «live location» (сек)  
* `heading` — азимут движения (°)  

```jsonc
{
  "update_id": 123,
  "message": {
    "location": {
      "latitude": 55.751244,
      "longitude": 37.618423,
      "live_period": 600
    }
  }
}

При «live location» приходят новые edited_message-обновления каждые 1-2 секунды, пока не истечёт live_period.  ￼ ￼ ￼

⸻

Product Requirements Document (PRD)

1. Overview / Problem

Путешественникам и городским исследователям не хватает лёгкого способа получать интересные, нетривиальные факты о местах вокруг себя одним тапом. MVP-бот в Telegram отвечает на отправленную локацию коротким фактом, сгенерированным GPT-4.1-mini, и тем самым делает открытие нового рядом стоящего места игрой “one-click trivia”.

2. Key User Flows
	1.	Статичная точка
	1.	Пользователь открывает чат с ботом.
	2.	Жмёт 📎 → Location и отправляет точку.
	3.	Через ≤3 с получает сообщение-факт (1-2 предложения).
	2.	Live-location (v 1.1)
	1.	Пользователь шэрит «live location» на выбранное время.
	2.	Бот каждые 10 мин автоматически присылает новый факт, пока активна трансляция.
	3.	После остановки трансляции бот присылает «✔️ Location sharing ended».

3. Functional Requirements
	•	F-1 Обработка message.location; извлечение latitude, longitude.
	•	F-2 Запрос к OpenAI chat.completions (GPT-4.1-mini) со шаблоном:
“Give one unusual fact about any place within 1 km of {lat},{lon}; 2 sentences, max 60 words.”
	•	F-3 Ответ пользователю тем же сообщением-фактом.
	•	F-4 Логирование ошибок (stdout + Railway logs).
	•	F-5 Локальный запуск через python main.py и туннель ngrok для Telegram → localhost.
	•	F-6 (v 1.1) Поддержка live-location:
	•	подписка на edited_message.location
	•	таймер на 10 мин; при срабатывании — новый факт с текущими координатами
	•	остановка таймера при отсутствии обновлений > live_period.
	•	F-7 Rate-limit: не чаще 1 запроса к OpenAI в 2 с на пользователя.

4. Non-Goals
	•	Маршрутизация, рекомендации ресторанов, афиша.
	•	Хранение истории локаций или профилей пользователей.
	•	Админ-панель и аналитика.
	•	Мультиязычный контент (будет рассмотрено позже).

5. Milestones & Release Plan

Дата (Paris)	Цель	Артефакт
Сегодня, 19:00-22:00	MVP локально: парсинг локации, вызов GPT, ответ в чат	main.py + .env.example
Сегодня, 22:30	Деплой в Railway, проверка prod-бота	railway.app URL, Procfile
v 1.0 Release	23:00 — публикация бота «@NearbyFactBot»	сообщение в личный канал
v 1.1 (D + 3)	Live-location, таймер 10 мин	теги git v1.1
v 1.2 (backlog)	i18n (RU/EN), кэширование фактов, inline-mode	roadmap.md

