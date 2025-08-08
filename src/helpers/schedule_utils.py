from dataclasses import dataclass
from typing import Optional


# pylint: disable=too-many-instance-attributes
@dataclass(slots=True)
class PingSchedule:
    role_id: int
    ch_id: int
    ping_hour: int
    ping_min: int
    days: tuple[int, ...]
    msg: str
    delete_hour: Optional[int] = None
    delete_min: Optional[int] = None

    def __post_init__(self):
        object.__setattr__(self, "days", tuple(self.days))
        # (sanity checks)
        for d in self.days:
            assert 0 <= d <= 6
        assert 0 <= self.ping_hour <= 23 and 0 <= self.ping_min <= 59
        if self.delete_hour is not None:
            assert 0 <= self.delete_hour <= 23
        if self.delete_min is not None:
            assert 0 <= self.delete_min <= 59
