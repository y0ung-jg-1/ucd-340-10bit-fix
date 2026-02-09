# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

UCD-340 色彩分析仪 (Color Analyzer) v1.3.0 — Extracts the most frequently occurring RGB color from UCD-exported bin files, and exports full-pixel BIN data as TIFF images or H.265/H.264 video. Supports 10-bit (0-1023) and 8-bit (0-255) color modes with configurable deduplication tolerance.

## Commands

### Run GUI application
```bash
python extract_top_colors_gui.py
```

### Run CLI version (color extraction)
```bash
python extract_top_colors.py <bin_directory> [output_csv_path] [--bit-depth 8|10] [--no-dedup] [--dedup-tolerance N]
```

### Run CLI version (TIFF export)
```bash
python extract_top_colors.py <bin_file_or_directory> --export-tiff [--output-dir DIR] [--width W] [--height H] [--bit-depth 8|10]
```

### Run CLI version (video export)
```bash
python extract_top_colors.py <bin_directory> --export-video [--fps 30] [--color-space sdr|hdr] [--output-dir DIR] [--width W] [--height H] [--bit-depth 8|10]
```

### Build standalone executable
```bash
pip install pyinstaller numpy Pillow tifffile
pyinstaller --onefile --noconsole --name "10bit_RGB_Extractor" extract_top_colors_gui.py
```

### Create macOS DMG installer
```bash
mkdir -p dist/dmg_temp && cp -r dist/10bit_RGB_Extractor.app dist/dmg_temp/ && ln -s /Applications dist/dmg_temp/Applications
hdiutil create -volname "10bit_RGB_Extractor" -srcfolder dist/dmg_temp -ov -format UDZO dist/10bit_RGB_Extractor.dmg
rm -rf dist/dmg_temp
```

## Architecture

Two entry points share the same color extraction logic but implement it independently:

- **`extract_top_colors.py`** (CLI) — Standalone functions: `extract_top_color()` parses a single BIN file, `batch_extract()` processes a directory, `decode_bin_to_rgb_array()` / `export_bin_to_tiff()` / `batch_export_tiff()` handle TIFF export, `_decode_bin_raw_frame()` / `export_bin_to_video()` handle video export via FFmpeg pipe. Uses `argparse` for CLI arguments. CSV output uses `utf-8` encoding.
- **`extract_top_colors_gui.py`** (GUI) — `ColorExtractor` class wraps the same extraction, TIFF export, and video export logic. `Application` class manages the Tkinter UI with mode selector (CSV extraction / TIFF export / video export), a background worker thread and a message queue for thread-safe UI updates. CSV output uses `utf-8-sig` encoding (BOM for Excel compatibility).

**Important:** The extraction logic is duplicated between the two files, not shared via import. Changes to parsing logic must be applied to both files.

## BIN File Format

Each pixel is 4 bytes in BGR order:
```
[B_high_8][G_high_8][R_high_8][extra: xxBBGGRR]
```

- **10-bit mode**: `value = (high_8 << 2) | low_2_bits` — range 0-1023
- **8-bit mode**: `value = high_8` — range 0-255

RGB values are combined into a single 32-bit integer `(r << 20) | (g << 10) | b` for efficient frequency counting via `np.unique()`.

## Deduplication

Files are sorted by sequence number extracted from filename pattern `ucd_video_XXXXX_*.bin`. Consecutive frames with identical or similar colors (within per-channel tolerance) are skipped. Tolerance of 0 means exact match only.

## Coding Conventions

- 4-space indentation, `snake_case` for functions/variables, `PascalCase` for classes, `_private_method` prefix for UI helpers.
- User-facing strings use Chinese/English mix consistent with existing UI.
- Commits use Conventional Commit prefixes: `feat:`, `fix:`, `docs:`, `chore:`.

## Testing

No automated test suite. Manually verify: 10-bit and 8-bit modes produce correct ranges, dedup behavior matches settings, CSV opens correctly in Excel/Numbers, TIFF export produces valid images (10-bit → 16-bit TIFF, 8-bit → 8-bit TIFF), video export produces valid mp4 (10-bit → H.265 yuv420p10le, 8-bit → H.264 yuv420p).

## Dependencies

- Python 3.x
- numpy
- tifffile (for 10-bit TIFF export; lazy-imported, existing features work without it)
- Pillow (for 8-bit TIFF export; lazy-imported, existing features work without it)
- tkinter (GUI only, included with Python)
- FFmpeg (external, required for video export; must be in system PATH)
- Note: macOS system Tk 8.5 crashes on launch; use Homebrew Python with Tk 8.6+/9.0 for macOS builds.
