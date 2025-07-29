"""Location message handler for Telegram bot."""

import asyncio
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
from ..services.async_donors_wrapper import get_async_donors_db

logger = logging.getLogger(__name__)

# Localized messages for location handler
LOCATION_MESSAGES = {
    'ru': {
        'image_fallback': "⚠️ Изображения не загрузились, но вот факт:\n\n",
        'live_location_received': "🔴 *Живая локация получена!*\n\n📍 Отслеживание на {minutes} минут\n\nКак часто присылать интересные факты?",
        'interval_5min': "Каждые 5 минут",
        'interval_10min': "Каждые 10 минут", 
        'interval_30min': "Каждые 30 минут",
        'interval_60min': "Каждые 60 минут",
        'live_activated': "🔴 *Живая локация активирована!*\n\n📍 Отслеживание: {minutes} минут\n⏰ Факты каждые: {interval} минут\n\n🚀 Сейчас пришлю первый факт, затем буду присылать автоматически!\n\nОстановите sharing чтобы завершить сессию.",
        'place_label': "📍 *Место:*",
        'fact_label': "💡 *Факт:*",
        'live_fact_label': "🔴 *Факт #{number}*",
        'attraction_address': "Достопримечательность: {place}",
        'static_fact_format': "📍 *Место:* {place}\n\n💡 *Факт:* {fact}",
        'live_fact_format': "🔴 *Факт #{number}*\n\n📍 *Место:* {place}\n\n💡 *Факт:* {fact}",
        'error_no_info': "😔 *Упс!*\n\nНе удалось найти интересную информацию о данном месте.\nПопробуйте немного сместиться или отправить другую локацию.",
        'near_you': "рядом с вами"
    },
    'en': {
        'image_fallback': "⚠️ Images failed to load, but here's the fact:\n\n",
        'live_location_received': "🔴 *Live location received!*\n\n📍 Tracking for {minutes} minutes\n\nHow often should I send interesting facts?",
        'interval_5min': "Every 5 minutes",
        'interval_10min': "Every 10 minutes",
        'interval_30min': "Every 30 minutes", 
        'interval_60min': "Every 60 minutes",
        'live_activated': "🔴 *Live location activated!*\n\n📍 Tracking: {minutes} minutes\n⏰ Facts every: {interval} minutes\n\n🚀 I'll send the first fact now, then continue automatically!\n\nStop sharing to end the session.",
        'place_label': "📍 *Place:*",
        'fact_label': "💡 *Fact:*",
        'live_fact_label': "🔴 *Fact #{number}*",
        'attraction_address': "Attraction: {place}",
        'static_fact_format': "📍 *Place:* {place}\n\n💡 *Fact:* {fact}",
        'live_fact_format': "🔴 *Fact #{number}*\n\n📍 *Place:* {place}\n\n💡 *Fact:* {fact}",
        'error_no_info': "😔 *Oops!*\n\nCouldn't find interesting information about this location.\nTry moving slightly or sending a different location.",
        'near_you': "near you"
    }
    # Add more languages as needed
}


async def get_localized_message(user_id: int, key: str, **kwargs) -> str:
    """Get localized message for user."""
    try:
        donors_db = await get_async_donors_db()
        user_language = await donors_db.get_user_language(user_id)
        messages = LOCATION_MESSAGES.get(user_language, LOCATION_MESSAGES['en'])
        message = messages.get(key, LOCATION_MESSAGES['en'].get(key, key))
        return message.format(**kwargs) if kwargs else message
    except Exception as e:
        logger.warning(f"Error getting localized message: {e}")
        # Fallback to English
        message = LOCATION_MESSAGES['en'].get(key, key)
        return message.format(**kwargs) if kwargs else message


async def send_fact_with_images(bot, chat_id, formatted_response, search_keywords, place, user_id=None, reply_to_message_id=None):
    """Send fact message with Wikipedia images if available.
    
    Args:
        bot: Telegram bot instance
        chat_id: Chat ID to send to
        formatted_response: Formatted text response
        search_keywords: Keywords to search images for
        place: Place name for caption
        user_id: User ID for localization (optional)
        reply_to_message_id: Message ID to reply to (optional)
    """
    try:
        # Try to get Wikipedia images
        openai_client = get_openai_client()
        image_urls = await openai_client.get_wikipedia_images(search_keywords, max_images=4)  # Max 4 for media group
        
        if image_urls:
            # Try sending all images with text as media group
            try:
                logger.info(f"Attempting to send fact with {len(image_urls)} images for {place}")
                logger.debug(f"Formatted response length: {len(formatted_response)} chars")
                
                if len(formatted_response) <= 1024:
                    # Caption fits in Telegram limit, send as media group with caption
                    media_list = []
                    for i, image_url in enumerate(image_urls):
                        if i == 0:
                            # First image gets the full fact as caption
                            media_list.append(InputMediaPhoto(media=image_url, caption=formatted_response, parse_mode="Markdown"))
                        else:
                            # Other images get no caption
                            media_list.append(InputMediaPhoto(media=image_url))
                    
                    await bot.send_media_group(
                        chat_id=chat_id,
                        media=media_list,
                        reply_to_message_id=reply_to_message_id
                    )
                    logger.info(f"Successfully sent {len(image_urls)} images with caption in media group for {place}")
                else:
                    # Caption too long, send text first then all images as media group
                    await bot.send_message(
                        chat_id=chat_id,
                        text=formatted_response,
                        parse_mode="Markdown",
                        reply_to_message_id=reply_to_message_id
                    )
                    
                    # Send all images as media group without captions
                    media_list = []
                    for image_url in image_urls:
                        media_list.append(InputMediaPhoto(media=image_url))
                    
                    await bot.send_media_group(
                        chat_id=chat_id,
                        media=media_list
                    )
                    logger.info(f"Successfully sent long text + {len(image_urls)} images as media group for {place}")
                return
                
            except Exception as media_group_error:
                logger.error(f"Failed to send text + media group: {media_group_error}")
                logger.error(f"Error type: {type(media_group_error)}")
                logger.error(f"Image URLs that failed: {[img.media for img in media_list]}")
                
                # Try with fewer images if we had multiple images
                if len(image_urls) > 2:
                    logger.info(f"Retrying with fewer images (2 instead of {len(image_urls)})")
                    try:
                        # Retry with only first 2 images
                        retry_media_list = []
                        for i, image_url in enumerate(image_urls[:2]):
                            if i == 0:
                                retry_media_list.append(InputMediaPhoto(media=image_url, caption=formatted_response, parse_mode="Markdown"))
                            else:
                                retry_media_list.append(InputMediaPhoto(media=image_url))
                        
                        await bot.send_media_group(
                            chat_id=chat_id,
                            media=retry_media_list,
                            reply_to_message_id=reply_to_message_id
                        )
                        logger.info(f"Successfully sent {len(retry_media_list)} images on retry for {place}")
                        return
                    except Exception as retry_error:
                        logger.error(f"Retry with fewer images also failed: {retry_error}")
                
                # Check if text was sent successfully by trying to send it again
                # (This is a fallback in case the text sending also failed)
                try:
                    fallback_message = await get_localized_message(user_id or 0, 'image_fallback') if user_id else "⚠️ Изображения не загрузились, но вот факт:\n\n"
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"{fallback_message}{formatted_response}",
                        parse_mode="Markdown",
                        reply_to_message_id=reply_to_message_id
                    )
                    logger.info(f"Sent fallback text-only message for {place}")
                    return
                except Exception as text_fallback_error:
                    logger.error(f"Failed to send fallback text: {text_fallback_error}")
                
                # Last resort: try sending individual images
                try:
                    # Try to send individual images (up to 2 to avoid spam)
                    successful_images = 0
                    for image_url in image_urls[:2]:  # Limit to 2 images
                        try:
                            await bot.send_photo(
                                chat_id=chat_id,
                                photo=image_url,
                                caption=f"📸 {place}",
                                reply_to_message_id=reply_to_message_id
                            )
                            successful_images += 1
                        except Exception as individual_error:
                            logger.debug(f"Failed to send individual image: {individual_error}")
                            continue
                    
                    if successful_images > 0:
                        logger.info(f"Sent {successful_images} individual images (no text) for {place}")
                    else:
                        logger.warning(f"All image sending methods failed for {place}")
                    return
                    
                except Exception as individual_fallback_error:
                    logger.error(f"Failed to send individual images fallback: {individual_fallback_error}")
        
        # No images found or all fallbacks failed, send just the text
        await bot.send_message(
            chat_id=chat_id,
            text=formatted_response,
            parse_mode="Markdown",
            reply_to_message_id=reply_to_message_id
        )
        logger.info(f"Sent fact without images for {place}")
            
    except Exception as e:
        logger.warning(f"Failed to send fact with images: {e}")
        # Final fallback to text-only message
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
                        await get_localized_message(user_id, 'interval_5min'),
                        callback_data=f"interval_5_{lat}_{lon}_{location.live_period}",
                    ),
                    InlineKeyboardButton(
                        await get_localized_message(user_id, 'interval_10min'),
                        callback_data=f"interval_10_{lat}_{lon}_{location.live_period}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        await get_localized_message(user_id, 'interval_30min'),
                        callback_data=f"interval_30_{lat}_{lon}_{location.live_period}",
                    ),
                    InlineKeyboardButton(
                        await get_localized_message(user_id, 'interval_60min'),
                        callback_data=f"interval_60_{lat}_{lon}_{location.live_period}",
                    ),
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Send interval selection message
            interval_response = await get_localized_message(user_id, 'live_location_received', minutes=location.live_period // 60)

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

        # For static locations, send immediate fact with history tracking
        openai_client = get_openai_client()
        
        # Use coordinates as stable cache key instead of unreliable AI-generated keywords
        # Round coordinates to ~111m precision for caching (3 decimal places)
        cache_key = f"{round(lat, 3)}_{round(lon, 3)}"
        logger.info(f"Static location - using coordinate-based cache key: '{cache_key}'")
        
        # Get fact with history using coordinate key
        response = await openai_client.get_nearby_fact_with_history(lat, lon, cache_key, user_id)
        
        # Parse the response to extract place and fact
        logger.info(f"Final response for static location: {response[:100]}...")
        place = await get_localized_message(user_id, 'near_you')  # Default location
        fact = response  # Default to full response if parsing fails
        final_search_keywords = None

        # Try to parse structured response from <answer> tags first
        answer_match = re.search(r"<answer>(.*?)</answer>", response, re.DOTALL)
        if answer_match:
            answer_content = answer_match.group(1).strip()
            
            # Extract location from answer content
            location_match = re.search(r"Location:\s*(.+?)(?:\n|$)", answer_content)
            if location_match:
                place = location_match.group(1).strip()
            
            # Extract search keywords from answer content
            search_match = re.search(r"Search:\s*(.+?)(?:\n|$)", answer_content)
            if search_match:
                final_search_keywords = search_match.group(1).strip()
            
            # Extract fact from answer content
            fact_match = re.search(r"Interesting fact:\s*(.*?)(?:\n\s*$|$)", answer_content, re.DOTALL)
            if fact_match:
                fact = fact_match.group(1).strip()
        
        # Legacy fallback for old format responses
        else:
            lines = response.split("\n")
            
            # Try to parse old structured response format
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
            
            # Extract search keywords from legacy format
            legacy_search_match = re.search(r"Поиск:\s*(.+?)(?:\n|$)", response)
            if legacy_search_match:
                final_search_keywords = legacy_search_match.group(1).strip()

        # Format the response for static location
        formatted_response = await get_localized_message(user_id, 'static_fact_format', place=place, fact=fact)
        
        # Send fact with images using extracted search keywords
        if final_search_keywords:
            await send_fact_with_images(
                context.bot, 
                chat_id, 
                formatted_response, 
                final_search_keywords, 
                place,
                user_id=user_id,
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
                    address=await get_localized_message(user_id, 'attraction_address', place=place),
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
        error_response = await get_localized_message(user_id, 'error_no_info')

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
        if len(data_parts) != 5:
            logger.error(f"Invalid callback data format: {query.data}")
            await query.edit_message_text(
                text="😔 Invalid callback data. Please try again.",
                parse_mode="Markdown",
            )
            return
            
        interval_minutes = int(data_parts[1])
        lat = float(data_parts[2])
        lon = float(data_parts[3])
        live_period = int(data_parts[4])

        user_id = update.effective_user.id
        chat_id = update.effective_chat.id

        logger.info(f"Processing interval callback for user {user_id}: {interval_minutes} min interval")

        # Start live location tracking with selected interval
        tracker = get_live_location_tracker()
        
        # Add small delay to ensure any previous session cleanup is complete
        await asyncio.sleep(0.1)
        
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
        confirmation_text = await get_localized_message(user_id, 'live_activated', 
                                                 minutes=live_period // 60, 
                                                 interval=interval_minutes)

        await query.edit_message_text(text=confirmation_text, parse_mode="Markdown")

        # Send initial fact immediately (live location - detailed with o4-mini)
        openai_client = get_openai_client()
        response = await openai_client.get_nearby_fact(lat, lon, is_live_location=True, user_id=user_id)

        # Parse the response to extract place and fact
        place = await get_localized_message(user_id, 'near_you')  # Default location
        fact = response  # Default to full response if parsing fails
        search_keywords = ""

        # Try to parse structured response from <answer> tags first
        answer_match = re.search(r"<answer>(.*?)</answer>", response, re.DOTALL)
        if answer_match:
            answer_content = answer_match.group(1).strip()
            
            # Extract location from answer content
            location_match = re.search(r"Location:\s*(.+?)(?:\n|$)", answer_content)
            if location_match:
                place = location_match.group(1).strip()
            
            # Extract search keywords from answer content
            search_match = re.search(r"Search:\s*(.+?)(?:\n|$)", answer_content)
            if search_match:
                search_keywords = search_match.group(1).strip()
            
            # Extract fact from answer content
            fact_match = re.search(r"Interesting fact:\s*(.*?)(?:\n\s*$|$)", answer_content, re.DOTALL)
            if fact_match:
                fact = fact_match.group(1).strip()
        
        # Legacy fallback for old format responses
        else:
            lines = response.split("\n")
            
            # Try to parse old structured response format
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
        initial_fact_response = await get_localized_message(user_id, 'live_fact_format', number=fact_number, place=place, fact=fact)

        # Save initial fact to history
        if user_id in tracker._active_sessions:
            tracker._active_sessions[user_id].fact_history.append(f"{place}: {fact}")

        # Send initial fact with images using extracted search keywords
        if search_keywords:
            await send_fact_with_images(
                context.bot, 
                chat_id, 
                initial_fact_response, 
                search_keywords, 
                place,
                user_id=user_id
            )
        else:
            # Legacy fallback: try to extract search keywords from old format
            legacy_search_match = re.search(r"Поиск:\s*(.+?)(?:\n|$)", response)
            if legacy_search_match:
                legacy_search_keywords = legacy_search_match.group(1).strip()
                await send_fact_with_images(
                    context.bot, 
                    chat_id, 
                    initial_fact_response, 
                    legacy_search_keywords, 
                    place,
                    user_id=user_id
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
                    address=await get_localized_message(user_id, 'attraction_address', place=place),
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
            text="😔 An error occurred while setting up live location. Please try again.",
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

            # Send confirmation message (default to English since we can't get user_id from this context)
            stop_response = (
                "✅ *Live location stopped*\n\n"
                "Thank you for using NearbyFactBot! 🗺️✨"
            )

            await context.bot.send_message(
                chat_id=chat_id,
                text=stop_response,
                parse_mode="Markdown",
            )

            logger.info(f"Live location tracking stopped for user {user_id}")

    except Exception as e:
        logger.error(f"Error stopping live location for user {user_id}: {e}")
