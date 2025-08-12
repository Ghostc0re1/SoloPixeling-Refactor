# src/helpers/level_helper.py
import logging
import time
from typing import Optional
import os
from dotenv import load_dotenv

import aiohttp

from utility.level_utils import build_public_storage_url

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")

_banner_cache: dict[str, tuple[float, bytes]] = {}
_BANNER_TTL = 600.0  # seconds


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
