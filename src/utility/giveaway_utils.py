# src/helpers/giveaway_utils.py
from datetime import datetime
from typing import Optional
import re

MESSAGE_LINK_RE = re.compile(
    r"^https?://(?:(?:ptb|canary)\.)?(?:discord(?:app)?\.com)/channels/\d+/(?P<channel_id>\d+)/(?P<message_id>\d+)$"
)


def parse_message_id(s: str) -> Optional[int]:
    s = s.strip()
    m = MESSAGE_LINK_RE.match(s)
    if m:
        return int(m.group("message_id"))
    return int(s) if s.isdigit() else None


def parse_utc_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))
