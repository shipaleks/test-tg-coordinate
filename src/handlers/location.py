"""Location message handler for Telegram bot."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from ..services.openai_client import get_openai_client

logger = logging.getLogger(__name__)


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle location messages from users.

    Args:
        update: Telegram update containing location message
        context: Bot context
    """
    if not update.message or not update.message.location:
        logger.warning("Received location handler call without location data")
        return

    location = update.message.location
    lat = location.latitude
    lon = location.longitude

    logger.info(f"Received location: {lat}, {lon} from user {update.effective_user.id}")

    try:
        # Send typing indicator
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action="typing"
        )

        # Get fact from OpenAI
        openai_client = get_openai_client()
        fact = await openai_client.get_nearby_fact(lat, lon)

        # Send the fact to user
        await update.message.reply_text(
            text=f"🗺️ {fact}", reply_to_message_id=update.message.message_id
        )

        logger.info(f"Sent fact to user {update.effective_user.id}")

    except Exception as e:
        logger.error(
            f"Error processing location for user {update.effective_user.id}: {e}"
        )

        # Send error message to user
        await update.message.reply_text(
            text="😔 Не найдено мест поблизости",
            reply_to_message_id=update.message.message_id,
        )
