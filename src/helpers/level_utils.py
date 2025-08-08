# level_utils.py
from dataclasses import dataclass


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
