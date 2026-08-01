"""Language selection handlers for bot localization."""

import logging

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from ..services.async_donors_wrapper import get_async_donors_db
from ..utils.i18n import LANGUAGE_MESSAGES as WELCOME_MESSAGES

logger = logging.getLogger(__name__)

# Models offered in the /reason settings menu: (model_id, label)
CLAUDE_MODELS = [
    ("claude-opus-5", "Opus 5 (Best Quality)"),
    ("claude-sonnet-5", "Sonnet 5 (Balanced)"),
    ("claude-haiku-4-5-20251001", "Haiku 4.5 (Fastest)"),
]

# Reasoning levels offered in the /reason settings menu: (level_id, label)
REASONING_LEVELS = [
    ("none", "None (Instant)"),
    ("low", "Low (Quick)"),
    ("medium", "Medium (Thorough)"),
    ("high", "High (Deep Analysis)"),
]


def _build_settings_menu(
    current_model: str, current_reasoning: str
) -> tuple[str, InlineKeyboardMarkup]:
    """Build the /reason settings message text and keyboard."""
    rows = [[InlineKeyboardButton("🤖 Models:", callback_data="noop")]]
    for model_id, model_name in CLAUDE_MODELS:
        mark = "✅" if model_id == current_model else "○"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{mark} {model_name}", callback_data=f"set_model:{model_id}"
                )
            ]
        )

    rows.append([InlineKeyboardButton("🧠 Reasoning:", callback_data="noop")])
    for level_id, level_name in REASONING_LEVELS:
        mark = "✅" if level_id == current_reasoning else "○"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{mark} {level_name}", callback_data=f"set_reason:{level_id}"
                )
            ]
        )

    text = (
        "⚙️ **Settings** (Internal Testing)\n\n"
        f"Model: {current_model}\n"
        f"Reasoning: {current_reasoning}\n\n"
        "Select options below:"
    )
    return text, InlineKeyboardMarkup(rows)


async def reason_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Hidden command to set model (Claude Opus/Sonnet/Haiku) and reasoning level."""
    user = update.effective_user
    donors_db = await get_async_donors_db()
    current_model = await donors_db.get_user_model(user.id)
    current_reasoning = await donors_db.get_user_reasoning(user.id)

    text, reply_markup = _build_settings_menu(current_model, current_reasoning)
    await update.message.reply_text(
        text,
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


async def handle_reason_model_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    donors_db = await get_async_donors_db()
    user = query.from_user

    # Handle noop callbacks (section headers)
    if data == "noop":
        return

    # Handle setting changes
    if data.startswith("set_reason:"):
        level = data.split(":", 1)[1]
        await donors_db.set_user_reasoning(user.id, level)
        logger.info(f"User {user.id} set reasoning level: {level}")
    elif data.startswith("set_model:"):
        model = data.split(":", 1)[1]
        await donors_db.set_user_model(user.id, model)
        logger.info(f"User {user.id} set model: {model}")

    # Refresh menu with updated selections
    current_model = await donors_db.get_user_model(user.id)
    current_reasoning = await donors_db.get_user_reasoning(user.id)

    text, reply_markup = _build_settings_menu(current_model, current_reasoning)
    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


# Language mapping with flags and names
LANGUAGES = {
    "ru": {"name": "Русский", "flag": "🇷🇺"},
    "en": {"name": "English", "flag": "🇺🇸"},
    "fr": {"name": "Français", "flag": "🇫🇷"},
    "pt": {"name": "Português (Brasil)", "flag": "🇧🇷"},
    "uk": {"name": "Українська", "flag": "🇺🇦"},
}

# Welcome messages in different languages


async def show_language_selection(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show language selection menu to user."""
    user = update.effective_user

    # Get current language for welcome message (default to English)
    donors_db = await get_async_donors_db()
    current_lang = await donors_db.get_user_language(user.id)

    welcome_text = WELCOME_MESSAGES.get(current_lang, WELCOME_MESSAGES["en"])["welcome"]

    # Create language selection keyboard
    keyboard = []

    # Main languages in rows of 2
    keyboard.append(
        [
            InlineKeyboardButton(
                f"{LANGUAGES['ru']['flag']} {LANGUAGES['ru']['name']}",
                callback_data="lang_ru",
            ),
            InlineKeyboardButton(
                f"{LANGUAGES['en']['flag']} {LANGUAGES['en']['name']}",
                callback_data="lang_en",
            ),
        ]
    )

    keyboard.append(
        [
            InlineKeyboardButton(
                f"{LANGUAGES['fr']['flag']} {LANGUAGES['fr']['name']}",
                callback_data="lang_fr",
            ),
            InlineKeyboardButton(
                f"{LANGUAGES['pt']['flag']} {LANGUAGES['pt']['name']}",
                callback_data="lang_pt",
            ),
        ]
    )

    keyboard.append(
        [
            InlineKeyboardButton(
                f"{LANGUAGES['uk']['flag']} {LANGUAGES['uk']['name']}",
                callback_data="lang_uk",
            ),
        ]
    )

    # Custom language option
    keyboard.append(
        [
            InlineKeyboardButton(
                "🌐 Other language / Autre langue", callback_data="lang_custom"
            ),
        ]
    )

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(
            welcome_text, parse_mode="Markdown", reply_markup=reply_markup
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            welcome_text, parse_mode="Markdown", reply_markup=reply_markup
        )


async def handle_language_selection(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
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
            prompt_text = WELCOME_MESSAGES.get(current_lang, WELCOME_MESSAGES["en"])[
                "custom_prompt"
            ]

            # Store state for custom language input
            context.user_data["awaiting_custom_language"] = True

            await query.edit_message_text(
                f"🌐 **Custom Language / Langue personnalisée**\n\n{prompt_text}",
                parse_mode="Markdown",
            )
            return

        # Set predefined language
        if lang_code in LANGUAGES:
            success = await donors_db.set_user_language(user.id, lang_code)

            if success:
                language_info = LANGUAGES[lang_code]
                success_text = WELCOME_MESSAGES.get(lang_code, WELCOME_MESSAGES["en"])[
                    "language_set"
                ].format(flag=language_info["flag"], name=language_info["name"])

                await query.edit_message_text(success_text)

                # Clear user data
                context.user_data.pop("awaiting_custom_language", None)

                # Send welcome message in selected language
                from ..main import send_welcome_message

                await send_welcome_message(
                    user.id, query.message.chat_id, context.bot, lang_code
                )

                logger.info(f"User {user.id} selected language: {lang_code}")
            else:
                await query.edit_message_text(
                    "❌ Error setting language. Please try again."
                )
        else:
            await query.edit_message_text("❌ Invalid language selection.")


async def handle_custom_language_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle custom language input from user."""
    if not context.user_data.get("awaiting_custom_language"):
        return

    user = update.effective_user
    language_input = update.message.text.strip().lower()

    # Clear the awaiting state
    context.user_data.pop("awaiting_custom_language", None)

    # Validate language input (basic validation)
    if len(language_input) < 2 or len(language_input) > 50:
        donors_db = await get_async_donors_db()
        current_lang = await donors_db.get_user_language(user.id)
        error_text = WELCOME_MESSAGES.get(current_lang, WELCOME_MESSAGES["en"])[
            "invalid_language"
        ]
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
            "es": {"flag": "🇪🇸", "name": "Español"},
            "de": {"flag": "🇩🇪", "name": "Deutsch"},
            "it": {"flag": "🇮🇹", "name": "Italiano"},
            "ja": {"flag": "🇯🇵", "name": "日本語"},
            "ko": {"flag": "🇰🇷", "name": "한국어"},
            "zh": {"flag": "🇨🇳", "name": "中文"},
            "ar": {"flag": "🇸🇦", "name": "العربية"},
            "hi": {"flag": "🇮🇳", "name": "हिन्दी"},
        }

        if language_input in common_langs:
            flag = common_langs[language_input]["flag"]
            name = common_langs[language_input]["name"]

        success_text = f"✅ Language set: {flag} {name}"
        await update.message.reply_text(success_text)

        # Send welcome message in custom language
        from ..main import send_welcome_message

        await send_welcome_message(
            user.id, update.message.chat_id, context.bot, language_input
        )

        logger.info(f"User {user.id} set custom language: {language_input}")
    else:
        await update.message.reply_text("❌ Error setting language. Please try again.")


async def reset_language_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /reset command to reset user's language preference."""
    user = update.effective_user
    donors_db = await get_async_donors_db()

    # Reset language
    success = await donors_db.reset_user_language(user.id)

    if success:
        # Always use English message after reset since language is now None
        reset_text = WELCOME_MESSAGES["en"]["language_reset"]
        await update.message.reply_text(reset_text)
        logger.info(f"User {user.id} reset their language preference")
    else:
        await update.message.reply_text(
            "❌ Error resetting language. Please try again."
        )
