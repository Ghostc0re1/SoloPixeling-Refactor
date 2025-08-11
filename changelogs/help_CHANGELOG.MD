# Changelog

## [Unreleased] – Help Cog Refactor

### Changed

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

### Removed

- Inline `HelpView` class definition from cog file — now imported from `views.help_view`.
- Inline button logic from cog — now encapsulated in the view module.

### Fixed

- Avoids ephemeral message timeout when processing many commands.
- Properly handles cases with no commands available, returning a friendly message instead of an empty embed list.
