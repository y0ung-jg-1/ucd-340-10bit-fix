# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

UCD-340 色彩分析仪 (Color Analyzer) - A tool to extract the most frequently occurring RGB color from UCD-exported bin files. Supports both 10-bit (0-1023) and 8-bit (0-255) color modes.

## Commands

### Run GUI application
```bash
python extract_top_colors_gui.py
```

### Run CLI version
```bash
python extract_top_colors.py <bin_directory> [output_csv_path]
```

### Build standalone executable
```bash
pip install pyinstaller numpy
pyinstaller --onefile --noconsole --name "10bit_RGB_Extractor" extract_top_colors_gui.py
```

### Create macOS DMG installer
```bash
mkdir -p dist/dmg_temp && cp -r dist/10bit_RGB_Extractor.app dist/dmg_temp/ && ln -s /Applications dist/dmg_temp/Applications
hdiutil create -volname "10bit_RGB_Extractor" -srcfolder dist/dmg_temp -ov -format UDZO dist/10bit_RGB_Extractor.dmg
rm -rf dist/dmg_temp
```

## Architecture

Two entry points sharing the same color extraction logic:
- `extract_top_colors.py` - CLI version with `extract_top_color()` function and `batch_extract()` for processing
- `extract_top_colors_gui.py` - Tkinter GUI wrapping `ColorExtractor` class with threading for non-blocking UI

## BIN File Format

Each pixel is 4 bytes in BGR order:
```
[B_high_8][G_high_8][R_high_8][extra: xxBBGGRR]
```

- **10-bit mode**: `value = (high_8 << 2) | low_2_bits`
- **8-bit mode**: `value = high_8`

The extraction combines RGB into a single 32-bit value for efficient counting via `np.unique()`.

## Dependencies

- Python 3.x
- numpy
- tkinter (GUI only, included with Python)
