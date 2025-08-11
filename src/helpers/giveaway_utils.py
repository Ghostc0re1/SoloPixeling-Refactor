# src/helpers/giveaway_utils.py
from datetime import datetime
from typing import Optional
import re

import discord

MESSAGE_LINK_RE = re.compile(
    r"^https?://(?:(?:ptb|canary)\.)?(?:discord(?:app)?\.com)/channels/\d+/(?P<channel_id>\d+)/(?P<message_id>\d+)$"
)


def parse_message_id(s: str) -> Optional[int]:
    s = s.strip()
    m = MESSAGE_LINK_RE.match(s)
    if m:
        return int(m.group("message_id"))
    return int(s) if s.isdigit() else None


async def fetch_member_safe(
    guild: discord.Guild, user_id: int
) -> discord.Member | None:
    m = guild.get_member(user_id)
    if m:
        return m
    try:
        return await guild.fetch_member(user_id)
    except (discord.NotFound, discord.Forbidden):
        return None


def parse_utc_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))
