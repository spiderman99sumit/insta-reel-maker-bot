"""AI Visual Generator for 1080x1920 Vertical Reels."""

import logging
import random
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFilter

logger = logging.getLogger(__name__)

CANDID_DIR = Path("assets/images/candid")

# Authentic reference-grade candid visual library categorized by style
STYLE_CANDID_MAP: Dict[str, List[str]] = {
    "sexy": [
        "sheer_saree_mirror_selfie.jpg",
        "saree_night_balcony.jpg",
        "bedroom_slipdress_selfie.jpg",
        "halter_denim_candid.jpg",
        "desi_saree_candid_selfie.jpg",
        "desi_backless_blouse_candid.jpg",
        "candid_croptop_mirror_selfie.jpg",
    ],
    "romantic": [
        "pastel_saree_romantic.jpg",
        "saree_night_balcony.jpg",
        "desi_backless_blouse_candid.jpg",
        "royal_green_saree.jpg",
        "sheer_saree_mirror_selfie.jpg",
    ],
    "cinematic": [
        "cinematic_night_drive.jpg",
        "saree_night_balcony.jpg",
        "sheer_saree_mirror_selfie.jpg",
        "desi_saree_candid_selfie.jpg",
    ],
    "traditional": [
        "royal_green_saree.jpg",
        "sheer_saree_mirror_selfie.jpg",
        "desi_saree_candid_selfie.jpg",
        "desi_backless_blouse_candid.jpg",
        "pastel_saree_romantic.jpg",
    ],
    "quote": [
        "cinematic_night_drive.jpg",
        "sheer_saree_mirror_selfie.jpg",
        "bedroom_slipdress_selfie.jpg",
        "saree_night_balcony.jpg",
        "royal_green_saree.jpg",
    ],
    "minimal": [
        "halter_denim_candid.jpg",
        "candid_croptop_mirror_selfie.jpg",
        "cinematic_night_drive.jpg",
        "bedroom_slipdress_selfie.jpg",
    ],
}

_RECENT_IMAGES: List[str] = []


def select_candid_image(style: str, text: Optional[str] = None) -> Optional[Path]:
    """Select authentic candid Pinterest-grade image matching style and text context."""
    if not CANDID_DIR.exists():
        return None

    available_files = {p.name: p for p in CANDID_DIR.glob("*.jpg") if p.stat().st_size > 10000}
    if not available_files:
        return None

    style_key = style.lower().strip()
    text_lower = (text or "").lower()

    candidates: List[str] = []

    # Text keyword specific routing
    if any(k in text_lower for k in ["saree", "saari", "blouse", "pallu", "jhumka"]):
        candidates = [
            "sheer_saree_mirror_selfie.jpg",
            "saree_night_balcony.jpg",
            "desi_saree_candid_selfie.jpg",
            "desi_backless_blouse_candid.jpg",
            "royal_green_saree.jpg",
            "pastel_saree_romantic.jpg",
        ]
    elif any(k in text_lower for k in ["croptop", "crop top", "halter", "jeans", "top"]):
        candidates = [
            "halter_denim_candid.jpg",
            "candid_croptop_mirror_selfie.jpg",
        ]
    elif any(k in text_lower for k in ["drive", "car", "neon", "road", "city", "travel"]):
        candidates = [
            "cinematic_night_drive.jpg",
        ]
    elif any(k in text_lower for k in ["bed", "sleep", "neend", "night", "raat", "good girl", "ruin"]):
        candidates = [
            "bedroom_slipdress_selfie.jpg",
            "saree_night_balcony.jpg",
            "candid_croptop_mirror_selfie.jpg",
        ]
    elif any(k in text_lower for k in ["love", "ishq", "pyar", "romantic", "dil", "sun", "khoya"]):
        candidates = [
            "pastel_saree_romantic.jpg",
            "saree_night_balcony.jpg",
            "royal_green_saree.jpg",
            "desi_backless_blouse_candid.jpg",
        ]
    else:
        candidates = STYLE_CANDID_MAP.get(style_key, STYLE_CANDID_MAP["sexy"])

    valid_candidates = [c for c in candidates if c in available_files]
    if not valid_candidates:
        valid_candidates = list(available_files.keys())

    # Pick an unseen/least recent image to ensure variety every single time
    unseen = [c for c in valid_candidates if c not in _RECENT_IMAGES]
    chosen_name = random.choice(unseen if unseen else valid_candidates)

    _RECENT_IMAGES.append(chosen_name)
    if len(_RECENT_IMAGES) > 6:
        _RECENT_IMAGES.pop(0)

    chosen_path = available_files[chosen_name]
    logger.info(f"Selected authentic candid reference image: {chosen_name} for style '{style}'")
    return chosen_path


def generate_ai_visual(
    style: str,
    output_path: Path,
    text: Optional[str] = None,
    use_flux_ai: bool = True,
    timeout_sec: int = 30,
) -> Path:
    """Generate 1080x1920 visual base using authentic Pinterest candid library."""
    style_key = style.lower().strip()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    candid_path = select_candid_image(style_key, text=text)
    if candid_path and candid_path.exists():
        try:
            with Image.open(candid_path) as im:
                if im.size != (1080, 1920):
                    im_resized = im.resize((1080, 1920), Image.Resampling.LANCZOS)
                    im_resized.save(str(output_path), "JPEG", quality=95)
                else:
                    shutil.copy2(candid_path, output_path)
            logger.info(f"Deployed authentic candid image {candid_path.name} to {output_path}")
            return output_path
        except Exception as e:
            logger.warning(f"Failed to process candid image {candid_path}: {e}")

    # Fallback to aesthetic gradient canvas
    return create_aesthetic_gradient_canvas(style_key, output_path)


PALETTES = {
    "sexy": [(31, 3, 8), (48, 6, 14), (18, 1, 4)],
    "cinematic": [(10, 14, 23), (22, 31, 48), (7, 9, 15)],
    "romantic": [(45, 13, 27), (74, 25, 44), (25, 7, 15)],
    "meme": [(20, 18, 28), (40, 30, 60), (12, 10, 20)],
    "quote": [(12, 12, 14), (20, 20, 24), (8, 8, 10)],
    "minimal": [(18, 18, 18), (28, 28, 28), (10, 10, 10)],
}


def create_aesthetic_gradient_canvas(style: str, output_path: Path) -> Path:
    """Generate high-resolution 1080x1920 aesthetic gradient canvas with subtle grain."""
    width, height = 1080, 1920
    colors = PALETTES.get(style.lower(), PALETTES["sexy"])
    c1, c2, c3 = colors

    base = Image.new("RGB", (width, height), c1)
    draw = ImageDraw.Draw(base)

    for y in range(height):
        ratio = y / height
        if ratio < 0.5:
            local_ratio = ratio * 2
            r = int(c1[0] + (c2[0] - c1[0]) * local_ratio)
            g = int(c1[1] + (c2[1] - c1[1]) * local_ratio)
            b = int(c1[2] + (c2[2] - c1[2]) * local_ratio)
        else:
            local_ratio = (ratio - 0.5) * 2
            r = int(c2[0] + (c3[0] - c2[0]) * local_ratio)
            g = int(c2[1] + (c3[1] - c2[1]) * local_ratio)
            b = int(c3[2] + (c3[2] - c2[2]) * local_ratio)

        draw.line([(0, y), (width, y)], fill=(r, g, b))

    base = base.filter(ImageFilter.GaussianBlur(radius=8))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    base.save(str(output_path), "JPEG", quality=95)
    return output_path
