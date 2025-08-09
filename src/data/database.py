# database.py

from datetime import datetime
import os
import discord
from dotenv import load_dotenv
from supabase import create_client, Client


#
# --- Initialization ---
#
load_dotenv()
#
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
#
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Supabase URL and Key must be set in the .env file.")
#
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


#
# --- Daily XP Functions ---
#
def increment_daily_xp(user_id: int, guild_id: int, amount: int):
    """Adds XP to today's gain for a user by calling the database function."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    supabase.rpc(
        "increment_daily_xp_for_user",
        {
            "p_guild_id": guild_id,
            "p_user_id": user_id,
            "p_date": today,
            "p_amount": amount,
        },
    ).execute()


#
def get_daily_top_user(guild_id: int, date: str) -> tuple | None:
    """Returns (user_id, xp_gain) for the top gainer on `date` in this guild."""
    response = (
        supabase.table("daily_xp")
        .select("user_id", "xp_gain")
        .eq("guild_id", guild_id)
        .eq("date", date)
        .order("xp_gain", desc=True)
        .limit(1)
        .execute()
    )
    if response.data:
        top_user = response.data[0]
        return top_user["user_id"], top_user["xp_gain"]
    return None


#
def reset_daily_xp(date: str):
    """Purges all rows for a given date."""
    supabase.table("daily_xp").delete().eq("date", date).execute()


#
# --- Cooldown Functions ---
#
def set_xp_cooldown(guild_id: int, seconds: int):
    """Saves a new XP cooldown for a guild."""
    set_guild_setting(guild_id, {"xp_cooldown": seconds})


#
def get_all_cooldowns() -> dict[int, int]:
    """
    Loads all custom guild cooldowns by processing the main settings dump.
    """
    all_settings = get_all_guild_settings()
    cooldowns = {}
    for guild_id, settings in all_settings.items():
        if settings.get("xp_cooldown") is not None:
            cooldowns[guild_id] = settings["xp_cooldown"]
    return cooldowns


#
# --- User Level Functions ---
#
def get_user(user_id: int, guild_id: int):
    """Fetches a user's XP and level from Supabase."""
    response = (
        supabase.table("users")
        .select("xp", "level")
        .eq("user_id", user_id)
        .eq("guild_id", guild_id)
        .execute()
    )
    if response.data:
        # Supabase returns a list, so we get the first item
        user_data = response.data[0]
        return user_data["xp"], user_data["level"]
    return None  # Return None if user not found, matching fetchone() behavior


#
def set_user_xp_and_level(user_id: int, guild_id: int, xp: int, level: int):
    """Creates or updates a user's record with new XP and level using upsert."""
    supabase.table("users").upsert(
        {"user_id": user_id, "guild_id": guild_id, "xp": xp, "level": level}
    ).execute()


#
def get_user_rank(user_id: int, guild_id: int) -> int | None:
    """Gets a user's rank in the guild by calling the database function."""
    response = supabase.rpc(
        "get_user_rank_in_guild", {"p_guild_id": guild_id, "p_user_id": user_id}
    ).execute()
    if response.data:
        return response.data[0]["rank"]
    return None


#
# --- Leaderboard Functions ---
#
def get_leaderboard(guild_id: int, top: int) -> list[tuple]:
    """Gets the top users for the leaderboard by total XP."""
    response = (
        supabase.table("users")
        .select("user_id", "level", "xp")
        .eq("guild_id", guild_id)
        .order("xp", desc=True)
        .limit(top)
        .execute()
    )
    # Convert list of dicts to list of tuples to match original output format
    return [(user["user_id"], user["level"], user["xp"]) for user in response.data]


#
def get_all_xp_ranges() -> dict[int, tuple[int, int]]:
    """
    Loads all custom guild XP ranges by processing the main settings dump.
    """
    all_settings = get_all_guild_settings()
    xp_ranges = {}
    for guild_id, settings in all_settings.items():
        # Ensure both min_xp and max_xp exist before adding
        min_xp = settings.get("min_xp")
        max_xp = settings.get("max_xp")
        if min_xp is not None and max_xp is not None:
            xp_ranges[guild_id] = (min_xp, max_xp)
    return xp_ranges


#
def update_xp_range(guild_id: int, min_xp: int, max_xp: int):
    """Saves a new min/max XP range for a guild."""
    set_guild_setting(guild_id, {"min_xp": min_xp, "max_xp": max_xp})


#
# --- Guild Settings ---
#
def get_all_channel_settings() -> dict[int, dict[str, int]]:
    """
    Loads all channel settings by processing the main settings dump.
    """
    all_settings = get_all_guild_settings()
    channel_settings = {}
    for guild_id, settings in all_settings.items():
        channel_settings[guild_id] = {
            "welcome": settings.get("welcome_channel_id"),
            "levelup": settings.get("levelup_channel_id"),
        }
    return channel_settings


#
def set_guild_setting(guild_id: int, settings: dict):
    """A generic function to update any guild setting using upsert."""
    # Add the primary key to the settings dict for upsert
    settings["guild_id"] = guild_id
    supabase.table("guild_settings").upsert(settings).execute()


#
def set_welcome_channel(guild_id: int, channel_id: int | None):
    """Saves a new welcome channel for a guild."""
    set_guild_setting(guild_id, {"welcome_channel_id": channel_id})


#
def set_levelup_channel(guild_id: int, channel_id: int | None):
    """Saves a new level-up channel for a guild."""
    set_guild_setting(guild_id, {"levelup_channel_id": channel_id})


#
def get_all_guild_settings() -> dict:
    """Loads all guild settings from the database into a single dictionary."""
    response = supabase.table("guild_settings").select("*").execute()
    # Create a dictionary keyed by guild_id
    return {row["guild_id"]: row for row in response.data}


# --- Giveaway Functions ---


async def create_giveaway(
    message: discord.Message,
    prize: str,
    end_time: datetime,
    winner_count: int,
    host: discord.Member,
) -> None:
    """Stores a new giveaway in the database."""
    giveaway_data = {
        "message_id": message.id,
        "channel_id": message.channel.id,
        "guild_id": message.guild.id,
        "prize": prize,
        "end_time": end_time.isoformat(),
        "winner_count": winner_count,
        "host_id": host.id,
        "is_active": True,
    }
    supabase.table("giveaways").insert(giveaway_data).execute()


async def add_entry(giveaway_id: int, user_id: int) -> tuple[bool, str]:
    """Adds a user entry to a giveaway. Returns (success, message)."""
    try:
        supabase.table("entries").insert(
            {"giveaway_id": giveaway_id, "user_id": user_id}
        ).execute()
        return (True, "You have entered the giveaway!")
    except Exception as e:
        # We can check for that specific error code.
        if "23505" in str(e):  # 23505 is PostgreSQL's unique_violation error code
            return (False, "You have already entered this giveaway!")
        print(f"Error adding entry: {e}")
        return (False, "An error occurred while entering the giveaway.")


async def get_entry_count(giveaway_id: int) -> int:
    """Gets the number of entries for a giveaway."""
    response = (
        supabase.table("entries")
        .select("id", count="exact")
        .eq("giveaway_id", giveaway_id)
        .execute()
    )
    return response.count


async def get_active_giveaways() -> list:
    """Fetches all giveaways that are currently active."""
    response = supabase.table("giveaways").select("*").eq("is_active", True).execute()
    return response.data


async def get_giveaway_entrants(giveaway_id: int) -> list[int]:
    """Gets a list of user IDs for all entrants of a giveaway."""
    response = (
        supabase.table("entries")
        .select("user_id")
        .eq("giveaway_id", giveaway_id)
        .execute()
    )
    return [entry["user_id"] for entry in response.data]


async def end_giveaway(message_id: int) -> bool:
    # only flip if still active to avoid races
    res = (
        supabase.table("giveaways")
        .update({"is_active": False})
        .eq("message_id", message_id)
        .eq("is_active", True)
        .execute()
    )
    return bool(res.data)
