"""Main application entry point for NearbyFactBot."""

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

# Localized welcome messages
LOCALIZED_MESSAGES = {
    'ru': {
        'welcome': (
            "🗺️ *Добро пожаловать в бот удивительных фактов!*\n\n"
            "🔴 *Живая локация — ваш персональный экскурсовод:*\n"
            "📎 → Location → Share Live Location (15 мин - 8 часов)\n"
            "Автоматические факты каждые 5-60 минут во время прогулки\n\n"
            "📍 *Также доступно:* разовая отправка текущей геопозиции\n"
            "Нажмите кнопку ниже для мгновенного факта о месте\n\n"
            "_Каждый факт — это маленькое открытие рядом с вами!_ ✨"
        ),
        'buttons': {
            'info': "📱💡 Как поделиться Live Location",
            'location': "🔴📍 Поделиться локацией",
            'donate': "⭐💝 Поддержать проект"
        },
        'info_text': (
            "📱 *Как поделиться Live Location:*\n\n"
            "🔴 *Живая локация — основной режим:*\n"
            "1️⃣ Скрепка 📎 → Location → Share Live Location\n"
            "2️⃣ Выберите время отслеживания (15 мин - 8 часов)\n"
            "3️⃣ Настройте частоту фактов (каждые 5-60 минут)\n"
            "4️⃣ Гуляйте и получайте факты автоматически!\n\n"
            "*💡 Почему живая локация лучше?*\n"
            "• Персональный экскурсовод в кармане\n"
            "• Факты приходят сами по мере движения\n"
            "• Не нужно постоянно отправлять локацию\n"
            "• Идеально для туристических прогулок\n\n"
            "📍 *Разовая геопозиция:*\n"
            "• Кнопка «🔴 Поделиться локацией»\n"
            "• Мгновенный факт о текущем месте\n"
            "• Подходит для быстрых запросов"
        )
    },
    'en': {
        'welcome': (
            "🗺️ *Welcome to the amazing facts bot!*\n\n"
            "🔴 *Live location — your personal tour guide:*\n"
            "📎 → Location → Share Live Location (15 min - 8 hours)\n"
            "Automatic facts every 5-60 minutes during your walk\n\n"
            "📍 *Also available:* one-time current location sharing\n"
            "Press the button below for an instant fact about the place\n\n"
            "_Every fact is a small discovery near you!_ ✨"
        ),
        'buttons': {
            'info': "📱💡 How to share Live Location",
            'location': "🔴📍 Share location",
            'donate': "⭐💝 Support project"
        },
        'info_text': (
            "📱 *How to share Live Location:*\n\n"
            "🔴 *Live location — main mode:*\n"
            "1️⃣ Paperclip 📎 → Location → Share Live Location\n"
            "2️⃣ Choose tracking time (15 min - 8 hours)\n"
            "3️⃣ Set fact frequency (every 5-60 minutes)\n"
            "4️⃣ Walk and get facts automatically!\n\n"
            "*💡 Why is live location better?*\n"
            "• Personal tour guide in your pocket\n"
            "• Facts come automatically as you move\n"
            "• No need to constantly send location\n"
            "• Perfect for tourist walks\n\n"
            "📍 *One-time location:*\n"
            "• Button «🔴 Share location»\n"
            "• Instant fact about current place\n"
            "• Suitable for quick queries"
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
            'info': "📱💡 Comment partager Live Location",
            'location': "🔴📍 Partager la position",
            'donate': "⭐💝 Soutenir le projet"
        },
        'info_text': (
            "📱 *Comment partager Live Location :*\n\n"
            "🔴 *Position en direct — mode principal :*\n"
            "1️⃣ Trombone 📎 → Location → Share Live Location\n"
            "2️⃣ Choisissez la durée de suivi (15 min - 8 heures)\n"
            "3️⃣ Réglez la fréquence des faits (toutes les 5-60 minutes)\n"
            "4️⃣ Promenez-vous et recevez des faits automatiquement !\n\n"
            "*💡 Pourquoi la position en direct est-elle meilleure ?*\n"
            "• Guide touristique personnel dans votre poche\n"
            "• Les faits arrivent automatiquement en vous déplaçant\n"
            "• Pas besoin d'envoyer constamment votre position\n"
            "• Parfait pour les promenades touristiques\n\n"
            "📍 *Position unique :*\n"
            "• Bouton « 🔴 Partager la position »\n"
            "• Fait instantané sur le lieu actuel\n"
            "• Convient pour les demandes rapides"
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
    keyboard = [
        [KeyboardButton(buttons['info'])],
        [KeyboardButton(buttons['location'], request_location=True)],
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
    """Handle info button press."""
    user = update.effective_user
    donors_db = await get_async_donors_db()
    language = await donors_db.get_user_language(user.id)
    
    # Get localized info text (default to English) 
    messages = LOCALIZED_MESSAGES.get(language, LOCALIZED_MESSAGES['en'])
    info_text = messages['info_text']

    await update.message.reply_text(info_text, parse_mode="Markdown")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors."""
    logger.error(f"Exception while handling an update: {context.error}")


def main() -> None:
    """Main function to run the bot."""
    logger.info("Starting NearbyFactBot...")
    
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
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("dbtest", dbtest_command))
    application.add_handler(CommandHandler("reset", reset_language_command))

    # Add universal button handlers (check multiple language variants)
    # Info button patterns
    info_patterns = [
        "^📱💡 Как поделиться Live Location$",
        "^📱💡 How to share Live Location$"
    ]
    for pattern in info_patterns:
        application.add_handler(
            MessageHandler(filters.TEXT & filters.Regex(pattern), info_command)
        )
    
    # Donate button patterns  
    donate_patterns = [
        "^⭐💝 Поддержать проект$",
        "^⭐💝 Support project$"
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
