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
    reason_command,
    handle_reason_model_callback,
)
from .services.firebase_stats import ensure_user as fb_ensure_user
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
    
    # Safety: cancel any existing live session for this user
    try:
        from .services.live_location_tracker import get_live_location_tracker
        tracker = get_live_location_tracker()
        if tracker.is_user_tracking(user.id):
            await tracker.stop_live_location(user.id)
            logger.info(f"/start: stopped existing live session for user {user.id}")
    except Exception as e:
        logger.warning(f"/start: failed to stop existing session for user {user.id}: {e}")
    # Best-effort: register user in Firestore (non-blocking failure)
    try:
        await fb_ensure_user(user.id, user.username, user.first_name)
    except Exception:
        pass
    
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
            "Шаг 2/3. Открой вкладку 📍 Геопозиция/Location снизу.",
            "Шаг 3/3. Выбери 🟢 Транслировать геопозицию/Share My Live Location.",
        ],
        'en': [
            "Live location = share your real‑time location for a chosen time. You can close Telegram — I’ll keep sending facts.",
            "Step 1/3. Tap 📎 below.",
            "Step 2/3. Open the 📍 Location tab at the bottom.",
            "Step 3/3. Choose 🟢 Share My Live Location.",
        ],
        'fr': [
            "Position en direct = partager votre position en temps réel pendant une durée choisie. Vous pouvez fermer Telegram — j’enverrai quand même les faits.",
            "Étape 1/3. Touchez 📎 en bas.",
            "Étape 2/3. Ouvrez l’onglet 📍 Localisation/Location en bas.",
            "Étape 3/3. Choisissez 🟢 Partager la position en direct/Share My Live Location.",
        ],
    }
    labels = {
        'ru': { 'next': "Далее", 'done': "Готово", 'go': "Поехали" },
        'en': { 'next': "Next", 'done': "Done", 'go': "Let’s go" },
        'fr': { 'next': "Suivant", 'done': "Terminé", 'go': "C’est parti" },
    }
    lang_steps = steps.get(language, steps['en'])
    lang_labels = labels.get(language, labels['en'])

    # No video or GIF: send only text + step images

    # Send definition text first
    if lang_steps:
        await context.bot.send_message(chat_id=chat_id, text=lang_steps[0])

    # Then send 3 step messages with images if available
    import os
    base_path = Path(__file__).resolve().parent.parent
    step_images = ["IMG_9249.PNG", "IMG_9248.PNG", "IMG_9247.PNG"]
    step_file_ids = [
        os.getenv("HOWTO_STEP1_FILE_ID"),
        os.getenv("HOWTO_STEP2_FILE_ID"), 
        os.getenv("HOWTO_STEP3_FILE_ID"),
    ]

    for idx in range(1, min(4, len(lang_steps))):
        caption = lang_steps[idx]
        sent_photo = False
        
        # First priority: use file_id from environment (best for Railway)
        file_id = step_file_ids[idx-1]
        if file_id:
            try:
                await context.bot.send_photo(chat_id=chat_id, photo=file_id, caption=caption)
                logger.info(f"Sent step {idx} image via file_id")
                sent_photo = True
            except Exception as e:
                logger.warning(f"Failed to send step {idx} photo via file_id: {e}")
        
        # Second priority: try local file (for local development)
        if not sent_photo:
            image_name = step_images[idx-1]
            image_path = base_path / "docs" / image_name
            
            if image_path.exists():
                try:
                    with open(image_path, "rb") as f:
                        await context.bot.send_photo(chat_id=chat_id, photo=f, caption=caption)
                    logger.info(f"Sent step {idx} image from {image_path}")
                    sent_photo = True
                except Exception as e:
                    logger.warning(f"Failed to send photo {image_path}: {e}")
        
        # Fallback to text-only message
        if not sent_photo:
            await context.bot.send_message(chat_id=chat_id, text=caption)


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

    # Optional: reset languages on fresh deploy if requested
    if os.environ.get("RESET_LANG_ON_DEPLOY", "").lower() == "true":
        try:
            import asyncio
            async def _reset_all_languages():
                db = await get_async_donors_db()
                # best-effort: if backend supports bulk reset; otherwise skip
                reset_supported = hasattr(db._db, "reset_all_languages")  # type: ignore[attr-defined]
                if reset_supported:
                    await db._db.reset_all_languages()  # type: ignore[attr-defined]
            asyncio.get_event_loop_policy().get_event_loop().run_until_complete(_reset_all_languages())
            logger.info("RESET_LANG_ON_DEPLOY executed")
        except Exception as e:
            logger.warning(f"RESET_LANG_ON_DEPLOY failed or unsupported: {e}")

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
    # Hidden command to control reasoning effort per user
    application.add_handler(CommandHandler("reason", reason_command))
    # Hidden callbacks for reasoning/model toggles
    application.add_handler(CallbackQueryHandler(handle_reason_model_callback, pattern="^(set_reason|set_model):"))

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
