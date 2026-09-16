"""Main application entrypoint for Telegram Reel Maker Bot."""

import asyncio
import logging
import sys
from telegram import Update
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.handlers.commands import (
    cancel_command,
    help_command,
    start_command,
    status_command,
    templates_command,
)
from bot.handlers.media import (
    handle_document_media,
    handle_photo,
    handle_video,
    reel_command,
)
from bot.handlers.templates import (
    handle_audio,
    handle_template_selection,
    skip_command,
)
from bot.handlers.text import handle_overlay_text
from bot.handlers.auto import (
    auto_command,
    handle_auto_callbacks,
    reset_history_command,
    set_gemini_key_command,
    set_openai_key_command,
)
from bot.services.autopilot import (
    autopilot_command,
    handle_autopilot_callbacks,
    register_autopilot_jobs,
    testing_mode_command,
)
from bot.handlers.instagram_handler import (
    insta_login_command,
    insta_session_command,
    insta_status_command,
    insta_autopost_command,
    insta_logout_command,
    handle_post_to_insta_callback,
)
from bot.utils.cleanup import cleanup_expired_outputs
from bot.utils.config import config, mask_token
from bot.utils.ffmpeg_check import check_ffmpeg_installed, check_ffprobe_installed, get_ffmpeg_version
from database.db import db_manager

# Ensure UTF-8 output encoding across Windows and POSIX
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Configure logging
logging.basicConfig(
    format="%(asctime)s - [%(levelname)s] - %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("reel_bot")


async def periodic_cleanup_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scheduled task to clean expired output files."""
    cleaned = cleanup_expired_outputs(config.output_retention_hours)
    if cleaned > 0:
        logger.info(f"Periodic cleanup: deleted {cleaned} expired output reels")


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log uncaught exceptions to prevent bot from crashing."""
    logger.error("Exception occurred while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ An unexpected error occurred. Please try again with /reel or type /cancel."
            )
        except Exception:
            pass


async def setup_bot() -> Application:
    """Verify prerequisites, initialize database, and register handlers."""
    logger.info("Verifying environment...")
    if not check_ffmpeg_installed():
        logger.error("❌ FFmpeg is not installed or not found in system PATH!")
        sys.exit(1)
    if not check_ffprobe_installed():
        logger.error("❌ FFprobe is not installed or not found in system PATH!")
        sys.exit(1)

    logger.info(f"FFmpeg detected: {get_ffmpeg_version()}")
    logger.info(f"Configuration loaded: {config}")

    if not config.bot_token:
        logger.error(
            "❌ TELEGRAM_BOT_TOKEN is not configured!\n"
            "Please create a .env file from .env.example and set your TELEGRAM_BOT_TOKEN from @BotFather."
        )
        sys.exit(1)

    # Initialize SQLite database
    await db_manager.init_db()

    # Configure robust connection and upload timeouts for video reels
    request_config = HTTPXRequest(
        connection_pool_size=16,
        connect_timeout=30.0,
        read_timeout=180.0,
        write_timeout=180.0,
    )

    # Build Telegram Bot application
    app = ApplicationBuilder().token(config.bot_token).request(request_config).build()

    # Register Command Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("templates", templates_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("reel", reel_command))
    app.add_handler(CommandHandler("skip", skip_command))
    app.add_handler(CommandHandler("auto", auto_command))
    app.add_handler(CommandHandler("reset_history", reset_history_command))
    app.add_handler(CommandHandler("set_gemini_key", set_gemini_key_command))
    app.add_handler(CommandHandler("set_openai_key", set_openai_key_command))

    # Register Media & Content Handlers
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VIDEO | filters.ANIMATION, handle_video))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document_media))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_overlay_text))

    # Register Callback Query Handlers (Template selection & Autonomous)
    app.add_handler(CallbackQueryHandler(handle_template_selection, pattern=r"^tmpl_"))
    app.add_handler(CallbackQueryHandler(handle_auto_callbacks, pattern=r"^(cat_|pick_|shuffle_|back_|auto_|reel_|gen_|fetch_|reset_|upload_|studio_)"))
    app.add_handler(CallbackQueryHandler(handle_post_to_insta_callback, pattern=r"^post_insta"))
    app.add_handler(CallbackQueryHandler(handle_autopilot_callbacks, pattern=r"^(autopilot_|cancel_autopost_|post_now_|user_posting_)"))

    # Register Autopilot & Instagram Commands
    app.add_handler(CommandHandler(["autopilot", "schedule"], autopilot_command))
    app.add_handler(CommandHandler(["testing_mode", "test_mode", "testing"], testing_mode_command))
    app.add_handler(CommandHandler("insta_login", insta_login_command))
    app.add_handler(CommandHandler("insta_session", insta_session_command))
    app.add_handler(CommandHandler("insta_status", insta_status_command))
    app.add_handler(CommandHandler("insta_autopost", insta_autopost_command))
    app.add_handler(CommandHandler("insta_logout", insta_logout_command))

    # Register Global Error Handler
    app.add_error_handler(global_error_handler)

    # Register Periodic Cleanup Job & Daily AutoPilot Schedulers
    if app.job_queue:
        app.job_queue.run_repeating(periodic_cleanup_job, interval=3600, first=60)
        logger.info("Scheduled retention cleanup job (interval: 1 hour)")
        register_autopilot_jobs(app)

    return app


def start_health_server() -> None:
    """Run lightweight HTTP healthcheck server for cloud hosting (Render, Koyeb, Railway)."""
    import os
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler

    port_str = os.environ.get("PORT")
    if not port_str:
        return

    port = int(port_str)

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Telegram Reel Maker Bot is running!")

        def log_message(self, format, *args):
            pass

    try:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"Healthcheck server listening on port {port}")
    except Exception as e:
        logger.warning(f"Could not start healthcheck server on port {port}: {e}")


def main() -> None:
    """Run bot polling."""
    start_health_server()
    # Run setup asynchronously
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app = loop.run_until_complete(setup_bot())

    logger.info("🚀 Telegram Reel Maker Bot is running and polling for updates...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
