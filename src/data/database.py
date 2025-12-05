# database.py
import time
from typing import Callable, TypeVar
import random
import asyncio
from datetime import datetime, timezone
import logging
import os
import tempfile
import httpx
import httpcore
import discord
from dotenv import load_dotenv
from supabase import create_client, Client

from helpers.logging_helper import get_logger


#
# --- Initialization ---
#
load_dotenv()
logger = get_logger("database")
#
url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_ANON_KEY")
BOT_EMAIL = os.getenv("BOT_EMAIL")
BOT_PASSWORD = os.getenv("BOT_PASSWORD")
T = TypeVar("T")
#
if not url or not key:
    raise ValueError("Supabase URL and Key must be set in the .env file.")
#
supabase: Client = create_client(url, key)

_DB_SEM = asyncio.Semaphore(8)

_TRANSIENT = (
    httpx.ReadError,
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.TimeoutException,
    httpcore.ReadError,
    httpcore.TimeoutException,
)


def _extract_access_token(sess) -> str | None:
    # supabase-py v2 (Pydantic model)
    if hasattr(sess, "access_token"):
        return getattr(sess, "access_token")
    if (
        hasattr(sess, "session")
        and getattr(sess, "session") is not None
        and hasattr(sess.session, "access_token")
    ):
        return getattr(sess.session, "access_token")

    if isinstance(sess, dict):
        return sess.get("access_token") or (sess.get("session") or {}).get(
            "access_token"
        )

    return None


def _has_valid_session() -> bool:
    sess = supabase.auth.get_session()
    return bool(_extract_access_token(sess))


def _ensure_session() -> None:
    if _has_valid_session():
        return
    supabase.auth.sign_in_with_password({"email": BOT_EMAIL, "password": BOT_PASSWORD})
    if not _has_valid_session():
        raise RuntimeError("Supabase user session missing after login")


async def _db(call):
    async with _DB_SEM:
        try:
            return await asyncio.wait_for(asyncio.to_thread(call), timeout=35.0)
        except asyncio.TimeoutError:
            logger.error("DB call timed out after 35s in _db()", exc_info=True)
            raise


async def _db_authed_async(call: Callable[[], T]) -> T:
    def _wrapped():
        _ensure_session()
        return call()

    return await _db(_wrapped)


def _retry_sync(
    call,
    *,
    retries: int = 4,
    base_delay: float = 0.35,
    factor: float = 2.0,
    cap: float = 5.0,
):
    """
    Retry helper for sync DB operations.

    Retries ONLY if the exception is transient and does NOT contain signs
    of a PostgREST server-side failure such as:
        - "Internal server error"
        - "JSON could not be generated"

    Logs structured diagnostic information and records retry attempts.
    """
    delay = base_delay
    attempts = 0

    for attempt in range(retries):
        try:
            if attempt > 0:
                logger.warning(
                    "retry_sync: Attempt %d/%d executing call()",
                    attempt,
                    retries - 1,
                )
            return call()

        except _TRANSIENT as exc:
            attempts = attempt

            message = str(exc).lower()

            server_error = (
                "internal server error" in message
                or "json could not be generated" in message
                or "556" in message
            )

            if server_error:
                logger.error(
                    "retry_sync: Server-side failure detected. "
                    "Not retrying. Attempts=%d, Error=%s",
                    attempt,
                    exc,
                )
                raise

            if attempt == retries - 1:
                logger.error(
                    "retry_sync: Out of retries for transient error. Attempts=%d Error=%s",
                    attempt,
                    exc,
                )
                raise

            sleep_time = min(delay, cap) + random.uniform(0.0, 0.25)
            logger.warning(
                "retry_sync: Transient error. Retrying in %.2fs. "
                "Attempts=%d/%d. Error=%s",
                sleep_time,
                attempt,
                retries - 1,
                exc,
            )
            time.sleep(sleep_time)
            delay *= factor

    return None


async def authenticate_bot() -> bool:
    def _exec():
        try:
            _ensure_session()
            return _has_valid_session()
        except Exception as e:
            logger.error("Supabase auth failed: %s", e)
            return False

    return await _db(_exec)


#
# --- Daily XP Functions ---
#
async def increment_daily_xp(user_id: int, guild_id: int, delta: int) -> None:
    def _exec():
        return supabase.rpc(
            "increment_daily_xp_for_user",
            {"p_guild_id": guild_id, "p_user_id": user_id, "p_delta": delta},
        ).execute()

    await _db_authed_async(_exec)


#
async def get_daily_top_user(guild_id: int, date: str) -> tuple[int, int] | None:
    """Return (user_id, xp_gain) for the ET calendar `date` in this guild, or None."""

    def _exec():
        return supabase.rpc(
            "get_daily_top_user", {"p_guild_id": guild_id, "p_date": date}
        ).execute()

    resp = await _db_authed_async(_exec)

    if resp.data:
        r = resp.data
        return int(r["user_id"]), int(r["xp_gain"])

    return None


# ---------- Outbox: stage a winner (UPSERT) ----------
async def stage_daily_award(
    guild_id: int, target_date: str, user_id: int, xp_gain: int, channel_id: int | None
) -> dict:
    payload = {"channel_id": channel_id}

    def _exec():
        return supabase.rpc(
            "stage_daily_award",
            {
                "p_guild_id": guild_id,
                "p_target_date": target_date,  # 'YYYY-MM-DD'
                "p_user_id": user_id,
                "p_xp_gain": xp_gain,
                "p_payload": payload,
            },
        ).execute()

    resp = await _db_authed_async(_exec)
    return resp.data or {}


# ---------- Outbox: list pending (announced_at IS NULL) ----------
async def list_outbox_pending(limit: int = 50) -> list[dict]:
    # If you exposed a dedicated RPC, use it; otherwise query the table.
    def _exec():
        return (
            supabase.table("daily_award_outbox")
            .select("*")
            .is_("announced_at", None)
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )

    res = await _db_authed_async(_exec)
    return res.data or []


# ---------- Outbox: mark announced (stores message_id, sets announced_at) ----------
async def mark_award_announced(
    guild_id: int, target_date: str, message_id: int
) -> dict:
    def _exec():
        return supabase.rpc(
            "mark_award_announced",
            {
                "p_guild_id": guild_id,
                "p_target_date": target_date,
                "p_message_id": message_id,
            },
        ).execute()

    resp = await _db_authed_async(_exec)
    return resp.data or {}


#
async def reset_daily_xp(date_str: str) -> int:
    """Deletes all rows for ET date `date_str` via SECURITY DEFINER RPC. Returns deleted count."""

    def _exec():
        return supabase.rpc("admin_reset_daily_xp", {"p_date": date_str}).execute()

    resp = await _db_authed_async(_exec)
    deleted = int(resp.data or 0)
    logger.info("reset_daily_xp(%s) deleted=%s", date_str, deleted)
    return deleted


async def reset_daily_xp_for_guild(guild_id: int, date_str: str) -> int:
    """Deletes all rows for a specific guild and ET date `date_str`."""

    def _exec():
        # The RPC function now takes two parameters
        params = {"p_guild_id": guild_id, "p_date": date_str}
        return supabase.rpc("admin_reset_daily_xp_for_guild", params).execute()

    resp = await _db_authed_async(_exec)
    deleted = int(resp.data or 0)
    logger.info(
        "reset_daily_xp_for_guild(guild=%s, date=%s) deleted=%s",
        guild_id,
        date_str,
        deleted,
    )
    return deleted


# ---------- Cleanup: ONLY if announced_at is set ----------
async def reset_daily_xp_after_announce(guild_id: int, target_date: str) -> int:
    def _exec():
        return supabase.rpc(
            "reset_daily_xp_after_announce",
            {"p_guild_id": guild_id, "p_target_date": target_date},
        ).execute()

    resp = await _db_authed_async(_exec)
    deleted = int(resp.data or 0)
    logger.info(
        "reset_daily_xp_after_announce(guild=%s, date=%s) deleted=%s",
        guild_id,
        target_date,
        deleted,
    )
    return deleted


# Returns True if any daily_xp rows exist for the given date
async def daily_xp_exists(date: str) -> bool:
    def _exec():
        return (
            supabase.table("daily_xp")
            .select("user_id", count="exact")
            .eq("date", date)
            .limit(1)
            .execute()
        )

    res = await _db_authed_async(_exec)
    return (getattr(res, "count", None) or 0) > 0 or bool(res.data)


#
# --- Cooldown Functions ---
#
async def set_xp_cooldown(guild_id: int, seconds: int):
    """Saves a new XP cooldown for a guild."""
    await set_guild_setting(guild_id, {"xp_cooldown": seconds})


#
async def get_all_cooldowns() -> dict[int, int]:
    """
    Loads all custom guild cooldowns by processing the main settings dump.
    """
    all_settings = await get_all_guild_settings()
    cooldowns: dict[int, int] = {}
    for guild_id, settings in all_settings.items():
        if settings.get("xp_cooldown") is not None:
            cooldowns[guild_id] = settings["xp_cooldown"]
    return cooldowns


#
# --- User Level Functions ---
#
async def get_user(user_id: int, guild_id: int):
    """Fetches a user's XP and level from Supabase."""

    def _exec():
        return (
            supabase.table("users")
            .select("xp", "level")
            .eq("user_id", user_id)
            .eq("guild_id", guild_id)
            .execute()
        )

    response = await _db_authed_async(_exec)
    if response.data:
        user_data = response.data[0]
        return user_data["xp"], user_data["level"]
    return None


#
async def set_user_xp_and_level(user_id: int, guild_id: int, xp: int, level: int):
    """Creates or updates a user's record with new XP and level using upsert."""

    def _exec():
        supabase.table("users").upsert(
            {"user_id": user_id, "guild_id": guild_id, "xp": xp, "level": level},
            on_conflict="user_id,guild_id",
        ).execute()

    await _db_authed_async(_exec)


#
async def get_user_rank(user_id: int, guild_id: int) -> int | None:
    """Gets a user's rank in the guild by calling the database function."""

    def _exec():
        return supabase.rpc(
            "get_user_rank_in_guild", {"p_guild_id": guild_id, "p_user_id": user_id}
        ).execute()

    resp = await _db_authed_async(_exec)
    d = resp.data
    if d is None:
        return None
    if isinstance(d, (int, float)):
        return int(d)
    if isinstance(d, list) and d:
        if isinstance(d[0], dict) and "rank" in d[0]:
            return int(d[0]["rank"])
        if isinstance(d[0], (int, float)):
            return int(d[0])
    return None


async def get_user_profile(user_id: int, guild_id: int) -> dict | None:
    """Fetches a user's profile customization settings."""

    def _exec():
        return (
            supabase.table("user_profiles")
            .select("*")
            .eq("user_id", user_id)
            .eq("guild_id", guild_id)
            .execute()
        )

    response = await _db_authed_async(_exec)
    return response.data[0] if response.data else None


async def update_user_profile(user_id: int, guild_id: int, settings: dict) -> None:
    """Updates a user's profile settings in the database."""

    def _exec():
        supabase.table("user_profiles").upsert(
            {"user_id": user_id, "guild_id": guild_id, **settings},
            on_conflict="user_id,guild_id",
        ).execute()

    await _db_authed_async(_exec)


async def set_profile_colors(
    user_id: int, guild_id: int, primary: str | None, accent: str | None
) -> None:
    payload = {"user_id": user_id, "guild_id": guild_id}
    if primary is not None:
        payload["primary_color"] = primary
    if accent is not None:
        payload["accent_color"] = accent

    def _exec():
        supabase.table("user_profiles").upsert(
            payload, on_conflict="user_id,guild_id"
        ).execute()

    await _db_authed_async(_exec)


async def set_profile_banner_path(
    user_id: int, guild_id: int, banner_path: str | None
) -> None:
    def _exec():
        supabase.table("user_profiles").upsert(
            {"user_id": user_id, "guild_id": guild_id, "banner_path": banner_path},
            on_conflict="user_id,guild_id",
        ).execute()

    await _db_authed_async(_exec)


async def clear_profile_colors(user_id: int, guild_id: int) -> None:
    # explicitly set both columns to NULL
    def _exec():
        supabase.table("user_profiles").upsert(
            {
                "user_id": user_id,
                "guild_id": guild_id,
                "primary_color": None,
                "accent_color": None,
            },
            on_conflict="user_id,guild_id",
        ).execute()

    await _db_authed_async(_exec)


#
# --- Leaderboard Functions ---
#
async def get_leaderboard(guild_id: int, top: int) -> list[tuple]:
    """Gets the top users for the leaderboard by total XP."""

    def _exec():
        return (
            supabase.table("users")
            .select("user_id", "level", "xp")
            .eq("guild_id", guild_id)
            .order("xp", desc=True)
            .limit(top)
            .execute()
        )

    response = await _db_authed_async(_exec)
    return [(user["user_id"], user["level"], user["xp"]) for user in response.data]


#
async def get_all_xp_ranges() -> dict[int, tuple[int, int]]:
    """
    Loads all custom guild XP ranges by processing the main settings dump.
    """
    all_settings = await get_all_guild_settings()
    xp_ranges: dict[int, tuple[int, int]] = {}
    for guild_id, settings in all_settings.items():
        # Ensure both min_xp and max_xp exist before adding
        min_xp = settings.get("min_xp")
        max_xp = settings.get("max_xp")
        if min_xp is not None and max_xp is not None:
            xp_ranges[guild_id] = (min_xp, max_xp)
    return xp_ranges


#
async def update_xp_range(guild_id: int, min_xp: int, max_xp: int):
    """Saves a new min/max XP range for a guild."""
    await set_guild_setting(guild_id, {"min_xp": min_xp, "max_xp": max_xp})


#
# --- Guild Settings ---
#
async def get_all_channel_settings() -> dict[int, dict[str, int]]:
    """
    Loads all channel settings by processing the main settings dump.
    """
    all_settings = await get_all_guild_settings()
    channel_settings: dict[int, dict[str, int]] = {}
    for guild_id, settings in all_settings.items():
        channel_settings[guild_id] = {
            "welcome": settings.get("welcome_channel_id"),
            "levelup": settings.get("levelup_channel_id"),
        }
    return channel_settings


#
async def set_guild_setting(guild_id: int, settings) -> dict:
    """Upsert guild settings without mutating the input and without blocking the loop."""
    payload = {"guild_id": guild_id, **dict(settings)}

    def _exec():
        return supabase.table("guild_settings").upsert(payload).execute()

    return await _db_authed_async(_exec)


#
async def set_welcome_channel(guild_id: int, channel_id: int | None):
    """Saves a new welcome channel for a guild."""
    await set_guild_setting(guild_id, {"welcome_channel_id": channel_id})


async def set_levelup_channel(guild_id: int, channel_id: int | None):
    """Saves a new level-up channel for a guild."""
    await set_guild_setting(guild_id, {"levelup_channel_id": channel_id})


#
async def get_all_guild_settings() -> dict:
    """Loads all guild settings from the database into a single dictionary."""

    def _exec():
        return supabase.table("guild_settings").select("*").execute()

    response = await _db_authed_async(_exec)
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

    def _exec():
        supabase.table("giveaways").insert(giveaway_data).execute()

    await _db_authed_async(_exec)


async def add_entry(giveaway_id: int, user_id: int) -> tuple[bool, str]:
    """Adds a user entry to a giveaway. Returns (success, message)."""

    def _exec() -> tuple[bool, str]:
        try:
            supabase.table("entries").insert(
                {"giveaway_id": giveaway_id, "user_id": user_id}
            ).execute()
            return (True, "You have entered the giveaway!")
        except Exception as e:
            # Check for PostgreSQL's unique_violation error code
            if "23505" in str(e):
                return (False, "You have already entered this giveaway!")

            logger.exception("add_entry failed")
            return (False, "An error occurred while entering the giveaway.")

    return await _db_authed_async(_exec)


async def get_entry_count(giveaway_id: int) -> int:
    def _exec():
        return (
            supabase.table("entries")
            .select("id")
            .eq("giveaway_id", giveaway_id)
            .execute()
        )

    response = await _db_authed_async(_exec)
    return len(response.data or [])


async def get_active_giveaways() -> list:
    """Fetches all giveaways that are currently active."""

    def _exec():
        return supabase.table("giveaways").select("*").eq("is_active", True).execute()

    response = await _db_authed_async(_exec)
    return response.data


async def get_giveaway_entrants(giveaway_id: int) -> list[int]:
    """Gets a list of user IDs for all entrants of a giveaway."""

    def _exec():
        return (
            supabase.table("entries")
            .select("user_id")
            .eq("giveaway_id", giveaway_id)
            .execute()
        )

    response = await _db_authed_async(_exec)
    return [entry["user_id"] for entry in response.data]


async def end_giveaway(message_id: int) -> bool:
    """Atomically marks a giveaway as inactive. Returns True if a row was changed."""

    def _exec():
        return (
            supabase.table("giveaways")
            .update({"is_active": False}, returning="representation")
            .eq("message_id", message_id)
            .eq("is_active", True)
            .execute()
        )

    res = await _db_authed_async(_exec)
    return bool(res.data)


async def get_giveaway_by_id(message_id: int) -> dict | None:
    """Fetches a single giveaway by its message ID."""

    def _exec():
        return (
            supabase.table("giveaways")
            .select("*")
            .eq("message_id", message_id)
            .limit(1)
            .execute()
        )

    resp = await _db_authed_async(_exec)
    return resp.data[0] if resp.data else None


async def list_active_giveaways_for_guild(guild_id: int) -> list[dict]:
    """Lists all active giveaways for a specific guild."""

    def _exec():
        return (
            supabase.table("giveaways")
            .select("*")
            .eq("guild_id", guild_id)
            .eq("is_active", True)
            .order("end_time", desc=False)
            .execute()
        )

    resp = await _db_authed_async(_exec)
    return resp.data


async def set_giveaway_end_time_now(message_id: int) -> None:
    """Updates a giveaway's end time to the current time."""

    def _exec():
        supabase.table("giveaways").update(
            {"end_time": datetime.now(timezone.utc).isoformat()}
        ).eq("message_id", message_id).execute()

    await _db_authed_async(_exec)


async def get_due_giveaways(now_iso: str) -> list[dict]:
    def _exec():
        return _retry_sync(
            lambda: supabase.table("giveaways")
            .select("*")
            .eq("is_active", True)
            .lte("end_time", now_iso)
            .execute()
        )

    resp = await _db_authed_async(_exec)
    return resp.data


async def upload_rank_banner(
    user_id: int, guild_id: int, data: bytes, mime: str, ext: str
) -> str:
    path = f"banners/{guild_id}/{user_id}/rank_banner.{ext}"

    def _exec():
        # Try #1: some versions accept raw bytes directly
        try:
            return supabase.storage.from_("rank-banners").upload(
                path=path,
                file=data,  # <-- raw bytes, NOT BytesIO
                file_options={
                    # most clients read these camelCase keys
                    "contentType": mime,
                    "cacheControl": "public, max-age=31536000, immutable",
                    # some versions honor x-upsert only via header-like option
                    "x-upsert": "true",
                },
            )
        except TypeError:
            # Try #2: client wants a filesystem path
            with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=True) as tmp:
                tmp.write(data)
                tmp.flush()
                return supabase.storage.from_("rank-banners").upload(
                    path=path,
                    file=tmp.name,  # <-- pass a str path
                    file_options={
                        "contentType": mime,
                        "cacheControl": "public, max-age=31536000, immutable",
                        "x-upsert": "true",
                    },
                )

    await _db_authed_async(_exec)
    return path


async def set_rank_banner(
    user_id: int, guild_id: int, data: bytes, mime: str, ext: str
) -> None:
    """
    Upload banner to Storage and save its path to user_profiles.banner_path.
    Works across supabase-py variants (no upsert kwarg).
    """
    path = f"banners/{guild_id}/{user_id}/rank_banner.{ext}"
    bucket = supabase.storage.from_("rank-banners")

    def _meta(hyphenated: bool = True) -> dict:
        # Try hyphenated first; some builds want underscored.
        if hyphenated:
            return {
                "content-type": mime,
                "cache-control": "public, max-age=31536000, immutable",
            }
        return {
            "content_type": mime,
            "cache_control": "public, max-age=31536000, immutable",
        }

    def _upload_bytes(fn):
        # Call `fn(path=..., file=..., file_options=...)` with bytes first,
        # then fall back to a temp file path if the client insists on str path.
        try:
            return fn(path=path, file=data, file_options=_meta(True))
        except TypeError:
            # try underscored keys with bytes
            try:
                return fn(path=path, file=data, file_options=_meta(False))
            except TypeError:
                # final fallback: write to temp file and pass path
                with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=True) as tmp:
                    tmp.write(data)
                    tmp.flush()
                    try:
                        return fn(path=path, file=tmp.name, file_options=_meta(True))
                    except TypeError:
                        return fn(path=path, file=tmp.name, file_options=_meta(False))

    def _do_upload_or_update():
        # 1) Try upload (new file)
        try:
            return _upload_bytes(bucket.upload)
        except Exception as e:
            # If duplicate/409 or your client raises here, try update (overwrite)
            logging.debug("upload() failed, attempting update(): %r", e)
            return _upload_bytes(bucket.update)

    # do the storage write
    resp = await _db_authed_async(_do_upload_or_update)
    logging.debug("rank banner storage response: %r", resp)

    # persist the pointer
    def _save_path():
        return (
            supabase.table("user_profiles")
            .upsert(
                {"user_id": user_id, "guild_id": guild_id, "banner_path": path},
                on_conflict="user_id,guild_id",
            )
            .execute()
        )

    await _db_authed_async(_save_path)


async def remove_rank_banner(
    user_id: int, guild_id: int, delete_file: bool = False
) -> None:
    """
    Clear banner_path. Optionally also delete the file from Storage.
    """

    # Read current path (so we know what to delete if requested)
    def _get():
        return (
            supabase.table("user_profiles")
            .select("banner_path")
            .eq("user_id", user_id)
            .eq("guild_id", guild_id)
            .limit(1)
            .execute()
        )

    resp = await _db_authed_async(_get)
    current_path = resp.data[0]["banner_path"] if resp.data else None

    # Clear pointer
    def _clear():
        return (
            supabase.table("user_profiles")
            .upsert(
                {"user_id": user_id, "guild_id": guild_id, "banner_path": None},
                on_conflict="user_id,guild_id",
            )
            .execute()
        )

    await _db_authed_async(_clear)

    # Delete underlying file if asked and known
    if delete_file and current_path:

        def _rm():
            # Some clients want a list for remove()
            return supabase.storage.from_("rank-banners").remove([current_path])

        try:
            await _db_authed_async(_rm)
        except Exception:
            # don't hard-fail remove: storage cleanup best-effort
            logging.exception("Failed to delete banner file %s", current_path)
