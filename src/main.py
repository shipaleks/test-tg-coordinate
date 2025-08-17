"""Main application entry point for Bot Voyage."""

import logging
import os

from dotenv import load_dotenv
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from .handlers.location import (
    handle_edited_location,
    handle_interval_callback,
    handle_location,
)
from .handlers.donations import (
    donate_command,
    handle_donation_callback,
    handle_pre_checkout_query,
    handle_successful_payment,
    stats_command,
    dbtest_command,
)
from .handlers.language_selection import (
    show_language_selection,
    handle_language_selection,
    handle_custom_language_input,
    reset_language_command,
)
from .services.async_donors_wrapper import get_async_donors_db
from pathlib import Path

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Localized welcome messages (focus on Live Location)
LOCALIZED_MESSAGES = {
    'ru': {
        'welcome': (
            "🗺️ Привет! Я *Bot Voyage*. Покажу неожиданные факты вокруг тебя.\n\n"
            "ℹ️ Живая локация — это когда ты делишься местоположением в реальном времени на выбранный срок. Telegram можно закрыть — факты придут пушами.\n\n"
            "🔴 Включим? Нажми ниже — покажу в 3 шага."
        ),
        'buttons': {
            'info': "📱💡 Как включить живую локацию",
            'donate': "⭐💝 Поддержать проект"
        },
        'info_text': (
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
        )
    },
    'en': {
        'welcome': (
            "🗺️ Hi, I’m *Bot Voyage*. I’ll show surprising facts around you.\n\n"
            "ℹ️ Live location means you share your real‑time location for a chosen time. You can close Telegram — I’ll keep sending facts as push notifications.\n\n"
            "🔴 Turn it on? Tap below — 3 short steps."
        ),
        'buttons': {
            'info': "📱💡 How to enable Live Location",
            'donate': "⭐💝 Support project"
        },
        'info_text': (
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
        )
    },
    'fr': {
        'welcome': (
            "🗺️ Bonjour, je suis *Bot Voyage*. Je montre des faits inattendus autour de vous.\n\n"
            "ℹ️ La position en direct = partager votre position en temps réel pendant une durée choisie. Vous pouvez fermer Telegram — j’enverrai quand même les faits.\n\n"
            "🔴 On l’active ? 3 étapes ci‑dessous."
        ),
        'buttons': {
            'info': "📱💡 Activer la position en direct",
            'donate': "⭐💝 Soutenir le projet"
        },
        'info_text': (
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
        )
    }
    # Add more languages as needed
}


async def send_welcome_message(user_id: int, chat_id: int, bot, language: str = None) -> None:
    """Send welcome message in user's language."""
    if language is None:
        from src.services.async_donors_wrapper import get_async_donors_db
        donors_db = await get_async_donors_db()
        language = await donors_db.get_user_language(user_id)
    
    # Get localized messages (default to English)
    messages = LOCALIZED_MESSAGES.get(language, LOCALIZED_MESSAGES['en'])
    
    welcome_text = messages['welcome']
    buttons = messages['buttons']
    
    # Create keyboard with localized buttons
    # Focus on Live Location: no direct one-time location button
    keyboard = [
        [KeyboardButton(buttons['info'])],
        [KeyboardButton(buttons['donate'])],
    ]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=False
    )

    await bot.send_message(
        chat_id=chat_id,
        text=welcome_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user = update.effective_user
    donors_db = await get_async_donors_db()
    
    # Check if user has language set
    if not await donors_db.has_language_set(user.id):
        # Show language selection for new users
        await show_language_selection(update, context)
        return
    
    # User has language set, send welcome message in their language
    await send_welcome_message(user.id, update.message.chat_id, context.bot)


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send concise, sequential live-location onboarding with GIF."""
    user = update.effective_user
    donors_db = await get_async_donors_db()
    language = await donors_db.get_user_language(user.id)

    chat_id = update.effective_chat.id

    # Localized sequence: definition + 3 steps (no buttons)
    steps = {
        'ru': [
            "Что такое живая локация: ты делишься местоположением в реальном времени на выбранный срок. Telegram можно закрыть — факты придут пушами.",
            "Шаг 1/3. Нажми 📎 внизу.",
            "Шаг 2/3. 📍 Геопозиция/Location → 🔴 Транслировать геопозицию/Share Live Location.",
            "Шаг 3/3. Поставь 60 мин — дальше я сам присылаю факты каждые 5–60 мин.",
        ],
        'en': [
            "Live location = share your real‑time location for a chosen time. You can close Telegram — I’ll keep sending facts.",
            "Step 1/3. Tap 📎 below.",
            "Step 2/3. 📍 Location → 🔴 Share Live Location.",
            "Step 3/3. Choose 60 min — I’ll auto‑send facts every 5–60 min.",
        ],
        'fr': [
            "Position en direct = partager votre position en temps réel pendant une durée choisie. Vous pouvez fermer Telegram — j’enverrai quand même les faits.",
            "Étape 1/3. Touchez 📎 en bas.",
            "Étape 2/3. 📍 Location → 🔴 Share Live Location.",
            "Étape 3/3. Choisissez 60 min — j’enverrai des faits automatiquement (5–60 min).",
        ],
    }
    labels = {
        'ru': { 'next': "Далее", 'done': "Готово", 'go': "Поехали" },
        'en': { 'next': "Next", 'done': "Done", 'go': "Let’s go" },
        'fr': { 'next': "Suivant", 'done': "Terminé", 'go': "C’est parti" },
    }
    lang_steps = steps.get(language, steps['en'])
    lang_labels = labels.get(language, labels['en'])

    # Always try to send GIF first
    try:
        import os
        candidates = []
        env_path = os.getenv("HOWTO_GIF_PATH")
        if env_path:
            candidates.append(Path(env_path))
        # Project root: src/main.py -> src -> project root
        here = Path(__file__).resolve().parent.parent
        candidates += [
            here / "howtobot.gif",
            here / "docs" / "howtobot.gif",
            here / "assets" / "howtobot.gif",
            Path("howtobot.gif").resolve(),
        ]
        sent = False
        for p in candidates:
            if p.exists() and p.is_file():
                try:
                    with p.open("rb") as f:
                        await context.bot.send_animation(chat_id=chat_id, animation=f)
                    logger.info(f"Sent how-to gif from {p}")
                    sent = True
                    break
                except Exception as e:
                    logger.warning(f"send_animation failed for {p}: {e}; trying as document")
                    try:
                        with p.open("rb") as f:
                            await context.bot.send_document(chat_id=chat_id, document=f)
                        logger.info(f"Sent how-to as document from {p}")
                        sent = True
                        break
                    except Exception as e2:
                        logger.warning(f"send_document failed for {p}: {e2}")
        if not sent:
            file_id = os.getenv("HOWTO_GIF_FILE_ID")
            file_url = os.getenv("HOWTO_GIF_URL")
            if file_id:
                await context.bot.send_animation(chat_id=chat_id, animation=file_id)
                logger.info("Sent how-to gif via file_id")
            elif file_url:
                await context.bot.send_animation(chat_id=chat_id, animation=file_url)
                logger.info("Sent how-to gif via URL")
    except Exception as e:
        logger.warning(f"Failed to send how-to gif: {e}")

    # Send all steps sequentially (no buttons)
    for line in lang_steps:
        await context.bot.send_message(chat_id=chat_id, text=line)


# Removed callback-based onboarding (now sequential messages without buttons)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors."""
    logger.error(f"Exception while handling an update: {context.error}")


def main() -> None:
    """Main function to run the bot."""
    logger.info("Starting Bot Voyage...")
    
    # Run database migration if PostgreSQL is configured
    if os.environ.get("DATABASE_URL"):
        logger.info("PostgreSQL detected, checking for migration...")
        try:
            import asyncio
            from src.utils.migrate_to_postgres import check_and_migrate
            
            # Create new event loop for migration
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(check_and_migrate())
            loop.close()
            
            # Reset event loop for telegram bot
            asyncio.set_event_loop(asyncio.new_event_loop())
        except Exception as e:
            logger.error(f"Migration check failed: {e}")
            # Continue anyway - database will be created empty

    # Get bot token from environment
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

    # Create application
    application = Application.builder().token(bot_token).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("donate", donate_command))
    application.add_handler(CommandHandler("live", info_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("dbtest", dbtest_command))
    application.add_handler(CommandHandler("reset", reset_language_command))

    # Add universal button handlers (check multiple language variants)
    # Info button patterns
    info_patterns = [
        "^📱💡 Как включить живую локацию$",
        "^📱💡 How to enable Live Location$",
        "^📱💡 Activer la position en direct$"
    ]
    for pattern in info_patterns:
        application.add_handler(
            MessageHandler(filters.TEXT & filters.Regex(pattern), info_command)
        )
    
    # Donate button patterns  
    donate_patterns = [
        "^⭐💝 Поддержать проект$",
        "^⭐💝 Support project$",
        "^⭐💝 Soutenir le projet$"
    ]
    for pattern in donate_patterns:
        application.add_handler(
            MessageHandler(filters.TEXT & filters.Regex(pattern), donate_command)
        )
    
    # Add custom language input handler (must be after button handlers)
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.LOCATION, handle_custom_language_input
        )
    )

    # Add location handlers (exclude edited messages)
    application.add_handler(
        MessageHandler(
            filters.LOCATION & ~filters.UpdateType.EDITED_MESSAGE, handle_location
        )
    )

    # Add handler for live location updates (edited messages only)
    application.add_handler(
        MessageHandler(
            filters.UpdateType.EDITED_MESSAGE & filters.LOCATION, handle_edited_location
        )
    )

    # Add callback query handlers
    application.add_handler(
        CallbackQueryHandler(handle_interval_callback, pattern="^interval_")
    )
    # No callback handler needed: onboarding sends sequential messages without buttons
    application.add_handler(
        CallbackQueryHandler(handle_donation_callback, pattern="^donate_")
    )
    application.add_handler(
        CallbackQueryHandler(handle_language_selection, pattern="^lang_")
    )
    
    # Add payment handlers
    application.add_handler(PreCheckoutQueryHandler(handle_pre_checkout_query))
    application.add_handler(
        MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment)
    )

    # Add error handler
    application.add_error_handler(error_handler)

    # Check if we should use webhook or polling
    webhook_url = os.getenv("WEBHOOK_URL")
    port = int(os.getenv("PORT", "8000"))

    if webhook_url:
        # Use webhook for production
        logger.info(f"Starting webhook on port {port}")
        # Use synchronous run_webhook which handles event loop internally
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            webhook_url=webhook_url,
        )
    else:
        # Use polling for local development
        logger.info("Starting polling mode")
        # Use synchronous run_polling which handles event loop internally
        application.run_polling()


if __name__ == "__main__":
    main()
