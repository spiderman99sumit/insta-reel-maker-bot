"""Auto-Caption & Viral Hashtag Generation Engine for Instagram Reels."""

import random
from typing import List, Optional

# High-CTR CTAs tailored for flirty, aesthetic & viral reels
CTAS: List[str] = [
    "Drop a '🖤' if you agree...",
    "Save this for late night vibes 🌙✨",
    "Tag your 2 AM person 🥀",
    "Double tap if this hit home ❤️‍🩹",
    "Share with someone who needs to see this 💬",
    "Comment your mood in one emoji 🌚",
    "Rehne do cutie, sach bolna allowed nahi hai 🤫",
    "Don't forget to save this 📌",
]

# Naughty / flirty contextual teasers
TEASERS: List[str] = [
    "Some thoughts are just better left unspoken... or maybe not 🥀🖤",
    "Sharafat ka zamana gaya, late night vibes only 🌙",
    "If you know, you know 🤫",
    "Main kuch nahi bol rahi, bas aankhein bol rahi hain ✨",
    "2 AM rules are always unwritten 🥀",
    "Ek glance hi kafi tha hosh udane ke liye 💋",
    "Don't blame me, blame the vibe 🌙✨",
]

# Curated high-reach hashtags for explore page algorithms
GENERAL_HASHTAGS: List[str] = [
    "#reels", "#explorepage", "#viralreels", "#trendingreels",
    "#reelitfeelit", "#fyp", "#foryou", "#explore", "#viral",
    "#instadaily", "#trending", "#reelsinstagram"
]

STYLE_HASHTAGS = {
    "sexy": [
        "#seductivelook", "#latenightvibes", "#flirty", "#desi",
        "#sareelover", "#desiattire", "#indianbeauty", "#moodygrams",
        "#aestheticvibes", "#desiaesthetic", "#boldlook", "#nightowl"
    ],
    "romantic": [
        "#romanticvibes", "#lovequotes", "#romance", "#feelings",
        "#deepthoughts", "#couplesgoals", "#soulmate", "#aesthetic",
        "#emotionalquotes", "#silentlove"
    ],
    "cinematic": [
        "#cinematicreels", "#visualart", "#moodyedits", "#filmphotography",
        "#darkaesthetic", "#cinematography", "#aestheticfeed", "#storytelling"
    ],
    "meme": [
        "#relatablememes", "#funnymemes", "#humor", "#memesdaily",
        "#dailymemes", "#indianmemes", "#dankmemes", "#relatable"
    ],
}


def generate_instagram_caption(
    hook_text: str,
    style: str = "sexy",
    custom_tag_count: int = 15,
) -> str:
    """Generate an Instagram-ready caption complete with hook, teaser, CTA, and hashtags."""
    clean_hook = hook_text.strip()
    
    # Pick teaser and CTA
    teaser = random.choice(TEASERS)
    cta = random.choice(CTAS)
    
    # Assemble hashtag stack
    style_key = style.lower().strip()
    specific_tags = STYLE_HASHTAGS.get(style_key, STYLE_HASHTAGS["sexy"])
    
    # Combine general + specific tags, shuffle and pick target count
    all_tags = list(set(GENERAL_HASHTAGS + specific_tags))
    random.shuffle(all_tags)
    selected_tags = all_tags[:custom_tag_count]
    hashtag_block = " ".join(selected_tags)
    
    # Format caption with aesthetic line spacing
    parts = [
        clean_hook,
        "",
        teaser,
        "",
        f"• {cta}",
        "• Follow for more unreleased daily reels 🖤",
        "",
        ".",
        ".",
        ".",
        hashtag_block
    ]
    return "\n".join(parts)

