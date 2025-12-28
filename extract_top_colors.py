from collections import Counter
import os
import glob
import re
import csv
import numpy as np


def extract_top_color(bin_file, width=1280, height=720, bit_depth=10):
    """
    从BGR bin文件中提取出现最多的颜色
    格式: [B高8位][G高8位][R高8位][扩展位: xxBBGGRR]
    bit_depth: 10 或 8
    返回: (R, G, B)
    """
    data = np.fromfile(bin_file, dtype=np.uint8)
    data = data.reshape(-1, 4)

    b8 = data[:, 0].astype(np.uint16)
    g8 = data[:, 1].astype(np.uint16)
    r8 = data[:, 2].astype(np.uint16)
    extra = data[:, 3]

    if bit_depth == 10:
        r = (r8 << 2) | (extra & 0x3)
        g = (g8 << 2) | ((extra >> 2) & 0x3)
        b = (b8 << 2) | ((extra >> 4) & 0x3)
        mask = 0x3FF
    else:  # 8bit
        r = r8
        g = g8
        b = b8
        mask = 0xFF

    # 合并为单个值便于统计
    rgb_combined = (r.astype(np.uint32) << 20) | (g.astype(np.uint32) << 10) | b
    values, counts = np.unique(rgb_combined, return_counts=True)
    top_idx = np.argmax(counts)
    top_val = values[top_idx]

    r_out = (top_val >> 20) & mask
    g_out = (top_val >> 10) & mask
    b_out = top_val & mask
    return (int(r_out), int(g_out), int(b_out))


def get_file_index(filename):
    """从文件名提取序号，如 ucd_video_00235_xxx.bin -> 235"""
    match = re.search(r'ucd_video_(\d+)_', filename)
    if match:
        return int(match.group(1))
    return -1


def batch_extract(input_dir, output_csv):
    """
    批量提取bin文件中出现最多的颜色，写入CSV
    跳过与前一张相同的图片
    """
    bin_files = glob.glob(os.path.join(input_dir, "*.bin"))
    bin_files = sorted(bin_files, key=lambda f: get_file_index(os.path.basename(f)))

    print(f"找到 {len(bin_files)} 个bin文件")

    results = []
    prev_color = None
    skipped = 0

    for i, bin_file in enumerate(bin_files):
        filename = os.path.basename(bin_file)
        color = extract_top_color(bin_file)

        if color == prev_color:
            skipped += 1
            continue

        results.append(color)
        prev_color = color
        print(f"[{i+1}/{len(bin_files)}] {filename} -> R={color[0]}, G={color[1]}, B={color[2]}")

    print(f"\n完成! 提取 {len(results)} 个颜色, 跳过 {skipped} 个重复帧")

    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['R', 'G', 'B'])
        for r, g, b in results:
            writer.writerow([r, g, b])

    print(f"已保存到: {output_csv}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2:
        input_dir = sys.argv[1]
        output_csv = sys.argv[2] if len(sys.argv) >= 3 else os.path.join(input_dir, "output.csv")
        batch_extract(input_dir, output_csv)
    else:
        print("用法: python extract_top_colors.py <bin文件目录> [输出csv路径]")
