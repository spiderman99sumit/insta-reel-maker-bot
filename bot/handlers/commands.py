"""Telegram command handlers: /start, /help, /templates, /status, /cancel."""

import logging
from functools import wraps
from typing import Callable
from telegram import Update
from telegram.ext import ContextTypes

from bot.templates.styles import TEMPLATES
from bot.utils.cleanup import cleanup_chat_files
from bot.utils.config import config
from database.db import db_manager

logger = logging.getLogger(__name__)


def restricted(func: Callable):
    """Decorator to enforce ADMIN_TELEGRAM_ID restriction if configured."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if user and not config.is_admin(user.id):
            logger.warning(f"Unauthorized access attempt by user {user.id} ({user.username})")
            if update.effective_message:
                await update.effective_message.reply_text("⛔ You are not authorized to use this bot.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


@restricted
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command - welcome user and explain bot usage."""
    welcome_msg = (
        "🎬 *Welcome to the Telegram Reel Maker Bot\\!*\n\n"
        "I create high\\-quality, vertical *9:16 Instagram Reels* \\(1080x1920\\) "
        "autonomously with AI or from your own media\\.\n\n"
        "🤖 *AI Autonomous Mode \\(Self\\-Creation\\):*\n"
        "• Just send the word `image` or `video`\n"
        "• Or use `/auto` \\(or `/auto sexy`, `/auto meme`\\)\n"
        "• I will automatically write viral hooks, generate AI visuals, and render the complete reel\\!\n\n"
        "🎨 *Manual Upload Mode:*\n"
        "• Type /reel to upload your own photo/video, custom text, and music\\.\n\n"
        "⚡ *Commands:*\n"
        "• `/auto` \\- One\\-tap AI autonomous creator\n"
        "• `/reel` \\- Manual reel creator\n"
        "• `/templates` \\- Browse all 6 styles \\(including Sexy 💋\\)\n"
        "• `/status` \\- Check active job\n"
        "• `/cancel` \\- Discard active job\n"
        "• `/help` \\- Full guide"
    )
    if update.effective_message:
        await update.effective_message.reply_text(welcome_msg, parse_mode="MarkdownV2")


@restricted
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    help_text = (
        "📖 *Reel Maker Bot Guide*\n\n"
        "*Step 1: Media*\n"
        "• Send photos (JPG, PNG, WebP) or videos (MP4, MOV, MKV).\n"
        "• Images automatically get a smooth Ken Burns pan/zoom.\n"
        "• Non-9:16 media is intelligently fitted with a blurred background.\n"
        f"• Max video size: {config.max_video_size_mb} MB.\n\n"
        "*Step 2: Text*\n"
        "• Text wraps automatically and fits Instagram safe margins.\n"
        "• Font size adapts dynamically for longer quotes.\n\n"
        "*Step 3: Music*\n"
        "• Send any audio/MP3, or type /skip to keep original audio or silent track.\n"
        "• Background music automatically ducks under original video dialogue.\n"
        f"• Max audio size: {config.max_audio_size_mb} MB.\n\n"
        "*Step 4: Templates*\n"
        "• Choose from 5 styles: Cinematic, Meme, Romantic, Quote, or Minimal.\n\n"
        "Use /cancel anytime to discard an active draft."
    )
    if update.effective_message:
        await update.effective_message.reply_text(help_text, parse_mode="Markdown")


@restricted
async def templates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /templates command."""
    msg = ["🎨 *Available Reel Templates:*\n"]
    for idx, (key, style) in enumerate(TEMPLATES.items(), 1):
        msg.append(f"*{idx}. {style.display_name}*")
        msg.append(f"_{style.description}_\n")

    msg.append("Ready to make one? Type /reel to start!")
    if update.effective_message:
        await update.effective_message.reply_text("\n".join(msg), parse_mode="Markdown")


@restricted
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command."""
    chat_id = update.effective_chat.id
    session = await db_manager.get_session(chat_id)

    if not session or session.get("current_step") == "IDLE":
        text = "ℹ️ You currently have no active reel job. Type /reel to begin!"
    else:
        step = session.get("current_step", "UNKNOWN")
        m_type = session.get("media_type") or "Not uploaded"
        has_txt = "Yes" if session.get("overlay_text") else "Pending"
        has_mus = "Yes" if session.get("music_path") else "Pending / Skipped"
        tmpl = session.get("selected_template") or "Not selected"

        text = (
            f"📊 *Current Job Status*\n\n"
            f"• *Step:* `{step}`\n"
            f"• *Media:* `{m_type}`\n"
            f"• *Text:* `{has_txt}`\n"
            f"• *Music:* `{has_mus}`\n"
            f"• *Template:* `{tmpl}`\n\n"
            f"Type /cancel to discard this draft."
        )

    if update.effective_message:
        await update.effective_message.reply_text(text, parse_mode="Markdown")


@restricted
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /cancel command."""
    chat_id = update.effective_chat.id
    await db_manager.reset_session(chat_id)
    cleanup_chat_files(chat_id)

    if update.effective_message:
        await update.effective_message.reply_text("🛑 Current reel creation cancelled. Type /reel to start fresh!")
