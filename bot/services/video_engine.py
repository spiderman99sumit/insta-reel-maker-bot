"""FFmpeg video rendering engine for generating 9:16 Instagram Reels."""

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

from bot.services.text_overlay import create_text_overlay
from bot.templates.styles import TemplateStyle, get_template
from bot.utils.config import config
from bot.utils.ffmpeg_check import check_ffmpeg_installed, probe_media

logger = logging.getLogger(__name__)


class VideoEngineError(Exception):
    """Custom exception for video engine rendering failures."""
    pass


def run_ffmpeg_command(cmd: list) -> None:
    """Execute ffmpeg command safely with logging."""
    logger.info(f"Running ffmpeg: {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        logger.error(f"FFmpeg failed with code {result.returncode}:\n{result.stderr}")
        raise VideoEngineError(f"FFmpeg rendering error: {result.stderr[-400:]}")


def create_image_reel(
    image_path: Path,
    output_path: Path,
    duration: float,
    template: TemplateStyle,
    fps: int = 25,
) -> Path:
    """Convert static image into 9:16 video with blurred background and Ken Burns effect."""
    if not check_ffmpeg_installed():
        raise VideoEngineError("FFmpeg is not installed")

    total_frames = int(duration * fps)

    # Ken Burns filter logic
    if template.ken_burns == "zoom_in":
        zoom_expr = f"zoompan=z='min(zoom+0.0008,1.20)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s=1080x1920:fps={fps}"
    elif template.ken_burns == "zoom_out":
        zoom_expr = f"zoompan=z='if(lte(zoom,1.0),1.20,max(1.001,zoom-0.0008))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s=1080x1920:fps={fps}"
    else:
        zoom_expr = "format=yuv420p"

    # Filter complex with smart aspect ratio blurred background + foreground aspect fit
    if template.ken_burns in ("zoom_in", "zoom_out"):
        filter_complex = (
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:25[bg];"
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{zoom_expr},format=yuv420p[v]"
        )
    else:
        filter_complex = (
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:25[bg];"
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]

    run_ffmpeg_command(cmd)
    return output_path


def process_video_reel(
    video_path: Path,
    output_path: Path,
    max_duration: float = 60.0,
    fps: int = 30,
) -> Path:
    """Format video to vertical 9:16 (1080x1920) with blurred background padding."""
    if not check_ffmpeg_installed():
        raise VideoEngineError("FFmpeg is not installed")

    filter_complex = (
        f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:25,setsar=1[bg];"
        f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,setsar=1[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={fps},format=yuv420p[v]"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-t", str(max_duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]

    run_ffmpeg_command(cmd)
    return output_path


def add_music(
    video_path: Path,
    audio_path: Optional[Path],
    output_path: Path,
    duration: float,
) -> Path:
    """Add, mix, or loop background music to video."""
    video_info = probe_media(video_path)
    has_orig_audio = video_info.get("has_audio", False)

    fade_out_st = max(0.0, duration - 2.0)

    if audio_path and audio_path.exists():
        if has_orig_audio:
            # Duck original audio and mix with background music
            filter_complex = (
                f"[0:a]volume=0.3[orig];"
                f"[1:a]volume=0.75,afade=t=in:st=0:d=2.0,afade=t=out:st={fade_out_st}:d=2.0[bg];"
                f"[orig][bg]amix=inputs=2:duration=first:dropout_transition=2[a]"
            )
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-stream_loop", "-1", "-i", str(audio_path),
                "-filter_complex", filter_complex,
                "-map", "0:v",
                "-map", "[a]",
                "-t", str(duration),
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                str(output_path),
            ]
        else:
            # No original audio: apply background music directly
            filter_complex = (
                f"[1:a]volume=0.85,afade=t=in:st=0:d=2.0,afade=t=out:st={fade_out_st}:d=2.0[a]"
            )
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-stream_loop", "-1", "-i", str(audio_path),
                "-filter_complex", filter_complex,
                "-map", "0:v",
                "-map", "[a]",
                "-t", str(duration),
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                str(output_path),
            ]
    else:
        # No background music provided
        if has_orig_audio:
            # Keep original audio
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-t", str(duration),
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                str(output_path),
            ]
        else:
            # Synthesize silent AAC audio track for Instagram compatibility
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-t", str(duration),
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                str(output_path),
            ]

    run_ffmpeg_command(cmd)
    return output_path


def render_final_video(
    video_path: Path,
    overlay_png_path: Path,
    output_path: Path,
    duration: float,
    template: TemplateStyle,
) -> Path:
    fade_in_d = 1.0
    text_fade_out_st = max(0.0, duration - 2.0)
    video_fade_out_st = max(0.0, duration - 1.5)

    # 1. Text alpha fade: fades in at 0.5s over 1.0s, stays, fades out at duration-2.0s over 1.5s
    # 2. Video fade: fades out to black over the final 1.5 seconds
    filter_complex = (
        f"[1:v]format=rgba,fade=t=in:st=0.5:d={fade_in_d}:alpha=1,fade=t=out:st={text_fade_out_st}:d=1.5:alpha=1[txt];"
        f"[0:v][txt]overlay=0:0,fade=t=out:st={video_fade_out_st}:d=1.5[v]"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-loop", "1", "-i", str(overlay_png_path),
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "0:a?",
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]

    run_ffmpeg_command(cmd)
    return output_path


def render_complete_reel(
    media_path: Path,
    media_type: str,  # 'image' or 'video'
    text: str,
    template_key: str,
    audio_path: Optional[Path],
    output_path: Path,
    temp_dir: Path,
    target_duration: Optional[float] = None,
) -> Path:
    """Unified master rendering pipeline producing optimized 1080x1920 MP4 reel."""
    template = get_template(template_key)

    # 1. Determine duration
    if media_type == "image":
        duration = float(target_duration or config.output_duration_seconds)
    else:
        probe = probe_media(media_path)
        vid_dur = probe.get("duration", 0.0)
        duration = min(60.0, vid_dur) if vid_dur > 0.5 else float(target_duration or config.output_duration_seconds)

    stem = media_path.stem
    overlay_png = temp_dir / f"{stem}_text_overlay.png"
    base_video = temp_dir / f"{stem}_base.mp4"
    audiomixed_video = temp_dir / f"{stem}_with_audio.mp4"

    # Step A: Generate Text Overlay PNG
    create_text_overlay(
        text=text,
        template=template,
        output_png_path=overlay_png,
        font_path=config.font_path,
    )

    # Step B: Create base 9:16 video
    if media_type == "image":
        create_image_reel(
            image_path=media_path,
            output_path=base_video,
            duration=duration,
            template=template,
        )
    else:
        process_video_reel(
            video_path=media_path,
            output_path=base_video,
            max_duration=duration,
        )

    # Step C: Add / Mix audio
    add_music(
        video_path=base_video,
        audio_path=audio_path,
        output_path=audiomixed_video,
        duration=duration,
    )

    # Step D: Final text overlay composite
    render_final_video(
        video_path=audiomixed_video,
        overlay_png_path=overlay_png,
        output_path=output_path,
        duration=duration,
        template=template,
    )

    return output_path
