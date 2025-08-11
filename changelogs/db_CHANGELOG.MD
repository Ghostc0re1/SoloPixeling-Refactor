# Changelog

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
