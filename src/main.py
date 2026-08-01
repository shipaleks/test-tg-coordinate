"""Main application entry point for Bot Voyage."""

import asyncio
import logging
import os
from pathlib import Path

from aiohttp import web
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

from src.handlers.donations import (
    dbtest_command,
    donate_command,
    handle_donation_callback,
    handle_pre_checkout_query,
    handle_successful_payment,
    stats_command,
)
from src.handlers.language_selection import (
    handle_custom_language_input,
    handle_language_selection,
    handle_reason_model_callback,
    reason_command,
    reset_language_command,
    show_language_selection,
)
from src.handlers.location import (
    handle_edited_location,
    handle_interval_callback,
    handle_location,
)
from src.services.async_donors_wrapper import get_async_donors_db
from src.services.firebase_stats import ensure_user as fb_ensure_user
from src.utils.i18n import ONBOARDING_STEPS, WELCOME_MESSAGES

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def send_welcome_message(
    user_id: int, chat_id: int, bot, language: str = None
) -> None:
    """Send welcome message in user's language."""
    if language is None:
        from src.services.async_donors_wrapper import get_async_donors_db

        donors_db = await get_async_donors_db()
        language = await donors_db.get_user_language(user_id)

    # Get localized messages (default to English)
    messages = WELCOME_MESSAGES.get(language, WELCOME_MESSAGES["en"])

    welcome_text = messages["welcome"]
    buttons = messages["buttons"]

    # Create keyboard with localized buttons
    # Focus on Live Location, but include one-time location for convenience
    keyboard = [
        [KeyboardButton(buttons["info"])],
        [KeyboardButton(buttons["one_time"], request_location=True)],
        [KeyboardButton(buttons["language"]), KeyboardButton(buttons["donate"])],
    ]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=False
    )

    await bot.send_message(
        chat_id=chat_id,
        text=welcome_text,
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    logger.info(f"/start received from user {user.id}")

    # FIRST: Always respond immediately to avoid hanging
    try:
        await update.message.reply_text("⏳ Processing...")
    except Exception as e:
        logger.error(f"Failed to send initial response: {e}")

    # Safety: cancel any existing live session for this user
    try:
        from src.services.live_location_tracker import get_live_location_tracker

        tracker = get_live_location_tracker()
        if tracker.is_user_tracking(user.id):
            logger.info(f"Stopping live location for user {user.id}")
            await tracker.stop_live_location(user.id)
            # Inform user that we reset the session
            try:
                from src.utils.i18n import get_localized_message as _msg

                reset_text = await _msg(user.id, "live_manual_stop")
            except Exception:
                reset_text = "✅ Session reset. Let's start fresh."
            await context.bot.send_message(
                chat_id=chat_id, text=reset_text, parse_mode="Markdown"
            )
            logger.info(f"/start: stopped existing live session for user {user.id}")
    except Exception as e:
        logger.warning(
            f"/start: failed to stop existing session for user {user.id}: {e}"
        )

    # Best-effort: register user in Firestore (non-blocking failure)
    try:
        await fb_ensure_user(user.id, user.username, user.first_name)
    except Exception:
        pass

    # Get donors_db AFTER stopping sessions
    try:
        donors_db = await get_async_donors_db()
    except Exception as e:
        logger.error(f"Failed to get donors_db: {e}")
        await context.bot.send_message(
            chat_id=chat_id, text="❌ Initialization error. Please try again."
        )
        return

    try:
        # Check if user has language set
        has_lang = await donors_db.has_language_set(user.id)
        logger.info(f"User {user.id} has_language_set: {has_lang}")

        if not has_lang:
            # Show language selection for new users
            logger.info(f"Showing language selection for user {user.id}")
            await show_language_selection(update, context)
            return

        # User has language set, send welcome message in their language
        logger.info(f"User {user.id} has language, showing welcome")
        await send_welcome_message(user.id, chat_id, context.bot)
    except Exception as e:
        logger.error(f"/start flow error for user {user.id}: {e}")
        # Fallback minimal message so user always sees a response
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="👋 I'm ready. Send location (or Live Location) to start.",
            )
        except Exception:
            pass


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send concise, sequential live-location onboarding with GIF."""
    user = update.effective_user
    donors_db = await get_async_donors_db()
    language = await donors_db.get_user_language(user.id)

    chat_id = update.effective_chat.id

    # Localized sequence: definition + 3 steps (no buttons)
    lang_steps = ONBOARDING_STEPS.get(language, ONBOARDING_STEPS["en"])

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
        file_id = step_file_ids[idx - 1]
        if file_id:
            try:
                await context.bot.send_photo(
                    chat_id=chat_id, photo=file_id, caption=caption
                )
                logger.info(f"Sent step {idx} image via file_id")
                sent_photo = True
            except Exception as e:
                logger.warning(f"Failed to send step {idx} photo via file_id: {e}")

        # Second priority: try local file (for local development)
        if not sent_photo:
            image_name = step_images[idx - 1]
            image_path = base_path / "docs" / image_name

            if image_path.exists():
                try:
                    with open(image_path, "rb") as f:
                        await context.bot.send_photo(
                            chat_id=chat_id, photo=f, caption=caption
                        )
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


async def _run_startup_tasks() -> None:
    """One-time async startup tasks, run before the bot starts."""
    # Run database migration if PostgreSQL is configured
    if os.environ.get("DATABASE_URL"):
        logger.info("PostgreSQL detected, checking for migration...")
        try:
            from src.utils.migrate_to_postgres import check_and_migrate

            await check_and_migrate()
        except Exception as e:
            logger.error(f"Migration check failed: {e}")
            # Continue anyway - database will be created empty

    # Optional: reset languages on fresh deploy if requested
    if os.environ.get("RESET_LANG_ON_DEPLOY", "").lower() == "true":
        try:
            db = await get_async_donors_db()
            # best-effort: if backend supports bulk reset; otherwise skip
            if hasattr(db._db, "reset_all_languages"):  # type: ignore[attr-defined]
                await db._db.reset_all_languages()  # type: ignore[attr-defined]
            logger.info("RESET_LANG_ON_DEPLOY executed")
        except Exception as e:
            logger.warning(f"RESET_LANG_ON_DEPLOY failed or unsupported: {e}")


def _build_health_runner() -> web.AppRunner:
    """Healthcheck endpoints for Railway/Koyeb, served on the bot's loop."""

    async def _health(request: web.Request) -> web.Response:
        return web.Response(text="OK")

    health_app = web.Application()
    for path in ("/", "/health", "/healthz"):
        health_app.router.add_get(path, _health)
    # access_log=None: suppress per-request log spam (as the old server did)
    return web.AppRunner(health_app, access_log=None)


def main() -> None:
    """Main function to run the bot."""
    logger.info("Starting Bot Voyage...")

    # Run startup tasks on the loop PTB will reuse (run_webhook/run_polling
    # pick up the current event loop), so loop-bound resources like DB
    # connections stay valid for the bot's lifetime.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_run_startup_tasks())

    # Get bot token from environment
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

    # Webhook vs polling is decided by WEBHOOK_URL
    webhook_url = os.getenv("WEBHOOK_URL")
    port = int(os.getenv("PORT", "8000"))

    # Create application
    builder = Application.builder().token(bot_token)

    if webhook_url:
        # Healthcheck server for Railway/Koyeb on port+1, started on the
        # bot's own event loop (replaces the old threaded HTTPServer).
        health_port = port + 1
        health_runner = _build_health_runner()

        async def _start_health_server(app: Application) -> None:
            await health_runner.setup()
            site = web.TCPSite(health_runner, "0.0.0.0", health_port)
            await site.start()
            logger.info(
                f"Healthcheck server started on port {health_port} (/, /health, /healthz)"
            )

        async def _stop_health_server(app: Application) -> None:
            await health_runner.cleanup()

        builder = builder.post_init(_start_health_server).post_shutdown(
            _stop_health_server
        )

    application = builder.build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("donate", donate_command))
    application.add_handler(CommandHandler("live", info_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("dbtest", dbtest_command))
    application.add_handler(CommandHandler("reset", reset_language_command))

    # Debug command
    async def debuguser_command(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Debug user state in Firestore."""
        user = update.effective_user

        try:
            donors_db = await get_async_donors_db()

            # Check if using Firestore
            if hasattr(donors_db, "_use_firestore") and donors_db._use_firestore:
                from src.services.firebase_client import get_firestore

                db = get_firestore()

                # Get user document
                user_doc = db.collection("users").document(str(user.id)).get()

                if user_doc.exists:
                    user_data = user_doc.to_dict()
                    debug_text = f"🔍 User {user.id} Debug Info\n\n"
                    debug_text += "Firestore Document:\n"
                    for key, value in user_data.items():
                        debug_text += f"• {key}: {value}\n"
                else:
                    debug_text = f"❌ No Firestore document found for user {user.id}"
            else:
                debug_text = "Not using Firestore database"

            # Also check language settings
            has_lang = await donors_db.has_language_set(user.id)
            current_lang = await donors_db.get_user_language(user.id)
            debug_text += "\n\nLanguage Check:\n"
            debug_text += f"• has_language_set: {has_lang}\n"
            debug_text += f"• current_language: {current_lang}"

            await update.message.reply_text(debug_text)

        except Exception as e:
            await update.message.reply_text(f"❌ Debug error: {str(e)}")

    application.add_handler(CommandHandler("debuguser", debuguser_command))
    # Hidden command to control reasoning effort per user
    application.add_handler(CommandHandler("reason", reason_command))
    # Hidden callbacks for reasoning/model toggles
    application.add_handler(
        CallbackQueryHandler(
            handle_reason_model_callback, pattern="^(set_reason|set_model):"
        )
    )

    # Add universal button handlers (check multiple language variants)
    # Info button patterns
    info_patterns = [
        "^📱💡 Как включить живую локацию$",
        "^📱💡 How to enable Live Location$",
        "^📱💡 Activer la position en direct$",
    ]
    for pattern in info_patterns:
        application.add_handler(
            MessageHandler(filters.TEXT & filters.Regex(pattern), info_command)
        )

    # Language button patterns
    language_patterns = [
        "^🌐 Язык / Language$",
        "^🌐 Language / Язык$",
        "^🌐 Langue / Language$",
    ]
    for pattern in language_patterns:
        application.add_handler(
            MessageHandler(
                filters.TEXT & filters.Regex(pattern), show_language_selection
            )
        )

    # Donate button patterns
    donate_patterns = [
        "^⭐💝 Поддержать проект$",
        "^⭐💝 Support project$",
        "^⭐💝 Soutenir le projet$",
    ]
    for pattern in donate_patterns:
        application.add_handler(
            MessageHandler(filters.TEXT & filters.Regex(pattern), donate_command)
        )

    # Add custom language input handler (must be after button handlers)
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.LOCATION,
            handle_custom_language_input,
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

    # Handler for "show live info" button (after static fact)
    async def show_live_info_callback(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Show live location info when user clicks upsell button."""
        query = update.callback_query
        await query.answer()
        # Reuse existing info_command
        await info_command(update, context)

    application.add_handler(
        CallbackQueryHandler(show_live_info_callback, pattern="^show_live_info$")
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
