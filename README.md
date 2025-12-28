# UCD-340 色彩分析仪 10-bit RGB 导出器

从 UCD 导出的 bin 文件中批量提取出现最多的 RGB 颜色值。

## 功能特点

- 支持 **10-bit** (0-1023) 和 **8-bit** (0-255) 模式
- 批量处理 bin 文件，按序号排序
- 自动去重（跳过与前一帧相同的颜色）
- 输出 CSV 格式（R, G, B）
- GUI 界面，操作简单

## 文件说明

| 文件 | 说明 |
|------|------|
| `10bit_RGB_Extractor.exe` | 打包好的 exe，可直接运行 |
| `extract_top_colors_gui.py` | GUI 主程序源码 |
| `extract_top_colors.py` | 命令行版本源码 |
| `10bit_RGB_Extractor.spec` | PyInstaller 打包配置 |

## 使用方法

### GUI 版本

1. 双击 `10bit_RGB_Extractor.exe` 运行
2. 选择 BIN 文件夹
3. 选择位深度（10-bit 或 8-bit）
4. 点击"开始提取"

### 命令行版本

```bash
python extract_top_colors.py <bin文件目录> [输出csv路径]
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

```bash
# 打包 .app
pyinstaller --onefile --noconsole --name "10bit_RGB_Extractor" extract_top_colors_gui.py

# 创建 DMG 安装包（含 Applications 快捷方式）
mkdir -p dist/dmg_temp
cp -r dist/10bit_RGB_Extractor.app dist/dmg_temp/
ln -s /Applications dist/dmg_temp/Applications
hdiutil create -volname "10bit_RGB_Extractor" -srcfolder dist/dmg_temp -ov -format UDZO dist/10bit_RGB_Extractor.dmg
rm -rf dist/dmg_temp
```

生成文件：`dist/10bit_RGB_Extractor.dmg`
