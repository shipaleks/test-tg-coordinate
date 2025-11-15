"""Language selection handlers for bot localization."""

import logging
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from ..services.async_donors_wrapper import get_async_donors_db

logger = logging.getLogger(__name__)
async def reason_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Hidden command to set reasoning (minimal/low/medium/high) and model (gpt-5.1/gpt-5.1-mini) via buttons."""
    user = update.effective_user
    donors_db = await get_async_donors_db()
    current_level = await donors_db.get_user_reasoning(user.id)
    current_model = await donors_db.get_user_model(user.id)

    # Build inline keyboard
    rows = []
    # Reasoning row
    for level in ["minimal", "low", "medium", "high"]:
        mark = "✅" if level == current_level else ""
        rows.append([
            InlineKeyboardButton(f"{mark} Reasoning: {level}", callback_data=f"set_reason:{level}")
        ])
    # Model row
    for model in ["gpt-5.1", "gpt-5.1-mini"]:
        mark = "✅" if model == current_model else ""
        rows.append([
            InlineKeyboardButton(f"{mark} Model: {model}", callback_data=f"set_model:{model}")
        ])

    reply_markup = InlineKeyboardMarkup(rows)
    await update.message.reply_text("Developer settings:", reply_markup=reply_markup)


async def handle_reason_model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    donors_db = await get_async_donors_db()
    user = query.from_user

    if data.startswith("set_reason:"):
        level = data.split(":", 1)[1]
        await donors_db.set_user_reasoning(user.id, level)
    elif data.startswith("set_model:"):
        model = data.split(":", 1)[1]
        await donors_db.set_user_model(user.id, model)

    # Refresh menu
    current_level = await donors_db.get_user_reasoning(user.id)
    current_model = await donors_db.get_user_model(user.id)
    rows = []
    for level in ["minimal", "low", "medium", "high"]:
        mark = "✅" if level == current_level else ""
        rows.append([
            InlineKeyboardButton(f"{mark} Reasoning: {level}", callback_data=f"set_reason:{level}")
        ])
    for model in ["gpt-5.1", "gpt-5.1-mini"]:
        mark = "✅" if model == current_model else ""
        rows.append([
            InlineKeyboardButton(f"{mark} Model: {model}", callback_data=f"set_model:{model}")
        ])
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(rows))

# Language mapping with flags and names
LANGUAGES = {
    'ru': {'name': 'Русский', 'flag': '🇷🇺'},
    'en': {'name': 'English', 'flag': '🇺🇸'},
    'fr': {'name': 'Français', 'flag': '🇫🇷'},
    'pt': {'name': 'Português (Brasil)', 'flag': '🇧🇷'},
    'uk': {'name': 'Українська', 'flag': '🇺🇦'},
}

# Welcome messages in different languages
WELCOME_MESSAGES = {
    'ru': {
        'welcome': "🌍 **Выберите ваш язык:**\n\nВыбранный язык будет использоваться для всех фактов и сообщений бота.",
        'custom_prompt': "Введите код языка (например: es, de, it) или название языка:",
        'language_set': "✅ Язык установлен: {flag} {name}",
        'language_reset': "🔄 Язык сброшен. Используйте /start для выбора нового языка.",
        'invalid_language': "❌ Некорректный язык. Попробуйте еще раз."
    },
    'en': {
        'welcome': "🌍 **Choose your language:**\n\nThe selected language will be used for all facts and bot messages.",
        'custom_prompt': "Enter language code (e.g.: es, de, it) or language name:",
        'language_set': "✅ Language set: {flag} {name}",
        'language_reset': "🔄 Language reset. Use /start to choose a new language.",
        'invalid_language': "❌ Invalid language. Please try again."
    },
    'fr': {
        'welcome': "🌍 **Choisissez votre langue :**\n\nLa langue sélectionnée sera utilisée pour tous les faits et messages du bot.",
        'custom_prompt': "Entrez le code de langue (ex : es, de, it) ou le nom de la langue :",
        'language_set': "✅ Langue définie : {flag} {name}",
        'language_reset': "🔄 Langue réinitialisée. Utilisez /start pour choisir une nouvelle langue.",
        'invalid_language': "❌ Langue invalide. Veuillez réessayer."
    },
    'pt': {
        'welcome': "🌍 **Escolha seu idioma:**\n\nO idioma selecionado será usado para todos os fatos e mensagens do bot.",
        'custom_prompt': "Digite o código do idioma (ex: es, de, it) ou nome do idioma:",
        'language_set': "✅ Idioma definido: {flag} {name}",
        'language_reset': "🔄 Idioma redefinido. Use /start para escolher um novo idioma.",
        'invalid_language': "❌ Idioma inválido. Tente novamente."
    },
    'uk': {
        'welcome': "🌍 **Оберіть вашу мову:**\n\nОбрана мова буде використовуватися для всіх фактів та повідомлень бота.",
        'custom_prompt': "Введіть код мови (наприклад: es, de, it) або назву мови:",
        'language_set': "✅ Мову встановлено: {flag} {name}",
        'language_reset': "🔄 Мову скинуто. Використовуйте /start для вибору нової мови.",
        'invalid_language': "❌ Некоректна мова. Спробуйте ще раз."
    }
}


async def show_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show language selection menu to user."""
    user = update.effective_user
    
    # Get current language for welcome message (default to English)
    donors_db = await get_async_donors_db()
    current_lang = await donors_db.get_user_language(user.id)
    
    welcome_text = WELCOME_MESSAGES.get(current_lang, WELCOME_MESSAGES['en'])['welcome']
    
    # Create language selection keyboard
    keyboard = []
    
    # Main languages in rows of 2
    keyboard.append([
        InlineKeyboardButton(
            f"{LANGUAGES['ru']['flag']} {LANGUAGES['ru']['name']}", 
            callback_data="lang_ru"
        ),
        InlineKeyboardButton(
            f"{LANGUAGES['en']['flag']} {LANGUAGES['en']['name']}", 
            callback_data="lang_en"
        ),
    ])
    
    keyboard.append([
        InlineKeyboardButton(
            f"{LANGUAGES['fr']['flag']} {LANGUAGES['fr']['name']}", 
            callback_data="lang_fr"
        ),
        InlineKeyboardButton(
            f"{LANGUAGES['pt']['flag']} {LANGUAGES['pt']['name']}", 
            callback_data="lang_pt"
        ),
    ])
    
    keyboard.append([
        InlineKeyboardButton(
            f"{LANGUAGES['uk']['flag']} {LANGUAGES['uk']['name']}", 
            callback_data="lang_uk"
        ),
    ])
    
    # Custom language option
    keyboard.append([
        InlineKeyboardButton("🌐 Other language / Autre langue", callback_data="lang_custom"),
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(
            welcome_text, 
            parse_mode="Markdown", 
            reply_markup=reply_markup
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            welcome_text, 
            parse_mode="Markdown", 
            reply_markup=reply_markup
        )


async def handle_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle language selection from inline keyboard."""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    donors_db = await get_async_donors_db()
    
    if query.data.startswith("lang_"):
        lang_code = query.data.replace("lang_", "")
        
        if lang_code == "custom":
            # Show custom language input prompt
            current_lang = await donors_db.get_user_language(user.id)
            prompt_text = WELCOME_MESSAGES.get(current_lang, WELCOME_MESSAGES['en'])['custom_prompt']
            
            # Store state for custom language input
            context.user_data['awaiting_custom_language'] = True
            
            await query.edit_message_text(
                f"🌐 **Custom Language / Langue personnalisée**\n\n{prompt_text}",
                parse_mode="Markdown"
            )
            return
        
        # Set predefined language
        if lang_code in LANGUAGES:
            success = await donors_db.set_user_language(user.id, lang_code)
            
            if success:
                language_info = LANGUAGES[lang_code]
                success_text = WELCOME_MESSAGES.get(lang_code, WELCOME_MESSAGES['en'])['language_set'].format(
                    flag=language_info['flag'],
                    name=language_info['name']
                )
                
                await query.edit_message_text(success_text)
                
                # Clear user data
                context.user_data.pop('awaiting_custom_language', None)
                
                # Send welcome message in selected language
                from ..main import send_welcome_message
                await send_welcome_message(user.id, query.message.chat_id, context.bot, lang_code)
                
                logger.info(f"User {user.id} selected language: {lang_code}")
            else:
                await query.edit_message_text("❌ Error setting language. Please try again.")
        else:
            await query.edit_message_text("❌ Invalid language selection.")


async def handle_custom_language_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle custom language input from user."""
    if not context.user_data.get('awaiting_custom_language'):
        return
    
    user = update.effective_user
    language_input = update.message.text.strip().lower()
    
    # Clear the awaiting state
    context.user_data.pop('awaiting_custom_language', None)
    
    # Validate language input (basic validation)
    if len(language_input) < 2 or len(language_input) > 50:
        donors_db = await get_async_donors_db()
        current_lang = await donors_db.get_user_language(user.id)
        error_text = WELCOME_MESSAGES.get(current_lang, WELCOME_MESSAGES['en'])['invalid_language']
        await update.message.reply_text(error_text)
        return
    
    # Save custom language
    donors_db = await get_async_donors_db()
    success = await donors_db.set_user_language(user.id, language_input)
    
    if success:
        # Try to determine flag and name for common languages
        flag = "🌐"
        name = language_input.capitalize()
        
        # Common language mappings
        common_langs = {
            'es': {'flag': '🇪🇸', 'name': 'Español'},
            'de': {'flag': '🇩🇪', 'name': 'Deutsch'},
            'it': {'flag': '🇮🇹', 'name': 'Italiano'},
            'ja': {'flag': '🇯🇵', 'name': '日本語'},
            'ko': {'flag': '🇰🇷', 'name': '한국어'},
            'zh': {'flag': '🇨🇳', 'name': '中文'},
            'ar': {'flag': '🇸🇦', 'name': 'العربية'},
            'hi': {'flag': '🇮🇳', 'name': 'हिन्दी'},
        }
        
        if language_input in common_langs:
            flag = common_langs[language_input]['flag']
            name = common_langs[language_input]['name']
        
        success_text = f"✅ Language set: {flag} {name}"
        await update.message.reply_text(success_text)
        
        # Send welcome message in custom language
        from ..main import send_welcome_message
        await send_welcome_message(user.id, update.message.chat_id, context.bot, language_input)
        
        logger.info(f"User {user.id} set custom language: {language_input}")
    else:
        await update.message.reply_text("❌ Error setting language. Please try again.")


async def reset_language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /reset command to reset user's language preference."""
    user = update.effective_user
    donors_db = await get_async_donors_db()
    
    # Get current language for message
    current_lang = await donors_db.get_user_language(user.id)
    
    # Reset language
    success = await donors_db.reset_user_language(user.id)
    
    if success:
        # Always use English message after reset since language is now None
        reset_text = WELCOME_MESSAGES['en']['language_reset']
        await update.message.reply_text(reset_text)
        logger.info(f"User {user.id} reset their language preference")
    else:
        await update.message.reply_text("❌ Error resetting language. Please try again.")