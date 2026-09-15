"""Instagram Reels Publishing & Account Management Service.

Provides:
1. Direct Local Reel Publishing via instagrapi (Session persistence & local upload)
2. Challenge / 2FA Handling
3. Auto-Posting Integration
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from instagrapi import Client
from instagrapi.exceptions import (
    BadPassword,
    TwoFactorRequired,
    ChallengeRequired,
    FeedbackRequired,
    LoginRequired
)

from database.db import db_manager

# Ensure moviepy has VideoFileClip for instagrapi compatibility
try:
    import moviepy
    if not hasattr(moviepy, "VideoFileClip"):
        from moviepy.editor import VideoFileClip
        moviepy.VideoFileClip = VideoFileClip
except Exception:
    pass

logger = logging.getLogger(__name__)

SESSION_DIR = Path("data/sessions")


class InstagramService:
    """Unified Instagram Publishing and Session Manager."""

    def __init__(self, session_dir: Path = SESSION_DIR):
        self.session_dir = session_dir
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_path(self, chat_id: int) -> Path:
        return self.session_dir / f"instagram_{chat_id}.json"

    def _create_client(self) -> Client:
        cl = Client()
        cl.delay_range = [1, 3]
        return cl

    async def login_user(
        self,
        chat_id: int,
        username: str,
        password: str,
        verification_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """Authenticate Instagram account, save session cookie file, and record in DB."""
        session_path = self._get_session_path(chat_id)
        cl = self._create_client()

        def _do_login():
            try:
                # If session exists, try loading it first
                if session_path.exists():
                    try:
                        cl.load_settings(session_path)
                    except Exception:
                        pass
                
                if verification_code:
                    cl.login(username, password, verification_code=verification_code)
                else:
                    cl.login(username, password)

                cl.dump_settings(session_path)
                user_info = cl.user_info(cl.user_id)
                return {
                    "success": True,
                    "username": username,
                    "full_name": user_info.full_name,
                    "pk": cl.user_id,
                }
            except BadPassword:
                return {"success": False, "error": "Invalid password. Please check your credentials."}
            except TwoFactorRequired:
                return {
                    "success": False,
                    "error": "Two-Factor Authentication (2FA) required. Run `/insta_2fa <code>` to verify.",
                    "requires_2fa": True
                }
            except ChallengeRequired:
                return {
                    "success": False,
                    "error": "Instagram security challenge required. Please open Instagram app on your phone, approve the login, and try again."
                }
            except FeedbackRequired as e:
                return {"success": False, "error": f"Instagram rate limit/feedback required: {e}"}
            except Exception as e:
                logger.exception(f"Instagram login failed: {e}")
                return {"success": False, "error": str(e)}

        result = await asyncio.to_thread(_do_login)
        if result.get("success"):
            await db_manager.save_instagram_account(
                chat_id=chat_id,
                username=username,
                session_file=str(session_path),
                auto_post=0
            )
            logger.info(f"Instagram user @{username} successfully connected for chat {chat_id}")
        return result

    async def login_with_sessionid(
        self,
        chat_id: int,
        sessionid: str
    ) -> Dict[str, Any]:
        """Authenticate using browser sessionid cookie, save session, and record in DB."""
        session_path = self._get_session_path(chat_id)
        cl = self._create_client()

        def _do_login():
            try:
                clean_sid = sessionid.strip().strip('"').strip("'")
                cl.login_by_sessionid(clean_sid)
                cl.dump_settings(session_path)
                username = cl.username
                user_info = cl.user_info(cl.user_id)
                return {
                    "success": True,
                    "username": username,
                    "full_name": user_info.full_name,
                    "pk": cl.user_id,
                }
            except Exception as e:
                logger.exception(f"Instagram session login failed: {e}")
                return {"success": False, "error": str(e)}

        result = await asyncio.to_thread(_do_login)
        if result.get("success"):
            await db_manager.save_instagram_account(
                chat_id=chat_id,
                username=result["username"],
                session_file=str(session_path),
                auto_post=0
            )
            logger.info(f"Instagram user @{result['username']} connected via sessionid for chat {chat_id}")
        return result


    async def get_authenticated_client(self, chat_id: int) -> Optional[Client]:
        """Retrieve instagrapi Client with active session."""
        acc = await db_manager.get_instagram_account(chat_id)
        if not acc:
            return None

        session_path = Path(acc["session_file"])
        if not session_path.exists():
            return None

        cl = self._create_client()
        try:
            cl.load_settings(session_path)
            return cl
        except Exception as e:
            logger.warning(f"Could not load Instagram session for {chat_id}: {e}")
            return None

    async def is_connected(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """Check if an active Instagram account is linked."""
        return await db_manager.get_instagram_account(chat_id)

    async def set_autopost(self, chat_id: int, enabled: bool) -> bool:
        """Enable or disable automatic posting on reel creation."""
        acc = await self.is_connected(chat_id)
        if not acc:
            return False
        await db_manager.set_instagram_autopost(chat_id, enabled)
        return True

    async def logout(self, chat_id: int) -> bool:
        """Disconnect Instagram account and delete stored session file."""
        session_path = self._get_session_path(chat_id)
        if session_path.exists():
            try:
                session_path.unlink()
            except Exception:
                pass
        await db_manager.delete_instagram_account(chat_id)
        return True

    async def upload_reel(
        self,
        chat_id: int,
        video_path: Path,
        caption: str = ""
    ) -> Dict[str, Any]:
        """Upload a 1080x1920 MP4 reel directly to user's Instagram feed/reels."""
        cl = await self.get_authenticated_client(chat_id)
        if not cl:
            return {
                "success": False,
                "error": "Instagram account not connected. Use `/insta_login username password` first."
            }

        if not video_path.exists():
            return {"success": False, "error": f"Video file not found: {video_path}"}

        # Generate custom thumbnail at 2.0s using FFmpeg to avoid MoviePy thumbnailer
        thumb_path = video_path.with_suffix(".thumb.jpg")
        if not thumb_path.exists():
            try:
                import subprocess
                subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-ss", "00:00:02",
                        "-i", str(video_path),
                        "-vframes", "1",
                        "-q:v", "2",
                        str(thumb_path),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=10,
                )
            except Exception as e:
                logger.warning(f"Could not generate ffmpeg thumbnail: {e}")

        def _do_upload():
            try:
                logger.info(f"Uploading clip {video_path} to Instagram...")
                media = cl.clip_upload(
                    path=str(video_path),
                    caption=caption,
                    thumbnail=str(thumb_path) if thumb_path.exists() else None,
                )
                media_code = getattr(media, "code", None)
                media_id = getattr(media, "id", None)
                post_url = f"https://www.instagram.com/reel/{media_code}/" if media_code else None
                return {
                    "success": True,
                    "media_id": media_id,
                    "code": media_code,
                    "url": post_url
                }
            except LoginRequired:
                return {"success": False, "error": "Instagram session expired. Please re-login with /insta_login."}
            except Exception as e:
                logger.exception(f"Failed to upload reel to Instagram: {e}")
                return {"success": False, "error": str(e)}

        return await asyncio.to_thread(_do_upload)


# Singleton instance
instagram_service = InstagramService()
