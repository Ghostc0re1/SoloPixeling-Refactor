from dataclasses import asdict, dataclass
from typing import Optional
import os
import config


# pylint:disable=too-many-instance-attributes
@dataclass(frozen=True, slots=True)
class CogLogging:
    # root/app
    level: Optional[str] = None
    fmt: str = config.DEFAULT_FMT
    datefmt: str = config.DEFAULT_DATEFMT
    file_path: Optional[str] = "logs/bot.log"
    max_bytes: int = 5_000_000
    backup_count: int = 3
    discord_level: str = "WARNING"

    # dedicated HTTP log
    http_log_path: Optional[str] = None
    http_level: str = "INFO"
    http_propagate: bool = False
    http_logger_names: tuple[str, ...] = ("httpx", "httpcore", "urllib3")

    @property
    def level_norm(self) -> str:
        return (self.level or os.getenv("LOG_LEVEL", "INFO")).upper()

    def to_kwargs(self) -> dict:
        return {
            "level": self.level_norm,
            "fmt": self.fmt,
            "datefmt": self.datefmt,
            "file_path": self.file_path,
            "max_bytes": self.max_bytes,
            "backup_count": self.backup_count,
            "discord_level": self.discord_level,
            "http_log_path": self.http_log_path,
            "http_level": self.http_level,
            "http_propagate": self.http_propagate,
            "http_logger_names": self.http_logger_names,
        }

    @classmethod
    def from_env(cls) -> "CogLogging":
        return cls(
            level=os.getenv("LOG_LEVEL"),
            file_path=os.getenv("LOG_FILE", "logs/bot.log"),
        )

    @classmethod
    def build(cls, base: "CogLogging | None" = None, **overrides) -> "CogLogging":
        """
        Merge an optional base dataclass with kwargs (overrides win), coerce types.
        """
        data = asdict(base) if base else {}
        data.update({k: v for k, v in overrides.items() if v is not None})
        # ensure tuple type if a list/iterable was passed
        if "http_logger_names" in data and not isinstance(
            data["http_logger_names"], tuple
        ):
            data["http_logger_names"] = tuple(data["http_logger_names"])  # type: ignore[arg-type]
        return cls(**data)
