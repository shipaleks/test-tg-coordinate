"""Donation handlers for Telegram Stars payments."""

import logging
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Update,
)
from telegram.ext import ContextTypes

from ..services.donors_db import get_donors_db

logger = logging.getLogger(__name__)


async def donate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /donate command."""
    user = update.effective_user
    
    # Check current premium status
    donors_db = get_donors_db()
    is_premium = donors_db.is_premium_user(user.id)
    donor_info = donors_db.get_donor_info(user.id)
    
    # Create status text
    if donor_info:
        status_text = f"🎁 *Донатер проекта*\n📊 Всего звезд: {donor_info['total_stars']}⭐\n🧠 o3 модель активна для живых локаций\n\n"
    else:
        status_text = ""
    
    donate_text = (
        "🌟 *Поддержать проект*\n\n"
        + status_text +
        "Ваша поддержка помогает:\n"
        "• 🤖 Оплачивать OpenAI API для качественных фактов\n"
        "• 🚀 Развивать новые функции бота\n"
        "• 📡 Поддерживать сервер 24/7\n\n"
        "💝 *Любая поддержка добровольна и очень ценится!*"
    )
    
    # Create donation buttons
    keyboard = [
        [
            InlineKeyboardButton("10⭐", callback_data="donate_10"),
            InlineKeyboardButton("50⭐", callback_data="donate_50"),
            InlineKeyboardButton("100⭐", callback_data="donate_100"),
        ],
        [
            InlineKeyboardButton("💰 Другая сумма", callback_data="donate_custom"),
        ],
    ]
    
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        donate_text, 
        parse_mode="Markdown", 
        reply_markup=reply_markup
    )


async def handle_donation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle donation button callbacks."""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    chat_id = query.message.chat_id
    
    
    # Handle donation amounts
    if query.data.startswith("donate_"):
        amount_str = query.data.replace("donate_", "")
        
        if amount_str == "custom":
            custom_keyboard = [
                [
                    InlineKeyboardButton("25⭐", callback_data="donate_25"),
                    InlineKeyboardButton("75⭐", callback_data="donate_75"),
                ],
                [
                    InlineKeyboardButton("200⭐", callback_data="donate_200"),
                    InlineKeyboardButton("500⭐", callback_data="donate_500"),
                ],
                [
                    InlineKeyboardButton("← Назад", callback_data="donate_back"),
                ],
            ]
            custom_markup = InlineKeyboardMarkup(custom_keyboard)
            
            await query.edit_message_text(
                "💰 *Выберите сумму:*\n\n"
                "✨ Любая поддержка очень ценится!",
                parse_mode="Markdown",
                reply_markup=custom_markup
            )
            return
        
        if amount_str == "back":
            # Go back to main donate screen - we need to recreate the original message
            user = query.from_user
            donors_db = get_donors_db()
            is_premium = donors_db.is_premium_user(user.id)
            donor_info = donors_db.get_donor_info(user.id)
            
            # Create status text
            if donor_info:
                status_text = f"🎁 *Донатер проекта*\n📊 Всего звезд: {donor_info['total_stars']}⭐\n🧠 o3 модель активна для живых локаций\n\n"
            else:
                status_text = ""
            
            donate_text = (
                "🌟 *Поддержать проект*\n\n"
                + status_text +
                "Ваша поддержка помогает:\n"
                "• 🤖 Оплачивать OpenAI API для качественных фактов\n"
                "• 🚀 Развивать новые функции бота\n"
                "• 📡 Поддерживать сервер 24/7\n\n"
                "💝 *Любая поддержка добровольна и очень ценится!*"
            )
            
            # Create donation buttons
            keyboard = [
                [
                    InlineKeyboardButton("10⭐", callback_data="donate_10"),
                    InlineKeyboardButton("50⭐", callback_data="donate_50"),
                    InlineKeyboardButton("100⭐", callback_data="donate_100"),
                ],
                [
                    InlineKeyboardButton("💰 Другая сумма", callback_data="donate_custom"),
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                donate_text, 
                parse_mode="Markdown", 
                reply_markup=reply_markup
            )
            return
        
        try:
            amount = int(amount_str)
        except ValueError:
            await query.edit_message_text("❌ Некорректная сумма")
            return
        
        # Create and send invoice
        await send_donation_invoice(
            context.bot,
            chat_id,
            user,
            amount,
            query.message.message_id
        )


async def send_donation_invoice(bot, chat_id: int, user, stars_amount: int, reply_to_message_id: int = None):
    """Send Telegram Stars invoice for donation.
    
    Args:
        bot: Telegram bot instance
        chat_id: Chat ID to send invoice to
        user: User object
        stars_amount: Amount of stars to request
        reply_to_message_id: Message ID to reply to
    """
    try:
        # Create invoice payload for tracking
        payload = f"donate_{user.id}_{stars_amount}"
        
        title = f"Поддержка проекта {stars_amount}⭐"
        description = f"Спасибо за поддержку проекта! Ваши {stars_amount} звезд помогут улучшить качество бота."
        
        # Create price in Telegram Stars
        prices = [LabeledPrice(label=f"{stars_amount} Telegram Stars", amount=stars_amount)]
        
        # Send invoice
        await bot.send_invoice(
            chat_id=chat_id,
            title=title,
            description=description,
            payload=payload,
            provider_token="",  # Empty for Telegram Stars
            currency="XTR",  # Telegram Stars currency
            prices=prices,
            reply_to_message_id=reply_to_message_id,
        )
        
        logger.info(f"Sent donation invoice: user_id={user.id}, amount={stars_amount} stars")
        
    except Exception as e:
        logger.error(f"Failed to send donation invoice: {e}")
        await bot.send_message(
            chat_id=chat_id,
            text="❌ Не удалось создать инвойс. Попробуйте позже.",
            reply_to_message_id=reply_to_message_id
        )


async def handle_pre_checkout_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle pre-checkout query (approve payment)."""
    query = update.pre_checkout_query
    
    try:
        # Validate the payload
        if not query.invoice_payload.startswith("donate_"):
            logger.warning(f"Invalid invoice payload: {query.invoice_payload}")
            await query.answer(ok=False, error_message="Некорректный платеж")
            return
        
        # Parse payload
        parts = query.invoice_payload.split("_")
        if len(parts) != 3:
            logger.warning(f"Invalid payload format: {query.invoice_payload}")
            await query.answer(ok=False, error_message="Некорректный формат платежа")
            return
        
        user_id = int(parts[1])
        stars_amount = int(parts[2])
        
        # Validate user
        if user_id != query.from_user.id:
            logger.warning(f"User ID mismatch: payload={user_id}, actual={query.from_user.id}")
            await query.answer(ok=False, error_message="Ошибка валидации пользователя")
            return
        
        # Validate amount
        if stars_amount <= 0 or stars_amount > 10000:  # Telegram Stars limit
            logger.warning(f"Invalid stars amount: {stars_amount}")
            await query.answer(ok=False, error_message="Некорректная сумма")
            return
        
        # Approve the payment
        await query.answer(ok=True)
        logger.info(f"Pre-checkout approved: user_id={user_id}, amount={stars_amount} stars")
        
    except Exception as e:
        logger.error(f"Error in pre-checkout query: {e}")
        await query.answer(ok=False, error_message="Внутренняя ошибка")


async def handle_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle successful payment."""
    payment = update.message.successful_payment
    user = update.effective_user
    
    try:
        # Extract payment details
        payment_id = payment.telegram_payment_charge_id
        stars_amount = payment.total_amount  # Amount in stars (XTR currency)
        invoice_payload = payment.invoice_payload
        
        logger.info(f"Processing successful payment: user_id={user.id}, payment_id={payment_id}, amount={stars_amount}")
        
        # Validate payload
        if not invoice_payload.startswith("donate_"):
            logger.error(f"Invalid payment payload: {invoice_payload}")
            await update.message.reply_text("❌ Ошибка обработки платежа")
            return
        
        # Add to database
        donors_db = get_donors_db()
        success = donors_db.add_donation(
            user_id=user.id,
            payment_id=payment_id,
            stars_amount=stars_amount,
            telegram_username=user.username,
            first_name=user.first_name,
            invoice_payload=invoice_payload
        )
        
        if success:
            # Get updated donor info
            donor_info = donors_db.get_donor_info(user.id)
            total_stars = donor_info['total_stars'] if donor_info else stars_amount
            
            # Check if this is first donation (show bonus message)
            is_first_donation = total_stars == stars_amount
            
            if is_first_donation:
                # First donation - explain the bonus as gratitude
                success_text = (
                    f"🎉 *Спасибо за поддержку!*\n\n"
                    f"💫 Получено: {stars_amount}⭐\n\n"
                    f"🎁 *В благодарность мы включили вам более мощные модели!*\n\n"
                    f"🧠 **Для живых локаций теперь доступна модель o3:**\n"
                    f"• Более глубокий анализ мест при прогулках\n"
                    f"• Детальнее исторические факты\n"
                    f"• Лучше понимание контекста локации\n\n"
                    f"✨ Это наш способ сказать спасибо за то, что помогаете проекту развиваться!"
                )
            else:
                # Repeat donation - simpler thanks
                success_text = (
                    f"🎉 *Спасибо за поддержку!*\n\n"
                    f"💫 Получено: {stars_amount}⭐\n"
                    f"📊 Всего звезд: {total_stars}⭐\n\n"
                    f"🙏 Ваша повторная поддержка очень ценна!\n"
                    f"✨ Продолжайте наслаждаться улучшенными фактами!"
                )
            
            
            await update.message.reply_text(success_text, parse_mode="Markdown")
            
            # Log for analytics
            logger.info(f"Donation processed successfully: user_id={user.id}, total_stars={total_stars}")
            
        else:
            logger.error(f"Failed to save donation to database: user_id={user.id}, payment_id={payment_id}")
            await update.message.reply_text(
                "⚠️ Платеж получен, но произошла ошибка при обработке. "
                "Обратитесь в поддержку с ID платежа: " + payment_id
            )
    
    except Exception as e:
        logger.error(f"Error processing successful payment: {e}")
        await update.message.reply_text(
            "❌ Ошибка обработки платежа. Обратитесь в поддержку."
        )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stats command (for debugging/admin)."""
    try:
        donors_db = get_donors_db()
        stats = donors_db.get_stats()
        
        if not stats:
            await update.message.reply_text("❌ Ошибка получения статистики")
            return
        
        stats_text = (
            "📊 *Статистика проекта*\n\n"
            f"👥 Донатеров: {stats.get('total_donors', 0)}\n"
            f"💰 Всего донатов: {stats.get('total_donations', 0)}\n"
            f"⭐ Собрано звезд: {stats.get('total_stars', 0)}\n"
            f"💎 Активных премиум: {stats.get('active_premium', 0)}"
        )
        
        await update.message.reply_text(stats_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error in stats command: {e}")
        await update.message.reply_text("❌ Ошибка получения статистики")