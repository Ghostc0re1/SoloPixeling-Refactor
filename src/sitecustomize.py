import sys

# pylint: disable=deprecated-module
try:
    import audioop as _audioop  # noqa: F401
except Exception:
    import audioop_lts as _audioop  # type: ignore

    sys.modules["audioop"] = _audioop
