# UCD-340 色彩分析仪 10-bit RGB 导出器

从 UCD 导出的 bin 文件中批量提取出现最多的 RGB 颜色值。

## 功能特点

- 支持 **10-bit** (0-1023) 和 **8-bit** (0-255) 模式
- 批量处理 bin 文件，按序号排序
- 自动去重（可设置阈值，跳过与上一帧相同/相似的颜色）
- 输出 CSV 格式（R, G, B）
- GUI 界面，操作简单

## 文件说明

| 文件 | 说明 |
|------|------|
| `dist/10bit_RGB_Extractor.exe` | （可选）Windows 打包产物，需自行用 PyInstaller 生成 |
| `extract_top_colors_gui.py` | GUI 主程序源码 |
| `extract_top_colors.py` | 命令行版本源码 |
| `10bit_RGB_Extractor.spec` | PyInstaller 打包配置 |

## 使用方法

### GUI 版本

1. 运行源码：`python3 extract_top_colors_gui.py`（推荐开发/调试）
2. 或运行打包产物：`dist/10bit_RGB_Extractor.app`（macOS）/ `dist/10bit_RGB_Extractor.exe`（Windows，需自行打包）
3. 选择 BIN 文件夹
4. 选择位深度（10-bit 或 8-bit）
5. 点击"开始提取"

### 命令行版本

```bash
python3 extract_top_colors.py <bin文件目录> [输出csv路径] [--dedup-tolerance N] [--no-dedup] [--bit-depth 8|10]
```

## bin 文件格式

每像素 4 字节，BGR 顺序：

```
[B高8位][G高8位][R高8位][扩展位: xxBBGGRR]
```

- **10-bit 模式**: `值 = (高8位 << 2) | 低2位`
- **8-bit 模式**: `值 = 高8位`

## 依赖

- Python 3.x
- numpy

## 打包

### 安装打包工具

```bash
pip install pyinstaller numpy
```

### Windows 打包 (.exe)

```bash
pyinstaller --onefile --noconsole --name "10bit_RGB_Extractor" extract_top_colors_gui.py
```

生成文件：`dist/10bit_RGB_Extractor.exe`

### macOS 打包 (.app + .dmg)

> 注意：macOS 26 上系统自带的 Tk 8.5 会在启动时崩溃（`TkpInit` / `Tcl_Panic`）。
> 建议使用 Homebrew 的 Python（或 python.org 安装包）来打包，确保 Tk 版本为 8.6+/9.0。

```bash
# 建议使用 Homebrew Python（示例路径：/opt/homebrew/bin/python3）
/opt/homebrew/bin/python3 -m venv .venv
source .venv/bin/activate
python -m pip install pyinstaller numpy

# 打包 .app
pyinstaller 10bit_RGB_Extractor.spec
或者
pyinstaller --onefile --noconsole --name "10bit_RGB_Extractor" extract_top_colors_gui.py

# 创建 DMG 安装包（含 Applications 快捷方式）
mkdir -p dist/dmg_temp
cp -r dist/10bit_RGB_Extractor.app dist/dmg_temp/
ln -s /Applications dist/dmg_temp/Applications
hdiutil create -volname "10bit_RGB_Extractor" -srcfolder dist/dmg_temp -ov -format UDZO dist/10bit_RGB_Extractor.dmg
rm -rf dist/dmg_temp
```

生成文件：`dist/10bit_RGB_Extractor.dmg`
