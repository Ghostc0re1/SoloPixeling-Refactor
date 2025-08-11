# Changelog

## [Unreleased] – Leveling Cog Refactor

### Added

- **Rank card customization commands:**
  - `/rank-set-banner` – Upload and auto-scale a custom banner (1600×400) stored in the database.
  - `/rank-remove-banner` – Remove your custom banner.
  - `/rank-set-colors` – Set primary/accent hex colors for your rank card.
  - `/rank-reset-colors` – Reset colors to defaults.
- **RankCardData** dataclass for passing user profile data to `image_utils.generate_rank_card`.
- **Banner processing** via Pillow:
  - Auto-resizes and letterboxes images.
  - Saves as WebP (preferred) or JPEG.
- `_is_hex` utility for validating color codes.
- `_process_banner_bytes` helper to handle scaling and format conversion.
- **New database operations**:
  - `get_user_profile`
  - `set_rank_banner`
  - `remove_rank_banner`
  - `set_profile_colors`
  - `clear_profile_colors`
  - `fetch_banner_bytes`

### Changed

- **All database calls are now asynchronous** (`await`).
- **LeaderboardView** moved to `views.leaderboard_view` for cleaner cog organization.
- **XP cooldown** is now tracked per guild and per user (prevents cross-guild bleed).
- **Level calculation** now derives from `level_from_xp` using current XP (ignores stale stored levels).
- **Daily awards task**:
  - Fully async DB calls.
  - Handles missing permissions and missing members gracefully.
  - Uses `_awards_started` flag to prevent duplicate starts.
- **/rank command**:
  - Now includes user-specific colors and banners when present.
  - Improved error handling with clearer messages.
- **/leaderboard command**:
  - Uses external `LeaderboardView`.
  - Added robust error handling.
- **Logging**:
  - Switched from `print()` to `logging` with contextual details.
  - Added debug logs for XP processing.
  - Consistent `logger = logging.getLogger(__name__)`.

### Fixed

- XP cooldown no longer incorrectly shared between guilds.
- Daily awards no longer silently fail due to missing members or permissions.
- Level-up announcements now handle missing channels, roles, and permission errors.
- Ensured `cog_unload` cleanly stops the daily award task.

### Breaking Changes

- **Database layer must support async methods**:
  - `get_all_cooldowns`, `get_all_xp_ranges`, `get_all_channel_settings`
  - `get_user`, `set_user_xp_and_level`, `increment_daily_xp`
  - `get_user_rank`, `get_leaderboard`
  - `get_daily_top_user`, `reset_daily_xp`
- `image_utils.generate_rank_card` signature now accepts a `RankCardData` object.
- **Config additions required**:
  - `ALLOWED_MIME`, `MAX_UPLOAD_BYTES`, `CARD_WIDTH`, `CARD_HEIGHT`
- **Dependencies**:
  - Added `Pillow` for image processing.

---
