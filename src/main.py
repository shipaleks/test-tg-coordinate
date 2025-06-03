"""Main application entry point for NearbyFactBot."""

import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters, CallbackQueryHandler

from .handlers.location import handle_location, handle_edited_location, handle_interval_callback

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
        "Я — ваш персональный гид по скрытым историям мест. "
        "Отправьте мне локацию, и я расскажу малоизвестный, "
        "но захватывающий факт о месте поблизости.\n\n"
        "*📍 Обычная локация:*\n"
        "1️⃣ Нажмите на скрепку 📎\n"
        "2️⃣ Выберите «Location» 📍\n"
        "3️⃣ Отправьте свою геопозицию\n"
        "4️⃣ Получите мгновенный факт!\n\n"
        "*🔴 Живая локация (для прогулок):*\n"
        "1️⃣ Скрепка 📎 → «Location» 📍\n"
        "2️⃣ Выберите «Share Live Location»\n"
        "3️⃣ Установите время (15 мин - 8 часов)\n"
        "4️⃣ Выберите частоту фактов (5-60 минут)\n"
        "5️⃣ Получайте факты автоматически!\n\n"
        "*Примеры использования:*\n"
        "• Прогулка по историческому центру\n"
        "• Поездка на автомобиле по новому маршруту\n"
        "• Туристическая экскурсия\n"
        "• Исследование незнакомого района\n\n"
        "_Каждый факт — это маленькое открытие!_ ✨"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


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

    # Add handlers
    application.add_handler(
        MessageHandler(filters.COMMAND & filters.Regex("^/start"), start_command)
    )
    application.add_handler(MessageHandler(filters.LOCATION, handle_location))
    
    # Add handler for live location updates (edited messages)
    application.add_handler(
        MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.LOCATION, handle_edited_location)
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
