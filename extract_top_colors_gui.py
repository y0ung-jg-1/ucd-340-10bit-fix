#!/usr/bin/env python3
"""
10-bit RGB颜色提取工具 - GUI版本
从bin文件批量提取出现最多的10-bit RGB颜色值
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import queue
import os
import glob
import re
import csv
import shutil
import subprocess
from datetime import datetime

import numpy as np


class ColorExtractor:
    """10-bit RGB颜色提取器"""

    def __init__(self, width=1280, height=720):
        self.width = width
        self.height = height

    def extract_top_color(self, bin_file, bit_depth=10):
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

        rgb_combined = (r.astype(np.uint32) << 20) | (g.astype(np.uint32) << 10) | b
        values, counts = np.unique(rgb_combined, return_counts=True)
        top_idx = np.argmax(counts)
        top_val = values[top_idx]

        r_out = (top_val >> 20) & mask
        g_out = (top_val >> 10) & mask
        b_out = top_val & mask
        return (int(r_out), int(g_out), int(b_out))

    def get_file_index(self, filename):
        """从文件名提取序号"""
        match = re.search(r'ucd_video_(\d+)_', filename)
        if match:
            return int(match.group(1))
        return -1

    def colors_similar(self, color, prev_color, tolerance):
        if prev_color is None:
            return False
        if tolerance <= 0:
            return color == prev_color
        return all(abs(c - p) <= tolerance for c, p in zip(color, prev_color))

    def decode_bin_to_rgb_array(self, bin_file, bit_depth=10):
        """
        将BIN文件解码为RGB图像数组
        返回: numpy array, shape (height, width, 3), dtype uint16(10-bit) 或 uint8(8-bit)
        """
        expected_size = self.width * self.height * 4
        file_size = os.path.getsize(bin_file)
        if file_size != expected_size:
            raise ValueError(
                f"文件大小不匹配: 期望 {expected_size} 字节 ({self.width}x{self.height}x4), "
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

        return rgb.reshape(self.height, self.width, 3)

    def export_bin_to_tiff(self, bin_file, output_path, bit_depth=10):
        """将单个BIN文件导出为TIFF图像"""
        rgb_array = self.decode_bin_to_rgb_array(bin_file, bit_depth)

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

    def batch_export_tiff(self, input_dir, output_dir, bit_depth=10,
                          progress_callback=None, stop_flag=None):
        """批量将BIN文件导出为TIFF图像"""
        bin_files = glob.glob(os.path.join(input_dir, "*.bin"))
        bin_files = sorted(bin_files, key=lambda f: self.get_file_index(os.path.basename(f)))

        total = len(bin_files)
        if total == 0:
            return 0, "未找到bin文件"

        os.makedirs(output_dir, exist_ok=True)
        exported = 0

        for i, bin_file in enumerate(bin_files):
            if stop_flag and stop_flag():
                return exported, "已停止"

            filename = os.path.basename(bin_file)
            stem = os.path.splitext(filename)[0]
            output_path = os.path.join(output_dir, f"{stem}.tiff")

            self.export_bin_to_tiff(bin_file, output_path, bit_depth)
            exported += 1

            if progress_callback:
                progress_callback(i + 1, total, f"{filename} -> {stem}.tiff")

        return exported, "完成"

    def _decode_bin_raw_frame(self, bin_file, bit_depth=10):
        """
        将BIN文件解码为原始帧字节，供FFmpeg stdin消费
        10-bit: rgb48le格式 (每通道16-bit, 值左移6位)
        8-bit: rgb24格式
        """
        expected_size = self.width * self.height * 4
        file_size = os.path.getsize(bin_file)
        if file_size != expected_size:
            raise ValueError(
                f"文件大小不匹配: 期望 {expected_size} 字节 ({self.width}x{self.height}x4), "
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
            r = (r << 6).astype(np.uint16)
            g = (g << 6).astype(np.uint16)
            b = (b << 6).astype(np.uint16)
            rgb = np.stack([r, g, b], axis=1).reshape(self.height, self.width, 3)
            return rgb.tobytes()
        else:
            r = r8.astype(np.uint8)
            g = g8.astype(np.uint8)
            b = b8.astype(np.uint8)
            rgb = np.stack([r, g, b], axis=1).reshape(self.height, self.width, 3)
            return rgb.tobytes()

    def export_bin_to_video(self, input_dir, output_path, bit_depth=10, fps=30,
                            color_space='sdr', progress_callback=None, stop_flag=None):
        """将BIN文件序列合成为视频"""
        if not shutil.which('ffmpeg'):
            raise RuntimeError(
                "未找到FFmpeg，请安装FFmpeg并确保其在系统PATH中。\n"
                "下载地址: https://ffmpeg.org/download.html"
            )

        bin_files = glob.glob(os.path.join(input_dir, "*.bin"))
        bin_files = sorted(bin_files, key=lambda f: self.get_file_index(os.path.basename(f)))

        total = len(bin_files)
        if total == 0:
            return 0, "未找到bin文件"

        if bit_depth == 10:
            cmd = [
                'ffmpeg', '-y',
                '-f', 'rawvideo', '-pix_fmt', 'rgb48le',
                '-s', f'{self.width}x{self.height}',
                '-r', str(fps), '-i', '-',
                '-c:v', 'libx265', '-pix_fmt', 'yuv420p10le',
                '-crf', '18', '-tag:v', 'hvc1',
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
            cmd = [
                'ffmpeg', '-y',
                '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                '-s', f'{self.width}x{self.height}',
                '-r', str(fps), '-i', '-',
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
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

        encoded = 0
        try:
            for i, bin_file in enumerate(bin_files):
                if stop_flag and stop_flag():
                    proc.stdin.close()
                    proc.terminate()
                    proc.wait()
                    stderr_thread.join(timeout=2)
                    return encoded, "已停止"

                filename = os.path.basename(bin_file)
                frame_data = self._decode_bin_raw_frame(bin_file, bit_depth)
                proc.stdin.write(frame_data)
                encoded += 1

                if progress_callback:
                    progress_callback(i + 1, total, f"编码帧: {filename}")

            proc.stdin.close()
            proc.wait()
            stderr_thread.join()

            if proc.returncode != 0:
                stderr_output = b''.join(stderr_chunks).decode('utf-8', errors='replace')
                raise RuntimeError(f"FFmpeg编码失败 (返回码 {proc.returncode}):\n{stderr_output}")

            return encoded, "完成"
        except BrokenPipeError:
            proc.wait()
            stderr_thread.join()
            stderr_output = b''.join(stderr_chunks).decode('utf-8', errors='replace')
            raise RuntimeError(f"FFmpeg进程异常退出:\n{stderr_output}")
        finally:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
            if proc.poll() is None:
                proc.terminate()
            proc.wait()

    def batch_extract(self, input_dir, output_csv, enable_dedup=True,
                      dedup_tolerance=0, bit_depth=10, progress_callback=None, stop_flag=None):
        """批量提取颜色并输出CSV"""
        bin_files = glob.glob(os.path.join(input_dir, "*.bin"))
        bin_files = sorted(bin_files, key=lambda f: self.get_file_index(os.path.basename(f)))

        total = len(bin_files)
        if total == 0:
            return 0, 0, "未找到bin文件"

        results = []
        prev_color = None
        skipped = 0

        for i, bin_file in enumerate(bin_files):
            if stop_flag and stop_flag():
                return len(results), skipped, "已停止"

            filename = os.path.basename(bin_file)
            color = self.extract_top_color(bin_file, bit_depth)

            if enable_dedup and self.colors_similar(color, prev_color, dedup_tolerance):
                skipped += 1
                if progress_callback:
                    if dedup_tolerance > 0:
                        progress_callback(i + 1, total, f"{filename}: 跳过(相似, 阈值={dedup_tolerance})")
                    else:
                        progress_callback(i + 1, total, f"{filename}: 跳过(重复)")
            else:
                results.append(color)
                prev_color = color
                if progress_callback:
                    r, g, b = color
                    progress_callback(i + 1, total, f"{filename}: R={r}, G={g}, B={b}")

        with open(output_csv, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['R', 'G', 'B'])
            for r, g, b in results:
                writer.writerow([r, g, b])

        return len(results), skipped, "完成"


class Application(tk.Tk):
    """主应用程序窗口"""
    VERSION = "1.3.0"

    def __init__(self):
        super().__init__()
        self.title(f"10-bit RGB颜色提取工具 v{self.VERSION}")
        self.geometry("800x700")
        self.resizable(True, True)

        self.is_processing = False
        self.stop_flag = False
        self.message_queue = queue.Queue()

        self._create_widgets()
        self._setup_layout()
        self._poll_messages()

    def _create_widgets(self):
        """创建所有控件"""
        self.mode_var = tk.StringVar(value="extract")
        self.bin_dir_var = tk.StringVar()
        self.bin_file_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.width_var = tk.StringVar(value="1280")
        self.height_var = tk.StringVar(value="720")
        self.bit_depth_var = tk.IntVar(value=10)
        self.dedup_var = tk.BooleanVar(value=True)
        self.dedup_tolerance_var = tk.StringVar(value="0")
        self.fps_var = tk.StringVar(value="30")
        self.color_space_var = tk.StringVar(value="sdr")
        self.progress_var = tk.DoubleVar(value=0)
        self.status_var = tk.StringVar(value="就绪")

    def _setup_layout(self):
        """布局管理"""
        # 操作模式选择区
        mode_frame = ttk.LabelFrame(self, text="操作模式", padding=10)
        mode_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Radiobutton(
            mode_frame, text="提取颜色 CSV", variable=self.mode_var,
            value="extract", command=self._update_mode_controls
        ).pack(side=tk.LEFT, padx=(0, 20))
        ttk.Radiobutton(
            mode_frame, text="导出TIFF图像", variable=self.mode_var,
            value="tiff", command=self._update_mode_controls
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            mode_frame, text="导出10-bit视频", variable=self.mode_var,
            value="video", command=self._update_mode_controls
        ).pack(side=tk.LEFT, padx=(20, 0))

        # 文件选择区
        file_frame = ttk.LabelFrame(self, text="文件选择", padding=10)
        file_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(file_frame, text="BIN文件夹:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(file_frame, textvariable=self.bin_dir_var, width=45).grid(row=0, column=1, padx=5)
        ttk.Button(file_frame, text="选择文件夹...", command=self._browse_bin_dir).grid(row=0, column=2)

        self.bin_file_label = ttk.Label(file_frame, text="BIN文件:")
        self.bin_file_label.grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        self.bin_file_entry = ttk.Entry(file_frame, textvariable=self.bin_file_var, width=45)
        self.bin_file_entry.grid(row=1, column=1, padx=5, pady=(5, 0))
        self.bin_file_btn = ttk.Button(file_frame, text="选择文件...", command=self._browse_bin_file)
        self.bin_file_btn.grid(row=1, column=2, pady=(5, 0))

        ttk.Label(file_frame, text="输出文件夹:").grid(row=2, column=0, sticky=tk.W, pady=(5,0))
        ttk.Entry(file_frame, textvariable=self.output_dir_var, width=45).grid(row=2, column=1, padx=5, pady=(5,0))
        ttk.Button(file_frame, text="选择文件夹...", command=self._browse_output_dir).grid(row=2, column=2, pady=(5,0))

        # 参数配置区
        param_frame = ttk.LabelFrame(self, text="参数配置", padding=10)
        param_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(param_frame, text="图像宽度:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(param_frame, textvariable=self.width_var, width=10).grid(row=0, column=1, padx=5)
        ttk.Label(param_frame, text="图像高度:").grid(row=0, column=2, padx=(20,0))
        ttk.Entry(param_frame, textvariable=self.height_var, width=10).grid(row=0, column=3, padx=5)

        ttk.Label(param_frame, text="位深度:").grid(row=1, column=0, sticky=tk.W, pady=(5,0))
        ttk.Radiobutton(param_frame, text="10-bit (0-1023)", variable=self.bit_depth_var, value=10).grid(row=1, column=1, sticky=tk.W, pady=(5,0))
        ttk.Radiobutton(param_frame, text="8-bit (0-255)", variable=self.bit_depth_var, value=8).grid(row=1, column=2, columnspan=2, sticky=tk.W, pady=(5,0))

        self.dedup_check = ttk.Checkbutton(
            param_frame,
            text="启用去重(跳过相同/相似颜色)",
            variable=self.dedup_var,
            command=self._update_dedup_controls,
        )
        self.dedup_check.grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=(5,0))

        self.dedup_tolerance_label = ttk.Label(param_frame, text="去重阈值:")
        self.dedup_tolerance_label.grid(row=3, column=0, sticky=tk.W, pady=(5,0))
        self.dedup_tolerance_entry = ttk.Entry(param_frame, textvariable=self.dedup_tolerance_var, width=10)
        self.dedup_tolerance_entry.grid(row=3, column=1, padx=5, sticky=tk.W, pady=(5,0))
        self.dedup_tolerance_hint = ttk.Label(param_frame, text="(每通道允许差值，0=完全相同)")
        self.dedup_tolerance_hint.grid(row=3, column=2, columnspan=2, sticky=tk.W, pady=(5,0))

        self.fps_label = ttk.Label(param_frame, text="视频帧率:")
        self.fps_label.grid(row=4, column=0, sticky=tk.W, pady=(5,0))
        self.fps_entry = ttk.Entry(param_frame, textvariable=self.fps_var, width=10)
        self.fps_entry.grid(row=4, column=1, padx=5, sticky=tk.W, pady=(5,0))
        self.fps_hint = ttk.Label(param_frame, text="(fps, 默认30)")
        self.fps_hint.grid(row=4, column=2, columnspan=2, sticky=tk.W, pady=(5,0))

        self.color_space_label = ttk.Label(param_frame, text="色彩空间:")
        self.color_space_label.grid(row=5, column=0, sticky=tk.W, pady=(5,0))
        self.color_space_sdr = ttk.Radiobutton(
            param_frame, text="SDR (Rec.709)", variable=self.color_space_var, value="sdr")
        self.color_space_sdr.grid(row=5, column=1, sticky=tk.W, pady=(5,0))
        self.color_space_hdr = ttk.Radiobutton(
            param_frame, text="HDR (Rec.2020 PQ)", variable=self.color_space_var, value="hdr")
        self.color_space_hdr.grid(row=5, column=2, columnspan=2, sticky=tk.W, pady=(5,0))

        # 操作按钮区
        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill=tk.X, padx=10)

        self.start_btn = ttk.Button(btn_frame, text="开始提取", command=self._start_process)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = ttk.Button(btn_frame, text="停止", command=self._stop_process, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        self._update_mode_controls()

        # 进度显示区
        progress_frame = ttk.LabelFrame(self, text="进度", padding=10)
        progress_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(progress_frame, textvariable=self.status_var).pack(anchor=tk.W)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=5)

        # 日志区
        log_frame = ttk.LabelFrame(self, text="日志", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.log_text = tk.Text(log_frame, height=10, state=tk.DISABLED)
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _browse_bin_dir(self):
        """选择BIN文件夹"""
        path = filedialog.askdirectory(title="选择BIN文件夹")
        if path:
            self.bin_dir_var.set(path)
            if not self.output_dir_var.get():
                self.output_dir_var.set(path)

    def _browse_bin_file(self):
        """选择单个BIN文件"""
        path = filedialog.askopenfilename(
            title="选择BIN文件",
            filetypes=[("BIN文件", "*.bin"), ("所有文件", "*.*")]
        )
        if path:
            self.bin_file_var.set(path)
            if not self.output_dir_var.get():
                self.output_dir_var.set(os.path.dirname(path))

    def _browse_output_dir(self):
        """选择输出文件夹"""
        path = filedialog.askdirectory(title="选择输出文件夹")
        if path:
            self.output_dir_var.set(path)

    def _log(self, message):
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _validate_inputs(self):
        """验证输入"""
        mode = self.mode_var.get()

        if mode == "tiff":
            has_file = self.bin_file_var.get() and os.path.isfile(self.bin_file_var.get())
            has_dir = self.bin_dir_var.get() and os.path.isdir(self.bin_dir_var.get())
            if not has_file and not has_dir:
                messagebox.showerror("错误", "请选择BIN文件或文件夹")
                return False
        else:
            if not self.bin_dir_var.get():
                messagebox.showerror("错误", "请选择BIN文件夹")
                return False
            if not os.path.isdir(self.bin_dir_var.get()):
                messagebox.showerror("错误", "BIN文件夹不存在")
                return False

        try:
            w = int(self.width_var.get())
            h = int(self.height_var.get())
            if w <= 0 or h <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("错误", "请输入有效的图像尺寸")
            return False

        if mode == "extract":
            try:
                tol = int(self.dedup_tolerance_var.get() or "0")
                if tol < 0:
                    raise ValueError()
            except ValueError:
                messagebox.showerror("错误", "请输入有效的去重阈值(非负整数)")
                return False

        if mode == "video":
            if not self.bin_dir_var.get() or not os.path.isdir(self.bin_dir_var.get()):
                messagebox.showerror("错误", "视频导出需要选择BIN文件夹")
                return False
            try:
                fps = int(self.fps_var.get())
                if fps <= 0:
                    raise ValueError()
            except ValueError:
                messagebox.showerror("错误", "请输入有效的帧率(正整数)")
                return False

        return True

    def _update_dedup_controls(self):
        mode = self.mode_var.get()
        if mode in ("tiff", "video"):
            return
        state = tk.NORMAL if self.dedup_var.get() else tk.DISABLED
        self.dedup_tolerance_entry.configure(state=state)

    def _update_mode_controls(self):
        """根据操作模式切换控件状态"""
        mode = self.mode_var.get()
        if mode == "tiff":
            self.bin_file_label.grid()
            self.bin_file_entry.grid()
            self.bin_file_btn.grid()
            self.dedup_check.configure(state=tk.DISABLED)
            self.dedup_tolerance_entry.configure(state=tk.DISABLED)
            self.dedup_tolerance_label.configure(state=tk.DISABLED)
            self.dedup_tolerance_hint.configure(state=tk.DISABLED)
            self.fps_label.grid_remove()
            self.fps_entry.grid_remove()
            self.fps_hint.grid_remove()
            self.color_space_label.grid_remove()
            self.color_space_sdr.grid_remove()
            self.color_space_hdr.grid_remove()
            self.start_btn.configure(text="开始导出")
        elif mode == "video":
            self.bin_file_label.grid_remove()
            self.bin_file_entry.grid_remove()
            self.bin_file_btn.grid_remove()
            self.dedup_check.configure(state=tk.DISABLED)
            self.dedup_tolerance_entry.configure(state=tk.DISABLED)
            self.dedup_tolerance_label.configure(state=tk.DISABLED)
            self.dedup_tolerance_hint.configure(state=tk.DISABLED)
            self.fps_label.grid()
            self.fps_entry.grid()
            self.fps_hint.grid()
            self.color_space_label.grid()
            self.color_space_sdr.grid()
            self.color_space_hdr.grid()
            self.start_btn.configure(text="开始导出")
        else:
            self.bin_file_label.grid_remove()
            self.bin_file_entry.grid_remove()
            self.bin_file_btn.grid_remove()
            self.dedup_check.configure(state=tk.NORMAL)
            self.dedup_tolerance_label.configure(state=tk.NORMAL)
            self.dedup_tolerance_hint.configure(state=tk.NORMAL)
            self._update_dedup_controls()
            self.fps_label.grid_remove()
            self.fps_entry.grid_remove()
            self.fps_hint.grid_remove()
            self.color_space_label.grid_remove()
            self.color_space_sdr.grid_remove()
            self.color_space_hdr.grid_remove()
            self.start_btn.configure(text="开始提取")

    def _start_process(self):
        """开始处理"""
        if not self._validate_inputs():
            return

        self.is_processing = True
        self.stop_flag = False
        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        self.progress_var.set(0)

        thread = threading.Thread(target=self._process_task, daemon=True)
        thread.start()

    def _stop_process(self):
        """停止处理"""
        self.stop_flag = True
        self.stop_btn.configure(state=tk.DISABLED)
        self._log("正在停止...")

    def _process_task(self):
        """后台处理任务 - 根据模式分发"""
        try:
            mode = self.mode_var.get()
            if mode == "tiff":
                self._process_tiff_export()
            elif mode == "video":
                self._process_video_export()
            else:
                self._process_color_extract()
        except ImportError as e:
            self.message_queue.put(("log", str(e)))
            self.message_queue.put(("complete", "错误: 缺少依赖库"))
        except RuntimeError as e:
            self.message_queue.put(("log", str(e)))
            self.message_queue.put(("complete", "错误: 导出失败"))
        except Exception as e:
            self.message_queue.put(("log", f"错误: {e}"))
            self.message_queue.put(("complete", "处理出错"))

    def _process_color_extract(self):
        """颜色提取处理"""
        bin_dir = self.bin_dir_var.get()
        output_dir = self.output_dir_var.get() or bin_dir
        folder_name = os.path.basename(bin_dir.rstrip('/\\'))
        csv_path = os.path.join(output_dir, f'{folder_name}.csv')

        width = int(self.width_var.get())
        height = int(self.height_var.get())
        bit_depth = self.bit_depth_var.get()
        enable_dedup = self.dedup_var.get()
        dedup_tolerance = int(self.dedup_tolerance_var.get() or "0")

        def stop_check():
            return self.stop_flag

        if enable_dedup and dedup_tolerance > 0:
            self.message_queue.put(("log", f"开始提取颜色 ({bit_depth}-bit模式，去重阈值={dedup_tolerance})..."))
        else:
            self.message_queue.put(("log", f"开始提取颜色 ({bit_depth}-bit模式)..."))
        self.message_queue.put(("status", "提取中..."))

        extractor = ColorExtractor(width, height)

        def progress_callback(current, total, msg):
            progress = (current / total) * 100
            self.message_queue.put(("progress", progress))
            self.message_queue.put(("log", msg))

        valid, skipped, status = extractor.batch_extract(
            bin_dir, csv_path,
            enable_dedup=enable_dedup,
            dedup_tolerance=dedup_tolerance,
            bit_depth=bit_depth,
            progress_callback=progress_callback,
            stop_flag=stop_check,
        )

        if self.stop_flag:
            self.message_queue.put(("complete", f"已停止，提取了{valid}个颜色"))
            return

        self.message_queue.put(("log", f"提取完成: 有效{valid}个, 跳过{skipped}个"))
        self.message_queue.put(("log", f"CSV已保存: {csv_path}"))
        self.message_queue.put(("complete", "处理完成!"))

    def _process_tiff_export(self):
        """TIFF导出处理"""
        width = int(self.width_var.get())
        height = int(self.height_var.get())
        bit_depth = self.bit_depth_var.get()
        extractor = ColorExtractor(width, height)

        bin_file = self.bin_file_var.get()
        bin_dir = self.bin_dir_var.get()
        output_dir = self.output_dir_var.get()

        def stop_check():
            return self.stop_flag

        def progress_callback(current, total, msg):
            progress = (current / total) * 100
            self.message_queue.put(("progress", progress))
            self.message_queue.put(("log", msg))

        # 单文件模式
        if bin_file and os.path.isfile(bin_file):
            out_dir = output_dir or os.path.dirname(bin_file)
            os.makedirs(out_dir, exist_ok=True)
            stem = os.path.splitext(os.path.basename(bin_file))[0]
            output_path = os.path.join(out_dir, f"{stem}.tiff")

            self.message_queue.put(("log", f"开始导出TIFF ({bit_depth}-bit模式)..."))
            self.message_queue.put(("status", "导出中..."))

            extractor.export_bin_to_tiff(bin_file, output_path, bit_depth)

            self.message_queue.put(("progress", 100))
            self.message_queue.put(("log", f"已导出: {output_path}"))
            self.message_queue.put(("complete", "导出完成!"))
            return

        # 批量模式
        if bin_dir and os.path.isdir(bin_dir):
            out_dir = output_dir or bin_dir
            self.message_queue.put(("log", f"开始批量导出TIFF ({bit_depth}-bit模式)..."))
            self.message_queue.put(("status", "导出中..."))

            exported, status = extractor.batch_export_tiff(
                bin_dir, out_dir, bit_depth=bit_depth,
                progress_callback=progress_callback,
                stop_flag=stop_check,
            )

            if self.stop_flag:
                self.message_queue.put(("complete", f"已停止，导出了{exported}个TIFF"))
                return

            self.message_queue.put(("log", f"导出完成: {exported}个TIFF文件"))
            self.message_queue.put(("log", f"输出目录: {out_dir}"))
            self.message_queue.put(("complete", "导出完成!"))

    def _process_video_export(self):
        """视频导出处理"""
        bin_dir = self.bin_dir_var.get()
        output_dir = self.output_dir_var.get() or bin_dir
        folder_name = os.path.basename(bin_dir.rstrip('/\\'))
        output_path = os.path.join(output_dir, f"{folder_name}.mp4")

        width = int(self.width_var.get())
        height = int(self.height_var.get())
        bit_depth = self.bit_depth_var.get()
        fps = int(self.fps_var.get())
        color_space = self.color_space_var.get()

        extractor = ColorExtractor(width, height)

        def stop_check():
            return self.stop_flag

        def progress_callback(current, total, msg):
            progress = (current / total) * 100
            self.message_queue.put(("progress", progress))
            self.message_queue.put(("log", msg))

        codec = "H.265" if bit_depth == 10 else "H.264"
        cs_label = "HDR Rec.2020 PQ" if color_space == "hdr" else "SDR Rec.709"
        self.message_queue.put(("log", f"开始导出视频 ({bit_depth}-bit, {codec}, {cs_label}, {fps}fps)..."))
        self.message_queue.put(("status", "导出中..."))

        os.makedirs(output_dir, exist_ok=True)

        encoded, status = extractor.export_bin_to_video(
            bin_dir, output_path, bit_depth=bit_depth, fps=fps,
            color_space=color_space,
            progress_callback=progress_callback,
            stop_flag=stop_check,
        )

        if self.stop_flag:
            self.message_queue.put(("complete", f"已停止，编码了{encoded}帧"))
            return

        self.message_queue.put(("log", f"导出完成: {encoded}帧"))
        self.message_queue.put(("log", f"视频已保存: {output_path}"))
        self.message_queue.put(("complete", "导出完成!"))

    def _poll_messages(self):
        """轮询消息队列更新UI"""
        try:
            while True:
                msg_type, msg_data = self.message_queue.get_nowait()
                if msg_type == "log":
                    self._log(msg_data)
                elif msg_type == "progress":
                    self.progress_var.set(msg_data)
                elif msg_type == "status":
                    self.status_var.set(msg_data)
                elif msg_type == "complete":
                    self._log(msg_data)
                    self.status_var.set(msg_data)
                    self.progress_var.set(100)
                    self.is_processing = False
                    self.start_btn.configure(state=tk.NORMAL)
                    self.stop_btn.configure(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.after(100, self._poll_messages)


if __name__ == "__main__":
    app = Application()
    app.mainloop()
