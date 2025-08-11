# Changelog

## [Unreleased] – Image & Rank Card Utilities Refactor

### Added

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

### Changed

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

### Removed

- Duplicate inline font loading paths without normalization (now `str(fp)`).
- Old `generate_rank_card(member, level, rank, current_xp, required_xp, total_xp)` signature.
- Redundant comments and mixed concerns inside public functions.

### Fixed

- Safer fallbacks when fonts or backgrounds are missing.
- Avoided variable shadowing (e.g., `data` vs. local variables).
- More robust bytes handling for avatars and banners.

### Breaking Changes

- **API**:
  - Update callers to: `await image_utils.generate_rank_card(RankCardData(...))`
  - `make_glow_image` call sites must pass `prefix=` and `suffix=`.
- **Imports**:
  - Bring in `RankCardData` from `helpers.level_utils`.
- **Config expectations**:
  - Uses `config.CARD_WIDTH`, `config.CARD_HEIGHT`, `RANK_CARD_BACKGROUND_PATH`,
    and font paths (`REGULAR_FONT_PATH`, `BOLD_ITALIC_FONT_PATH`).

### Notes

- Visual output remains familiar but now supports per-user themes and custom banners.
- Helper types make it easier to unit-test layout and rendering in isolation.
]
