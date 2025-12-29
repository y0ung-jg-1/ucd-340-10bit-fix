from collections import Counter
import os
import glob
import re
import csv
import argparse


def extract_top_color(bin_file, width=1280, height=720, bit_depth=10):
    """
    从BGR bin文件中提取出现最多的颜色
    格式: [B高8位][G高8位][R高8位][扩展位: xxBBGGRR]
    bit_depth: 10 或 8
    返回: (R, G, B)
    """
    import numpy as np

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


def colors_similar(color, prev_color, tolerance):
    if prev_color is None:
        return False
    if tolerance <= 0:
        return color == prev_color
    return all(abs(c - p) <= tolerance for c, p in zip(color, prev_color))


def batch_extract(input_dir, output_csv, bit_depth=10, enable_dedup=True, dedup_tolerance=0):
    """
    批量提取bin文件中出现最多的颜色，写入CSV
    去重：当每通道与上一帧差值均 <= dedup_tolerance 时视为同一帧
    """
    bin_files = glob.glob(os.path.join(input_dir, "*.bin"))
    bin_files = sorted(bin_files, key=lambda f: get_file_index(os.path.basename(f)))

    print(f"找到 {len(bin_files)} 个bin文件")

    results = []
    prev_color = None
    skipped = 0

    for i, bin_file in enumerate(bin_files):
        filename = os.path.basename(bin_file)
        color = extract_top_color(bin_file, bit_depth=bit_depth)

        if enable_dedup and colors_similar(color, prev_color, dedup_tolerance):
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
    parser = argparse.ArgumentParser(
        description="从 UCD 导出的 bin 文件中批量提取出现最多的 RGB 颜色值，并输出 CSV。"
    )
    parser.add_argument("input_dir", help="bin 文件目录")
    parser.add_argument("output_csv", nargs="?", help="输出 CSV 路径（默认：<bin目录>/output.csv）")
    parser.add_argument("--bit-depth", type=int, choices=[8, 10], default=10, help="位深度（默认：10）")
    parser.add_argument("--no-dedup", action="store_true", help="关闭去重")
    parser.add_argument(
        "--dedup-tolerance",
        type=int,
        default=0,
        help="去重阈值：每通道与上一帧差值 <= N 视为同一帧（默认：0，完全相同）",
    )

    args = parser.parse_args()
    if args.dedup_tolerance < 0:
        parser.error("--dedup-tolerance 必须为非负整数")

    output_csv = args.output_csv or os.path.join(args.input_dir, "output.csv")
    batch_extract(
        args.input_dir,
        output_csv,
        bit_depth=args.bit_depth,
        enable_dedup=not args.no_dedup,
        dedup_tolerance=args.dedup_tolerance,
    )
