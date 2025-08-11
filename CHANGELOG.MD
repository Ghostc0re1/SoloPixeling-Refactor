# Unified Changelog

## Db

## [Unreleased] – Database Layer Migration (SQLite → Supabase)

### Added

- **Supabase-backed, fully async data layer** (`src/data/database.py`):
  - Connection via `SUPABASE_URL` and `SUPABASE_KEY` (from `.env`).
  - Concurrency guard with `asyncio.Semaphore` and `asyncio.to_thread` wrapper.
- **Guild settings consolidation**:
  - `get_all_guild_settings()` returns a single map of all settings per guild.
  - `set_guild_setting(guild_id, settings)` upserts arbitrary settings keys.
- **User profile customization**:
  - `get_user_profile`, `update_user_profile`
  - `set_profile_colors`, `clear_profile_colors`
  - **Banner storage**:
    - `set_rank_banner` (upload + persist path)
    - `upload_rank_banner` (helper)
    - `remove_rank_banner` (clear path, optional storage delete)
    - Uses Supabase Storage bucket `rank-banners` with cache-friendly metadata.
- **Giveaways (new DB-backed model)**:
  - `create_giveaway`, `get_active_giveaways`, `get_giveaway_by_id`,
    `list_active_giveaways_for_guild`, `set_giveaway_end_time_now`,
    `get_due_giveaways`
  - Entrants: `add_entry`, `get_entry_count`, `get_giveaway_entrants`
  - Atomic finalize: `end_giveaway(message_id)` guards against double-processing.
- **Daily XP (async)**:
  - `increment_daily_xp` → calls RPC `increment_daily_xp_for_user`
  - `get_daily_top_user`, `reset_daily_xp`
- **Ranks & leaderboards (async)**:
  - `get_user`, `set_user_xp_and_level`, `get_user_rank` (via RPC `get_user_rank_in_guild`)
  - `get_leaderboard(guild_id, top)`
- **Derived settings helpers**:
  - `get_all_cooldowns()` and `get_all_xp_ranges()` built from unified guild settings.
  - `get_all_channel_settings()` derived from unified settings.

### Changed

- **Module location**: `database.py` (root) → `src/data/database.py`.
- **All functions are asynchronous**; callers now `await` DB methods.
- **Settings API**:
  - Channel setters: `set_welcome_channel`, `set_levelup_channel` now async and wrap `set_guild_setting`.
  - `get_all_*` helpers synthesize views from a single `guild_settings` table.
- **Dates & time**:
  - Consistent UTC ISO-8601 (`.isoformat()`) in giveaways and daily XP RPC calls.
- **Storage behavior**:
  - Rank banner uploads prefer bytes upload; robust fallbacks for client variants (bytes vs. path, hyphenated vs. underscored metadata keys).

### Removed

- **SQLite implementation** and file path config (`config.DB_PATH`).
- `init_db()` table-creation routine.
- Duplicate legacy functions in the old module (e.g., duplicate `get_user_rank`, `set_user_xp_and_level`).
- Any direct SQL; all persistence now via Supabase tables/RPC/storage.

### Fixed

- Eliminated race risks by serializing calls through a semaphore.
- Ranking logic delegated to a DB-side function (stable & indexable).
- Daily XP and giveaway finalization can’t double-apply thanks to atomic `end_giveaway`.

### Breaking Changes

- **Everything is async**: update all call sites to `await` database functions.
- **Environment**: requires `.env` with `SUPABASE_URL` and `SUPABASE_KEY`.
- **Schema/RPC expectations** (Supabase/Postgres):
  - Tables:
    - `users(user_id, guild_id, xp, level)`
    - `guild_settings(guild_id, xp_cooldown, min_xp, max_xp, welcome_channel_id, levelup_channel_id, …)`
    - `daily_xp(guild_id, user_id, date, xp_gain)`
    - `user_profiles(user_id, guild_id, primary_color, accent_color, banner_path)`
    - `giveaways(message_id, channel_id, guild_id, prize, end_time, winner_count, host_id, is_active)`
    - `entries(id, giveaway_id, user_id)`
  - RPCs:
    - `increment_daily_xp_for_user(p_guild_id, p_user_id, p_date, p_amount)`
    - `get_user_rank_in_guild(p_guild_id, p_user_id)` → returns rank
  - Storage:
    - Bucket `rank-banners` with write access for your service role.
- **Return shapes**:
  - Some functions now return lists/dicts from Supabase; caller code updated accordingly.

### Migration Checklist

1. **Create Supabase project & set env**:
   - Add `SUPABASE_URL` and `SUPABASE_KEY` to `.env`.
2. **Provision schema** (tables above). Add indexes on common filters:
   - `users (guild_id, xp DESC)`, `giveaways (is_active, end_time)`, `entries (giveaway_id)`, `daily_xp (guild_id, date)`.
3. **Define RPCs**:
   - `increment_daily_xp_for_user` (UPSERT/UPDATE daily_xp row).
   - `get_user_rank_in_guild` (window function or rank over `xp` / `level,xp` as desired).
4. **Create storage bucket** `rank-banners`; grant service-role write.
5. **(Optional) Migrate data** from SQLite:
   - Export `users`, `guild_settings`, `daily_xp` and import to Supabase.
6. **Update callers**:
   - Replace imports with `from data import database as db`.
   - Add `await` to all DB calls (cogs already updated in this release).
7. **Policies**:
   - If RLS is enabled, ensure service role or appropriate policies for server-side operations.

### Notes

- Concurrency: `_DB_SEM = asyncio.Semaphore(8)` throttles parallel calls; tune for your workload.
- The rank banner uploader gracefully handles multiple supabase-py variants (bytes vs. path, metadata key styles) and falls back to `update` on 409-like failures.

---

## Events

## [Unreleased] – Events Cog Refactor

### Events Cog Refactor Changed

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

### Events Cog Refactor Removed

- Direct string interpolation in logging statements (replaced with parameterized style for performance and safety).

---

## Giveaway

## [Unreleased] – Giveaway Cog Overhaul

### Giveaway Cog Overhaul Added

- **Full database-backed giveaway system** replacing file-based JSON persistence:
  - Uses async DB operations for all giveaway state (`create_giveaway`, `get_due_giveaways`, `end_giveaway`, etc.).
  - Supports reattaching to active giveaways after bot restart without losing data.
- **New admin commands**:
  - `/giveaway` – Start a giveaway with prize, duration, and winner count.
  - `/giveaway-end` – Force finalize a giveaway by message ID or link.
  - `/giveaway-list` – List active giveaways in the server, optionally filtered by channel.
  - `/giveaway-reroll` – Reroll winners for a finished giveaway.
- **Background processing**:
  - `check_giveaways_loop` runs at `config.GIVEAWAY_CHECK_INTERVAL` to end giveaways automatically.
- **Robust winner selection**:
  - Weighted by `ROLE_WEIGHTS` and `DEFAULT_WEIGHT` in config.
  - Skips entrants who left the server.
- **Giveaway embed builder** with consistent end-state formatting.

### Giveaway Cog Overhaul Changed

- Removed legacy JSON file persistence (`giveaways.json`) and in-memory state management.
- Giveaway entry tracking moved to DB with persistent entrant lists.
- Moved button handling logic out of the view and into cog helpers for clarity.
- Entry handling now uses `fetch_member_safe` for resilience against missing cache entries.
- Greatly expanded error handling and logging:
  - `logger.exception` with structured `extra` context (guild, channel, message IDs).
  - Differentiated handling for `discord.NotFound` and `discord.Forbidden`.
- Embeds for ended giveaways rebuilt cleanly even if original embed missing/changed.
- Duration and winner count validation added (winners ≤ 50, duration ≤ 14 days).
- Placeholders replaced with final giveaway embeds immediately upon start.

### Giveaway Cog Overhaul Removed

- Old `GiveawayView` persistence and local `asyncio` scheduling logic.
- `_watchdog` task and JSON state rebuild code.
- Local weighting and winner logic inside `View` – now lives in `_weights_for` and `_pick_winners` on the cog.
- Commands:
  - `/giveaway_finalize`
  - `/giveaway_list` (old in-memory variant)
  - `/giveaway_where`
  - File-path debug output.

### Giveaway Cog Overhaul Fixed

- Multiple restart-related issues that previously caused giveaways to freeze or fail to end.
- Entrant count now correctly updates in embed after entry.
- Eliminated race conditions between entry and finalization.
- Winners now always announced and added to the embed regardless of original message state.

### Giveaway Cog Overhaul Breaking Changes

- **Database layer must support new async giveaway schema**:
  - `create_giveaway`, `get_due_giveaways`, `end_giveaway`, `get_giveaway_entrants`, `list_active_giveaways_for_guild`, `get_giveaway_by_id`.
- **Config additions required**:
  - `GIVEAWAY_CHECK_INTERVAL`
  - `DEFAULT_WEIGHT` and `ROLE_WEIGHTS` for weighted draws.
- Old file-based giveaways are not migrated – any active giveaways in JSON will not be recovered.

---

---

## Help

## [Unreleased] – Help Cog Refactor

### Help Cog Refactor Changed

- **View extraction**:
  - Moved `HelpView` from `help.py` into a dedicated `views/help_view.py` module for cleaner separation of UI logic from command logic.
- **Response handling**:
  - Added `await interaction.response.defer(ephemeral=True)` at the start of the command to handle slower processing and prevent interaction timeouts.
  - Replaced `interaction.response.send_message` + `original_response` pattern with `interaction.followup.send` for deferred responses.
- **Error handling**:
  - Wrapped command logic in `try/except` block.
  - Added `logging.error()` calls for unexpected exceptions with detailed error messages.
- **Embed handling**:
  - Moved page footer setting (`Page X/Y`) after embed list creation for better clarity.
  - Minor style consistency improvements in embed creation.
- **Code clarity**:
  - Improved inline comments for categorization and view setup.
  - Renamed some inline comments for precision.

### Help Cog Refactor Removed

- Inline `HelpView` class definition from cog file — now imported from `views.help_view`.
- Inline button logic from cog — now encapsulated in the view module.

### Help Cog Refactor Fixed

- Avoids ephemeral message timeout when processing many commands.
- Properly handles cases with no commands available, returning a friendly message instead of an empty embed list.

---

## Image Utils

## [Unreleased] – Image & Rank Card Utilities Refactor

### Image & Rank Card Utilities Refactor Added

- **Typed helpers & dataclasses**
  - `GlowStyle` (glow color + radii), `TextRun`, and `TextDrawSpec` for clearer, testable text rendering.
- **Color utilities**
  - `_hex_to_rgb()` to safely parse `#RRGGBB` with sensible fallbacks.
- **Themed rank cards**
  - `generate_rank_card(data: RankCardData)` now supports per-user theming:
    - `primary_color` and `accent_color` (hex) control headings and XP bar.
    - Optional `banner_bytes` used as background with a soft overlay.
- **Reusable text drawing**
  - `draw_text()` now returns a `TextDrawSpec` (also immediately renders).

### Image & Rank Card Utilities Refactor Changed

- **Function signatures**
  - `generate_rank_card(...)` switched from many positional args to a single `RankCardData` object (import from `helpers.level_utils`).
  - `make_glow_image(...)` now keyword-only for `prefix` and `suffix`.
- **Structure & readability**
  - Broke out private helpers: `_measure_text`, `_find_max_font_size`, `_build_glow_layer`.
  - Normalized variable naming (`w/h`), consistent center math, and Pillow calls.
- **Background handling**
  - If a custom banner is supplied, it’s **fitted** with `ImageOps.fit` (LANCZOS) and darkened with a subtle overlay.  
  - Default background still supported; alpha reduced so foreground pops.
- **XP bar & labels**
  - XP bar fill now uses **accent color**; text uses **primary color** with outline.
  - Rank/level spacing logic preserved, cleaned up for `None` values.
- **Multiline glow**
  - Keeps visual style, clarifies autoscale target (50% width window) and iteration.

### Image & Rank Card Utilities Refactor Removed

- Duplicate inline font loading paths without normalization (now `str(fp)`).
- Old `generate_rank_card(member, level, rank, current_xp, required_xp, total_xp)` signature.
- Redundant comments and mixed concerns inside public functions.

### Image & Rank Card Utilities Refactor Fixed

- Safer fallbacks when fonts or backgrounds are missing.
- Avoided variable shadowing (e.g., `data` vs. local variables).
- More robust bytes handling for avatars and banners.

### Image & Rank Card Utilities Refactor Breaking Changes

- **API**:
  - Update callers to: `await image_utils.generate_rank_card(RankCardData(...))`
  - `make_glow_image` call sites must pass `prefix=` and `suffix=`.
- **Imports**:
  - Bring in `RankCardData` from `helpers.level_utils`.
- **Config expectations**:
  - Uses `config.CARD_WIDTH`, `config.CARD_HEIGHT`, `RANK_CARD_BACKGROUND_PATH`,
    and font paths (`REGULAR_FONT_PATH`, `BOLD_ITALIC_FONT_PATH`).

### Image & Rank Card Utilities Refactor Notes

- Visual output remains familiar but now supports per-user themes and custom banners.
- Helper types make it easier to unit-test layout and rendering in isolation.
]

---

## Level Utils

## [Unreleased] – Level Utils Expansion & XP System Enhancements

### Level Utils Expansion & XP System Enhancements Added

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

### Level Utils Expansion & XP System Enhancements Changed

- **Function signatures**:
  - Original `xp_for_level` and `level_from_xp` retained, but integrated into a richer XP/leveling ecosystem.
- **Organization**:
  - Grouped XP logic, dataclasses, and banner fetching in one module for central management.
- **Type safety**:
  - Added `Optional` typing for nullable fields like `primary_color`, `accent_color`, and `banner_bytes`.

### Level Utils Expansion & XP System Enhancements Fixed

- Prevents repeated banner downloads via TTL-based in-memory caching.
- Safe Supabase URL generation with trimming of trailing slashes and leading slashes in paths.

### Level Utils Expansion & XP System Enhancements Breaking Changes

- Code generating rank cards should now pass a `RankCardData` object instead of multiple loose parameters.
- Banner assets for rank cards are now fetched asynchronously via `fetch_banner_bytes()`.

### Level Utils Expansion & XP System Enhancements Notes

- XP scaling (`level**1.30`) is still adjustable in `xp_for_level` for future balancing.
- New dataclass-based structure improves testability and reduces parameter-passing errors.

---

## Leveling

## [Unreleased] – Leveling Cog Refactor

### Leveling Cog Refactor Added

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

### Leveling Cog Refactor Changed

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

### Leveling Cog Refactor Fixed

- XP cooldown no longer incorrectly shared between guilds.
- Daily awards no longer silently fail due to missing members or permissions.
- Level-up announcements now handle missing channels, roles, and permission errors.
- Ensured `cog_unload` cleanly stops the daily award task.

### Leveling Cog Refactor Breaking Changes

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

---

## Scheduling

## [Unreleased] – Scheduling Cog Refactor

### Scheduling Cog Refactor Changed

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

### Scheduling Cog Refactor Removed

- Tuple-based schedule parsing logic.
- `cog_unload` sync method replaced with async `cog_unload` (matching other async-safe cogs).

### Scheduling Cog Refactor Fixed

- Potential errors when handling schedules with optional delete times (no need for tuple length checks).
- More consistent handling of missing channels/roles in both loop and `testschedule`.

### Scheduling Cog Refactor Notes

- **Breaking Change**: Requires `config.PING_SCHEDULES` to be a list of `PingSchedule` objects. Old tuple format is no longer supported.

---

## Settings

## [Unreleased] – Settings Cog Refactor

### Settings Cog Refactor Changed

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

### Settings Cog Refactor Removed

- Manual XP/level progress calculation in `removeallxp`, `addxp`, and `removexp`.
- Inline `PurgeConfirmationView` class — now imported from views module.

### Settings Cog Refactor Fixed

- XP range and cooldown commands now consistently update cog-level caches (`guild_xp_ranges`, `guild_cooldowns`).
- More consistent ephemeral response handling across all commands.
- Fixed potential race condition where original purge confirmation message might not be stored before use.

### Settings Cog Refactor Notes

- **Breaking Change**: Requires updated `database` module to support new async methods.
- **Dependencies**: `helpers.level_utils.build_xp_status` must exist and return an object with `.level` and `.total_xp` attributes.

---

## Utility

## [Unreleased] – Utility Cog Refactor

### Utility Cog Refactor Changed

- **Bug report modal extraction**:
  - `BugReportModal` class moved from `utility.py` into dedicated `views/bugreport_view.py` for better separation of concerns.
  - Updated `UtilityCog` to import `BugReportModal` from the new `views` module.
- **UI text formatting**:
  - Improved readability in modal `steps` field by splitting placeholder text into multiple lines.
- **Code style**:
  - Added `# pylint: disable=arguments-differ` to `on_submit` and `on_error` overrides to prevent linter warnings.
  - Reorganized imports for clarity and consistency.

### Utility Cog Refactor Removed

- Inline modal definition from `UtilityCog`.
- Redundant imports from `utility.py` (e.g., `ui`, `TextStyle`, `config`, `traceback`) now handled in the `views` module.

### Utility Cog Refactor Fixed

- None functionally, but code is now cleaner and easier to maintain.

### Utility Cog Refactor Notes

- This refactor improves modularity — the `views` directory now handles UI components separately from cog logic.

---
