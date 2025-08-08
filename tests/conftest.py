# tests/conftest.py
import sys

# Py 3.13: alias audioop-lts -> audioop so discord.py imports succeed
try:
    import audioop as _audioop  # noqa: F401
except Exception:
    import audioop_lts as _audioop  # type: ignore

    sys.modules["audioop"] = _audioop
