"""Location message handler for Telegram bot."""

import logging
import re

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from ..services.live_location_tracker import get_live_location_tracker
from ..services.openai_client import get_openai_client

logger = logging.getLogger(__name__)


async def send_fact_with_images(bot, chat_id, formatted_response, search_keywords, place, reply_to_message_id=None):
    """Send fact message with Wikipedia images if available.
    
    Args:
        bot: Telegram bot instance
        chat_id: Chat ID to send to
        formatted_response: Formatted text response
        search_keywords: Keywords to search images for
        place: Place name for caption
        reply_to_message_id: Message ID to reply to (optional)
    """
    try:
        # Try to get Wikipedia images
        openai_client = get_openai_client()
        image_urls = await openai_client.get_wikipedia_images(search_keywords, max_images=4)  # Max 4 for media group
        
        if image_urls:
            # Send images as media group with the fact as caption on first image
            media_list = []
            for i, image_url in enumerate(image_urls):
                if i == 0:
                    # First image gets the full fact as caption
                    media_list.append(InputMediaPhoto(media=image_url, caption=formatted_response, parse_mode="Markdown"))
                else:
                    # Other images get place name as caption
                    media_list.append(InputMediaPhoto(media=image_url, caption=f"📸 {place}"))
            
            await bot.send_media_group(
                chat_id=chat_id,
                media=media_list,
                reply_to_message_id=reply_to_message_id
            )
            logger.info(f"Sent {len(image_urls)} Wikipedia images with fact for {place}")
        else:
            # No images found, send just the text
            await bot.send_message(
                chat_id=chat_id,
                text=formatted_response,
                parse_mode="Markdown",
                reply_to_message_id=reply_to_message_id
            )
            logger.info(f"Sent fact without images for {place}")
            
    except Exception as e:
        logger.warning(f"Failed to send fact with images: {e}")
        # Fallback to text-only message
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=formatted_response,
                parse_mode="Markdown",
                reply_to_message_id=reply_to_message_id
            )
        except Exception as fallback_error:
            logger.error(f"Failed to send fallback message: {fallback_error}")


def get_location_keyboard() -> ReplyKeyboardMarkup:
    """Get the location sharing keyboard."""
    keyboard = [
        [KeyboardButton("📱 Как поделиться Live Location")],
        [KeyboardButton("🔴 Поделиться локацией", request_location=True)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle location messages from users.

    Args:
        update: Telegram update containing location message
        context: Bot context
    """
    if not update.message or not update.message.location:
        logger.warning(
            f"Received location handler call without location data. Update: {update}"
        )
        logger.warning(
            f"Update.message: {update.message if update.message else 'None'}"
        )
        if update.message:
            logger.warning(
                f"Message.location: {update.message.location if hasattr(update.message, 'location') else 'No location attr'}"
            )
        return

    location = update.message.location
    lat = location.latitude
    lon = location.longitude
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    logger.info(
        f"Received location: {lat}, {lon} from user {user_id}, live_period: {location.live_period if location.live_period else 'None'}"
    )

    try:
        # Send typing indicator
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        # Check if this is a live location
        if location.live_period:
            # This is a live location - show interval selection
            keyboard = [
                [
                    InlineKeyboardButton(
                        "Каждые 5 минут",
                        callback_data=f"interval_5_{lat}_{lon}_{location.live_period}",
                    ),
                    InlineKeyboardButton(
                        "Каждые 10 минут",
                        callback_data=f"interval_10_{lat}_{lon}_{location.live_period}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "Каждые 30 минут",
                        callback_data=f"interval_30_{lat}_{lon}_{location.live_period}",
                    ),
                    InlineKeyboardButton(
                        "Каждые 60 минут",
                        callback_data=f"interval_60_{lat}_{lon}_{location.live_period}",
                    ),
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Send interval selection message
            interval_response = (
                "🔴 *Живая локация получена!*\n\n"
                f"📍 Отслеживание на {location.live_period // 60} минут\n\n"
                "Как часто присылать интересные факты?"
            )

            await update.message.reply_text(
                text=interval_response,
                reply_markup=reply_markup,
                reply_to_message_id=update.message.message_id,
                parse_mode="Markdown",
            )

            logger.info(
                f"Sent interval selection for live location from user {user_id}"
            )
            return  # Don't send initial fact yet, wait for interval selection

        # For static locations, send immediate fact
        # Get fact from OpenAI (static location - fast with gpt-4.1)
        openai_client = get_openai_client()
        response = await openai_client.get_nearby_fact(lat, lon, is_live_location=False)

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

        # Format the response for static location
        formatted_response = f"📍 *Место:* {place}\n\n💡 *Факт:* {fact}"

        # Try to get search keywords and send fact with images
        search_match = re.search(r"Поиск:\s*(.+?)(?:\n|$)", response)
        if search_match:
            search_keywords = search_match.group(1).strip()
            await send_fact_with_images(
                context.bot, 
                chat_id, 
                formatted_response, 
                search_keywords, 
                place, 
                reply_to_message_id=update.message.message_id
            )
        else:
            # No search keywords, send just text
            await update.message.reply_text(
                text=formatted_response,
                reply_to_message_id=update.message.message_id,
                parse_mode="Markdown",
            )

        # Try to parse coordinates and send location for navigation using search keywords
        coordinates = await openai_client.parse_coordinates_from_response(response)
        if coordinates:
            venue_lat, venue_lon = coordinates
            try:
                # Send venue with location for navigation
                await context.bot.send_venue(
                    chat_id=chat_id,
                    latitude=venue_lat,
                    longitude=venue_lon,
                    title=place,
                    address=f"Достопримечательность: {place}",
                    reply_to_message_id=update.message.message_id,
                )
                logger.info(
                    f"Sent venue location for navigation: {place} at {venue_lat}, {venue_lon}"
                )
            except Exception as venue_error:
                logger.warning(f"Failed to send venue: {venue_error}")
                # Fallback to simple location
                try:
                    await context.bot.send_location(
                        chat_id=chat_id,
                        latitude=venue_lat,
                        longitude=venue_lon,
                        reply_to_message_id=update.message.message_id,
                    )
                    logger.info(f"Sent location as fallback: {venue_lat}, {venue_lon}")
                except Exception as loc_error:
                    logger.error(f"Failed to send location: {loc_error}")

        logger.info(f"Sent fact to user {user_id}")

    except Exception as e:
        logger.error(f"Error processing location for user {user_id}: {e}")

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


async def handle_interval_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle interval selection for live location.

    Args:
        update: Telegram update containing callback query
        context: Bot context
    """
    query = update.callback_query
    await query.answer()

    try:
        # Parse callback data: interval_<minutes>_<lat>_<lon>_<live_period>
        data_parts = query.data.split("_")
        interval_minutes = int(data_parts[1])
        lat = float(data_parts[2])
        lon = float(data_parts[3])
        live_period = int(data_parts[4])

        user_id = update.effective_user.id
        chat_id = update.effective_chat.id

        # Start live location tracking with selected interval
        tracker = get_live_location_tracker()
        await tracker.start_live_location(
            user_id=user_id,
            chat_id=chat_id,
            latitude=lat,
            longitude=lon,
            live_period=live_period,
            bot=context.bot,
            fact_interval_minutes=interval_minutes,
        )

        # Update the message to show confirmation
        confirmation_text = (
            "🔴 *Живая локация активирована!*\n\n"
            f"📍 Отслеживание: {live_period // 60} минут\n"
            f"⏰ Факты каждые: {interval_minutes} минут\n\n"
            "🚀 Сейчас пришлю первый факт, затем буду присылать автоматически!\n\n"
            "Остановите sharing чтобы завершить сессию."
        )

        await query.edit_message_text(text=confirmation_text, parse_mode="Markdown")

        # Send initial fact immediately (live location - detailed with o4-mini)
        openai_client = get_openai_client()
        response = await openai_client.get_nearby_fact(lat, lon, is_live_location=True)

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

        # Get the tracker to increment fact counter for initial fact
        tracker = get_live_location_tracker()
        if user_id in tracker._active_sessions:
            tracker._active_sessions[user_id].fact_count += 1
            fact_number = tracker._active_sessions[user_id].fact_count
        else:
            fact_number = 1  # Fallback

        # Format the initial fact with number
        initial_fact_response = (
            f"🔴 *Факт #{fact_number}*\n\n📍 *Место:* {place}\n\n💡 *Факт:* {fact}"
        )

        # Save initial fact to history
        if user_id in tracker._active_sessions:
            tracker._active_sessions[user_id].fact_history.append(f"{place}: {fact}")

        # Send initial fact with images
        search_match = re.search(r"Поиск:\s*(.+?)(?:\n|$)", response)
        if search_match:
            search_keywords = search_match.group(1).strip()
            await send_fact_with_images(
                context.bot, 
                chat_id, 
                initial_fact_response, 
                search_keywords, 
                place
            )
        else:
            # No search keywords, send just text
            await context.bot.send_message(
                chat_id=chat_id,
                text=initial_fact_response,
                parse_mode="Markdown",
            )

        # Try to parse coordinates and send location for navigation using search keywords (live location)
        coordinates = await openai_client.parse_coordinates_from_response(response)
        if coordinates:
            venue_lat, venue_lon = coordinates
            try:
                # Send venue with location for navigation
                await context.bot.send_venue(
                    chat_id=chat_id,
                    latitude=venue_lat,
                    longitude=venue_lon,
                    title=place,
                    address=f"Достопримечательность: {place}",
                )
                logger.info(
                    f"Sent venue location for live session navigation: {place} at {venue_lat}, {venue_lon}"
                )
            except Exception as venue_error:
                logger.warning(f"Failed to send venue for live session: {venue_error}")
                # Fallback to simple location
                try:
                    await context.bot.send_location(
                        chat_id=chat_id,
                        latitude=venue_lat,
                        longitude=venue_lon,
                    )
                    logger.info(
                        f"Sent location as fallback for live session: {venue_lat}, {venue_lon}"
                    )
                except Exception as loc_error:
                    logger.error(
                        f"Failed to send location for live session: {loc_error}"
                    )

        logger.info(
            f"Started live location tracking for user {user_id} with {interval_minutes} min interval"
        )

    except Exception as e:
        logger.error(f"Error handling interval callback: {e}")
        await query.edit_message_text(
            text="😔 Произошла ошибка при настройке живой локации. Попробуйте еще раз.",
            parse_mode="Markdown",
        )


async def handle_edited_location(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle live location updates (edited messages).

    Args:
        update: Telegram update containing edited location message
        context: Bot context
    """
    if not update.edited_message or not update.edited_message.location:
        logger.warning(
            f"Received edited location handler call without location data. Update: {update}"
        )
        logger.warning(
            f"Update.edited_message: {update.edited_message if update.edited_message else 'None'}"
        )
        if update.edited_message:
            logger.warning(
                f"Edited_message.location: {update.edited_message.location if hasattr(update.edited_message, 'location') else 'No location attr'}"
            )
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


async def handle_stop_live_location(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
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
                "✅ *Живая локация остановлена*\n\n"
                "Спасибо что пользуетесь NearbyFactBot! 🗺️✨"
            )

            await context.bot.send_message(
                chat_id=chat_id,
                text=stop_response,
                parse_mode="Markdown",
            )

            logger.info(f"Live location tracking stopped for user {user_id}")

    except Exception as e:
        logger.error(f"Error stopping live location for user {user_id}: {e}")
