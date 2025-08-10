# level_utils.py
from dataclasses import dataclass
import logging
import time
from typing import Optional
import os
from dotenv import load_dotenv

import aiohttp

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")

_banner_cache: dict[str, tuple[float, bytes]] = {}
_BANNER_TTL = 600.0  # seconds


def build_public_storage_url(bucket: str, path: str) -> str:
    base = SUPABASE_URL.rstrip("/")
    return f"{base}/storage/v1/object/public/{bucket}/{path.lstrip('/')}"


async def fetch_banner_bytes(banner_path: str) -> Optional[bytes]:
    if not banner_path:
        return None

    now = time.time()
    cached = _banner_cache.get(banner_path)
    if cached and now - cached[0] < _BANNER_TTL:
        return cached[1]

    url = build_public_storage_url("rank-banners", banner_path)
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.read()
                _banner_cache[banner_path] = (now, data)
                return data

    logging.warning("Banner fetch failed: %s", url)
    return None


@dataclass
class XpResult:
    leveled_up: bool
    new_level: int
    old_level: int


@dataclass(slots=True, frozen=True)
class XPStatus:
    total_xp: int
    level: int
    start_of_level_xp: int
    next_level_xp: int
    xp_into_level: int
    xp_to_next: int


def xp_for_level(level: int) -> int:
    if level <= 0:
        return 0
    return int(100 * (level**1.35))


def level_from_xp(xp: int) -> int:
    lvl = 0
    while xp >= xp_for_level(lvl + 1):
        lvl += 1
    return lvl


def build_xp_status(total_xp: int) -> XPStatus:
    level = level_from_xp(total_xp)
    start = xp_for_level(level)
    nxt = xp_for_level(level + 1)
    return XPStatus(
        total_xp=total_xp,
        level=level,
        start_of_level_xp=start,
        next_level_xp=nxt,
        xp_into_level=total_xp - start,
        xp_to_next=nxt - total_xp,
    )
