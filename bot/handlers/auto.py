"""Interactive Category-First Reel Studio with Image+Text Preview First and Song Name Input."""

import asyncio
import logging
import os
import random
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.handlers.commands import restricted
from bot.services.ai_image_engine import (
    generate_ai_visual,
    generate_ai_candid_image,
    fetch_pinterest_candid_image,
)
from bot.services.caption_generator import generate_instagram_caption
from bot.services.instagram_service import instagram_service
from bot.services.music_service import music_service
from bot.services.render_service import execute_render_job
from bot.services.text_overlay import generate_preview_composite
from bot.templates.styles import TEMPLATES
from bot.utils.cleanup import cleanup_chat_files
from bot.utils.config import config
from database.db import db_manager

logger = logging.getLogger(__name__)

# 4 Core Categories / Vibes
CATEGORIES: Dict[str, Dict[str, Any]] = {
    "sexy": {
        "id": "sexy",
        "title": "Sexy / Flirty Desi",
        "icon": "💋",
        "desc": "Bold, seductive candid selfies, backless saree & bedroom aesthetic",
        "style": "sexy",
    },
    "romantic": {
        "id": "romantic",
        "title": "Romantic / Love",
        "icon": "💖",
        "desc": "Pastel sarees, soulmate quotes & emotional love tracks",
        "style": "romantic",
    },
    "cinematic": {
        "id": "cinematic",
        "title": "Late Night / Cinematic",
        "icon": "🎬",
        "desc": "Moody streetlights, car drives, city bokeh & deep thoughts",
        "style": "cinematic",
    },
    "traditional": {
        "id": "traditional",
        "title": "Desi Traditional",
        "icon": "👑",
        "desc": "Royal silk sarees, classic Indian poise & timeless shayari",
        "style": "traditional",
    },
}

# 30 Curated Authentic Candid Reference Aesthetics (100% real photo aesthetic, zero CGI)
ALL_IMAGE_OPTIONS: List[Dict[str, Any]] = [
    {
        "id": "sheer_saree",
        "title": "Sheer Saree Mirror",
        "filename": "sheer_saree_mirror_selfie.jpg",
        "icon": "🖤",
        "desc": "Black sheer saree bedroom mirror selfie",
        "categories": ["sexy", "romantic", "traditional"],
    },
    {
        "id": "red_saree",
        "title": "Crimson Saree Mirror",
        "filename": "red_saree_candid_selfie.jpg",
        "icon": "🌹",
        "desc": "Crimson red chiffon saree bedroom mirror selfie",
        "categories": ["sexy", "romantic", "traditional"],
    },
    {
        "id": "balcony_saree",
        "title": "Balcony Night Saree",
        "filename": "saree_night_balcony.jpg",
        "icon": "🍷",
        "desc": "Burgundy silk saree with midnight city bokeh",
        "categories": ["cinematic", "romantic", "sexy"],
    },
    {
        "id": "slipdress_bedroom",
        "title": "Bedroom Lace Slipdress",
        "filename": "bedroom_slipdress_selfie.jpg",
        "icon": "🤍",
        "desc": "White lace slipdress bedroom mirror candid",
        "categories": ["sexy", "cinematic"],
    },
    {
        "id": "backless_saree",
        "title": "Backless Dori Saree",
        "filename": "desi_backless_blouse_candid.jpg",
        "icon": "💖",
        "desc": "Magenta pink saree with backless dori blouse",
        "categories": ["sexy", "traditional", "romantic"],
    },
    {
        "id": "royal_saree",
        "title": "Royal Emerald Saree",
        "filename": "royal_green_saree.jpg",
        "icon": "💚",
        "desc": "Royal emerald silk saree candid grace",
        "categories": ["traditional", "romantic", "cinematic"],
    },
    {
        "id": "halter_denim",
        "title": "Halter Top & Denim",
        "filename": "halter_denim_candid.jpg",
        "icon": "💛",
        "desc": "Yellow halter crop top with blue denim mirror",
        "categories": ["sexy", "cinematic"],
    },
    {
        "id": "croptop_mirror",
        "title": "Scoop Crop Top Mirror",
        "filename": "candid_croptop_mirror_selfie.jpg",
        "icon": "✨",
        "desc": "Black scoop crop top with white linen pants",
        "categories": ["sexy", "cinematic"],
    },
    {
        "id": "pastel_saree",
        "title": "Pastel Floral Saree",
        "filename": "pastel_saree_romantic.jpg",
        "icon": "🌸",
        "desc": "Lavender floral organza saree golden hour",
        "categories": ["romantic", "traditional"],
    },
    {
        "id": "desi_lamp_saree",
        "title": "Midnight Lamp Saree",
        "filename": "desi_saree_candid_selfie.jpg",
        "icon": "🕯️",
        "desc": "Black saree with warm bedroom night lamp",
        "categories": ["cinematic", "sexy", "traditional"],
    },
    {
        "id": "night_drive",
        "title": "Cinematic Night Drive",
        "filename": "cinematic_night_drive.jpg",
        "icon": "🌃",
        "desc": "Car passenger seat late night city neon bokeh",
        "categories": ["cinematic", "romantic"],
    },
    {
        "id": "candid_real_selfie",
        "title": "Golden Hour Glow",
        "filename": "candid_real_selfie.jpg",
        "icon": "🌅",
        "desc": "Warm golden hour natural candid selfie",
        "categories": ["romantic", "cinematic", "sexy"],
    },
    {
        "id": "sultry_bedroom_candid",
        "title": "Midnight Silk Slipdress",
        "filename": "sultry_bedroom_candid.jpg",
        "icon": "🖤",
        "desc": "Moody midnight bedroom silk candid aesthetic",
        "categories": ["sexy", "cinematic"],
    },
    {
        "id": "sultry_cinematic_portrait",
        "title": "Streetlights Cinematic",
        "filename": "sultry_cinematic_portrait.jpg",
        "icon": "🎬",
        "desc": "Evening ambient streetlights portrait with film grain",
        "categories": ["cinematic", "romantic"],
    },
    {
        "id": "sultry_lounge_portrait",
        "title": "Amber Lounge Candid",
        "filename": "sultry_lounge_portrait.jpg",
        "icon": "🍸",
        "desc": "Warm amber cocktail lounge candid elegance",
        "categories": ["sexy", "cinematic", "romantic"],
    },
    {
        "id": "sultry_night_elegance",
        "title": "Night City Elegance",
        "filename": "sultry_night_elegance.jpg",
        "icon": "✨",
        "desc": "Midnight city lights black evening dress candid",
        "categories": ["cinematic", "sexy", "romantic"],
    },
    {
        "id": "candid_black_saree_mirror",
        "title": "Black Saree Mirror",
        "filename": "candid_black_saree_mirror.jpg",
        "icon": "🖤",
        "desc": "Moody black chiffon saree with ornate earrings",
        "categories": ["sexy", "romantic", "traditional"],
    },
    {
        "id": "candid_wine_saree_balcony",
        "title": "Wine Chiffon Balcony",
        "filename": "candid_wine_saree_balcony.jpg",
        "icon": "🍷",
        "desc": "Deep wine red saree overlooking twinkling evening skyline",
        "categories": ["sexy", "romantic", "cinematic"],
    },
    {
        "id": "candid_cozy_sweater_coffee",
        "title": "Cozy Knit Coffee Candid",
        "filename": "candid_cozy_sweater_coffee.jpg",
        "icon": "☕",
        "desc": "Oversized warm knit sweater holding ceramic coffee mug",
        "categories": ["romantic", "cinematic"],
    },
    {
        "id": "candid_golden_hour_saree",
        "title": "Golden Hour Organza Saree",
        "filename": "candid_golden_hour_saree.jpg",
        "icon": "🌅",
        "desc": "Warm mustard & marigold sheer saree in setting sunbeams",
        "categories": ["romantic", "traditional"],
    },
    {
        "id": "candid_neon_car_passenger",
        "title": "Midnight Neon Car Drive",
        "filename": "candid_neon_car_passenger.jpg",
        "icon": "🚗",
        "desc": "Passenger seat candid with reflections of city neon lights",
        "categories": ["cinematic", "romantic"],
    },
    {
        "id": "candid_rooftop_midnight_lights",
        "title": "Rooftop City Lights",
        "filename": "candid_rooftop_midnight_lights.jpg",
        "icon": "🌃",
        "desc": "Midnight rooftop silhouette overlooking illuminated skyline",
        "categories": ["cinematic", "sexy", "romantic"],
    },
    {
        "id": "candid_temple_silk_saree",
        "title": "Kanjeevaram Temple Saree",
        "filename": "candid_temple_silk_saree.jpg",
        "icon": "🛕",
        "desc": "Deep crimson Kanjeevaram silk saree with rich antique gold zari",
        "categories": ["traditional", "romantic"],
    },
    {
        "id": "candid_banarasi_diya_courtyard",
        "title": "Banarasi Diya Courtyard",
        "filename": "candid_banarasi_diya_courtyard.jpg",
        "icon": "🪔",
        "desc": "Royal emerald Banarasi silk by flickering brass oil lamps",
        "categories": ["traditional", "romantic", "cinematic"],
    },
    {
        "id": "pin_saree_portrait_1",
        "title": "Vintage Silk Portrait",
        "filename": "pin_saree_portrait_1.jpg",
        "icon": "👑",
        "desc": "Vintage portrait in handcrafted silk saree with delicate pallu",
        "categories": ["traditional", "cinematic", "romantic"],
    },
    {
        "id": "pin_saree_portrait_2",
        "title": "Golden Zari Candid",
        "filename": "pin_saree_portrait_2.jpg",
        "icon": "✨",
        "desc": "Warm sunlit portrait with shimmering golden zari borders",
        "categories": ["traditional", "romantic"],
    },
    {
        "id": "pin_desi_candid_3",
        "title": "Desi Courtyard Sunlight",
        "filename": "pin_desi_candid_3.jpg",
        "icon": "🌞",
        "desc": "Natural candid sunlit courtyard moment with traditional jhumkas",
        "categories": ["traditional", "romantic"],
    },
    {
        "id": "pin_aesthetic_bedroom_4",
        "title": "Fairylight Bedroom Candid",
        "filename": "pin_aesthetic_bedroom_4.jpg",
        "icon": "💫",
        "desc": "Warm bedroom ambient bokeh with delicate string fairylights",
        "categories": ["sexy", "romantic", "cinematic"],
    },
    {
        "id": "pin_saree_candid_5",
        "title": "Emerald Chiffon Mirror",
        "filename": "pin_saree_candid_5.jpg",
        "icon": "💚",
        "desc": "Forest green chiffon saree mirror selfie with natural waves",
        "categories": ["sexy", "traditional", "romantic"],
    },
    {
        "id": "pin_saree_candid_6",
        "title": "Ruby Velvet Evening Saree",
        "filename": "pin_saree_candid_6.jpg",
        "icon": "🌹",
        "desc": "Rich ruby velvet evening saree with modern sleeveless blouse",
        "categories": ["sexy", "romantic", "cinematic"],
    },
]

# 30 Curated Viral Lyrical Hindi/Hinglish Hooks & Quotes categorized
ALL_HOOK_OPTIONS: List[Dict[str, Any]] = [
    {"id": "h_1", "text": "teri aankhon mein doob jane ka mann karta hai... 🖤", "categories": ["sexy", "romantic"]},
    {"id": "h_2", "text": "kuch log dil mein aise bas jaate hain ki unke baad koi accha nahi lagta... 🥀", "categories": ["cinematic", "romantic"]},
    {"id": "h_3", "text": "tum paas nahi ho, fir bhi sabse kareeb ho... ✨", "categories": ["cinematic", "romantic"]},
    {"id": "h_4", "text": "ek tera deedar hi kaafi hai mere poore din ko haseen banane ke liye... 💖", "categories": ["romantic", "traditional"]},
    {"id": "h_5", "text": "tere bina ab sham nahi dhaltee, har lamha sirf tera hi intezaar hai... 🌙", "categories": ["cinematic", "romantic"]},
    {"id": "h_6", "text": "kisi ko chaho toh is qadar chaho ki koi aur chahat na rahe... 🌹", "categories": ["sexy", "romantic"]},
    {"id": "h_7", "text": "meri har subah tere khayal se aur har raat teri yaadon se mukammal hoti hai... 💫", "categories": ["romantic", "cinematic"]},
    {"id": "h_8", "text": "tujhse milne ke baad samjh aaya ki sukoon kise kehte hain... 🤍", "categories": ["romantic", "traditional"]},
    {"id": "h_9", "text": "kuch baatein lafzon se nahi, bas ek nazar dekh kar bayaan ho jaati hain... 👁️", "categories": ["sexy", "cinematic"]},
    {"id": "h_10", "text": "tumhe dekhne ke baad kisi aur ko dekhne ki zaroorat nahi mehsoos hoti... 💋", "categories": ["sexy", "romantic"]},
    {"id": "h_11", "text": "dil ka sukoon ho tum, jiske bina sab adhoora lagta hai... 🌸", "categories": ["romantic", "traditional"]},
    {"id": "h_12", "text": "sirf ek baar muskura kar dekh lo, saari thakaan utar jaati hai... 🕯️", "categories": ["cinematic", "traditional", "romantic"]},
    {"id": "h_13", "text": "kabhi fursat mile toh aana hamare dil mein, wahan sirf tumhara hi naam hai... 💌", "categories": ["traditional", "romantic"]},
    {"id": "h_14", "text": "tere saath beeta har lamha kisi khwaab jaisa haseen lagta hai... 🕊️", "categories": ["romantic", "cinematic"]},
    {"id": "h_15", "text": "ab toh aadat si ho gayi hai har waqt tera khayal aane ki... 🥀", "categories": ["cinematic", "traditional"]},
    {"id": "h_16", "text": "khushnaseeb hain wo jo roz tera deedar karte hain... 💖", "categories": ["traditional", "romantic"]},
    {"id": "h_17", "text": "tujhse door reh kar bhi har pal tere kareeb rehta hoon... ✨", "categories": ["romantic", "cinematic"]},
    {"id": "h_18", "text": "ishq wahi jo aankhon se shuru ho aur rooh mein utar jaaye... 🖤", "categories": ["sexy", "cinematic", "romantic"]},
    {"id": "h_19", "text": "tumhe paane ki chahat nahi, bas tumhe khush dekhne ki tamanna hai... 🌙", "categories": ["cinematic", "romantic"]},
    {"id": "h_20", "text": "kuch log zindagi mein bina maange hi sabse anmol tofa ban kar aate hain... 🌹", "categories": ["traditional", "romantic"]},
    {"id": "h_21", "text": "hum toh fida the unki saadgi par, wo muskuraye aur hum ghayal ho gaye... 💋", "categories": ["sexy", "traditional"]},
    {"id": "h_22", "text": "tera hona hi mere har din ka sabse khoobsurat hissa hai... 🤍", "categories": ["romantic", "traditional"]},
    {"id": "h_23", "text": "tujhe sochna bhi kisi ibadat se kam nahi lagta... 💫", "categories": ["traditional", "romantic"]},
    {"id": "h_24", "text": "mere dil ki saari dhadkane ab tere naam se shuru hoti hain... 🌸", "categories": ["romantic", "traditional"]},
    {"id": "h_25", "text": "tum mil gaye toh jaise saari duniya mil gayi... 💖", "categories": ["romantic", "traditional"]},
    {"id": "h_26", "text": "uski ek jhalak ke liye ghanto intezaar karna bhi ishq hai... ⏳", "categories": ["cinematic", "sexy"]},
    {"id": "h_27", "text": "duniya ke liye tum ek shakhs ho sakte ho, par kisi ke liye poori duniya ho... 🌍", "categories": ["romantic", "cinematic"]},
    {"id": "h_28", "text": "hamesha saath rehna, kyunki tumhare bina mera koi wajood nahi... 🕊️", "categories": ["romantic", "traditional"]},
    {"id": "h_29", "text": "mohabbat lafzon ki mohtaj nahi hoti, bas do dilon ka ehsaas kaafi hai... 💌", "categories": ["traditional", "romantic"]},
    {"id": "h_30", "text": "tumhe chahna meri aadat nahi, meri rooh ka hissa ban chuka hai... 🖤", "categories": ["sexy", "romantic"]},
]


def get_image_option(img_id: str) -> Dict[str, Any]:
    """Retrieve image option dictionary by ID, custom upload, or dynamic slot."""
    if img_id == "custom_upload":
        return {
            "id": "custom_upload",
            "title": "Custom Uploaded Photo",
            "filename": "custom_upload.jpg",
            "icon": "📸",
            "desc": "User-provided custom image from ChatGPT/Gemini/Gallery",
            "categories": ["sexy", "romantic", "cinematic", "traditional"],
        }
    if img_id.startswith("dyn_") or img_id.startswith("ai_gen_"):
        return {
            "id": img_id,
            "title": "✨ Dynamic AI Candid Photo",
            "filename": f"{img_id}.jpg",
            "icon": "✨",
            "desc": "Dynamic AI visual generated uniquely for you",
            "categories": ["sexy", "romantic", "cinematic", "traditional"],
        }
    if img_id.startswith("pin_"):
        for opt in ALL_IMAGE_OPTIONS:
            if opt["id"] == img_id:
                return opt
        return {
            "id": img_id,
            "title": "📌 Pinterest Candid Photo",
            "filename": f"{img_id}.jpg",
            "icon": "📌",
            "desc": "Fresh candid visual from Pinterest CDN",
            "categories": ["sexy", "romantic", "cinematic", "traditional"],
        }
    for opt in ALL_IMAGE_OPTIONS:
        if opt["id"] == img_id:
            return opt
    return ALL_IMAGE_OPTIONS[0]


def get_category_info(cat_id: Optional[str]) -> Dict[str, Any]:
    """Retrieve category dictionary or default to 'sexy'."""
    if cat_id and cat_id.lower() in CATEGORIES:
        return CATEGORIES[cat_id.lower()]
    return CATEGORIES["sexy"]


async def get_fresh_image_options(
    chat_id: int,
    category: Optional[str] = None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Return 5 unused candid images for this user filtered by category, guaranteed zero repeats."""
    used = await db_manager.get_used_assets(chat_id, "image")
    cat = category.lower().strip() if category else None
    if cat:
        pool = [opt for opt in ALL_IMAGE_OPTIONS if cat in opt.get("categories", [])]
        if not pool:
            pool = ALL_IMAGE_OPTIONS
    else:
        pool = ALL_IMAGE_OPTIONS

    # 1. Unused candidates from requested category
    candidates = [opt for opt in pool if opt["id"] not in used]

    # 2. If fewer than limit, borrow unused images from other categories
    if len(candidates) < limit:
        other_unseen = [opt for opt in ALL_IMAGE_OPTIONS if opt["id"] not in used and opt not in candidates]
        random.shuffle(other_unseen)
        needed = limit - len(candidates)
        for opt in other_unseen[:needed]:
            adapted = dict(opt)
            if cat and cat not in adapted.get("categories", []):
                adapted["categories"] = list(adapted.get("categories", [])) + [cat]
            candidates.append(adapted)

    # 3. ZERO-REPEAT GUARANTEE:
    # If the user has used every single catalog image, generate brand new dynamic slots on the fly!
    # NEVER EVER recycle used images back into candidates!
    while len(candidates) < limit:
        dyn_idx = len(candidates) + 1
        unique_dyn_id = f"dyn_ai_{cat or 'vibe'}_{int(time.time())}_{random.randint(1000, 9999)}"
        candidates.append({
            "id": unique_dyn_id,
            "title": f"Fresh AI Candid #{dyn_idx}",
            "filename": f"{unique_dyn_id}.jpg",
            "icon": "✨",
            "desc": "100% brand new dynamic AI visual generation",
            "categories": [cat] if cat else ["sexy", "romantic", "cinematic", "traditional"],
        })

    random.shuffle(candidates)
    return candidates[:limit]


async def get_fresh_song_options(
    chat_id: int,
    category: Optional[str] = None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Return 5 unused vocal songs for this user filtered by category."""
    used = await db_manager.get_used_assets(chat_id, "music")
    return music_service.get_vocal_options(category=category, exclude_ids=used, limit=limit)


async def get_fresh_hook_options(
    chat_id: int,
    category: Optional[str] = None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Return 5 unused text hooks for this user filtered by category."""
    used = await db_manager.get_used_assets(chat_id, "text")
    cat = category.lower().strip() if category else None
    if cat:
        cat_pool = [h for h in ALL_HOOK_OPTIONS if cat in h.get("categories", [])]
        pool = cat_pool if cat_pool else ALL_HOOK_OPTIONS
    else:
        pool = ALL_HOOK_OPTIONS

    candidates = [h for h in pool if h["text"] not in used]
    if len(candidates) < limit:
        other_unseen = [h for h in ALL_HOOK_OPTIONS if h["text"] not in used and h not in candidates]
        random.shuffle(other_unseen)
        needed = limit - len(candidates)
        for h in other_unseen[:needed]:
            adapted = dict(h)
            if cat and cat not in adapted.get("categories", []):
                adapted["categories"] = list(adapted.get("categories", [])) + [cat]
            candidates.append(adapted)

    if not candidates:
        candidates = list(pool)

    random.shuffle(candidates)
    return candidates[:limit]


def build_category_selection_keyboard() -> InlineKeyboardMarkup:
    """Step 0: Category / Vibe Selection."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💋 Sexy / Flirty Desi", callback_data="cat_sexy"),
            InlineKeyboardButton("💖 Romantic / Love", callback_data="cat_romantic"),
        ],
        [
            InlineKeyboardButton("🎬 Late Night / Cinematic", callback_data="cat_cinematic"),
            InlineKeyboardButton("👑 Desi Traditional", callback_data="cat_traditional"),
        ],
    ])


def build_image_selection_keyboard(options: List[Dict[str, Any]], category: Optional[str] = None) -> InlineKeyboardMarkup:
    """Step 1/3: 5 Image options + AI Generate + Pinterest + Own Photo + Shuffle + Random + Reset + Back."""
    keyboard = []
    row = []
    for idx, opt in enumerate(options, start=1):
        btn = InlineKeyboardButton(f"{opt['icon']} {idx}. {opt['title']}", callback_data=f"pick_img_{opt['id']}")
        row.append(btn)
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    # Dynamic AI & Pinterest generation buttons
    keyboard.append([
        InlineKeyboardButton("✨ Generate New AI Photo", callback_data="gen_ai_photo"),
        InlineKeyboardButton("📌 Fetch Pinterest Photo", callback_data="fetch_pin_photo"),
    ])

    # Upload Own Image row
    keyboard.append([
        InlineKeyboardButton("📸 Send / Upload My Own Photo", callback_data="upload_own_img"),
    ])

    # Utility row: Shuffle & Random
    keyboard.append([
        InlineKeyboardButton("🔄 Shuffle / Other 5", callback_data="shuffle_imgs"),
        InlineKeyboardButton("🎲 Random Visual", callback_data="pick_img_random"),
    ])

    # Reset History & Back button
    keyboard.append([
        InlineKeyboardButton("🗑️ Reset History", callback_data="reset_my_history"),
        InlineKeyboardButton("⬅️ Change Category", callback_data="back_to_cats"),
    ])
    return InlineKeyboardMarkup(keyboard)


def build_hook_selection_keyboard(options: List[Dict[str, Any]], category: Optional[str] = None) -> InlineKeyboardMarkup:
    """Step 2/3: 5 viral text hooks + Custom text + Shuffle + Random + Back."""
    keyboard = [
        [
            InlineKeyboardButton("1️⃣ Hook #1", callback_data="pick_hook_0"),
            InlineKeyboardButton("2️⃣ Hook #2", callback_data="pick_hook_1"),
        ],
        [
            InlineKeyboardButton("3️⃣ Hook #3", callback_data="pick_hook_2"),
            InlineKeyboardButton("4️⃣ Hook #4", callback_data="pick_hook_3"),
        ],
        [
            InlineKeyboardButton("5️⃣ Hook #5", callback_data="pick_hook_4"),
            InlineKeyboardButton("🎲 Random Hook", callback_data="pick_hook_random"),
        ],
        [
            InlineKeyboardButton("🔄 Shuffle / Other 5", callback_data="shuffle_hooks"),
        ],
        [
            InlineKeyboardButton("✏️ Type My Own Custom Text", callback_data="pick_hook_custom"),
        ],
        [
            InlineKeyboardButton("⬅️ Back to Visuals", callback_data="back_to_imgs"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_song_selection_keyboard(options: List[Dict[str, Any]], category: Optional[str] = None) -> InlineKeyboardMarkup:
    """Step 3/3: 5 Bollywood vocal tracks + Shuffle + Random + Back."""
    rows = []
    for idx, t in enumerate(options, start=1):
        rows.append([
            InlineKeyboardButton(
                f"{t.get('icon', '🎤')} {idx}. {t['title']} ({t['artist']}) 🎤",
                callback_data=f"pick_song_{t['id']}",
            )
        ])
    rows.append([
        InlineKeyboardButton("🔄 Shuffle / Other 5", callback_data="shuffle_songs"),
        InlineKeyboardButton("🎲 Random Vocal Track", callback_data="pick_song_random"),
    ])
    rows.append([
        InlineKeyboardButton("⬅️ Change Text / Visual", callback_data="back_to_hooks"),
    ])
    return InlineKeyboardMarkup(rows)


@restricted
async def auto_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /auto command - starts Category-first selection flow."""
    msg = (
        "🎬 *Reel Studio: Choose Your Category*\n\n"
        "Please select the vibe / category for your reel first:\n\n"
        "• 💋 *Sexy / Flirty Desi:* Bold candid selfies & sultry vibes\n"
        "• 💖 *Romantic / Love:* Pastel sarees & heartwarming love lyrics\n"
        "• 🎬 *Late Night / Cinematic:* Neon bokeh & late night thoughts\n"
        "• 👑 *Desi Traditional:* Royal sarees & timeless shayari\n\n"
        "_(💡 Visuals, text hooks & Bollywood songs will strictly adapt to your choice!)_"
    )
    if update.effective_message:
        await update.effective_message.reply_text(
            msg,
            reply_markup=build_category_selection_keyboard(),
            parse_mode="Markdown",
        )


@restricted
async def reset_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reset used asset history for this chat."""
    chat_id = update.effective_chat.id
    await db_manager.clear_used_assets(chat_id)
    if update.effective_message:
        await update.effective_message.reply_text(
            "🔄 *History Cleared!*\nAll previously used images, songs, and hooks are now unlocked again.",
            parse_mode="Markdown",
        )


@restricted
async def handle_quick_text_triggers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user typed quick keywords like 'reel', 'new', 'start'."""
    message = update.effective_message
    if not message or not message.text:
        return False

    raw = message.text.strip().lower()
    if raw in ("reel", "reels", "auto", "start", "new", "image", "video", "create"):
        msg = (
            "🎬 *Reel Studio: Choose Your Category*\n\n"
            "Select the vibe / category for your reel first:\n\n"
            "• 💋 *Sexy / Flirty Desi*\n"
            "• 💖 *Romantic / Love*\n"
            "• 🎬 *Late Night / Cinematic*\n"
            "• 👑 *Desi Traditional*\n\n"
            "_(💡 Your choice determines 5 matching candid images, hooks & songs!)_"
        )
        await message.reply_text(
            msg,
            reply_markup=build_category_selection_keyboard(),
            parse_mode="Markdown",
        )
        return True

    return False


async def send_visual_text_preview(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    img_id: str,
    hook_text: str,
    cat_id: str,
    custom_media_path: Optional[Path] = None,
) -> None:
    """Generate 1080x1920 image composite preview and prompt user for song name."""
    cat_info = get_category_info(cat_id)
    img_opt = get_image_option(img_id)

    # Check for custom uploaded image or library image
    candid_src = None
    if custom_media_path and Path(custom_media_path).exists():
        candid_src = Path(custom_media_path)
    elif img_id == "custom_upload" or context.user_data.get("custom_media_path"):
        ctx_p = context.user_data.get("custom_media_path")
        if ctx_p and Path(ctx_p).exists():
            candid_src = Path(ctx_p)

    if not candid_src or not candid_src.exists():
        direct_p = Path("assets/images/candid") / img_opt.get("filename", "")
        if direct_p.exists():
            candid_src = direct_p
        elif img_id.startswith("pin_"):
            candid_src, _, _ = await asyncio.to_thread(fetch_pinterest_candid_image, category=cat_id, chat_id=chat_id)
        else:
            candid_src, _, _ = await asyncio.to_thread(generate_ai_candid_image, category=cat_id, chat_id=chat_id)

    timestamp = int(asyncio.get_event_loop().time())
    preview_path = config.temp_dir / f"{chat_id}_preview_{timestamp}.jpg"

    if candid_src.exists():
        await asyncio.to_thread(
            generate_preview_composite,
            image_path=candid_src,
            text=hook_text,
            template_key=cat_id,
            output_path=preview_path,
        )
    else:
        # Fallback if source file not found
        shutil.copy(candid_src, preview_path)

    # Save to context & DB session
    context.user_data["chosen_img"] = img_id
    context.user_data["chosen_hook"] = hook_text
    context.user_data["chosen_cat"] = cat_id

    await db_manager.start_reel_session(chat_id)
    await db_manager.update_session(
        chat_id,
        current_step="WAITING_SONG_NAME",
        media_path=str(candid_src),
        overlay_text=hook_text,
        selected_template=cat_id,
    )

    # 5 Fresh song options for this category
    fresh_songs = await get_fresh_song_options(chat_id, category=cat_id, limit=5)
    context.user_data["current_song_options"] = fresh_songs

    caption = (
        "📸 *Visual & Text Preview Ready!*\n\n"
        f"• 📂 *Category:* {cat_info['icon']} *{cat_info['title']}*\n"
        f"• 📸 *Visual:* {img_opt['icon']} {img_opt['title']}\n"
        f"• 📝 *Text:* \"{hook_text}\"\n\n"
        "🎵 *Step 3 of 3: Add Your Bollywood Song*\n"
        "💬 **Type ANY song name in this chat**\n"
        "_(e.g. \"Pee Loon\", \"Kesariya\", \"Zara Sa\", \"Tum Hi Ho\", etc.)_\n\n"
        "👇 **OR tap one of the 5 curated vocal tracks below:**"
    )

    with open(preview_path, "rb") as photo_file:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=photo_file,
            caption=caption,
            reply_markup=build_song_selection_keyboard(fresh_songs, category=cat_id),
            parse_mode="Markdown",
        )


async def handle_song_name_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    song_name: str,
) -> None:
    """Resolve user-typed song name and proceed to video rendering."""
    chat_id = update.effective_chat.id
    cat = context.user_data.get("chosen_cat")
    img_id = context.user_data.get("chosen_img")
    hook_text = context.user_data.get("chosen_hook")

    session = await db_manager.get_session(chat_id)
    if session:
        if not hook_text and session.get("overlay_text"):
            hook_text = session["overlay_text"]
        if not cat and session.get("selected_template"):
            cat = session["selected_template"]
        if not img_id and session.get("media_path"):
            media_p = session["media_path"]
            for opt in ALL_IMAGE_OPTIONS:
                if opt["filename"] in media_p:
                    img_id = opt["id"]
                    break

    cat = cat or "romantic"
    img_id = img_id or "balcony_saree"
    hook_text = hook_text or "tere bina ab sham nahi dhaltee, har lamha sirf tera hi intezaar hai... 🌙"

    resolving_msg = await update.effective_message.reply_text(
        f"🔍 *Matching Bollywood vocal track for \"{song_name}\"...*\nChecking library & vocal chorus...",
        parse_mode="Markdown",
    )

    audio_path, song_display = music_service.resolve_song_by_name(song_name, category=cat)
    song_id = audio_path.stem.replace("_vocal", "").replace("_raw", "")

    try:
        await resolving_msg.delete()
    except Exception:
        pass

    await render_custom_selected_reel(
        update,
        context,
        img_id=img_id,
        song_id=song_id,
        hook_text=hook_text,
        category=cat,
        resolved_audio_path=audio_path,
        resolved_song_title=song_display,
    )


async def render_custom_selected_reel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    img_id: str,
    song_id: str,
    hook_text: str,
    category: Optional[str] = None,
    resolved_audio_path: Optional[Path] = None,
    resolved_song_title: Optional[str] = None,
) -> None:
    """Render 15s 1080x1920 reel with selected non-repeating assets, fade animations and record usage."""
    chat_id = update.effective_chat.id
    cat = category or context.user_data.get("chosen_cat", "sexy")
    cat_info = get_category_info(cat)
    img_opt = get_image_option(img_id)

    # 1. Immediately record assets in DB so they will NEVER appear again!
    await db_manager.record_used_asset(chat_id, "image", img_opt["id"])
    await db_manager.record_used_asset(chat_id, "music", song_id)
    await db_manager.record_used_asset(chat_id, "text", hook_text)
    logger.info(f"Recorded used assets for chat {chat_id}: img={img_opt['id']}, song={song_id}, cat={cat}")

    # 2. Resolve vocal track
    if resolved_audio_path and resolved_audio_path.exists():
        vocal_path = resolved_audio_path
        song_title = resolved_song_title or music_service.get_track_title(vocal_path)
    else:
        vocal_path = music_service.get_vocal_track_by_id(song_id)
        if not vocal_path or not vocal_path.exists():
            vocal_path = music_service.get_bollywood_track(cat)
        song_title = music_service.get_track_title(vocal_path)

    # 3. Deploy authentic candid image (custom uploaded photo or library)
    candid_src = None
    if img_id == "custom_upload" or context.user_data.get("custom_media_path"):
        ctx_p = context.user_data.get("custom_media_path")
        if ctx_p and Path(ctx_p).exists():
            candid_src = Path(ctx_p)

    if not candid_src or not candid_src.exists():
        direct_p = Path("assets/images/candid") / img_opt.get("filename", "")
        if direct_p.exists():
            candid_src = direct_p
        elif img_id.startswith("pin_"):
            candid_src, _, _ = await asyncio.to_thread(fetch_pinterest_candid_image, category=cat, chat_id=chat_id)
        else:
            candid_src, _, _ = await asyncio.to_thread(generate_ai_candid_image, category=cat, chat_id=chat_id)

    timestamp = int(asyncio.get_event_loop().time())
    deployed_img = config.input_dir / f"{chat_id}_custom_{timestamp}.jpg"

    if candid_src.exists():
        shutil.copy(candid_src, deployed_img)
    else:
        await asyncio.to_thread(
            generate_ai_visual,
            style=cat,
            output_path=deployed_img,
            text=hook_text,
            use_flux_ai=True,
        )

    # 4. Status notification
    visual_display = "📸 Custom Uploaded Photo" if (img_id == "custom_upload" or context.user_data.get("custom_media_path")) else img_opt["title"]
    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "⚡ *Rendering Your Reel with Smooth Animations...*\n\n"
            f"• 📂 *Category:* {cat_info['icon']} {cat_info['title']}\n"
            f"• 📸 *Visual:* {visual_display}\n"
            f"• 🎤 *Song (Vocals):* {song_title}\n"
            f"• 📝 *Text:* \"{hook_text}\"\n"
            "• 🎬 *Effects:* Smooth Text Fade In/Out + Ken Burns Zoom + Video Fade-to-Black\n\n"
            "Mixing Bollywood vocal chorus & encoding MP4..."
        ),
        parse_mode="Markdown",
    )

    # 5. Save DB session
    await db_manager.start_reel_session(chat_id)
    await db_manager.update_session(
        chat_id,
        media_path=str(deployed_img),
        media_type="image",
        overlay_text=hook_text,
        selected_template=cat,
        music_path=str(vocal_path) if vocal_path else None,
    )

    # 6. Render final video
    try:
        final_video_path = await execute_render_job(chat_id)

        caption = (
            f"🔥 *Reel Ready!*\n\n"
            f"• 📂 *Category:* {cat_info['icon']} {cat_info['title']}\n"
            f"• 📸 *Visual:* {img_opt['title']}\n"
            f"• 📝 *Text:* \"{hook_text}\"\n"
            f"• 🎤 *Vocal Song:* {song_title}\n\n"
            f"Tap below to publish live to Instagram or create another!"
        )

        with open(final_video_path, "rb") as video_file:
            insta_acc = await instagram_service.is_connected(chat_id)
            reply_markup = None
            if insta_acc:
                username = insta_acc.get("username", "Instagram")
                reply_markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton(f"🚀 Post to Instagram (@{username})", callback_data="post_insta")
                ]])

            await context.bot.send_video(
                chat_id=chat_id,
                video=video_file,
                caption=caption,
                parse_mode="Markdown",
                supports_streaming=True,
                width=1080,
                height=1920,
                reply_markup=reply_markup,
                write_timeout=180.0,
                read_timeout=180.0,
            )

        # Prepare Instagram caption for auto-post
        ig_caption = generate_instagram_caption(hook_text, style=cat)

        # Auto-post if enabled
        if insta_acc and insta_acc.get("auto_post"):
            async def _bg_publish():
                try:
                    res = await instagram_service.upload_reel(chat_id, final_video_path, caption=ig_caption)
                    if res.get("success"):
                        url = res.get("url") or "Instagram Feed"
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"🚀 *Auto-Posted to Instagram!*\n🔗 [View Reel on Instagram]({url})",
                            parse_mode="Markdown",
                        )
                except Exception as ex:
                    logger.warning(f"Auto-post failed: {ex}")

            asyncio.create_task(_bg_publish())

        cleanup_chat_files(chat_id)
        await status_msg.delete()

    except Exception as e:
        logger.exception(f"Custom reel generation error: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="Rendering failed. Please try again with /reel or /auto.",
        )


@restricted
async def complete_custom_reel_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, custom_text: str) -> None:
    """Handle custom text input: generate preview first and ask for song name."""
    chat_id = update.effective_chat.id
    cat = context.user_data.get("chosen_cat", "sexy")
    img_id = context.user_data.get("chosen_img", "sheer_saree")
    await send_visual_text_preview(update, context, chat_id, img_id=img_id, hook_text=custom_text, cat_id=cat)


@restricted
async def handle_auto_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle interactive button presses for the Category-First 5-5-5 selection flow."""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    chat_id = update.effective_chat.id

    # -------------------------------------------------------------
    # Step 0 -> Step 1: User chose Category
    # -------------------------------------------------------------
    if data.startswith("cat_"):
        cat_id = data.replace("cat_", "")
        context.user_data["chosen_cat"] = cat_id
        cat_info = get_category_info(cat_id)

        fresh_images = await get_fresh_image_options(chat_id, category=cat_id, limit=5)
        context.user_data["current_img_options"] = fresh_images

        msg = (
            f"📸 *Step 1 of 3: Choose Visual (Image)*\n\n"
            f"📂 *Category:* {cat_info['icon']} *{cat_info['title']}*\n"
            f"_{cat_info['desc']}_\n\n"
            "Select 1 of 5 authentic candid photo aesthetics below:\n"
            "_(💡 Options match your category and never repeat!)_"
        )
        await query.edit_message_text(
            msg,
            reply_markup=build_image_selection_keyboard(fresh_images, category=cat_id),
            parse_mode="Markdown",
        )

    # -------------------------------------------------------------
    # Shuffle Images for Current Category
    # -------------------------------------------------------------
    elif data == "shuffle_imgs":
        cat_id = context.user_data.get("chosen_cat", "sexy")
        cat_info = get_category_info(cat_id)
        fresh_images = await get_fresh_image_options(chat_id, category=cat_id, limit=5)
        context.user_data["current_img_options"] = fresh_images

        msg = (
            f"📸 *Step 1 of 3: Choose Visual (Image)*\n\n"
            f"📂 *Category:* {cat_info['icon']} *{cat_info['title']}*\n"
            f"_{cat_info['desc']}_\n\n"
            "Select 1 of 5 authentic candid photo aesthetics below:\n"
            "_(💡 Shuffled 5 fresh options!)_"
        )
        await query.edit_message_text(
            msg,
            reply_markup=build_image_selection_keyboard(fresh_images, category=cat_id),
            parse_mode="Markdown",
        )

    # -------------------------------------------------------------
    # Back to Categories
    # -------------------------------------------------------------
    elif data == "back_to_cats":
        msg = (
            "🎬 *Reel Studio: Choose Your Category*\n\n"
            "Please select the vibe / category for your reel first:\n\n"
            "• 💋 *Sexy / Flirty Desi*\n"
            "• 💖 *Romantic / Love*\n"
            "• 🎬 *Late Night / Cinematic*\n"
            "• 👑 *Desi Traditional*\n\n"
            "_(💡 Visuals, text hooks & Bollywood songs will strictly adapt to your choice!)_"
        )
        await query.edit_message_text(
            msg,
            reply_markup=build_category_selection_keyboard(),
            parse_mode="Markdown",
        )

    # -------------------------------------------------------------
    # Upload Own Image Instruction
    # -------------------------------------------------------------
    elif data == "upload_own_img":
        cat_id = context.user_data.get("chosen_cat", "romantic")
        cat_info = get_category_info(cat_id)
        msg = (
            f"📸 *Send Your Custom Image Now:*\n\n"
            f"📂 *Active Category:* {cat_info['icon']} *{cat_info['title']}*\n\n"
            "Apne phone ya computer se ChatGPT Pro, Gemini, ya Gallery ki koi bhi photo **is chat me bhej dein**!\n\n"
            "💡 *Bot automatically:*\n"
            "• 1080x1920 HD vertical fit karega (cinematic blurred background)\n"
            "• Slow-zoom Ken Burns motion lagayega\n"
            "• Aur turant Text Hook & Song selection open karega."
        )
        await query.message.reply_text(msg, parse_mode="Markdown")

    # -------------------------------------------------------------
    # Dynamic AI Photo Generation Button
    # -------------------------------------------------------------
    elif data == "gen_ai_photo":
        cat_id = context.user_data.get("chosen_cat", "sexy")
        cat_info = get_category_info(cat_id)
        await query.edit_message_text(
            f"✨ *Generating a brand new AI candid photo for {cat_info['title']}...*\n"
            "_(Checking OpenAI / Gemini / Dynamic film synthesis - zero repeats)_",
            parse_mode="Markdown",
        )
        out_file, unique_id, title = await asyncio.to_thread(
            generate_ai_candid_image,
            category=cat_id,
            chat_id=chat_id,
        )
        context.user_data["custom_media_path"] = str(out_file)
        context.user_data["chosen_img"] = unique_id
        await db_manager.record_used_asset(chat_id, "image", unique_id)

        fresh_hooks = await get_fresh_hook_options(chat_id, category=cat_id, limit=5)
        context.user_data["current_hook_options"] = fresh_hooks
        hooks_text = "\n".join([f"{idx}️⃣ _{h['text']}_" for idx, h in enumerate(fresh_hooks, start=1)])

        msg = (
            f"📝 *Step 2 of 3: Choose Reel Text / Hook*\n\n"
            f"📂 *Category:* {cat_info['icon']} *{cat_info['title']}*\n"
            f"📸 *Visual:* {title}\n\n"
            f"Select 1 of 5 viral quotes below, or type your own:\n\n"
            f"{hooks_text}\n\n"
            f"_(💡 Next, an instant visual preview with this AI visual will be created!)_"
        )
        await query.message.reply_text(
            msg,
            reply_markup=build_hook_selection_keyboard(fresh_hooks, category=cat_id),
            parse_mode="Markdown",
        )

    # -------------------------------------------------------------
    # Fetch Pinterest Photo Button
    # -------------------------------------------------------------
    elif data == "fetch_pin_photo":
        cat_id = context.user_data.get("chosen_cat", "sexy")
        cat_info = get_category_info(cat_id)
        await query.edit_message_text(
            f"📌 *Fetching fresh vertical candid photo from Pinterest CDN...*\n"
            f"_(Category: {cat_info['title']} - zero repetition guarantee)_",
            parse_mode="Markdown",
        )
        out_file, unique_id, title = await asyncio.to_thread(
            fetch_pinterest_candid_image,
            category=cat_id,
            chat_id=chat_id,
        )
        context.user_data["custom_media_path"] = str(out_file)
        context.user_data["chosen_img"] = unique_id
        await db_manager.record_used_asset(chat_id, "image", unique_id)

        fresh_hooks = await get_fresh_hook_options(chat_id, category=cat_id, limit=5)
        context.user_data["current_hook_options"] = fresh_hooks
        hooks_text = "\n".join([f"{idx}️⃣ _{h['text']}_" for idx, h in enumerate(fresh_hooks, start=1)])

        msg = (
            f"📝 *Step 2 of 3: Choose Reel Text / Hook*\n\n"
            f"📂 *Category:* {cat_info['icon']} *{cat_info['title']}*\n"
            f"📸 *Visual:* {title}\n\n"
            f"Select 1 of 5 viral quotes below, or type your own:\n\n"
            f"{hooks_text}\n\n"
            f"_(💡 Next, an instant visual preview with this Pinterest photo will be created!)_"
        )
        await query.message.reply_text(
            msg,
            reply_markup=build_hook_selection_keyboard(fresh_hooks, category=cat_id),
            parse_mode="Markdown",
        )

    # -------------------------------------------------------------
    # Reset History Button
    # -------------------------------------------------------------
    elif data == "reset_my_history":
        await db_manager.clear_used_assets(chat_id, "image")
        cat_id = context.user_data.get("chosen_cat", "sexy")
        cat_info = get_category_info(cat_id)
        fresh_images = await get_fresh_image_options(chat_id, category=cat_id, limit=5)
        context.user_data["current_img_options"] = fresh_images

        msg = (
            f"🔄 *Image History Cleared!*\n\n"
            f"All 30+ candid aesthetics and dynamic slots are unlocked again.\n\n"
            f"📂 *Category:* {cat_info['icon']} *{cat_info['title']}*\n"
            f"Select 1 of 5 fresh options below:"
        )
        await query.edit_message_text(
            msg,
            reply_markup=build_image_selection_keyboard(fresh_images, category=cat_id),
            parse_mode="Markdown",
        )

    # -------------------------------------------------------------
    # Step 1 -> Step 2: User chose Image -> Show Text Hooks for Category
    # -------------------------------------------------------------
    elif data.startswith("pick_img_"):
        raw_img = data.replace("pick_img_", "")
        current_img_opts = context.user_data.get("current_img_options", ALL_IMAGE_OPTIONS)
        if raw_img == "random":
            chosen_opt = random.choice(current_img_opts)
        else:
            chosen_opt = get_image_option(raw_img)
        context.user_data["chosen_img"] = chosen_opt["id"]

        cat_id = context.user_data.get("chosen_cat", "sexy")
        cat_info = get_category_info(cat_id)

        # Fetch 5 fresh viral quotes matching this category
        fresh_hooks = await get_fresh_hook_options(chat_id, category=cat_id, limit=5)
        context.user_data["current_hook_options"] = fresh_hooks

        hooks_text = "\n".join([f"{idx}️⃣ _{h['text']}_" for idx, h in enumerate(fresh_hooks, start=1)])

        msg = (
            f"📝 *Step 2 of 3: Choose Reel Text / Hook*\n\n"
            f"📂 *Category:* {cat_info['icon']} *{cat_info['title']}*\n"
            f"📸 *Visual:* {chosen_opt['icon']} {chosen_opt['title']}\n\n"
            f"Select 1 of 5 viral quotes below, or type your own:\n\n"
            f"{hooks_text}\n\n"
            f"_(💡 Next, an instant visual preview with this text will be created!)_"
        )
        await query.edit_message_text(
            msg,
            reply_markup=build_hook_selection_keyboard(fresh_hooks, category=cat_id),
            parse_mode="Markdown",
        )

    # -------------------------------------------------------------
    # Shuffle Hooks for Current Category
    # -------------------------------------------------------------
    elif data == "shuffle_hooks":
        cat_id = context.user_data.get("chosen_cat", "sexy")
        cat_info = get_category_info(cat_id)
        img_id = context.user_data.get("chosen_img", "sheer_saree")
        img_opt = get_image_option(img_id)

        fresh_hooks = await get_fresh_hook_options(chat_id, category=cat_id, limit=5)
        context.user_data["current_hook_options"] = fresh_hooks

        hooks_text = "\n".join([f"{idx}️⃣ _{h['text']}_" for idx, h in enumerate(fresh_hooks, start=1)])

        msg = (
            f"📝 *Step 2 of 3: Choose Reel Text / Hook*\n\n"
            f"📂 *Category:* {cat_info['icon']} *{cat_info['title']}*\n"
            f"📸 *Visual:* {img_opt['icon']} {img_opt['title']}\n\n"
            f"Select 1 of 5 viral quotes below, or type your own:\n\n"
            f"{hooks_text}\n\n"
            f"_(💡 Shuffled 5 fresh quotes!)_"
        )
        await query.edit_message_text(
            msg,
            reply_markup=build_hook_selection_keyboard(fresh_hooks, category=cat_id),
            parse_mode="Markdown",
        )

    # -------------------------------------------------------------
    # Back to Visuals
    # -------------------------------------------------------------
    elif data == "back_to_imgs":
        cat_id = context.user_data.get("chosen_cat", "sexy")
        cat_info = get_category_info(cat_id)
        fresh_images = await get_fresh_image_options(chat_id, category=cat_id, limit=5)
        context.user_data["current_img_options"] = fresh_images

        msg = (
            f"📸 *Step 1 of 3: Choose Visual (Image)*\n\n"
            f"📂 *Category:* {cat_info['icon']} *{cat_info['title']}*\n"
            f"_{cat_info['desc']}_\n\n"
            "Select 1 of 5 authentic candid photo aesthetics below:"
        )
        await query.edit_message_text(
            msg,
            reply_markup=build_image_selection_keyboard(fresh_images, category=cat_id),
            parse_mode="Markdown",
        )

    # -------------------------------------------------------------
    # Step 2 -> Step 3: User chose a Hook -> Generate Instant Preview First!
    # -------------------------------------------------------------
    elif data.startswith("pick_hook_"):
        raw_hook = data.replace("pick_hook_", "")
        cat_id = context.user_data.get("chosen_cat", "sexy")
        img_id = context.user_data.get("chosen_img", "sheer_saree")

        if raw_hook == "custom":
            img_opt = get_image_option(img_id)
            await db_manager.start_reel_session(chat_id)
            await db_manager.update_session(chat_id, current_step="WAITING_CUSTOM_TEXT")

            await query.edit_message_text(
                f"✍️ *Type Your Custom Text*\n\n"
                f"📸 *Visual:* {img_opt['icon']} {img_opt['title']}\n\n"
                f"Please reply with your custom text in this chat:\n"
                f"_(Example: \"kisi ko itna chaho ki koi aur chahat na rahe... 💖\")_",
                parse_mode="Markdown",
            )
            return

        current_hook_opts = context.user_data.get("current_hook_options", ALL_HOOK_OPTIONS[:5])
        if raw_hook == "random":
            chosen_hook = random.choice(current_hook_opts)["text"]
        else:
            try:
                idx = int(raw_hook)
                chosen_hook = current_hook_opts[idx]["text"]
            except Exception:
                chosen_hook = current_hook_opts[0]["text"]

        await query.edit_message_text("⚡ Generating your high-definition visual & text preview...")
        await send_visual_text_preview(
            update,
            context,
            chat_id=chat_id,
            img_id=img_id,
            hook_text=chosen_hook,
            cat_id=cat_id,
        )

    # -------------------------------------------------------------
    # Shuffle Songs on Preview Screen
    # -------------------------------------------------------------
    elif data == "shuffle_songs":
        cat_id = context.user_data.get("chosen_cat", "sexy")
        fresh_songs = await get_fresh_song_options(chat_id, category=cat_id, limit=5)
        context.user_data["current_song_options"] = fresh_songs
        await query.edit_message_reply_markup(
            reply_markup=build_song_selection_keyboard(fresh_songs, category=cat_id)
        )

    # -------------------------------------------------------------
    # Back to Hooks from Preview
    # -------------------------------------------------------------
    elif data == "back_to_hooks":
        cat_id = context.user_data.get("chosen_cat", "sexy")
        cat_info = get_category_info(cat_id)
        img_id = context.user_data.get("chosen_img", "sheer_saree")
        img_opt = get_image_option(img_id)

        fresh_hooks = await get_fresh_hook_options(chat_id, category=cat_id, limit=5)
        context.user_data["current_hook_options"] = fresh_hooks
        hooks_text = "\n".join([f"{idx}️⃣ _{h['text']}_" for idx, h in enumerate(fresh_hooks, start=1)])

        msg = (
            f"📝 *Step 2 of 3: Choose Reel Text / Hook*\n\n"
            f"📂 *Category:* {cat_info['icon']} *{cat_info['title']}*\n"
            f"📸 *Visual:* {img_opt['icon']} {img_opt['title']}\n\n"
            f"Select 1 of 5 viral quotes below, or type your own:\n\n"
            f"{hooks_text}"
        )
        await query.edit_message_text(
            msg,
            reply_markup=build_hook_selection_keyboard(fresh_hooks, category=cat_id),
            parse_mode="Markdown",
        )

    # -------------------------------------------------------------
    # Step 3 -> Final Render: User tapped a Song button
    # -------------------------------------------------------------
    elif data.startswith("pick_song_"):
        raw_song = data.replace("pick_song_", "")
        current_song_opts = context.user_data.get("current_song_options", [])
        if raw_song == "random":
            chosen_song = random.choice(current_song_opts) if current_song_opts else {"id": "pee_loon", "title": "Pee Loon"}
            raw_song = chosen_song["id"]

        cat_id = context.user_data.get("chosen_cat", "sexy")
        img_id = context.user_data.get("chosen_img", "sheer_saree")
        hook_text = context.user_data.get("chosen_hook", "")

        await query.edit_message_text("⚡ Starting your animated reel generation with vocal audio...")
        await render_custom_selected_reel(
            update,
            context,
            img_id=img_id,
            song_id=raw_song,
            hook_text=hook_text,
            category=cat_id,
        )

    # -------------------------------------------------------------
    # Legacy Fallbacks
    # -------------------------------------------------------------
    elif data.startswith("reel_type_"):
        cat_id = data.replace("reel_type_", "")
        context.user_data["chosen_cat"] = cat_id
        cat_info = get_category_info(cat_id)
        fresh_images = await get_fresh_image_options(chat_id, category=cat_id, limit=5)
        context.user_data["current_img_options"] = fresh_images
        await query.edit_message_text(
            f"📸 *Step 1 of 3: Choose Visual (Image)*\n\n📂 *Category:* {cat_info['title']}\nSelect one of 5 candid aesthetics below:",
            reply_markup=build_image_selection_keyboard(fresh_images, category=cat_id),
            parse_mode="Markdown",
        )


@restricted
async def set_gemini_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set or update Google Gemini API key dynamically."""
    message = update.effective_message
    if not message:
        return
    args = context.args or []
    if not args:
        await message.reply_text(
            "🔑 *Usage:* `/set_gemini_key YOUR_GEMINI_API_KEY`\n\n"
            "Get your key starting with `AIzaSy...` from Google AI Studio:\n"
            "https://aistudio.google.com/app/apikey",
            parse_mode="Markdown",
        )
        return

    new_key = args[0].strip()
    os.environ["GEMINI_API_KEY"] = new_key
    try:
        env_file = Path(".env")
        if env_file.exists():
            lines = env_file.read_text(encoding="utf-8").splitlines()
            new_lines = []
            found = False
            for line in lines:
                if line.startswith("GEMINI_API_KEY="):
                    new_lines.append(f"GEMINI_API_KEY={new_key}")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"GEMINI_API_KEY={new_key}")
            env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except Exception as e:
        logger.warning(f"Could not write to .env: {e}")

    await message.reply_text(
        f"✅ *Google Gemini Key Saved!*\nKey prefix: `{new_key[:8]}...`\nBot will use Gemini Imagen 3 for dynamic AI candid photos!",
        parse_mode="Markdown",
    )


@restricted
async def set_openai_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set or update OpenAI API key dynamically."""
    message = update.effective_message
    if not message:
        return
    args = context.args or []
    if not args:
        await message.reply_text(
            "🔑 *Usage:* `/set_openai_key YOUR_OPENAI_API_KEY`\n\n"
            "Get your key from OpenAI Platform:\n"
            "https://platform.openai.com/api-keys",
            parse_mode="Markdown",
        )
        return

    new_key = args[0].strip()
    os.environ["OPENAI_API_KEY"] = new_key
    try:
        env_file = Path(".env")
        if env_file.exists():
            lines = env_file.read_text(encoding="utf-8").splitlines()
            new_lines = []
            found = False
            for line in lines:
                if line.startswith("OPENAI_API_KEY="):
                    new_lines.append(f"OPENAI_API_KEY={new_key}")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"OPENAI_API_KEY={new_key}")
            env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except Exception as e:
        logger.warning(f"Could not write to .env: {e}")

    await message.reply_text(
        f"✅ *OpenAI Key Saved!*\nKey prefix: `{new_key[:8]}...`\nBot will use DALL-E 3 for dynamic AI candid photos!",
        parse_mode="Markdown",
    )

