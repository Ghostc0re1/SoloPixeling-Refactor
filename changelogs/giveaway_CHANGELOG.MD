# Changelog

## [Unreleased] – Giveaway Cog Overhaul

### Added

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

### Changed

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

### Removed

- Old `GiveawayView` persistence and local `asyncio` scheduling logic.
- `_watchdog` task and JSON state rebuild code.
- Local weighting and winner logic inside `View` – now lives in `_weights_for` and `_pick_winners` on the cog.
- Commands:
  - `/giveaway_finalize`
  - `/giveaway_list` (old in-memory variant)
  - `/giveaway_where`
  - File-path debug output.

### Fixed

- Multiple restart-related issues that previously caused giveaways to freeze or fail to end.
- Entrant count now correctly updates in embed after entry.
- Eliminated race conditions between entry and finalization.
- Winners now always announced and added to the embed regardless of original message state.

### Breaking Changes

- **Database layer must support new async giveaway schema**:
  - `create_giveaway`, `get_due_giveaways`, `end_giveaway`, `get_giveaway_entrants`, `list_active_giveaways_for_guild`, `get_giveaway_by_id`.
- **Config additions required**:
  - `GIVEAWAY_CHECK_INTERVAL`
  - `DEFAULT_WEIGHT` and `ROLE_WEIGHTS` for weighted draws.
- Old file-based giveaways are not migrated – any active giveaways in JSON will not be recovered.

---
