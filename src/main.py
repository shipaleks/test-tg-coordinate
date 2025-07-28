"""Main application entry point for NearbyFactBot."""

import logging
import os

from dotenv import load_dotenv
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .handlers.location import (
    handle_edited_location,
    handle_interval_callback,
    handle_location,
)

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    welcome_text = (
        "🗺️ *Добро пожаловать в бот удивительных фактов!*\n\n"
        "🔴 *Живая локация — ваш персональный экскурсовод:*\n"
        "📎 → Location → Share Live Location (15 мин - 8 часов)\n"
        "Автоматические факты каждые 5-60 минут во время прогулки\n\n"
        "📍 *Также доступно:* разовая отправка текущей геопозиции\n"
        "Нажмите кнопку ниже для мгновенного факта о месте\n\n"
        "_Каждый факт — это маленькое открытие рядом с вами!_ ✨"
    )

    # Create location sharing keyboard with live location first
    keyboard = [
        [KeyboardButton("🔴 Поделиться локацией", request_location=True)],
        [KeyboardButton("📖 Как использовать бота")],
    ]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=False
    )

    await update.message.reply_text(
        welcome_text, parse_mode="Markdown", reply_markup=reply_markup
    )


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle info button press."""
    info_text = (
        "📖 *Как использовать бота:*\n\n"
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

    await update.message.reply_text(info_text, parse_mode="Markdown")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors."""
    logger.error(f"Exception while handling an update: {context.error}")


def main() -> None:
    """Main function to run the bot."""
    logger.info("Starting NearbyFactBot...")

    # Get bot token from environment
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

    # Create application
    application = Application.builder().token(bot_token).build()

    # Add command handlers
    application.add_handler(
        MessageHandler(filters.COMMAND & filters.Regex("^/start"), start_command)
    )

    # Add text message handlers
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex("^📖 Как использовать бота$"), info_command
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

    # Add callback query handler for interval selection
    application.add_handler(
        CallbackQueryHandler(handle_interval_callback, pattern="^interval_")
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
