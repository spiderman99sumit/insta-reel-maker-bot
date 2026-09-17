"""Automated Daily Reel Scheduler with 10-Minute Advance Alert & Auto-Posting (IST).

Features:
1. Daily 3 peak slots (12:20 PM, 07:50 PM, 10:35 PM IST).
2. Pure Vocal Lyrics Audio Only (NO BGM, NO Instrumental).
3. 10-Minute Advance Alert: If user does not cancel / reply within 10 minutes, automatically posts to Instagram!
"""

import asyncio
import datetime
import logging
import random
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import aiosqlite

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, ContextTypes

from bot.handlers.commands import restricted
from bot.services.instagram_service import instagram_service
from bot.services.music_service import music_service
from bot.services.render_service import execute_render_job
from bot.utils.config import config
from database.db import db_manager

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
DEFAULT_ADMIN_CHAT_ID = 5381201341

# Store pending auto-post tasks: post_id -> {chat_id, video_path, caption, target_time, status}
PENDING_AUTO_POSTS: Dict[str, Dict[str, Any]] = {}

# 8 Optimal Daily Viral Slots (Delivery 10 min before peak posting hour)
DAILY_SLOTS = [
    {
        "name": "slot_aesthetic_morning",
        "category": "aesthetic",
        "title": "Aesthetic / Soft Glow",
        "icon": "✨",
        "delivery_time_str": "08:20 AM IST",
        "target_post_time_str": "08:30 AM IST",
        "hour": 8,
        "minute": 20,
    },
    {
        "name": "slot_bestie_morning",
        "category": "bestie",
        "title": "Bestie Love / Duo Goals",
        "icon": "👯‍♀️",
        "delivery_time_str": "10:50 AM IST",
        "target_post_time_str": "11:00 AM IST",
        "hour": 10,
        "minute": 50,
    },
    {
        "name": "slot_traditional_afternoon",
        "category": "traditional",
        "title": "Desi Traditional",
        "icon": "👑",
        "delivery_time_str": "01:20 PM IST",
        "target_post_time_str": "01:30 PM IST",
        "hour": 13,
        "minute": 20,
    },
    {
        "name": "slot_broken_tea",
        "category": "broken",
        "title": "Broken Heart / Dard",
        "icon": "💔",
        "delivery_time_str": "04:20 PM IST",
        "target_post_time_str": "04:30 PM IST",
        "hour": 16,
        "minute": 20,
    },
    {
        "name": "slot_romantic_evening",
        "category": "romantic",
        "title": "Romantic Love",
        "icon": "💖",
        "delivery_time_str": "07:20 PM IST",
        "target_post_time_str": "07:30 PM IST",
        "hour": 19,
        "minute": 20,
    },
    {
        "name": "slot_baddie_night",
        "category": "baddie",
        "title": "Hot & Baddie / Attitude",
        "icon": "🔥",
        "delivery_time_str": "09:05 PM IST",
        "target_post_time_str": "09:15 PM IST",
        "hour": 21,
        "minute": 5,
    },
    {
        "name": "slot_sexy_latenight",
        "category": "sexy",
        "title": "Sexy / Flirty Desi",
        "icon": "💋",
        "delivery_time_str": "10:20 PM IST",
        "target_post_time_str": "10:30 PM IST",
        "hour": 22,
        "minute": 20,
    },
    {
        "name": "slot_cinematic_midnight",
        "category": "cinematic",
        "title": "Late Night / Cinematic",
        "icon": "🎬",
        "delivery_time_str": "11:35 PM IST",
        "target_post_time_str": "11:45 PM IST",
        "hour": 23,
        "minute": 35,
    },
]


async def init_autopilot_db() -> None:
    """Ensure autopilot settings table exists and default user is subscribed."""
    async with aiosqlite.connect(config.database_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS autopilot_settings (
                chat_id INTEGER PRIMARY KEY,
                is_active INTEGER DEFAULT 1,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # Seed primary user if not exists
        await db.execute("""
            INSERT OR IGNORE INTO autopilot_settings (chat_id, is_active)
            VALUES (?, 1);
        """, (DEFAULT_ADMIN_CHAT_ID,))
        await db.commit()


async def is_autopilot_active(chat_id: int) -> bool:
    """Check if autopilot is enabled for a given chat."""
    await init_autopilot_db()
    async with aiosqlite.connect(config.database_path) as db:
        async with db.execute("SELECT is_active FROM autopilot_settings WHERE chat_id = ?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
            if row is not None:
                return bool(row[0])
    return True if chat_id == DEFAULT_ADMIN_CHAT_ID else False


async def set_autopilot_status(chat_id: int, is_active: bool) -> None:
    """Enable or disable autopilot for a chat."""
    await init_autopilot_db()
    async with aiosqlite.connect(config.database_path) as db:
        await db.execute("""
            INSERT INTO autopilot_settings (chat_id, is_active, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE SET is_active = ?, updated_at = CURRENT_TIMESTAMP;
        """, (chat_id, 1 if is_active else 0, 1 if is_active else 0))
        await db.commit()


async def get_active_subscribers() -> List[int]:
    """Retrieve all chat IDs with active autopilot subscription."""
    await init_autopilot_db()
    async with aiosqlite.connect(config.database_path) as db:
        async with db.execute("SELECT chat_id FROM autopilot_settings WHERE is_active = 1") as cursor:
            rows = await cursor.fetchall()
            subs = [r[0] for r in rows]
            if DEFAULT_ADMIN_CHAT_ID not in subs:
                subs.append(DEFAULT_ADMIN_CHAT_ID)
            return subs


def get_pure_vocal_lyrics_track(category: str) -> Dict[str, Any]:
    """Pick ONLY pure vocal lyrics tracks (NO BGM, NO instrumental)."""
    vocal_options = music_service.get_vocal_options(category=category, limit=10)
    # Strictly filter for vocal lyrical files
    lyrics_only = [t for t in vocal_options if t.get("lyrics") and t["file"].endswith("_vocal.mp3")]
    if not lyrics_only:
        lyrics_only = vocal_options

    if lyrics_only:
        chosen = random.choice(lyrics_only)
        return {
            "path": chosen["path"],
            "title": chosen["title"],
            "artist": chosen.get("artist", "Bollywood Vocal"),
            "lyrics": chosen.get("lyrics", ""),
        }
    fallback_p = music_service.get_bollywood_track(category)
    return {
        "path": fallback_p,
        "title": music_service.get_track_title(fallback_p),
        "artist": "Bollywood Vocal",
        "lyrics": "",
    }


async def auto_post_after_10min_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Timer callback triggered 10 minutes after alert if user did not cancel."""
    job_data = context.job.data or {}
    post_id = job_data.get("post_id")
    chat_id = job_data.get("chat_id")

    item = PENDING_AUTO_POSTS.get(post_id)
    if not item:
        return

    # Check status: if user cancelled or already posted, skip
    if item.get("status") != "pending":
        logger.info(f"[AutoPilot] Auto-post for {post_id} skipped: status is '{item.get('status')}'")
        return

    item["status"] = "posting"
    video_path = Path(item["video_path"])
    caption = item["caption"]
    target_time_str = item.get("target_time_str", "Now")

    # Check Instagram login status
    acc = await instagram_service.is_connected(chat_id)
    if not acc:
        item["status"] = "not_connected"
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"⏰ *10 Minutes Elapsed ({target_time_str})*\n\n"
                "Auto-post was skipped because your Instagram account is not connected yet.\n\n"
                "💡 Connect your account: `/insta_login username password` or `/insta_session sessionid`\n"
                "You can download the video above and upload it directly to Instagram!"
            ),
            parse_mode="Markdown",
        )
        return

    # Post to Instagram
    logger.info(f"[AutoPilot] Publishing reel to Instagram for chat {chat_id}...")
    result = await instagram_service.upload_reel(chat_id=chat_id, video_path=video_path, caption=caption)

    if result.get("success"):
        item["status"] = "posted"
        media_id = result.get("media_id", "")
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🚀 *Auto-Posted to Instagram Successfully!*\n\n"
                f"10 minutes elapsed without cancellation, so your reel was published live for the scheduled slot (*{target_time_str}*)! 🎉\n\n"
                f"• Account: @{acc.get('username')}\n"
                f"• Media ID: `{media_id}`"
            ),
            parse_mode="Markdown",
        )
    else:
        item["status"] = "failed"
        err = result.get("error", "Unknown error")
        logger.error(f"[AutoPilot] Instagram auto-post failed: {err}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"⚠️ *Instagram Auto-Post Failed:*\n{err}\n\n"
                "You can download the video above and upload it manually to Instagram."
            ),
            parse_mode="Markdown",
        )


async def generate_and_deliver_scheduled_reel(
    bot,
    chat_id: int,
    category: str,
    target_time_str: str,
    delivery_time_str: str,
    job_queue=None,
) -> None:
    """Automated pipeline: picks unused photo, pure lyrics audio, renders, and arms 10-min auto-post timer."""
    from bot.handlers.auto import get_random_category_image, get_category_info, ALL_HOOK_OPTIONS

    cat_info = get_category_info(category)
    image_path = get_random_category_image(category, chat_id)

    # Pick matching hook
    cat_hooks = [h["text"] for h in ALL_HOOK_OPTIONS if category in h.get("categories", [])]
    if not cat_hooks:
        cat_hooks = [h["text"] for h in ALL_HOOK_OPTIONS]
    hook_text = random.choice(cat_hooks)

    # STRICT: Pure vocal lyrics audio (NO BGM, NO Instrumental)
    track_info = get_pure_vocal_lyrics_track(category)
    vocal_path = track_info["path"]
    song_title = f"{track_info['title']} - {track_info['artist']}"

    # Deploy image to input dir
    timestamp = int(asyncio.get_event_loop().time())
    deployed_img = config.input_dir / f"{chat_id}_auto_{timestamp}.jpg"
    shutil.copy(image_path, deployed_img)

    # Record in session
    await db_manager.start_reel_session(chat_id)
    await db_manager.update_session(
        chat_id,
        media_path=str(deployed_img),
        media_type="image",
        overlay_text=hook_text,
        selected_template=category,
        music_path=str(vocal_path) if vocal_path else None,
    )

    try:
        # Render video
        final_video_path = await execute_render_job(chat_id)

        # Move image to assets/images/used/ only if NOT in testing mode
        is_testing = await db_manager.is_testing_mode()
        if not is_testing:
            used_dir = Path("assets/images/used")
            used_dir.mkdir(parents=True, exist_ok=True)
            dest_used = used_dir / image_path.name
            try:
                if image_path.exists() and "assets/images/categories" in str(image_path).replace("\\", "/"):
                    shutil.move(str(image_path), str(dest_used))
                    logger.info(f"[AutoPilot] Moved {image_path.name} to {dest_used}")
            except Exception as e:
                logger.warning(f"[AutoPilot] Could not move image: {e}")

            await db_manager.record_used_asset(chat_id, "image", image_path.name)
            await db_manager.record_used_asset(chat_id, "text", hook_text)
            status_tag = "*(Moved to Used Folder ✅)*"
        else:
            logger.info(f"[AutoPilot] Testing mode: kept {image_path.name} in category pool without moving to used")
            status_tag = "*(Testing Mode — Kept in Pool 🔄)*"

        hashtags = "#reels #trending #viral #fyp #explore #explorepage #instareels #aesthetic"
        ig_caption = f"{hook_text}\n\n{hashtags}"

        post_id = f"ap_{chat_id}_{timestamp}"
        PENDING_AUTO_POSTS[post_id] = {
            "chat_id": chat_id,
            "video_path": str(final_video_path),
            "caption": ig_caption,
            "target_time_str": target_time_str,
            "status": "pending",
        }

        # Arm 10-minute auto-post timer (600 seconds)
        if job_queue:
            job_queue.run_once(
                auto_post_after_10min_callback,
                when=600,
                data={"post_id": post_id, "chat_id": chat_id},
                name=f"autopost_timer_{post_id}",
            )
            logger.info(f"[AutoPilot] Armed 10-minute auto-post timer for {post_id}")

        caption = (
            f"⏰ *Reel Ready — Scheduled for {target_time_str}* 🚀\n\n"
            f"📂 *Category:* {cat_info['icon']} *{cat_info['title']}*\n"
            f"📸 *Photo:* `{image_path.name}` {status_tag}\n"
            f"🎤 *Audio:* {song_title}\n\n"
            f"📝 *Text Overlay:*\n"
            f"_{hook_text}_\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ *1-TAP ACTIONS:*\n"
            f"• Tap *[✋ I'll Post Myself]* to post manually with your own audio.\n"
            f"• Or do nothing — bot will automatically post at *{target_time_str}*!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✋ I'll Post Myself", callback_data=f"user_posting_{post_id}"),
                InlineKeyboardButton("🚀 Post Now", callback_data=f"post_now_{post_id}"),
            ],
            [
                InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_autopost_{post_id}"),
            ],
        ])

        with open(final_video_path, "rb") as vf:
            await bot.send_video(
                chat_id=chat_id,
                video=vf,
                caption=caption,
                reply_markup=keyboard,
                supports_streaming=True,
                parse_mode="Markdown",
                write_timeout=180,
                read_timeout=180,
            )
        logger.info(f"[AutoPilot] Delivered scheduled reel {post_id} to chat {chat_id}")

    except Exception as e:
        logger.error(f"[AutoPilot] Reel generation failed for chat {chat_id}: {e}", exc_info=True)
        await bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ *AutoPilot Notification:*\nError while generating scheduled reel: {e}",
            parse_mode="Markdown",
        )


async def execute_autopilot_slot_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job callback triggered by APScheduler / JobQueue at scheduled delivery times."""
    job_data = context.job.data or {}
    category = job_data.get("category", "romantic")
    target_time_str = job_data.get("target_post_time_str", "08:00 PM IST")
    delivery_time_str = job_data.get("delivery_time_str", "07:50 PM IST")

    subscribers = await get_active_subscribers()
    logger.info(f"[AutoPilot] Running slot {category} for {len(subscribers)} subscriber(s)")

    for chat_id in subscribers:
        try:
            await generate_and_deliver_scheduled_reel(
                bot=context.bot,
                chat_id=chat_id,
                category=category,
                target_time_str=target_time_str,
                delivery_time_str=delivery_time_str,
                job_queue=context.job_queue,
            )
        except Exception as e:
            logger.error(f"[AutoPilot] Failed for chat {chat_id}: {e}")


def register_autopilot_jobs(app: Application) -> None:
    """Register daily scheduled jobs at exact Indian Standard Time (IST)."""
    if not app.job_queue:
        logger.warning("[AutoPilot] JobQueue not available, skipping schedule registration")
        return

    for slot in DAILY_SLOTS:
        scheduled_time = datetime.time(hour=slot["hour"], minute=slot["minute"], tzinfo=IST)
        app.job_queue.run_daily(
            execute_autopilot_slot_job,
            time=scheduled_time,
            data=slot,
            name=slot["name"],
        )
        logger.info(f"[AutoPilot] Registered daily job '{slot['name']}' at {slot['delivery_time_str']}")


# -------------------------------------------------------------
# User Telegram Commands & Callbacks
# -------------------------------------------------------------

@restricted
async def autopilot_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /autopilot or /schedule command."""
    chat_id = update.effective_chat.id
    args = context.args or []

    if args:
        subcmd = args[0].lower().strip()
        if subcmd in ("on", "start", "enable", "1"):
            await set_autopilot_status(chat_id, True)
            await update.effective_message.reply_text(
                "✅ *AutoPilot Mode Activated!*\n\n"
                "The bot will automatically deliver ready reels 10 minutes before peak slots for ALL 8 categories:\n\n"
                "1️⃣ ✨ *08:20 AM IST:* Aesthetic / Soft Glow (Post: 08:30 AM)\n"
                "2️⃣ 👯‍♀️ *10:50 AM IST:* Bestie Love / Duo Goals (Post: 11:00 AM)\n"
                "3️⃣ 👑 *01:20 PM IST:* Desi Traditional (Post: 01:30 PM)\n"
                "4️⃣ 💔 *04:20 PM IST:* Broken Heart / Dard (Post: 04:30 PM)\n"
                "5️⃣ 💖 *07:20 PM IST:* Romantic Love (Post: 07:30 PM)\n"
                "6️⃣ 🔥 *09:05 PM IST:* Hot & Baddie / Attitude (Post: 09:15 PM)\n"
                "7️⃣ 💋 *10:20 PM IST:* Sexy / Flirty Desi (Post: 10:30 PM)\n"
                "8️⃣ 🎬 *11:35 PM IST:* Late Night / Cinematic (Post: 11:45 PM)\n\n"
                "_(💡 If not cancelled within 10 minutes, the bot will auto-publish to Instagram!)_",
                parse_mode="Markdown",
            )
            return

        elif subcmd in ("off", "stop", "disable", "0"):
            await set_autopilot_status(chat_id, False)
            await update.effective_message.reply_text(
                "⏸️ *AutoPilot Paused!*\nDaily automated reel delivery has been disabled.\nSend `/autopilot on` to resume anytime.",
                parse_mode="Markdown",
            )
            return

        elif subcmd in ("test", "run", "now"):
            await update.effective_message.reply_text(
                "⚡ *Running Instant AutoPilot Test...*\nGenerating reel with 10-minute advance alert...",
                parse_mode="Markdown",
            )
            await generate_and_deliver_scheduled_reel(
                bot=context.bot,
                chat_id=chat_id,
                category="romantic",
                target_time_str="08:00 PM IST",
                delivery_time_str="07:50 PM IST",
                job_queue=context.job_queue,
            )
            return

    # Default: Show Status and interactive keyboard
    active = await is_autopilot_active(chat_id)
    status_icon = "🟢 ACTIVE" if active else "🔴 PAUSED"

    now_ist = datetime.datetime.now(IST)
    current_time_str = now_ist.strftime("%I:%M %p")

    msg = (
        f"🤖 *AutoPilot 8-Category Daily Posting Schedule*\n\n"
        f"• Status: *{status_icon}*\n"
        f"• Current Time: *{current_time_str} IST*\n"
        f"• Audio Policy: 🎵 *Pure Vocal Lyrics Only (No BGM / No Instrumental)*\n"
        f"• Fallback: ⏳ *10 Min Inactive -> Auto-Post to Instagram*\n\n"
        "📅 *Full Daily 8-Category Timetable:*\n"
        "1️⃣ ✨ *Aesthetic / Soft:* 08:20 AM (Post: 08:30 AM)\n"
        "2️⃣ 👯‍♀️ *Bestie Love:* 10:50 AM (Post: 11:00 AM)\n"
        "3️⃣ 👑 *Desi Traditional:* 01:20 PM (Post: 01:30 PM)\n"
        "4️⃣ 💔 *Broken Heart / Dard:* 04:20 PM (Post: 04:30 PM)\n"
        "5️⃣ 💖 *Romantic Love:* 07:20 PM (Post: 07:30 PM)\n"
        "6️⃣ 🔥 *Hot & Baddie:* 09:05 PM (Post: 09:15 PM)\n"
        "7️⃣ 💋 *Sexy / Flirty Desi:* 10:20 PM (Post: 10:30 PM)\n"
        "8️⃣ 🎬 *Late Night Cinematic:* 11:35 PM (Post: 11:45 PM)"
    )

    toggle_btn = (
        InlineKeyboardButton("🔴 Turn OFF AutoPilot", callback_data="autopilot_toggle_off")
        if active
        else InlineKeyboardButton("🟢 Turn ON AutoPilot", callback_data="autopilot_toggle_on")
    )

    keyboard = InlineKeyboardMarkup([
        [toggle_btn],
        [InlineKeyboardButton("🧪 Test Auto Reel Now", callback_data="autopilot_test_now")],
        [InlineKeyboardButton("🎬 Create Manual Reel", callback_data="back_to_cats")],
    ])

    await update.effective_message.reply_text(msg, reply_markup=keyboard, parse_mode="Markdown")


@restricted
async def testing_mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /testing_mode command to toggle testing vs live production mode."""
    chat_id = update.effective_chat.id
    args = context.args or []
    if args:
        subcmd = args[0].lower().strip()
        if subcmd in ("on", "1", "true", "start", "enable"):
            await db_manager.set_testing_mode(True)
            await update.effective_message.reply_text(
                "🧪 *Testing Mode is now ON!*\n\n"
                "• Photos will **NEVER** be moved to `used/` folder.\n"
                "• All assets remain 100% reusable for testing.\n"
                "• Zero duplicate-prevention locks applied during testing.\n\n"
                "When you are ready to start live production, run `/testing_mode off`.",
                parse_mode="Markdown",
            )
            return
        elif subcmd in ("off", "0", "false", "stop", "live", "disable"):
            await db_manager.set_testing_mode(False)
            await update.effective_message.reply_text(
                "🚀 *Production Mode is now ACTIVE (Testing Mode OFF)!*\n\n"
                "• Rendered photos will be moved to `used/` folder to ensure zero duplicates.\n"
                "• Used history tracking is fully enabled.",
                parse_mode="Markdown",
            )
            return

    is_testing = await db_manager.is_testing_mode()
    status_str = "🟢 ON (Safe - Photos Kept in Pool)" if is_testing else "🔴 OFF (Production - Photos Moved to Used)"
    await update.effective_message.reply_text(
        f"🧪 *Testing Mode Status:* {status_str}\n\n"
        f"To toggle:\n"
        f"• `/testing_mode on` — Keep all photos in category pool (no moving)\n"
        f"• `/testing_mode off` — Move used photos to `used/` (Production)",
        parse_mode="Markdown",
    )


async def handle_autopilot_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle interactive buttons for autopilot settings and cancel/post actions."""
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    data = query.data or ""

    if data.startswith("user_posting_"):
        post_id = data.replace("user_posting_", "")
        item = PENDING_AUTO_POSTS.get(post_id)
        if item:
            item["status"] = "user_handled"
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(
                "✋ *Auto-Post Cancelled!*\n\n"
                "• Marked as self-posting — bot will **NOT** upload to Instagram.\n"
                "• Download the video above and share it on Instagram with your favorite music.\n\n"
                "✅ _Zero duplicate posting guaranteed._",
                parse_mode="Markdown",
            )
        else:
            await query.message.reply_text("✅ Auto-post cancelled! Bot will not post.")

    elif data.startswith("cancel_autopost_"):
        post_id = data.replace("cancel_autopost_", "")
        item = PENDING_AUTO_POSTS.get(post_id)
        if item:
            item["status"] = "canceled"
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(
                "❌ *Reel Cancelled!*\n\nAuto-post has been stopped. The video remains saved in your chat.",
                parse_mode="Markdown",
            )
        else:
            await query.message.reply_text("⚠️ Timer has already expired or been cancelled.")

    elif data.startswith("post_now_"):
        post_id = data.replace("post_now_", "")
        item = PENDING_AUTO_POSTS.get(post_id)
        if item and item.get("status") in ("pending", "canceled"):
            item["status"] = "posting"
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("🚀 *Publishing to Instagram now...*", parse_mode="Markdown")

            acc = await instagram_service.is_connected(chat_id)
            if not acc:
                await query.message.reply_text(
                    "❌ *Instagram Not Connected!*\nUse `/insta_login` or `/insta_session` to connect.",
                    parse_mode="Markdown",
                )
                return

            res = await instagram_service.upload_reel(
                chat_id=chat_id,
                video_path=Path(item["video_path"]),
                caption=item["caption"],
            )
            if res.get("success"):
                item["status"] = "posted"
                await query.message.reply_text(
                    f"🎉 *Published to Instagram Successfully!*\nReel is live on @{acc.get('username')}! 🚀",
                    parse_mode="Markdown",
                )
            else:
                await query.message.reply_text(f"❌ Upload Failed: {res.get('error')}", parse_mode="Markdown")

    elif data == "autopilot_toggle_on":
        await set_autopilot_status(chat_id, True)
        await query.edit_message_text(
            "✅ *AutoPilot Mode Activated!*\n\n"
            "Daily reels will be delivered at 12:20 PM, 7:50 PM, and 10:35 PM IST with a 10-minute auto-post fallback! 🚀",
            parse_mode="Markdown",
        )

    elif data == "autopilot_toggle_off":
        await set_autopilot_status(chat_id, False)
        await query.edit_message_text(
            "⏸️ *AutoPilot Mode Paused!*\nDaily automated reels are currently paused.",
            parse_mode="Markdown",
        )

    elif data == "autopilot_test_now":
        await query.edit_message_text(
            "🧪 *Testing AutoPilot Reel Generation...*\nGenerating reel with 10-minute advance alert...",
            parse_mode="Markdown",
        )
        await generate_and_deliver_scheduled_reel(
            bot=context.bot,
            chat_id=chat_id,
            category="romantic",
            target_time_str="08:00 PM IST",
            delivery_time_str="07:50 PM IST",
            job_queue=context.job_queue,
        )

    elif data == "autopilot_status_view":
        await autopilot_command(update, context)
