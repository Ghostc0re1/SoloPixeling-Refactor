# Changelog

## [Unreleased] – Settings Cog Refactor

### Changed

- **Database layer is now fully asynchronous**:
  - All calls to `database` methods updated to `await` (`set_welcome_channel`, `set_levelup_channel`, `set_xp_cooldown`, `update_xp_range`, `get_user`, `set_user_xp_and_level`).
- **XP status computation**:
  - Replaced manual `xp_for_level`/`level_from_xp` progress math with centralized helper `build_xp_status` from `helpers.level_utils`.
  - Simplifies tracking of `level` and `total_xp` while reducing repeated math logic.
- **View handling**:
  - `PurgeConfirmationView` moved to `views.purge_confirmation_view`.
  - Purge confirmation and execution remain the same but now loaded from separate module.
- **Command error handling**:
  - All commands wrapped in `try/except` blocks with error logging.
  - Fallback error messages sent to the user when exceptions occur.
- **Code structure**:
  - Group commands (`channel_group`, `leveling_group`) preserved but internal logic simplified.
  - Removed inline duplicate logic for role add/remove and progress calculations by using `build_xp_status`.

### Removed

- Manual XP/level progress calculation in `removeallxp`, `addxp`, and `removexp`.
- Inline `PurgeConfirmationView` class — now imported from views module.

### Fixed

- XP range and cooldown commands now consistently update cog-level caches (`guild_xp_ranges`, `guild_cooldowns`).
- More consistent ephemeral response handling across all commands.
- Fixed potential race condition where original purge confirmation message might not be stored before use.

### Notes

- **Breaking Change**: Requires updated `database` module to support new async methods.
- **Dependencies**: `helpers.level_utils.build_xp_status` must exist and return an object with `.level` and `.total_xp` attributes.
