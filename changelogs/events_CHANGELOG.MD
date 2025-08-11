# Changelog

## [Unreleased] – Events Cog Refactor

### Changed

- **Async database access**  
  - `on_ready` now awaits `database.get_all_channel_settings()` instead of using a synchronous call.
- **Updated imports**  
  - Moved to modular imports: `from data import database` and `from helpers import image_utils`.
- **Improved logging**  
  - Switched to parameterized logging for safety (`log.warning("...", arg)` instead of f-strings).
  - Replaced generic `except Exception as e` with `log.exception()` for full stack traces.
- **Welcome message flow**  
  - Retains image generation logic but with cleaner, safer channel and guild checks.
  - Ensures buffer seeks to start before sending image file.
  - Fallback text message improved with clearer error handling.
- **Role alert handling**  
  - Still detects newly added roles, but logging is more explicit about missing permissions or missing channels.

### Removed

- Direct string interpolation in logging statements (replaced with parameterized style for performance and safety).
