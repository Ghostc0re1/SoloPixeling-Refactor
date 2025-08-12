# helpers/logging_helper.py
import logging
import time
import sys
from pathlib import Path
from typing import Optional
from logging.handlers import RotatingFileHandler

from utility.logging_utils import CogLogging


class EveryNSecondsFilter(logging.Filter):
    def __init__(self, seconds: int):
        super().__init__()
        self.seconds = seconds
        self._last = 0.0

    def filter(self, record: logging.LogRecord) -> bool:
        now = time.monotonic()
        if now - self._last >= self.seconds:
            self._last = now
            return True
        return False


def _apply_core_levels(cfg: CogLogging) -> logging.Logger:
    root = logging.getLogger()
    root.setLevel(cfg.level_norm)
    logging.getLogger("discord").setLevel(cfg.discord_level)
    logging.getLogger("asyncio").setLevel("WARNING")
    return root


def _clear_root_handlers(root: logging.Logger) -> None:
    for h in list(root.handlers):
        root.removeHandler(h)


def _attach_root_handlers(root: logging.Logger, cfg: CogLogging) -> None:
    fmt = logging.Formatter(cfg.fmt, cfg.datefmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    if cfg.file_path:
        try:
            Path(cfg.file_path).parent.mkdir(parents=True, exist_ok=True)
            fh = RotatingFileHandler(
                cfg.file_path,
                maxBytes=cfg.max_bytes,
                backupCount=cfg.backup_count,
                encoding="utf-8",
            )
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except Exception:
            root.exception(
                "Failed to attach file handler; continuing with console only."
            )


def _refresh_http_loggers(cfg: CogLogging) -> None:
    for name in cfg.http_logger_names:
        log = logging.getLogger(name)
        if cfg.http_log_path:
            log.setLevel(cfg.http_level)
            log.propagate = cfg.http_propagate
        else:
            # keep them quiet if not dedicating a file
            log.setLevel("WARNING")
            log.propagate = False


def _toggle_http_file_handler(
    current: Optional[RotatingFileHandler], cfg: CogLogging
) -> Optional[RotatingFileHandler]:
    """Create/replace/remove the dedicated http handler as needed, return new handler (or None)."""
    # remove if disabled
    if not cfg.http_log_path:
        if current:
            for nm in cfg.http_logger_names:
                logging.getLogger(nm).removeHandler(current)
            current.close()
        return None

    # need a new one?
    want_path = str(Path(cfg.http_log_path))
    need_new = current is None or getattr(current, "baseFilename", "") != want_path
    if not need_new:
        return current

    # replace old
    if current:
        for nm in cfg.http_logger_names:
            logging.getLogger(nm).removeHandler(current)
        current.close()

    try:
        Path(want_path).parent.mkdir(parents=True, exist_ok=True)
        http_fh = RotatingFileHandler(
            want_path,
            maxBytes=cfg.max_bytes,
            backupCount=cfg.backup_count,
            encoding="utf-8",
        )
        http_fh.setFormatter(logging.Formatter(cfg.fmt, cfg.datefmt))
        for nm in cfg.http_logger_names:
            logging.getLogger(nm).addHandler(http_fh)
        return http_fh
    except Exception:
        logging.getLogger().exception(
            "Failed to attach HTTP log handler; continuing without dedicated HTTP log."
        )
        return None


def setup_logging(cfg: CogLogging | None = None, **overrides) -> None:
    """
    Configure root logging once. Safe to call multiple times:
    - First call: attach handlers
    - Later calls: just update levels / HTTP routing
    """
    cfg = CogLogging.build(cfg, **overrides)

    root = _apply_core_levels(cfg)

    # Subsequent calls: refresh levels + HTTP routing and swap handler if needed
    if getattr(setup_logging, "configured", False):
        _refresh_http_loggers(cfg)
        prev = getattr(setup_logging, "http_handler", None)
        setup_logging.http_handler = _toggle_http_file_handler(prev, cfg)
        return

    # First-time wiring
    _clear_root_handlers(root)
    _attach_root_handlers(root, cfg)

    _refresh_http_loggers(cfg)
    setup_logging.http_handler = _toggle_http_file_handler(None, cfg)

    logging.captureWarnings(True)
    setup_logging.configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"bot.{name}")


def add_throttle(logger: logging.Logger, seconds: int) -> None:
    logger.addFilter(EveryNSecondsFilter(seconds))
