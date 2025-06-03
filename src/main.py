"""Main application entry point for NearbyFactBot."""

import logging
import os

from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
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
        "• Нажмите кнопку ниже или скрепку 📎 → Location\n"
        "• Получите мгновенный факт!\n\n"
        "*🔴 Живая локация (для прогулок):*\n"
        "• Нажмите кнопку → «Share Live Location»\n"
        "• Установите время (15 мин - 8 часов)\n"
        "• Выберите частоту фактов (5-60 минут)\n"
        "• Получайте факты автоматически!\n\n"
        "*Примеры использования:*\n"
        "• Прогулка по историческому центру\n"
        "• Поездка на автомобиле по новому маршруту\n"
        "• Туристическая экскурсия\n"
        "• Исследование незнакомого района\n\n"
        "_Каждый факт — это маленькое открытие!_ ✨"
    )
    
    # Create location sharing keyboard
    keyboard = [
        [KeyboardButton("📍 Поделиться локацией", request_location=True)],
        [KeyboardButton("ℹ️ Информация"), KeyboardButton("❌ Убрать кнопки")]
    ]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, 
        resize_keyboard=True, 
        one_time_keyboard=False  # Keep keyboard visible for convenience
    )
    
    await update.message.reply_text(
        welcome_text, 
        parse_mode="Markdown", 
        reply_markup=reply_markup
    )


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle info button press."""
    info_text = (
        "ℹ️ *Как пользоваться ботом:*\n\n"
        "*Обычная локация:*\n"
        "Нажмите «📍 Поделиться локацией» → «Отправить мою текущую геопозицию»\n\n"
        "*Живая локация:*\n"
        "Нажмите «📍 Поделиться локацией» → «Транслировать мою геопозицию»\n"
        "Выберите время трансляции → настройте интервал фактов\n\n"
        "*Команды:*\n"
        "/start - перезапустить бота\n\n"
        "_Бот работает только в личных чатах_"
    )
    
    await update.message.reply_text(info_text, parse_mode="Markdown")


async def remove_keyboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle remove keyboard button."""
    await update.message.reply_text(
        "✅ Кнопки убраны.\n\nИспользуйте /start чтобы вернуть их.", 
        reply_markup=ReplyKeyboardRemove()
    )


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
        MessageHandler(filters.TEXT & filters.Regex("^ℹ️ Информация$"), info_command)
    )
    application.add_handler(
        MessageHandler(filters.TEXT & filters.Regex("^❌ Убрать кнопки$"), remove_keyboard_command)
    )
    
    # Add location handlers
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
