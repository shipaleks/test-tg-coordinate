"""Centralized localization for all user-facing bot messages.

Every message dictionary lives here so handlers and services share one
source of truth — and services can localize without importing handlers
(which previously forced lazy imports to break circular dependencies).
"""

import logging

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "en"

# Welcome message + main menu buttons (used by /start)
WELCOME_MESSAGES = {
    "ru": {
        "welcome": (
            "🗺️ Привет! Я *Bot Voyage*. Покажу неожиданные факты вокруг тебя.\n\n"
            "ℹ️ Живая локация — это когда ты делишься местоположением в реальном времени на выбранный срок. Telegram можно закрыть — факты придут пушами.\n\n"
            "🔴 Включим? Нажми ниже — покажу в 3 шага."
        ),
        "buttons": {
            "info": "📱💡 Как включить живую локацию",
            "one_time": "📍 Отправить локацию",
            "language": "🌐 Язык / Language",
            "donate": "⭐💝 Поддержать проект",
        },
        "info_text": (
            "📱 *Как включить живую локацию:*\n\n"
            "1️⃣ Скрепка 📎 → 📍 Location → 🔴 Share Live Location\n"
            "2️⃣ Выберите время (обычно 60 мин удобно)\n"
            "3️⃣ Гуляйте — факты будут приходить сами (каждые 5–60 мин)\n\n"
            "*💡 Почему живая локация лучше?*\n"
            "• Персональный экскурсовод в кармане\n"
            "• Факты приходят сами по мере движения\n"
            "• Не нужно постоянно отправлять локацию\n"
            "• Идеально для туристических прогулок\n\n"
            "Если что — разовая локация тоже работает, просто отправьте её через 📎."
        ),
    },
    "en": {
        "welcome": (
            "🗺️ Hi, I'm *Bot Voyage*. I'll show surprising facts around you.\n\n"
            "ℹ️ Live location means you share your real‑time location for a chosen time. You can close Telegram — I'll keep sending facts as push notifications.\n\n"
            "🔴 Turn it on? Tap below — 3 short steps."
        ),
        "buttons": {
            "info": "📱💡 How to enable Live Location",
            "one_time": "📍 Send location",
            "language": "🌐 Language / Язык",
            "donate": "⭐💝 Support project",
        },
        "info_text": (
            "📱 *How to enable Live Location:*\n\n"
            "1️⃣ Paperclip 📎 → 📍 Location → 🔴 Share Live Location\n"
            "2️⃣ Pick a duration (60 min is a good default)\n"
            "3️⃣ Walk — facts will arrive automatically (every 5–60 min)\n\n"
            "*💡 Why is live location better?*\n"
            "• Personal tour guide in your pocket\n"
            "• Facts come automatically as you move\n"
            "• No need to constantly send location\n"
            "• Perfect for tourist walks\n\n"
            "One-time location also works — just send your location via 📎 if needed."
        ),
    },
    "fr": {
        "welcome": (
            "🗺️ Bonjour, je suis *Bot Voyage*. Je montre des faits inattendus autour de vous.\n\n"
            "ℹ️ La position en direct = partager votre position en temps réel pendant une durée choisie. Vous pouvez fermer Telegram — j'enverrai quand même les faits.\n\n"
            "🔴 On l'active ? 3 étapes ci‑dessous."
        ),
        "buttons": {
            "info": "📱💡 Activer la position en direct",
            "one_time": "📍 Envoyer ma position",
            "language": "🌐 Langue / Language",
            "donate": "⭐💝 Soutenir le projet",
        },
        "info_text": (
            "📱 *Activer la position en direct :*\n\n"
            "1️⃣ Trombone 📎 → 📍 Location → 🔴 Share Live Location\n"
            "2️⃣ Durée conseillée : 60 min\n"
            "3️⃣ Les faits arrivent automatiquement (5–60 min)\n\n"
            "*💡 Pourquoi la position en direct est-elle meilleure ?*\n"
            "• Guide touristique personnel dans votre poche\n"
            "• Les faits arrivent automatiquement en vous déplaçant\n"
            "• Pas besoin d'envoyer constamment votre position\n"
            "• Parfait pour les promenades touristiques\n\n"
            "La position unique fonctionne aussi via 📎 si besoin."
        ),
    },
    # Add more languages as needed
}

# Sequential /live onboarding steps (definition + 3 steps, no buttons)
ONBOARDING_STEPS = {
    "ru": [
        "Что такое живая локация: ты делишься местоположением в реальном времени на выбранный срок. Telegram можно закрыть — факты придут пушами.",
        "Шаг 1/3. Нажми 📎 внизу.",
        "Шаг 2/3. Открой вкладку 📍 Геопозиция/Location снизу.",
        "Шаг 3/3. Выбери 🟢 Транслировать геопозицию/Share My Live Location.",
    ],
    "en": [
        "Live location = share your real‑time location for a chosen time. You can close Telegram — I’ll keep sending facts.",
        "Step 1/3. Tap 📎 below.",
        "Step 2/3. Open the 📍 Location tab at the bottom.",
        "Step 3/3. Choose 🟢 Share My Live Location.",
    ],
    "fr": [
        "Position en direct = partager votre position en temps réel pendant une durée choisie. Vous pouvez fermer Telegram — j’enverrai quand même les faits.",
        "Étape 1/3. Touchez 📎 en bas.",
        "Étape 2/3. Ouvrez l’onglet 📍 Localisation/Location en bas.",
        "Étape 3/3. Choisissez 🟢 Partager la position en direct/Share My Live Location.",
    ],
}

# Language-selection flow messages (/start for new users, /reset)
LANGUAGE_MESSAGES = {
    "ru": {
        "welcome": "🌍 **Выберите ваш язык:**\n\nВыбранный язык будет использоваться для всех фактов и сообщений бота.",
        "custom_prompt": "Введите код языка (например: es, de, it) или название языка:",
        "language_set": "✅ Язык установлен: {flag} {name}",
        "language_reset": "🔄 Язык сброшен. Используйте /start для выбора нового языка.",
        "invalid_language": "❌ Некорректный язык. Попробуйте еще раз.",
    },
    "en": {
        "welcome": "🌍 **Choose your language:**\n\nThe selected language will be used for all facts and bot messages.",
        "custom_prompt": "Enter language code (e.g.: es, de, it) or language name:",
        "language_set": "✅ Language set: {flag} {name}",
        "language_reset": "🔄 Language reset. Use /start to choose a new language.",
        "invalid_language": "❌ Invalid language. Please try again.",
    },
    "fr": {
        "welcome": "🌍 **Choisissez votre langue :**\n\nLa langue sélectionnée sera utilisée pour tous les faits et messages du bot.",
        "custom_prompt": "Entrez le code de langue (ex : es, de, it) ou le nom de la langue :",
        "language_set": "✅ Langue définie : {flag} {name}",
        "language_reset": "🔄 Langue réinitialisée. Utilisez /start pour choisir une nouvelle langue.",
        "invalid_language": "❌ Langue invalide. Veuillez réessayer.",
    },
    "pt": {
        "welcome": "🌍 **Escolha seu idioma:**\n\nO idioma selecionado será usado para todos os fatos e mensagens do bot.",
        "custom_prompt": "Digite o código do idioma (ex: es, de, it) ou nome do idioma:",
        "language_set": "✅ Idioma definido: {flag} {name}",
        "language_reset": "🔄 Idioma redefinido. Use /start para escolher um novo idioma.",
        "invalid_language": "❌ Idioma inválido. Tente novamente.",
    },
    "uk": {
        "welcome": "🌍 **Оберіть вашу мову:**\n\nОбрана мова буде використовуватися для всіх фактів та повідомлень бота.",
        "custom_prompt": "Введіть код мови (наприклад: es, de, it) або назву мови:",
        "language_set": "✅ Мову встановлено: {flag} {name}",
        "language_reset": "🔄 Мову скинуто. Використовуйте /start для вибору нової мови.",
        "invalid_language": "❌ Некоректна мова. Спробуйте ще раз.",
    },
}

# Location handler + live session messages
LOCATION_MESSAGES = {
    "ru": {
        "image_fallback": "",
        "live_location_received": "🔴 *Живая локация получена!*\n\n📍 Отслеживание на {minutes} минут\n\nКак часто присылать интересные факты?",
        "interval_5min": "Каждые 5 минут",
        "interval_10min": "Каждые 10 минут",
        "interval_30min": "Каждые 30 минут",
        "interval_60min": "Каждые 60 минут",
        "live_activated": "🔴 *Живая локация активирована!*\n\n📍 Отслеживание: {minutes} минут\n⏰ Факты каждые: {interval} минут\n\n🚀 Первый факт придёт примерно через 3–5 минут, затем — автоматически по расписанию.\n\nОстановите sharing чтобы завершить сессию.",
        "static_upsell": "💡 *Совет:* Это был разовый факт.\n\nХотите получать факты автоматически во время прогулки? Включите *живую локацию* — не нужно нажимать каждый раз!",
        "static_upsell_button": "📱 Как включить живую локацию",
        "place_label": "📍 *Место:*",
        "fact_label": "💡 *Факт:*",
        "sources_label": "🔗 *Источники:*",
        "live_fact_label": "🔴 *Факт #{number}*",
        "attraction_address": "Достопримечательность: {place}",
        "static_fact_format": "📍 *Место:* {place}\n\n💡 *Факт:* {fact}",
        "live_fact_format": "🔴 *Факт #{number}*\n\n📍 *Место:* {place}\n\n💡 *Факт:* {fact}",
        "error_no_info": "😔 *Упс!*\n\nНе удалось найти интересную информацию о данном месте.\nПопробуйте немного сместиться или отправить другую локацию.",
        "near_you": "рядом с вами",
        "live_stopped": "✅ *Живая локация остановлена*\n\nСпасибо за использование Bot Voyage! 🗺️✨\nЗапустите новую живую локацию в любое время, чтобы продолжить исследование!",
        "live_expired": "✅ *Сессия живой локации завершена*\n\nПериод отслеживания истек. Запустите новую живую локацию, чтобы продолжить получать факты! 🗺️✨",
        "live_manual_stop": "✅ *Трансляция остановлена*\n\nВы прекратили делиться геопозицией.\nСпасибо за прогулку с нами! 🚶‍♂️🗺️",
    },
    "en": {
        "image_fallback": "",
        "live_location_received": "🔴 *Live location received!*\n\n📍 Tracking for {minutes} minutes\n\nHow often should I send interesting facts?",
        "interval_5min": "Every 5 minutes",
        "interval_10min": "Every 10 minutes",
        "interval_30min": "Every 30 minutes",
        "interval_60min": "Every 60 minutes",
        "live_activated": "🔴 *Live location activated!*\n\n📍 Tracking: {minutes} minutes\n⏰ Facts every: {interval} minutes\n\n🚀 The first fact will arrive in about 3–5 minutes, then continue automatically.\n\nStop sharing to end the session.",
        "static_upsell": "💡 *Tip:* This was a one-time fact.\n\nWant facts automatically during your walk? Enable *live location* — no need to tap each time!",
        "static_upsell_button": "📱 How to enable live location",
        "place_label": "📍 *Place:*",
        "fact_label": "💡 *Fact:*",
        "sources_label": "🔗 *Sources:*",
        "live_fact_label": "🔴 *Fact #{number}*",
        "attraction_address": "Attraction: {place}",
        "static_fact_format": "📍 *Place:* {place}\n\n💡 *Fact:* {fact}",
        "live_fact_format": "🔴 *Fact #{number}*\n\n📍 *Place:* {place}\n\n💡 *Fact:* {fact}",
        "error_no_info": "😔 *Oops!*\n\nCouldn't find interesting information about this location.\nTry moving slightly or sending a different location.",
        "near_you": "near you",
        "live_stopped": "✅ *Live location stopped*\n\nThank you for using Bot Voyage! 🗺️✨\nStart a new live location anytime to continue exploring!",
        "live_expired": "✅ *Live location session ended*\n\nThe tracking period has expired. Start a new live location to continue receiving facts! 🗺️✨",
        "live_manual_stop": "✅ *Broadcast stopped*\n\nYou stopped sharing your location.\nThank you for walking with us! 🚶‍♂️🗺️",
    },
    "fr": {
        "image_fallback": "",
        "live_location_received": "🔴 *Position en direct reçue !*\n\n📍 Suivi pendant {minutes} minutes\n\nÀ quelle fréquence souhaitez-vous recevoir des faits intéressants ?",
        "interval_5min": "Toutes les 5 minutes",
        "interval_10min": "Toutes les 10 minutes",
        "interval_30min": "Toutes les 30 minutes",
        "interval_60min": "Toutes les 60 minutes",
        "live_activated": "🔴 *Position en direct activée !*\n\n📍 Suivi : {minutes} minutes\n⏰ Faits toutes les : {interval} minutes\n\n🚀 Le premier fait arrivera dans ~3–5 minutes, puis automatiquement.\n\nArrêtez le partage pour terminer la session.",
        "static_upsell": "💡 *Conseil :* C'était un fait ponctuel.\n\nVoulez-vous recevoir des faits automatiquement pendant votre promenade ? Activez la *position en direct* — plus besoin de cliquer à chaque fois !",
        "static_upsell_button": "📱 Comment activer la position en direct",
        "place_label": "📍 *Lieu :*",
        "fact_label": "💡 *Fait :*",
        "sources_label": "🔗 *Sources :*",
        "live_fact_label": "🔴 *Fait #{number}*",
        "attraction_address": "Attraction : {place}",
        "static_fact_format": "📍 *Lieu :* {place}\n\n💡 *Fait :* {fact}",
        "live_fact_format": "🔴 *Fait #{number}*\n\n📍 *Lieu :* {place}\n\n💡 *Fait :* {fact}",
        "error_no_info": "😔 *Oups !*\n\nImpossible de trouver des informations intéressantes sur cet endroit.\nEssayez de vous déplacer légèrement ou d'envoyer une autre position.",
        "near_you": "près de vous",
        "live_stopped": "✅ *Position en direct arrêtée*\n\nMerci d'avoir utilisé Bot Voyage ! 🗺️✨\nDémarrez une nouvelle position en direct à tout moment pour continuer à explorer !",
        "live_expired": "✅ *Session de position en direct terminée*\n\nLa période de suivi a expiré. Démarrez une nouvelle position en direct pour continuer à recevoir des faits ! 🗺️✨",
        "live_manual_stop": "✅ *Diffusion arrêtée*\n\nVous avez cessé de partager votre position.\nMerci de vous promener avec nous ! 🚶‍♂️🗺️",
    },
    # Add more languages as needed
}

# Donation flow messages (/donate)
DONATION_MESSAGES = {
    "ru": {
        "title": "🌟 *Поддержать проект*",
        "donor_status": "🎁 *Донатер проекта*\n📊 Всего звезд: {total_stars}⭐\n🧠 Улучшенный reasoning (больше проверок) активирован",
        "support_helps": "Ваша поддержка помогает:",
        "help_points": [
            "🤖 Оплачивать Claude API для качественных фактов",
            "🚀 Развивать новые функции бота",
            "📡 Поддерживать сервер 24/7",
        ],
        "voluntary": "💝 *Любая поддержка добровольна и очень ценится!*",
        "other_amount": "💰 Other amount",
        "choose_amount": "💰 *Choose amount:*",
        "any_support": "✨ Any support is greatly appreciated!",
        "back": "← Back",
    },
    "en": {
        "title": "🌟 *Support the project*",
        "donor_status": "🎁 *Project supporter*\n📊 Total stars: {total_stars}⭐\n🧠 Enhanced reasoning (more verification) activated",
        "support_helps": "Your support helps:",
        "help_points": [
            "🤖 Pay for the Claude API for quality facts",
            "🚀 Develop new bot features",
            "📡 Maintain 24/7 server",
        ],
        "voluntary": "💝 *All support is voluntary and greatly appreciated!*",
        "other_amount": "💰 Other amount",
        "choose_amount": "💰 *Choose amount:*",
        "any_support": "✨ Any support is greatly appreciated!",
        "back": "← Back",
    },
    "fr": {
        "title": "🌟 *Soutenir le projet*",
        "donor_status": "🎁 *Soutien du projet*\n📊 Total étoiles : {total_stars}⭐\n🧠 Reasoning amélioré (plus de vérifications) activé",
        "support_helps": "Votre soutien aide à :",
        "help_points": [
            "🤖 Payer l'API Claude pour des faits de qualité",
            "🚀 Développer de nouvelles fonctionnalités",
            "📡 Maintenir le serveur 24h/24",
        ],
        "voluntary": "💝 *Tout soutien est volontaire et très apprécié !*",
        "other_amount": "💰 Autre montant",
        "choose_amount": "💰 *Choisissez le montant :*",
        "any_support": "✨ Tout soutien est grandement apprécié !",
        "back": "← Retour",
    },
}


def get_message(messages: dict, language: str, key: str, **kwargs) -> str:
    """Look up a message with English fallback and optional formatting."""
    lang_messages = messages.get(language, messages[DEFAULT_LANGUAGE])
    message = lang_messages.get(key, messages[DEFAULT_LANGUAGE].get(key, key))
    return message.format(**kwargs) if kwargs else message


async def get_user_language(user_id: int) -> str:
    """Fetch the user's stored language, defaulting to English on errors."""
    # Imported lazily so this module stays import-safe from anywhere
    # (handlers, services, tests) without dragging in DB backends.
    from ..services.async_donors_wrapper import get_async_donors_db

    try:
        donors_db = await get_async_donors_db()
        return await donors_db.get_user_language(user_id)
    except Exception as e:
        logger.warning(f"Failed to get language for user {user_id}: {e}")
        return DEFAULT_LANGUAGE


async def get_localized_message(user_id: int, key: str, **kwargs) -> str:
    """Get a localized location/live-session message for a user."""
    try:
        language = await get_user_language(user_id)
        return get_message(LOCATION_MESSAGES, language, key, **kwargs)
    except Exception as e:
        logger.warning(f"Error getting localized message: {e}")
        # Fallback to English
        message = LOCATION_MESSAGES[DEFAULT_LANGUAGE].get(key, key)
        return message.format(**kwargs) if kwargs else message
