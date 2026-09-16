"""SQLite database management for Telegram Reel Maker Bot user sessions."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
import aiosqlite

from bot.utils.config import config

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    telegram_chat_id INTEGER PRIMARY KEY,
    current_step TEXT NOT NULL DEFAULT 'IDLE',
    media_path TEXT,
    media_type TEXT,
    overlay_text TEXT,
    music_path TEXT,
    selected_template TEXT,
    output_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS instagram_accounts (
    telegram_chat_id INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    session_file TEXT NOT NULL,
    auto_post INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS used_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_chat_id INTEGER NOT NULL,
    asset_type TEXT NOT NULL,
    asset_identifier TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_used_history ON used_history(telegram_chat_id, asset_type);

CREATE TABLE IF NOT EXISTS bot_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


class DatabaseManager:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    async def init_db(self) -> None:
        """Initialize SQLite database tables."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(CREATE_TABLE_SQL)
            await db.commit()
            logger.info(f"Database initialized at {self.db_path}")

    async def get_session(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve the active session dictionary for a specific Telegram chat ID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM sessions WHERE telegram_chat_id = ?",
                (chat_id,),
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

    async def start_reel_session(self, chat_id: int) -> None:
        """Start or reset a session into WAITING_MEDIA step."""
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO sessions (
                    telegram_chat_id, current_step, media_path, media_type,
                    overlay_text, music_path, selected_template, output_path,
                    created_at, updated_at
                ) VALUES (?, 'WAITING_MEDIA', NULL, NULL, NULL, NULL, NULL, NULL, ?, ?)
                ON CONFLICT(telegram_chat_id) DO UPDATE SET
                    current_step='WAITING_MEDIA',
                    media_path=NULL,
                    media_type=NULL,
                    overlay_text=NULL,
                    music_path=NULL,
                    selected_template=NULL,
                    output_path=NULL,
                    updated_at=excluded.updated_at;
                """,
                (chat_id, now, now),
            )
            await db.commit()

    async def update_session(self, chat_id: int, **kwargs: Any) -> None:
        """Update arbitrary columns for a user's session."""
        if not kwargs:
            return

        kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [chat_id]

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"UPDATE sessions SET {set_clause} WHERE telegram_chat_id = ?",
                values,
            )
            await db.commit()

    async def reset_session(self, chat_id: int) -> None:
        """Reset session to IDLE state."""
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE sessions SET
                    current_step='IDLE',
                    media_path=NULL,
                    media_type=NULL,
                    overlay_text=NULL,
                    music_path=NULL,
                    selected_template=NULL,
                    output_path=NULL,
                    updated_at=?
                WHERE telegram_chat_id = ?
                """,
                (now, chat_id),
            )
            await db.commit()

    async def save_instagram_account(
        self,
        chat_id: int,
        username: str,
        session_file: str,
        auto_post: int = 0,
    ) -> None:
        """Save or update an authenticated Instagram account session."""
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO instagram_accounts (
                    telegram_chat_id, username, session_file, auto_post, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(telegram_chat_id) DO UPDATE SET
                    username=excluded.username,
                    session_file=excluded.session_file,
                    auto_post=excluded.auto_post,
                    updated_at=excluded.updated_at;
                """,
                (chat_id, username, session_file, auto_post, now, now),
            )
            await db.commit()

    async def get_instagram_account(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve Instagram account details for a chat ID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM instagram_accounts WHERE telegram_chat_id = ?",
                (chat_id,),
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

    async def set_instagram_autopost(self, chat_id: int, auto_post: bool) -> None:
        """Toggle auto_post flag for a user's Instagram account."""
        now = datetime.now(timezone.utc).isoformat()
        val = 1 if auto_post else 0
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE instagram_accounts SET auto_post = ?, updated_at = ? WHERE telegram_chat_id = ?",
                (val, now, chat_id),
            )
            await db.commit()

    async def delete_instagram_account(self, chat_id: int) -> None:
        """Disconnect and delete Instagram account record for a chat ID."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM instagram_accounts WHERE telegram_chat_id = ?",
                (chat_id,),
            )
            await db.commit()

    async def record_used_asset(self, chat_id: int, asset_type: str, asset_identifier: str) -> None:
        """Record an asset (image, music, text) as used so it won't be repeated."""
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO used_history (telegram_chat_id, asset_type, asset_identifier, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, asset_type, asset_identifier, now),
            )
            await db.commit()

    async def get_used_assets(self, chat_id: int, asset_type: str) -> set:
        """Get set of all asset identifiers already used by this chat."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT asset_identifier FROM used_history WHERE telegram_chat_id = ? AND asset_type = ?",
                (chat_id, asset_type),
            )
            rows = await cursor.fetchall()
            return {row[0] for row in rows}

    async def clear_used_assets(self, chat_id: int, asset_type: Optional[str] = None) -> None:
        """Reset used assets for a user (if needed)."""
        async with aiosqlite.connect(self.db_path) as db:
            if asset_type:
                await db.execute(
                    "DELETE FROM used_history WHERE telegram_chat_id = ? AND asset_type = ?",
                    (chat_id, asset_type),
                )
            else:
                await db.execute(
                    "DELETE FROM used_history WHERE telegram_chat_id = ?",
                    (chat_id,),
                )
            await db.commit()

    async def is_testing_mode(self) -> bool:
        """Check if bot is in testing mode (default True during testing phase)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("CREATE TABLE IF NOT EXISTS bot_settings (key TEXT PRIMARY KEY, value TEXT);")
            async with db.execute("SELECT value FROM bot_settings WHERE key = 'testing_mode'") as cursor:
                row = await cursor.fetchone()
                if row:
                    return row[0] == "1"
                return True

    async def set_testing_mode(self, is_testing: bool) -> None:
        """Toggle testing mode."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("CREATE TABLE IF NOT EXISTS bot_settings (key TEXT PRIMARY KEY, value TEXT);")
            await db.execute(
                "INSERT INTO bot_settings (key, value) VALUES ('testing_mode', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = ?;",
                ("1" if is_testing else "0", "1" if is_testing else "0"),
            )
            await db.commit()


# Singleton instance
db_manager = DatabaseManager(config.database_path)

