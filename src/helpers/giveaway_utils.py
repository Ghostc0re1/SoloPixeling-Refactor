from dataclasses import dataclass
import discord


@dataclass(slots=True)
class GiveawayState:
    prize: str
    winner_count: int
    host_id: int
    entries: set[int]
    winners: list[discord.Member]
