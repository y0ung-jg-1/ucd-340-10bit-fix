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

    def __init__(self):
        super().__init__()
        self.title("10-bit RGB颜色提取工具")
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
        self.bin_dir_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.width_var = tk.StringVar(value="1280")
        self.height_var = tk.StringVar(value="720")
        self.bit_depth_var = tk.IntVar(value=10)
        self.dedup_var = tk.BooleanVar(value=True)
        self.dedup_tolerance_var = tk.StringVar(value="0")
        self.progress_var = tk.DoubleVar(value=0)
        self.status_var = tk.StringVar(value="就绪")

    def _setup_layout(self):
        """布局管理"""
        # 文件选择区
        file_frame = ttk.LabelFrame(self, text="文件选择", padding=10)
        file_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(file_frame, text="BIN文件夹:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(file_frame, textvariable=self.bin_dir_var, width=45).grid(row=0, column=1, padx=5)
        ttk.Button(file_frame, text="浏览...", command=self._browse_bin_dir).grid(row=0, column=2)

        ttk.Label(file_frame, text="输出文件夹:").grid(row=1, column=0, sticky=tk.W, pady=(5,0))
        ttk.Entry(file_frame, textvariable=self.output_dir_var, width=45).grid(row=1, column=1, padx=5, pady=(5,0))
        ttk.Button(file_frame, text="浏览...", command=self._browse_output_dir).grid(row=1, column=2, pady=(5,0))

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

        ttk.Label(param_frame, text="去重阈值:").grid(row=3, column=0, sticky=tk.W, pady=(5,0))
        self.dedup_tolerance_entry = ttk.Entry(param_frame, textvariable=self.dedup_tolerance_var, width=10)
        self.dedup_tolerance_entry.grid(row=3, column=1, padx=5, sticky=tk.W, pady=(5,0))
        ttk.Label(param_frame, text="(每通道允许差值，0=完全相同)").grid(
            row=3, column=2, columnspan=2, sticky=tk.W, pady=(5,0)
        )

        self._update_dedup_controls()

        # 操作按钮区
        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill=tk.X, padx=10)

        self.start_btn = ttk.Button(btn_frame, text="开始提取", command=self._start_process)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = ttk.Button(btn_frame, text="停止", command=self._stop_process, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

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

        try:
            tol = int(self.dedup_tolerance_var.get() or "0")
            if tol < 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("错误", "请输入有效的去重阈值(非负整数)")
            return False
        return True

    def _update_dedup_controls(self):
        state = tk.NORMAL if self.dedup_var.get() else tk.DISABLED
        self.dedup_tolerance_entry.configure(state=state)

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
        """后台处理任务"""
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
            bin_dir,
            csv_path,
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
