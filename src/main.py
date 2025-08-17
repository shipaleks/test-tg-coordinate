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
            "🗺️ Привет! Я *Bot Voyage*. Я показываю неожиданные факты о местах вокруг тебя.\n\n"
            "🔴 Хочешь попробовать живую локацию? Я сам буду присылать факты по пути.\n"
            "Нажми ниже — коротко покажу, как включить."
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
            "🗺️ *Bot Voyage — facts while you walk!*\n\n"
            "🔴 *Live location is the main mode:*\n"
            "📎 → Location → Share Live Location (5–60 min and more)\n"
            "I’ll send facts automatically as you move\n\n"
            "Tap below to see how to enable live location."
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
            "🗺️ *Bienvenue dans le bot des faits étonnants !*\n\n"
            "🔴 *Position en direct — votre guide touristique personnel :*\n"
            "📎 → Location → Share Live Location (15 min - 8 heures)\n"
            "Faits automatiques toutes les 5-60 minutes pendant votre promenade\n\n"
            "📍 *Aussi disponible :* envoi unique de position actuelle\n"
            "Appuyez sur le bouton ci-dessous pour un fait instantané sur le lieu\n\n"
            "_Chaque fait est une petite découverte près de vous !_ ✨"
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
    """Interactive onboarding for Live Location (step-by-step)."""
    user = update.effective_user
    donors_db = await get_async_donors_db()
    language = await donors_db.get_user_language(user.id)

    # Simple state machine in memory (per chat)
    chat_id = update.effective_chat.id
    if "onboarding_step" not in context.chat_data:
        context.chat_data["onboarding_step"] = 0

    step = context.chat_data["onboarding_step"]

    # Localized short steps
    steps = {
        'ru': [
            "Шаг 1/3. Нажми скрепку 📎 внизу — это меню вложений.",
            "Шаг 2/3. Выбери 📍 Location → 🔴 Share Live Location — я начну следить за маршрутом.",
            "Шаг 3/3. Поставь время (обычно 60 мин). Дальше я сам буду присылать факты по пути.",
        ],
        'en': [
            "Step 1/3. Tap the paperclip 📎 below — that’s the attachment menu.",
            "Step 2/3. Choose 📍 Location → 🔴 Share Live Location — I’ll start following your route.",
            "Step 3/3. Pick a duration (60 min works well). I’ll send facts automatically as you walk.",
        ],
        'fr': [
            "Étape 1/3. Touchez le trombone 📎 en bas — le menu des pièces jointes.",
            "Étape 2/3. Choisissez 📍 Location → 🔴 Share Live Location — je suivrai votre trajet.",
            "Étape 3/3. Choisissez la durée (60 min). J’enverrai des faits automatiquement en marchant.",
        ],
    }
    labels = {
        'ru': { 'next': "Далее", 'done': "Готово", 'go': "Поехали" },
        'en': { 'next': "Next", 'done': "Done", 'go': "Let’s go" },
        'fr': { 'next': "Suivant", 'done': "Terminé", 'go': "C’est parti" },
    }
    lang_steps = steps.get(language, steps['en'])
    lang_labels = labels.get(language, labels['en'])

    # Send GIF on the first step
    if step == 0:
        try:
            import os
            gif_path = os.getenv("HOWTO_GIF_PATH", "howtobot.gif")
            if os.path.exists(gif_path):
                with open(gif_path, "rb") as f:
                    await context.bot.send_animation(chat_id=chat_id, animation=f)
            else:
                file_id = os.getenv("HOWTO_GIF_FILE_ID")
                if file_id:
                    await context.bot.send_animation(chat_id=chat_id, animation=file_id)
        except Exception as e:
            logger.debug(f"Failed to send how-to gif: {e}")

    # Compose inline keyboard for step
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    if step < len(lang_steps) - 1:
        buttons = [[InlineKeyboardButton(lang_labels['next'], callback_data="live_onboarding_next")]]
    else:
        buttons = [[InlineKeyboardButton(lang_labels['go'], callback_data="live_onboarding_done")]]

    await context.bot.send_message(
        chat_id=chat_id,
        text=lang_steps[step],
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    # Advance step
    context.chat_data["onboarding_step"] = (step + 1) % len(lang_steps)


async def live_onboarding_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    # Reuse info_command logic to send next step
    if data == "live_onboarding_next":
        await info_command(update, context)
    elif data == "live_onboarding_done":
        # Reset step and send short confirmation
        context.chat_data["onboarding_step"] = 0
        await query.edit_message_text("Отлично! Включайте живую локацию через 📎 → 📍 → 🔴, я жду.")


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
    application.add_handler(
        CallbackQueryHandler(live_onboarding_callback, pattern="^live_onboarding_")
    )
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
