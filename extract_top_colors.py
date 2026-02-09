import os
import glob
import re
import csv
import shutil
import subprocess
import threading
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


def decode_bin_to_rgb_array(bin_file, width=1280, height=720, bit_depth=10):
    """
    将BIN文件解码为RGB图像数组
    返回: numpy array, shape (height, width, 3), dtype uint16(10-bit) 或 uint8(8-bit)
    """
    import numpy as np

    expected_size = width * height * 4
    file_size = os.path.getsize(bin_file)
    if file_size != expected_size:
        raise ValueError(
            f"文件大小不匹配: 期望 {expected_size} 字节 ({width}x{height}x4), "
            f"实际 {file_size} 字节: {bin_file}"
        )

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
    else:  # 8bit
        r = r8
        g = g8
        b = b8

    if bit_depth == 10:
        # 缩放10-bit(0-1023)到16-bit满量程(0-65535)，否则图片查看器显示为纯黑
        r = (r.astype(np.uint32) * 65535 // 1023).astype(np.uint16)
        g = (g.astype(np.uint32) * 65535 // 1023).astype(np.uint16)
        b = (b.astype(np.uint32) * 65535 // 1023).astype(np.uint16)
        rgb = np.stack([r, g, b], axis=1)
    else:
        rgb = np.stack([r, g, b], axis=1).astype(np.uint8)

    return rgb.reshape(height, width, 3)


def _decode_bin_raw_frame(bin_file, width=1280, height=720, bit_depth=10):
    """
    将BIN文件解码为原始帧字节，供FFmpeg stdin消费
    10-bit: rgb48le格式 (每通道16-bit, 值左移6位)
    8-bit: rgb24格式
    返回: bytes
    """
    import numpy as np

    expected_size = width * height * 4
    file_size = os.path.getsize(bin_file)
    if file_size != expected_size:
        raise ValueError(
            f"文件大小不匹配: 期望 {expected_size} 字节 ({width}x{height}x4), "
            f"实际 {file_size} 字节: {bin_file}"
        )

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
        # 左移6位填充到16-bit供FFmpeg rgb48le消费
        r = (r << 6).astype(np.uint16)
        g = (g << 6).astype(np.uint16)
        b = (b << 6).astype(np.uint16)
        rgb = np.stack([r, g, b], axis=1).reshape(height, width, 3)
        return rgb.tobytes()
    else:
        r = r8.astype(np.uint8)
        g = g8.astype(np.uint8)
        b = b8.astype(np.uint8)
        rgb = np.stack([r, g, b], axis=1).reshape(height, width, 3)
        return rgb.tobytes()


def export_bin_to_tiff(bin_file, output_path, width=1280, height=720, bit_depth=10):
    """将单个BIN文件导出为TIFF图像"""
    rgb_array = decode_bin_to_rgb_array(bin_file, width, height, bit_depth)

    if bit_depth == 10:
        try:
            import tifffile
            tifffile.imwrite(output_path, rgb_array)
        except ImportError:
            raise ImportError(
                "导出10-bit TIFF需要安装tifffile库: pip install tifffile"
            )
    else:
        try:
            from PIL import Image
        except ImportError:
            raise ImportError("导出TIFF需要安装Pillow库: pip install Pillow")
        img = Image.fromarray(rgb_array)
        img.save(output_path, format='TIFF')


def batch_export_tiff(input_dir, output_dir, width=1280, height=720, bit_depth=10):
    """批量将BIN文件导出为TIFF图像"""
    bin_files = glob.glob(os.path.join(input_dir, "*.bin"))
    bin_files = sorted(bin_files, key=lambda f: get_file_index(os.path.basename(f)))

    print(f"找到 {len(bin_files)} 个bin文件")
    if not bin_files:
        return

    os.makedirs(output_dir, exist_ok=True)

    for i, bin_file in enumerate(bin_files):
        filename = os.path.basename(bin_file)
        stem = os.path.splitext(filename)[0]
        output_path = os.path.join(output_dir, f"{stem}.tiff")
        export_bin_to_tiff(bin_file, output_path, width, height, bit_depth)
        print(f"[{i+1}/{len(bin_files)}] {filename} -> {stem}.tiff")

    print(f"\n完成! 导出 {len(bin_files)} 个TIFF文件到: {output_dir}")


def export_bin_to_video(input_dir, output_path, width=1280, height=720,
                        bit_depth=10, fps=30, color_space='sdr'):
    """
    将BIN文件序列合成为视频
    10-bit: H.265编码, yuv420p10le
    8-bit: H.264编码, yuv420p
    color_space: 'sdr' (Rec.709) 或 'hdr' (Rec.2020 PQ)
    """
    if not shutil.which('ffmpeg'):
        raise RuntimeError(
            "未找到FFmpeg，请安装FFmpeg并确保其在系统PATH中。\n"
            "下载地址: https://ffmpeg.org/download.html"
        )

    bin_files = glob.glob(os.path.join(input_dir, "*.bin"))
    bin_files = sorted(bin_files, key=lambda f: get_file_index(os.path.basename(f)))

    total = len(bin_files)
    if total == 0:
        print("未找到bin文件")
        return

    print(f"找到 {total} 个bin文件，开始合成视频...")

    if bit_depth == 10:
        pix_fmt_in = 'rgb48le'
        cmd = [
            'ffmpeg', '-y',
            '-f', 'rawvideo',
            '-pix_fmt', pix_fmt_in,
            '-s', f'{width}x{height}',
            '-r', str(fps),
            '-i', '-',
            '-c:v', 'libx265',
            '-pix_fmt', 'yuv420p10le',
            '-crf', '18',
            '-tag:v', 'hvc1',
        ]
        if color_space == 'hdr':
            cmd += [
                '-colorspace', 'bt2020nc',
                '-color_trc', 'smpte2084',
                '-color_primaries', 'bt2020',
                '-x265-params',
                'hdr-opt=1:repeat-headers=1:colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc',
            ]
        else:
            cmd += [
                '-colorspace', 'bt709',
                '-color_trc', 'bt709',
                '-color_primaries', 'bt709',
            ]
        cmd.append(output_path)
    else:
        pix_fmt_in = 'rgb24'
        cmd = [
            'ffmpeg', '-y',
            '-f', 'rawvideo',
            '-pix_fmt', pix_fmt_in,
            '-s', f'{width}x{height}',
            '-r', str(fps),
            '-i', '-',
            '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            '-crf', '18',
            '-colorspace', 'bt709',
            '-color_trc', 'bt709',
            '-color_primaries', 'bt709',
            output_path,
        ]

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    # 后台线程持续读取stderr，防止管道缓冲区满导致死锁
    stderr_chunks = []
    def _drain_stderr():
        for line in proc.stderr:
            stderr_chunks.append(line)
    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    try:
        for i, bin_file in enumerate(bin_files):
            filename = os.path.basename(bin_file)
            frame_data = _decode_bin_raw_frame(bin_file, width, height, bit_depth)
            proc.stdin.write(frame_data)
            print(f"[{i+1}/{total}] {filename}")

        proc.stdin.close()
        proc.wait()
        stderr_thread.join()

        if proc.returncode != 0:
            stderr_output = b''.join(stderr_chunks).decode('utf-8', errors='replace')
            raise RuntimeError(f"FFmpeg编码失败 (返回码 {proc.returncode}):\n{stderr_output}")

        print(f"\n完成! 视频已保存: {output_path}")
    except BrokenPipeError:
        proc.wait()
        stderr_thread.join()
        stderr_output = b''.join(stderr_chunks).decode('utf-8', errors='replace')
        raise RuntimeError(f"FFmpeg进程异常退出:\n{stderr_output}")
    finally:
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.close()
        proc.wait()


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
        description="从 UCD 导出的 bin 文件中批量提取出现最多的 RGB 颜色值 (v1.3.0)。支持图片一致性检测（去重阈值设置）、TIFF图像导出和视频合成。"
    )
    parser.add_argument("input", help="bin 文件或目录")
    parser.add_argument("output_csv", nargs="?", help="输出 CSV 路径（默认：<bin目录>/output.csv）")
    parser.add_argument("--bit-depth", type=int, choices=[8, 10], default=10, help="位深度（默认：10）")
    parser.add_argument("--no-dedup", action="store_true", help="关闭去重")
    parser.add_argument(
        "--dedup-tolerance",
        type=int,
        default=0,
        help="去重阈值：每通道与上一帧差值 <= N 视为同一帧（默认：0，完全相同）",
    )
    parser.add_argument("--export-tiff", action="store_true", help="导出TIFF图像模式（而非提取颜色CSV）")
    parser.add_argument("--export-video", action="store_true", help="导出视频模式（BIN序列合成为H.265/H.264视频）")
    parser.add_argument("--fps", type=int, default=30, help="视频帧率（默认：30）")
    parser.add_argument("--color-space", choices=['sdr', 'hdr'], default='sdr',
                        help="视频色彩空间: sdr=Rec.709, hdr=Rec.2020 PQ（默认：sdr）")
    parser.add_argument("--output-dir", help="导出输出目录（默认：与输入同目录）")
    parser.add_argument("--width", type=int, default=1280, help="图像宽度（默认：1280）")
    parser.add_argument("--height", type=int, default=720, help="图像高度（默认：720）")

    args = parser.parse_args()

    if args.export_video:
        input_dir = args.input
        if not os.path.isdir(input_dir):
            parser.error(f"视频导出模式需要目录作为输入: {input_dir}")
        if args.fps <= 0:
            parser.error("--fps 必须为正整数")
        folder_name = os.path.basename(input_dir.rstrip('/\\'))
        output_dir = args.output_dir or input_dir
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{folder_name}.mp4")
        export_bin_to_video(
            input_dir, output_path,
            width=args.width, height=args.height,
            bit_depth=args.bit_depth, fps=args.fps,
            color_space=args.color_space,
        )
    elif args.export_tiff:
        input_path = args.input
        if os.path.isfile(input_path):
            output_dir = args.output_dir or os.path.dirname(input_path)
            stem = os.path.splitext(os.path.basename(input_path))[0]
            output_path = os.path.join(output_dir, f"{stem}.tiff")
            os.makedirs(output_dir, exist_ok=True)
            export_bin_to_tiff(input_path, output_path, args.width, args.height, args.bit_depth)
            print(f"已导出: {output_path}")
        elif os.path.isdir(input_path):
            output_dir = args.output_dir or input_path
            batch_export_tiff(input_path, output_dir, args.width, args.height, args.bit_depth)
        else:
            parser.error(f"输入路径不存在: {input_path}")
    else:
        if args.dedup_tolerance < 0:
            parser.error("--dedup-tolerance 必须为非负整数")
        input_dir = args.input
        if not os.path.isdir(input_dir):
            parser.error(f"颜色提取模式需要目录作为输入: {input_dir}")
        output_csv = args.output_csv or os.path.join(input_dir, "output.csv")
        batch_extract(
            input_dir,
            output_csv,
            bit_depth=args.bit_depth,
            enable_dedup=not args.no_dedup,
            dedup_tolerance=args.dedup_tolerance,
        )
