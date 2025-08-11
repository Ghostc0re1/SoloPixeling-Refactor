# Changelog

## [Unreleased] – Level Utils Expansion & XP System Enhancements

### Added

- **Data modeling**:
  - `XpResult` dataclass to encapsulate XP update results (`leveled_up`, `new_level`, `old_level`).
  - `XPStatus` dataclass (slots + frozen) for consistent XP/level progress tracking.
  - `RankCardData` dataclass to provide a single structured input for rank card generation, including optional theme colors and banner bytes.
- **XP status helper**:
  - `build_xp_status(total_xp)` now returns a fully populated `XPStatus` with start-of-level XP, next-level XP, and remaining XP needed.
- **Banner fetch & caching**:
  - `build_public_storage_url(bucket, path)` to create Supabase public file URLs.
  - `fetch_banner_bytes(banner_path)` async helper to fetch and cache banner images from Supabase (`rank-banners` bucket).
  - Local `_banner_cache` with TTL (`_BANNER_TTL`) to avoid repeated HTTP requests.
- **Environment config**:
  - `.env`-based `SUPABASE_URL` loading with `dotenv`.

### Changed

- **Function signatures**:
  - Original `xp_for_level` and `level_from_xp` retained, but integrated into a richer XP/leveling ecosystem.
- **Organization**:
  - Grouped XP logic, dataclasses, and banner fetching in one module for central management.
- **Type safety**:
  - Added `Optional` typing for nullable fields like `primary_color`, `accent_color`, and `banner_bytes`.

### Fixed

- Prevents repeated banner downloads via TTL-based in-memory caching.
- Safe Supabase URL generation with trimming of trailing slashes and leading slashes in paths.

### Breaking Changes

- Code generating rank cards should now pass a `RankCardData` object instead of multiple loose parameters.
- Banner assets for rank cards are now fetched asynchronously via `fetch_banner_bytes()`.

### Notes

- XP scaling (`level**1.30`) is still adjustable in `xp_for_level` for future balancing.
- New dataclass-based structure improves testability and reduces parameter-passing errors.
