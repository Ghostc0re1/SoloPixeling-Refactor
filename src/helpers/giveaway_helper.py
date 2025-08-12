# src/helpers/giveaway_helper.py
import discord


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
