"""Location message handler for Telegram bot."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from ..services.openai_client import get_openai_client
from ..services.live_location_tracker import get_live_location_tracker

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
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    logger.info(f"Received location: {lat}, {lon} from user {user_id}")

    try:
        # Send typing indicator
        await context.bot.send_chat_action(
            chat_id=chat_id, action="typing"
        )

        # Check if this is a live location
        if location.live_period:
            # This is a live location - start tracking
            tracker = get_live_location_tracker()
            
            await tracker.start_live_location(
                user_id=user_id,
                chat_id=chat_id,
                latitude=lat,
                longitude=lon,
                live_period=location.live_period,
                bot=context.bot,
            )
            
            # Send confirmation message
            confirmation_response = (
                "🔴 *Live Location Started*\n\n"
                f"📍 Tracking your location for {location.live_period // 60} minutes\n"
                "💡 I'll send you interesting facts every 10 minutes!\n\n"
                "Stop sharing your location to end the session."
            )
            
            await update.message.reply_text(
                text=confirmation_response,
                reply_to_message_id=update.message.message_id,
                parse_mode="Markdown",
            )
            
            logger.info(f"Started live location tracking for user {user_id} for {location.live_period}s")
        
        # For both static and live locations, send immediate fact
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

        # Format the response with appropriate indicator
        if location.live_period:
            formatted_response = f"🔴 *Initial Fact*\n\n📍 *Место:* {place}\n\n💡 *Факт:* {fact}"
        else:
            formatted_response = f"📍 *Место:* {place}\n\n💡 *Факт:* {fact}"

        # Send the fact to user with Markdown formatting
        await update.message.reply_text(
            text=formatted_response,
            reply_to_message_id=update.message.message_id,
            parse_mode="Markdown",
        )

        logger.info(f"Sent fact to user {user_id}")

    except Exception as e:
        logger.error(
            f"Error processing location for user {user_id}: {e}"
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


async def handle_edited_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle live location updates (edited messages).

    Args:
        update: Telegram update containing edited location message
        context: Bot context
    """
    if not update.edited_message or not update.edited_message.location:
        logger.warning("Received edited location handler call without location data")
        return

    location = update.edited_message.location
    lat = location.latitude
    lon = location.longitude
    user_id = update.effective_user.id

    logger.info(f"Received live location update: {lat}, {lon} from user {user_id}")

    try:
        # Update coordinates in the live tracker
        tracker = get_live_location_tracker()
        await tracker.update_live_location(user_id, lat, lon)
        
        logger.info(f"Updated live location for user {user_id}")

    except Exception as e:
        logger.error(f"Error updating live location for user {user_id}: {e}")


async def handle_stop_live_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle when live location sharing stops.

    Args:
        update: Telegram update
        context: Bot context
    """
    # This handler will be called when live location ends
    # We detect this by checking if a user had an active session that's no longer updating
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    try:
        tracker = get_live_location_tracker()
        
        if tracker.is_user_tracking(user_id):
            await tracker.stop_live_location(user_id)
            
            # Send confirmation message
            stop_response = (
                "✅ *Live Location Stopped*\n\n"
                "Location sharing has ended. Thank you for using NearbyFactBot!"
            )
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=stop_response,
                parse_mode="Markdown",
            )
            
            logger.info(f"Live location tracking stopped for user {user_id}")

    except Exception as e:
        logger.error(f"Error stopping live location for user {user_id}: {e}")
