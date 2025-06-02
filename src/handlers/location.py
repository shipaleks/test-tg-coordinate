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
        response = await openai_client.get_nearby_fact(lat, lon)

        # Parse the response to extract place and fact
        lines = response.split("\n")
        place = "рядом с вами"
        fact = response  # Default to full response if parsing fails

        # Try to parse structured response
        for i, line in enumerate(lines):
            if line.startswith("Локация:"):
                place = line.replace("Локация:", "").strip()
            elif line.startswith("Интересный факт:"):
                # Join all lines after Интересный факт: as the fact might be multiline
                fact_lines = []
                # Start from the current line, removing the prefix
                fact_lines.append(line.replace("Интересный факт:", "").strip())
                # Add all subsequent lines
                for j in range(i + 1, len(lines)):
                    if lines[j].strip():  # Only add non-empty lines
                        fact_lines.append(lines[j].strip())
                fact = " ".join(fact_lines)
                break

        # Format the response with simple styling
        formatted_response = f"📍 *Место:* {place}\n\n💡 *Факт:* {fact}"

        # Send the fact to user with Markdown formatting
        await update.message.reply_text(
            text=formatted_response,
            reply_to_message_id=update.message.message_id,
            parse_mode="Markdown",
        )

        logger.info(f"Sent fact to user {update.effective_user.id}")

    except Exception as e:
        logger.error(
            f"Error processing location for user {update.effective_user.id}: {e}"
        )

        # Send error message to user
        error_response = (
            "😔 *Упс!*\n\n"
            "Не удалось найти интересную информацию о данном месте.\n"
            "Попробуйте отправить другую локацию!"
        )

        await update.message.reply_text(
            text=error_response,
            reply_to_message_id=update.message.message_id,
            parse_mode="Markdown",
        )
