# Changelog

## [Unreleased] – Scheduling Cog Refactor

### Changed

- **Config structure updated**:
  - `config.PING_SCHEDULES` now contains `PingSchedule` objects instead of tuples.
  - Accessed via attributes (`role_id`, `ch_id`, `ping_hour`, `ping_min`, `delete_hour`, `delete_min`, `days`, `msg`) rather than tuple indexes.
- **Loop timing**:
  - Changed `@tasks.loop(seconds=60)` to `@tasks.loop(minutes=1)` for clarity.
- **Code readability**:
  - Removed tuple unpacking logic in favor of direct attribute access.
  - Simplified conditionals for day matching, ping sending, and channel purging.
  - Reformatted log/print messages for consistent and clear output.
- **`testschedule` command**:
  - Updated to work with `PingSchedule` objects.
  - Improved error messages for invalid indexes.
  - Refactored embed field construction for better readability.
  - Channel/role checks now use named attributes instead of tuple indices.

### Removed

- Tuple-based schedule parsing logic.
- `cog_unload` sync method replaced with async `cog_unload` (matching other async-safe cogs).

### Fixed

- Potential errors when handling schedules with optional delete times (no need for tuple length checks).
- More consistent handling of missing channels/roles in both loop and `testschedule`.

### Notes

- **Breaking Change**: Requires `config.PING_SCHEDULES` to be a list of `PingSchedule` objects. Old tuple format is no longer supported.
