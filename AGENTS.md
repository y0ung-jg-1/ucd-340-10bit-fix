# Repository Guidelines

## Project Structure & Module Organization

- `extract_top_colors.py`: CLI entry point. Contains the core extraction logic (`extract_top_color`) and batch processing (`batch_extract`).
- `extract_top_colors_gui.py`: Tkinter GUI. Wraps the same extraction logic in `ColorExtractor` and runs work in a background thread to keep the UI responsive.
- `10bit_RGB_Extractor.spec`: PyInstaller config used for bundling (notably `numpy` hidden imports).
- Generated artifacts: `build/` and `dist/` (local builds/packaging outputs). Avoid editing by hand.

## Build, Test, and Development Commands

- Run GUI locally: `python3 extract_top_colors_gui.py`
- Run CLI locally: `python3 extract_top_colors.py <bin_dir> [output_csv]`
- Install runtime deps: `python3 -m pip install numpy`
- Build standalone app (PyInstaller): `python3 -m pip install pyinstaller numpy` then `pyinstaller --onefile --noconsole --name "10bit_RGB_Extractor" extract_top_colors_gui.py` (or `pyinstaller 10bit_RGB_Extractor.spec`).
- macOS DMG packaging: see `README.md` for the `hdiutil create ...` workflow.

## Coding Style & Naming Conventions

- Python: 4-space indentation; follow existing structure and keep functions small and single-purpose.
- Naming: `snake_case` for functions/variables, `PascalCase` for classes, and `_private_method` prefix for UI helpers.
- Prefer clear Chinese/English mixed user-facing strings consistent with current UI/README terminology.

## Testing Guidelines

- No automated test suite is currently set up.
- Before opening a PR, manually verify:
  - 10-bit and 8-bit modes produce expected ranges.
  - Dedup behavior (skipping consecutive identical colors) matches the UI option.
  - CSV output encoding opens correctly in Excel/Numbers (`utf-8-sig` is used in the GUI).

## Commit & Pull Request Guidelines

- Commits: history uses short, imperative subjects and occasional Conventional Commit prefixes. Prefer `feat:`, `fix:`, `docs:`, `chore:` where applicable.
- PRs: include a short description, how you verified it (commands run + OS), and screenshots for GUI changes.
- Do not commit sample BIN files or large build outputs unless explicitly intended for release.

