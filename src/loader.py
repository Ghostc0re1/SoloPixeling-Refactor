import json
import os
from pathlib import Path
from string import Formatter
from typing import Dict
import logging

ALLOWED_FIELDS = {"mention", "role"}
REQUIRED_FIELDS = {"mention"}
FALLBACK_TEMPLATE = "Welcome {mention}!"

JSON_LOCATIONS = [
    Path(__file__).parent / "data" / "welcome_messages.json",
    Path(__file__).parent / "welcome_messages.json",
    Path.cwd() / "welcome_messages.json",
]

_MD_BALANCE_TOKENS = ["**", "__", "~~", "*"]

log = logging.getLogger("bot.loader")


def _balance_simple_markers(text: str) -> tuple[str, list[str]]:
    """
    Balance **, __, ~~ and * outside of backtick code spans.
    Returns (fixed_text, fixes_log).
    """
    fixes = []
    result = []
    i = 0
    in_code = False
    backtick_run = 0

    open_stack: list[str] = []

    def flush_unclosed():
        nonlocal fixes
        if open_stack:
            closing = "".join(reversed(open_stack))
            result.append(closing)
            fixes.append(f"Closed unbalanced markdown: appended '{closing}'")
            open_stack.clear()

    while i < len(text):
        ch = text[i]

        if ch == "`":
            start = i
            while i < len(text) and text[i] == "`":
                i += 1
            run = i - start
            if in_code and run == backtick_run:
                in_code = False
                backtick_run = 0
            elif not in_code:
                in_code = True
                backtick_run = run
            result.append("`" * run)
            continue

        if in_code:
            result.append(ch)
            i += 1
            continue

        matched = False
        for tok in _MD_BALANCE_TOKENS:
            if text.startswith(tok, i):
                if open_stack and open_stack[-1] == tok:
                    # close it
                    open_stack.pop()
                else:
                    # open it
                    open_stack.append(tok)
                result.append(tok)
                i += len(tok)
                matched = True
                break
        if matched:
            continue

        result.append(ch)
        i += 1

    if not in_code:
        flush_unclosed()
    else:
        result.append("`" * backtick_run)
        fixes.append(f"Closed unbalanced code span: appended {'`' * backtick_run}")

    return "".join(result), fixes


def _validate_markdown(template: str) -> tuple[str, list[str]]:
    """
    Best-effort fixer:
      - balances simple markers outside code
      - balances backticks
    """
    fixed, fixes = _balance_simple_markers(template)
    return fixed, fixes


def _extract_fields(template: str) -> set:
    return {f for _, f, _, _ in Formatter().parse(template) if f}


def _validate_template(gid: str, template: str) -> str:
    fields = _extract_fields(template)
    missing = REQUIRED_FIELDS - fields
    disallowed = fields - ALLOWED_FIELDS

    if missing:
        if "{mention}" not in template:
            template += " {mention}"

    if disallowed:
        for f in disallowed:
            template = template.replace("{" + f + "}", "")

    template, _md_fixes = _validate_markdown(template)
    for msg in _md_fixes:
        log.info("welcome template fix (%s): %s", gid, msg)

    return template or FALLBACK_TEMPLATE


def _env_overrides(messages: Dict[str, str]) -> Dict[str, str]:
    if os.getenv("WELCOME_MESSAGE_DEFAULT"):
        messages["default"] = os.getenv("WELCOME_MESSAGE_DEFAULT")

    for key, val in os.environ.items():
        if key.startswith("WELCOME_MESSAGE_") and key != "WELCOME_MESSAGE_DEFAULT":
            gid = key.split("WELCOME_MESSAGE_", 1)[1].strip()
            if gid.isdigit():
                messages[gid] = val
    return messages


def _find_json_file() -> Path | None:
    for candidate in JSON_LOCATIONS:
        if candidate.exists():
            log.info("welcome messages file: %s", candidate)
            return candidate
    log.warning("welcome messages file not found; using in-code defaults")
    return None


def load_welcome_messages() -> Dict[str, str]:
    path = _find_json_file()
    raw = {}
    if path:
        try:
            with path.open(encoding="utf-8") as f:
                raw = json.load(f)
        except json.JSONDecodeError as e:
            log.error("Invalid welcome_messages.json at %s: %s", path, e)
            raw = {}

        normalized: Dict[str, str] = {}
        for k, v in raw.items():
            key = str(k)
            val = v if isinstance(v, str) else str(v)
            val = val.strip()
            normalized[key] = val

    if "default" not in normalized or not normalized["default"].strip():
        normalized["default"] = FALLBACK_TEMPLATE

    normalized = _env_overrides(normalized)

    for gid in list(normalized.keys()):
        normalized[gid] = _validate_template(gid, normalized[gid])

    return normalized
