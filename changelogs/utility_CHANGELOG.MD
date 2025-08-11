# Changelog

## [Unreleased] – Utility Cog Refactor

### Changed

- **Bug report modal extraction**:
  - `BugReportModal` class moved from `utility.py` into dedicated `views/bugreport_view.py` for better separation of concerns.
  - Updated `UtilityCog` to import `BugReportModal` from the new `views` module.
- **UI text formatting**:
  - Improved readability in modal `steps` field by splitting placeholder text into multiple lines.
- **Code style**:
  - Added `# pylint: disable=arguments-differ` to `on_submit` and `on_error` overrides to prevent linter warnings.
  - Reorganized imports for clarity and consistency.

### Removed

- Inline modal definition from `UtilityCog`.
- Redundant imports from `utility.py` (e.g., `ui`, `TextStyle`, `config`, `traceback`) now handled in the `views` module.

### Fixed

- None functionally, but code is now cleaner and easier to maintain.

### Notes

- This refactor improves modularity — the `views` directory now handles UI components separately from cog logic.
