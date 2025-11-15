"""Donation handlers for Telegram Stars payments."""

import logging
import time
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Update,
)
from telegram.ext import ContextTypes

from ..services.async_donors_wrapper import get_async_donors_db
from ..services.firebase_stats import get_stats_for_user as fb_get_user_stats
from ..services.firebase_stats import get_global_stats as fb_get_global_stats

logger = logging.getLogger(__name__)

# Localized donation messages
DONATION_MESSAGES = {
    'ru': {
        'title': "🌟 *Поддержать проект*",
        'donor_status': "🎁 *Донатер проекта*\n📊 Всего звезд: {total_stars}⭐\n🧠 GPT-5.1 (reasoning + web_search) активна для живых локаций",
        'support_helps': "Ваша поддержка помогает:",
        'help_points': [
            "🤖 Оплачивать OpenAI API для качественных фактов",
            "🚀 Развивать новые функции бота", 
            "📡 Поддерживать сервер 24/7"
        ],
        'voluntary': "💝 *Любая поддержка добровольна и очень ценится!*",
        'other_amount': "💰 Other amount",
        'choose_amount': "💰 *Choose amount:*",
        'any_support': "✨ Any support is greatly appreciated!",
        'back': "← Back"
    },
    'en': {
        'title': "🌟 *Support the project*",
        'donor_status': "🎁 *Project supporter*\n📊 Total stars: {total_stars}⭐\n🧠 GPT-5.1 (reasoning + web_search) active for live locations",
        'support_helps': "Your support helps:",
        'help_points': [
            "🤖 Pay for OpenAI API for quality facts",
            "🚀 Develop new bot features",
            "📡 Maintain 24/7 server"
        ],
        'voluntary': "💝 *All support is voluntary and greatly appreciated!*",
        'other_amount': "💰 Other amount",
        'choose_amount': "💰 *Choose amount:*",
        'any_support': "✨ Any support is greatly appreciated!",
        'back': "← Back"
    },
    'fr': {
        'title': "🌟 *Soutenir le projet*",
        'donor_status': "🎁 *Soutien du projet*\n📊 Total étoiles : {total_stars}⭐\n🧠 GPT-5.1 (reasoning + web_search) actif pour les positions en direct",
        'support_helps': "Votre soutien aide à :",
        'help_points': [
            "🤖 Payer l'API OpenAI pour des faits de qualité",
            "🚀 Développer de nouvelles fonctionnalités",
            "📡 Maintenir le serveur 24h/24"
        ],
        'voluntary': "💝 *Tout soutien est volontaire et très apprécié !*",
        'other_amount': "💰 Autre montant",
        'choose_amount': "💰 *Choisissez le montant :*",
        'any_support': "✨ Tout soutien est grandement apprécié !",
        'back': "← Retour"
    }
}


async def donate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /donate command."""
    user = update.effective_user
    
    # Get user language
    donors_db = await get_async_donors_db()
    user_language = await donors_db.get_user_language(user.id)
    messages = DONATION_MESSAGES.get(user_language, DONATION_MESSAGES['en'])
    
    # Check current premium status
    is_premium = await donors_db.is_premium_user(user.id)
    donor_info = await donors_db.get_donor_info(user.id)
    
    # Create status text
    if donor_info and 'total_stars' in donor_info:
        status_text = messages['donor_status'].format(total_stars=donor_info['total_stars']) + "\n\n"
    else:
        status_text = ""
    
    # Build help points
    help_text = "\n".join([f"• {point}" for point in messages['help_points']])
    
    donate_text = (
        f"{messages['title']}\n\n"
        + status_text +
        f"{messages['support_helps']}\n"
        f"{help_text}\n\n"
        f"{messages['voluntary']}"
    )
    
    # Create donation buttons with increased amounts
    keyboard = [
        [
            InlineKeyboardButton("100⭐", callback_data="donate_100"),
            InlineKeyboardButton("250⭐", callback_data="donate_250"),
            InlineKeyboardButton("500⭐", callback_data="donate_500"),
        ],
        [
            InlineKeyboardButton(messages['other_amount'], callback_data="donate_custom"),
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
            # Get user language for localized text
            donors_db = await get_async_donors_db()
            user_language = await donors_db.get_user_language(user.id)
            messages = DONATION_MESSAGES.get(user_language, DONATION_MESSAGES['en'])
            
            custom_keyboard = [
                [
                    InlineKeyboardButton("50⭐", callback_data="donate_50"),
                    InlineKeyboardButton("150⭐", callback_data="donate_150"),
                ],
                [
                    InlineKeyboardButton("1000⭐", callback_data="donate_1000"),
                    InlineKeyboardButton("2000⭐", callback_data="donate_2000"),
                ],
                [
                    InlineKeyboardButton(messages['back'], callback_data="donate_back"),
                ],
            ]
            custom_markup = InlineKeyboardMarkup(custom_keyboard)
            
            await query.edit_message_text(
                f"{messages['choose_amount']}\n\n"
                f"{messages['any_support']}",
                parse_mode="Markdown",
                reply_markup=custom_markup
            )
            return
        
        if amount_str == "back":
            # Go back to main donate screen - we need to recreate the original message
            user = query.from_user
            donors_db = await get_async_donors_db()
            user_language = await donors_db.get_user_language(user.id)
            messages = DONATION_MESSAGES.get(user_language, DONATION_MESSAGES['en'])
            
            is_premium = await donors_db.is_premium_user(user.id)
            donor_info = await donors_db.get_donor_info(user.id)
            
            # Create status text
            if donor_info and 'total_stars' in donor_info:
                status_text = messages['donor_status'].format(total_stars=donor_info['total_stars']) + "\n\n"
            else:
                status_text = ""
            
            # Build help points
            help_text = "\n".join([f"• {point}" for point in messages['help_points']])
            
            donate_text = (
                f"{messages['title']}\n\n"
                + status_text +
                f"{messages['support_helps']}\n"
                f"{help_text}\n\n"
                f"{messages['voluntary']}"
            )
            
            # Create donation buttons
            keyboard = [
                [
                    InlineKeyboardButton("100⭐", callback_data="donate_100"),
                    InlineKeyboardButton("250⭐", callback_data="donate_250"),
                    InlineKeyboardButton("500⭐", callback_data="donate_500"),
                ],
                [
                    InlineKeyboardButton(messages['other_amount'], callback_data="donate_custom"),
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
        donors_db = await get_async_donors_db()
        logger.info(f"Attempting to add donation to database: user_id={user.id}, payment_id={payment_id}, stars={stars_amount}")
        
        success = await donors_db.add_donation(
            user_id=user.id,
            payment_id=payment_id,
            stars_amount=stars_amount,
            telegram_username=user.username,
            first_name=user.first_name,
            invoice_payload=invoice_payload
        )
        
        logger.info(f"Donation database operation result: success={success}")
        
        if success:
            # Get updated donor info
            donor_info = await donors_db.get_donor_info(user.id)
            total_stars = donor_info.get('total_stars', stars_amount) if donor_info else stars_amount
            
            # Check if this is first donation (show bonus message)
            is_first_donation = total_stars == stars_amount
            
            if is_first_donation:
                # First donation - discreet upgrade message
                success_text = (
                    f"🎉 *Спасибо за поддержку!*\n\n"
                    f"💫 Получено: {stars_amount}⭐\n\n"
                    f"🧠 Теперь факты будет составлять и проверять более умная модель — точнее и надёжнее.\n\n"
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
        # Firebase-based counters (user facts, total facts, total users)
        user_id = update.effective_user.id
        user_facts = await fb_get_user_stats(user_id)
        global_stats = await fb_get_global_stats()
        stats_text = (
            "📊 *Статистика*\n\n"
            f"Ты получил фактов: {user_facts}\n"
            f"Всего фактов: {global_stats.get('total_facts', 0)}\n"
            f"Пользователей: {global_stats.get('total_users', 0)}"
        )
        
        await update.message.reply_text(stats_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error in stats command: {e}")
        await update.message.reply_text("❌ Ошибка получения статистики")


async def dbtest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /dbtest command - database diagnostics."""
    try:
        # Use async wrapper for all database operations
        from ..services.async_donors_wrapper import get_async_donors_db
        donors_db = await get_async_donors_db()
        user_id = update.effective_user.id
        
        # Test database connection and basic operations
        test_results = []
        
        # 1. Check database file location
        db_path = str(donors_db.db_path)
        test_results.append(f"📁 *Database path:* `{db_path}`")
        
        # 2. Check if file exists and is writable
        import os
        if os.path.exists(db_path):
            if os.access(db_path, os.W_OK):
                test_results.append("✅ Database file exists and writable")
            else:
                test_results.append("⚠️ Database file exists but not writable")
        else:
            test_results.append("🆕 Database file will be created on first use")
        
        # 3. Test basic database operations
        try:
            # Get user info (should work even for non-donors)
            donor_info = await donors_db.get_donor_info(user_id)
            if donor_info:
                test_results.append(f"👤 *Your donor status:* Found (⭐{donor_info.get('total_stars', 0)})")
                
                # Check premium status with detailed timestamp info
                is_premium = await donors_db.is_premium_user(user_id)
                status = "🎁 Enhanced access active" if is_premium else "📱 Standard access"
                test_results.append(f"🧠 *Model access:* {status}")
                
                # Show detailed premium info
                current_time = int(time.time())
                premium_expires = donor_info.get('premium_expires', 0)
                if premium_expires > 0:
                    if premium_expires > current_time:
                        days_left = (premium_expires - current_time) // (24 * 60 * 60)
                        test_results.append(f"⏰ *Premium expires:* {days_left} days from now")
                    else:
                        test_results.append(f"⏰ *Premium status:* Expired")
                
                # Get donation history
                history = await donors_db.get_donation_history(user_id)
                test_results.append(f"📜 *Donation history:* {len(history)} transactions")
                
                # Show latest donation if exists
                if history:
                    latest = history[0]  # Most recent first
                    test_results.append(f"💳 *Latest donation:* {latest['stars_amount']}⭐ on {latest['payment_date']}")
            else:
                test_results.append("👤 *Your status:* Not a donor yet")
                test_results.append("🧠 *Model access:* Standard (GPT-4.1 static, o4-mini live)")
                
                # Check if there are any donations for this user in donations table
                # Skip SQLite specific checks for PostgreSQL
                if not os.environ.get("DATABASE_URL"):
                    import sqlite3
                    with sqlite3.connect(donors_db.db_path) as conn:
                        donations_count = conn.execute(
                            "SELECT COUNT(*) FROM donations WHERE user_id = ?", 
                            (user_id,)
                        ).fetchone()[0]
                        if donations_count > 0:
                            test_results.append(f"⚠️ *Found {donations_count} donations in donations table but no donor record!*")
            
            # Get overall stats
            stats = await donors_db.get_stats()
            test_results.append(f"📊 *Database stats:* {stats.get('total_donors', 0)} donors, {stats.get('total_donations', 0)} transactions")
            
            # Check raw table counts for debugging (SQLite only)
            if not os.environ.get("DATABASE_URL"):
                import sqlite3
                with sqlite3.connect(donors_db.db_path) as conn:
                    donors_count = conn.execute("SELECT COUNT(*) FROM donors").fetchone()[0]
                    donations_count = conn.execute("SELECT COUNT(*) FROM donations").fetchone()[0]
                    test_results.append(f"🔍 *Raw counts:* {donors_count} donors, {donations_count} donations in tables")
            
            test_results.append("✅ All database operations working correctly")
            
        except Exception as db_error:
            test_results.append(f"❌ Database operation failed: {str(db_error)}")
        
        # 4. Check Railway volume and environment
        import os
        railway_env_vars = {
            "RAILWAY_ENVIRONMENT_NAME": os.environ.get("RAILWAY_ENVIRONMENT_NAME", "Not set"),
            "RAILWAY_PROJECT_ID": os.environ.get("RAILWAY_PROJECT_ID", "Not set"),
            "RAILWAY_SERVICE_ID": os.environ.get("RAILWAY_SERVICE_ID", "Not set"),
            "RAILWAY_VOLUME_ID": os.environ.get("RAILWAY_VOLUME_ID", "Not set"),
            "RAILWAY_VOLUME_MOUNT_PATH": os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "Not set")
        }
        
        if "/data" in db_path:
            test_results.append("🚀 *Deployment:* Railway with persistent volume")
            if os.path.exists("/data") and os.access("/data", os.W_OK):
                test_results.append("✅ Railway volume mounted and accessible")
            else:
                test_results.append("⚠️ Railway volume path not accessible")
        else:
            test_results.append("💻 *Deployment:* Local development mode")
            # Show Railway environment variables for debugging
            if any(v != "Not set" for v in railway_env_vars.values()):
                test_results.append("⚠️ *Railway env detected but using local DB!*")
                for var, value in railway_env_vars.items():
                    if value != "Not set":
                        test_results.append(f"  - {var}: {value[:20]}...")
            
        # Check if /data exists at all
        if os.path.exists("/data"):
            test_results.append(f"📂 */data exists:* Yes (writable: {os.access('/data', os.W_OK)})")
            # Check permissions in detail
            try:
                import stat
                stats = os.stat("/data")
                mode = oct(stat.S_IMODE(stats.st_mode))
                test_results.append(f"📂 */data permissions:* `{mode}`")
                test_results.append(f"📂 */data owner UID:* `{stats.st_uid}`")
                
                # Try to list contents
                contents = os.listdir("/data")
                test_results.append(f"📂 */data contents:* {len(contents)} items")
                if contents:
                    safe_contents = [str(f).replace('*', '\\*').replace('_', '\\_') for f in contents[:5]]
                    test_results.append(f"📂 *Files:* {', '.join(safe_contents)}")
            except Exception as perm_error:
                error_msg = str(perm_error)[:50].replace('*', '\\*').replace('_', '\\_')
                test_results.append(f"⚠️ *Permission check error:* {error_msg}")
        else:
            test_results.append("📂 */data exists:* No")
        
        # Check for other possible volume paths
        possible_paths = [
            "/app/data",
            "/volume",
            "/mnt/volume",
            os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", ""),
            os.environ.get("VOLUME_PATH", "")
        ]
        
        for path in possible_paths:
            if path and os.path.exists(path):
                safe_path = str(path).replace('*', '\\*').replace('_', '\\_')
                test_results.append(f"📂 *{safe_path} exists:* Yes (writable: {os.access(path, os.W_OK)})")
        
        # Format results - temporarily disable Markdown to debug parsing issues
        test_text = "🔧 Database Diagnostics\n\n" + "\n".join(test_results)
        
        # Remove all Markdown formatting to avoid parsing errors
        clean_text = test_text.replace("*", "").replace("_", "").replace("`", "")
        
        await update.message.reply_text(clean_text)
        
    except Exception as e:
        logger.error(f"Error in dbtest command: {e}")
        await update.message.reply_text(
            f"❌ Database test failed\n\n"
            f"Error: {str(e)}\n\n"
            f"This might indicate a database configuration issue."
        )