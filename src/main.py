"""Main application entry point for NearbyFactBot."""

import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from .handlers.location import handle_location, handle_edited_location

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
        "*Как пользоваться:*\n"
        "1️⃣ Нажмите на скрепку 📎\n"
        "2️⃣ Выберите «Location» 📍\n"
        "3️⃣ Отправьте свою геопозицию\n\n"
        "_Каждый факт — это маленькое открытие!_"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors."""
    logger.error(f"Exception while handling an update: {context.error}")


def create_application() -> Application:
    """Create and configure the Telegram bot application."""
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

    return application


async def main() -> None:
    """Main function to run the bot."""
    logger.info("Starting NearbyFactBot...")

    application = create_application()

    # Check if we should use webhook or polling
    webhook_url = os.getenv("WEBHOOK_URL")
    port = int(os.getenv("PORT", "8000"))

    if webhook_url:
        # Use webhook for production
        logger.info(f"Starting webhook on port {port}")
        await application.run_webhook(
            listen="0.0.0.0",
            port=port,
            webhook_url=webhook_url,
        )
    else:
        # Use polling for local development
        logger.info("Starting polling mode")
        await application.run_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
