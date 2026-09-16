"""Unit tests for the AutoPilot Daily Scheduler."""

import pytest
from bot.services.autopilot import (
    DAILY_SLOTS,
    IST,
    DEFAULT_ADMIN_CHAT_ID,
    init_autopilot_db,
    is_autopilot_active,
    set_autopilot_status,
    get_active_subscribers,
)


def test_daily_slots_configuration():
    """Verify the 3 daily posting slots are correctly configured."""
    assert len(DAILY_SLOTS) == 3

    # Slot 1: Traditional (12:20 PM delivery, 12:30 PM post)
    s1 = DAILY_SLOTS[0]
    assert s1["category"] == "traditional"
    assert s1["hour"] == 12
    assert s1["minute"] == 20
    assert "12:30 PM" in s1["target_post_time_str"]

    # Slot 2: Romantic (07:50 PM delivery, 08:00 PM post)
    s2 = DAILY_SLOTS[1]
    assert s2["category"] == "romantic"
    assert s2["hour"] == 19
    assert s2["minute"] == 50
    assert "08:00 PM" in s2["target_post_time_str"]

    # Slot 3: Night Owl (10:35 PM delivery, 10:45 PM post)
    s3 = DAILY_SLOTS[2]
    assert s3["hour"] == 22
    assert s3["minute"] == 35
    assert "10:45 PM" in s3["target_post_time_str"]


@pytest.mark.asyncio
async def test_autopilot_subscription_db():
    """Verify DB settings for autopilot can be read, toggled, and retrieved."""
    test_chat_id = 999333444

    await init_autopilot_db()

    # Default admin is active
    admin_active = await is_autopilot_active(DEFAULT_ADMIN_CHAT_ID)
    assert admin_active is True

    # Toggle on for test chat
    await set_autopilot_status(test_chat_id, True)
    assert await is_autopilot_active(test_chat_id) is True

    subs = await get_active_subscribers()
    assert test_chat_id in subs
    assert DEFAULT_ADMIN_CHAT_ID in subs

    # Toggle off
    await set_autopilot_status(test_chat_id, False)
    assert await is_autopilot_active(test_chat_id) is False
    subs_after = await get_active_subscribers()
    assert test_chat_id not in subs_after
