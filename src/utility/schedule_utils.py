from dataclasses import dataclass
from typing import Optional, Tuple


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
        # normalize days to an immutable tuple
        days_tuple: Tuple[int, ...] = tuple(self.days)
        object.__setattr__(self, "days", days_tuple)

        if not days_tuple:
            raise ValueError(
                "days cannot be empty; provide 0–6 for Mon–Sun (or your chosen mapping)."
            )

        for d in days_tuple:
            if not 0 <= d <= 6:
                raise ValueError(f"day value {d!r} is out of range (expected 0..6).")

        if not 0 <= self.ping_hour <= 23 or not 0 <= self.ping_min <= 59:
            raise ValueError(
                f"invalid ping time: {self.ping_hour:02d}:{self.ping_min:02d} "
                "(hour 0..23, minute 0..59)."
            )

        # require delete_hour and delete_min to be both set or both None
        if (self.delete_hour is None) ^ (self.delete_min is None):
            raise ValueError(
                "delete_hour and delete_min must both be set or both be None."
            )

        if self.delete_hour is not None:
            if not 0 <= self.delete_hour <= 23:
                raise ValueError(
                    f"delete_hour {self.delete_hour!r} out of range (0..23)."
                )
            if not 0 <= self.delete_min <= 59:
                raise ValueError(
                    f"delete_min {self.delete_min!r} out of range (0..59)."
                )
