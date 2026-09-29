#!/usr/bin/env python3
"""
Video Converter (GUI) — Tkinter front-end for a bundled FFmpeg binary.

Folder layout expected:
    project/
      video_converter_gui.py
      bin/
        ffmpeg          (Linux/Mac)   or
        ffmpeg.exe      (Windows)

If ffmpeg isn't found in ./bin, the app falls back to "ffmpeg" on the
system PATH. Only standard library is used (tkinter, subprocess,
threading) — no extra pip installs needed.

Every option has a small "ⓘ" icon next to it — hover over it to see
what that ffmpeg flag does.

Run:
    python video_converter_gui.py
"""

import platform
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import sys

SCRIPT_DIR = Path(__file__).resolve().parent
APP_DIR = Path(getattr(sys, "_MEIPASS", SCRIPT_DIR))
BIN_DIR = APP_DIR / "bin"
ICON_PATH = APP_DIR / "ico2.ico"

VIDEO_CODECS = ["(copy/auto)", "libx264", "libx265", "libvpx-vp9", "mpeg4", "h264_nvenc", "h264_amf", "h264_qsv","mpeg1video","mpeg2video"]
AUDIO_CODECS = ["(copy/auto)", "aac", "mp3", "libopus", "flac", "ac3"]
PRESETS = ["(default)", "ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
CONTAINERS = ["mp4", "mkv", "mov", "webm", "avi", "gif", "mp3", "m4a", "wav", "mpeg", "mpg", "mpeg1"]
PIX_FMTS = ["(default)", "yuv420p", "yuv422p", "yuv444p", "rgb24", "gray"]

# "mpeg1" isn't a real file extension — it's a friendly label in the Container
# dropdown that always saves as .mpg and forces the mpeg1video codec below.
CONTAINER_EXT_MAP = {
    "mpeg1": "mpg",
}

# Text shown in the hover tooltip for each ffmpeg flag — matches the reference table.
FLAG_HELP = {
    "-i": "Input file — the source video/audio ffmpeg will read.",
    "-c:v": "Video codec — which encoder to use for the video stream (e.g. libx264, libx265).",
    "-c:a": "Audio codec — which encoder to use for the audio stream (e.g. aac, mp3).",
    "-vf": "Video filter — a custom filtergraph applied to the video stream (e.g. scale, crop, rotate).",
    "-af": "Audio filter — a custom filtergraph applied to the audio stream (e.g. volume, atempo).",
    "-b:v": "Video bitrate — target bitrate for the video stream, e.g. 2M, 800k.",
    "-b:a": "Audio bitrate — target bitrate for the audio stream, e.g. 192k.",
    "-q:v": "Video quality — quality level for quality-based codecs (lower is usually better, codec-dependent).",
    "-r": "Frame rate — output frames per second.",
    "-s": "Resolution — output frame size as WIDTHxHEIGHT, e.g. 1280x720.",
    "-aspect": "Aspect ratio — sets the display aspect ratio, e.g. 16:9 or 4:3.",
    "-pix_fmt": "Pixel format — the output color/pixel format, e.g. yuv420p for best compatibility.",
    "-map": "Select streams — explicitly choose which input streams to include, e.g. 0:v:0 0:a:1.",
    "-an": "Remove audio — drops the audio stream entirely from the output.",
    "-vn": "Remove video — drops the video stream entirely (useful for audio extraction).",
    "-sn": "Remove subtitles — drops any subtitle streams from the output.",
    "-threads": "Number of CPU threads ffmpeg is allowed to use for encoding.",
    "-ss": "Start time (seek) — where in the input to begin, e.g. 00:00:10.",
    "-to": "End time — absolute timestamp in the input to stop at, e.g. 00:00:40.",
    "-t": "Duration — how long the output should be, e.g. 00:00:30 (used instead of -to).",
    "-metadata": "Set metadata — tags written into the output file, as key=value pairs (comma-separated for several).",
    "-preset": "Encoding speed/efficiency tradeoff — supported by x264/x265 (ultrafast … veryslow).",
    "-crf": "Constant Rate Factor — quality target for x264/x265 (lower = better quality, larger file).",
    "-y": "Overwrite output file — replaces the output file if it already exists, without asking.",
    "-n": "Never overwrite — ffmpeg will refuse to run if the output file already exists.",
    "-shortest": "Stop when the shortest input stream ends (useful when mixing clips of different lengths).",
    "-movflags": "MP4-specific flags — e.g. faststart moves metadata to the front for web streaming.",
}


def find_ffmpeg() -> str:
    exe_name = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
    local_path = BIN_DIR / exe_name
    if local_path.is_file():
        return str(local_path)
    system_ffmpeg = shutil.which("ffmpeg")
    return system_ffmpeg or ""


_TIME_RE = re.compile(r"(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")
_PROGRESS_TIME_RE = re.compile(r"time=(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")
_PROGRESS_SIZE_RE = re.compile(r"size=\s*(\S+)")
_PROGRESS_SPEED_RE = re.compile(r"speed=\s*([\d.]+)x")


def _hms_to_seconds(h, m, s) -> float:
    return int(h) * 3600 + int(m) * 60 + float(s)


def seconds_to_hms(total_seconds: float) -> str:
    if total_seconds is None or total_seconds < 0:
        return "--:--:--"
    total_seconds = int(round(total_seconds))
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def probe_duration(ffmpeg_path: str, input_path: str) -> Optional[float]:
    """Runs ffmpeg -i <input> (no output) and scrapes 'Duration: HH:MM:SS.xx'
    from stderr. Returns seconds, or None if it can't be determined."""
    if not ffmpeg_path or not input_path:
        return None
    try:
        result = subprocess.run(
            [ffmpeg_path, "-i", input_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            timeout=15,
        )
        output = result.stdout or ""
    except Exception:
        return None

    match = re.search(r"Duration:\s*" + _TIME_RE.pattern, output)
    if not match:
        return None
    return _hms_to_seconds(*match.groups())


class Tooltip:
    """Small hover tooltip attached to a widget (typically the ⓘ icon)."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _event=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 16
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self.tip, text=self.text, background="#ffffe0", foreground="#111",
            relief="solid", borderwidth=1, font=("Segoe UI", 9),
            justify="left", wraplength=320,
        )
        label.pack(ipadx=5, ipady=3)

    def hide(self, _event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class VideoConverterGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Video Converter")
        self.geometry("820x760")
        self.minsize(760, 640)
        self._set_app_icon()

        self.ffmpeg_path = find_ffmpeg()
        self.process = None
        self.worker_thread = None
        self._pending_preset_note = None

        self._build_ui()

    # ---------- window/taskbar icon ----------
    def _set_app_icon(self):
        """Sets the title-bar and taskbar icon from ico2.ico, if present."""
        if ICON_PATH.is_file():
            try:
                self.iconbitmap(str(ICON_PATH))
            except tk.TclError:
                pass  # e.g. running on Linux/Mac, where .ico isn't supported

    # ---------- small helper: label + widget + info icon ----------
    def _field(self, parent, row, col, flag, label_text, widget):
        """Places label at (row,col), widget at (row,col+1), ⓘ icon at (row,col+2)."""
        ttk.Label(parent, text=label_text).grid(row=row, column=col, sticky="w", padx=(0, 4), pady=3)
        widget.grid(row=row, column=col + 1, sticky="w", padx=(0, 4), pady=3)
        icon = ttk.Label(parent, text=" ⓘ", foreground="#3366cc", cursor="question_arrow")
        icon.grid(row=row, column=col + 2, sticky="w", padx=(0, 16), pady=3)
        Tooltip(icon, f"{flag}\n{FLAG_HELP.get(flag, '')}")
        return widget

    # ---------- UI ----------
    def _build_ui(self):
        pad = {"padx": 8, "pady": 5}

        # Input / output files
        io_frame = ttk.LabelFrame(self, text="Files")
        io_frame.pack(fill="x", **pad)

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.container_var = tk.StringVar(value="mp4")

        row1 = ttk.Frame(io_frame); row1.pack(fill="x", padx=6, pady=4)
        lbl = ttk.Label(row1, text="Input:", width=8); lbl.pack(side="left")
        ttk.Entry(row1, textvariable=self.input_var).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(row1, text="Browse…", command=self.browse_input).pack(side="left")
        icon = ttk.Label(row1, text="ⓘ", foreground="#3366cc", cursor="question_arrow"); icon.pack(side="left", padx=4)
        Tooltip(icon, f"-i\n{FLAG_HELP['-i']}")

        row2 = ttk.Frame(io_frame); row2.pack(fill="x", padx=6, pady=4)
        ttk.Label(row2, text="Output:", width=8).pack(side="left")
        ttk.Entry(row2, textvariable=self.output_var).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(row2, text="Save As…", command=self.browse_output).pack(side="left")

        row3 = ttk.Frame(io_frame); row3.pack(fill="x", padx=6, pady=4)
        ttk.Label(row3, text="Container:", width=8).pack(side="left")
        container_combo = ttk.Combobox(row3, textvariable=self.container_var, values=CONTAINERS, width=10,
                                        state="readonly")
        container_combo.pack(side="left", padx=4)
        container_combo.bind("<<ComboboxSelected>>", self._on_container_changed)
        ttk.Label(row3, text="(used to suggest the output extension)").pack(side="left", padx=6)

        # ---- Scrollable options area ----
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, padx=8, pady=(0, 5))

        canvas = tk.Canvas(outer, borderwidth=0, highlightthickness=0)
        vscroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        opts_container = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=opts_container, anchor="nw")

        def _on_configure(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        opts_container.bind("<Configure>", _on_configure)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)          # Windows/Mac
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))  # Linux
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

        # --- Video section ---
        vid_frame = ttk.LabelFrame(opts_container, text="Video")
        vid_frame.pack(fill="x", padx=2, pady=4)
        vg = ttk.Frame(vid_frame); vg.pack(fill="x", padx=6, pady=4)

        self.video_codec_var = tk.StringVar(value=VIDEO_CODECS[0])
        self._field(vg, 0, 0, "-c:v", "Video codec:", ttk.Combobox(vg, textvariable=self.video_codec_var,
                    values=VIDEO_CODECS, width=16, state="readonly"))

        self.preset_var = tk.StringVar(value=PRESETS[0])
        self._field(vg, 0, 3, "-preset", "Preset:", ttk.Combobox(vg, textvariable=self.preset_var,
                    values=PRESETS, width=14, state="readonly"))

        self.crf_var = tk.StringVar()
        self._field(vg, 1, 0, "-crf", "CRF (0-51):", ttk.Entry(vg, textvariable=self.crf_var, width=18))

        self.qv_var = tk.StringVar()
        self._field(vg, 1, 3, "-q:v", "Video quality (q:v):", ttk.Entry(vg, textvariable=self.qv_var, width=16))

        self.bitrate_var = tk.StringVar()
        self._field(vg, 2, 0, "-b:v", "Video bitrate:", ttk.Entry(vg, textvariable=self.bitrate_var, width=18))

        self.fps_var = tk.StringVar()
        self._field(vg, 2, 3, "-r", "Frame rate (fps):", ttk.Entry(vg, textvariable=self.fps_var, width=16))

        self.resolution_var = tk.StringVar()
        self._field(vg, 3, 0, "-s", "Resolution WxH:", ttk.Entry(vg, textvariable=self.resolution_var, width=18))

        self.aspect_var = tk.StringVar()
        self._field(vg, 3, 3, "-aspect", "Aspect ratio:", ttk.Entry(vg, textvariable=self.aspect_var, width=16))

        self.pix_fmt_var = tk.StringVar(value=PIX_FMTS[0])
        self._field(vg, 4, 0, "-pix_fmt", "Pixel format:", ttk.Combobox(vg, textvariable=self.pix_fmt_var,
                    values=PIX_FMTS, width=16, state="readonly"))

        self.vf_var = tk.StringVar()
        self._field(vg, 4, 3, "-vf", "Video filter:", ttk.Entry(vg, textvariable=self.vf_var, width=16))

        # --- Audio section ---
        aud_frame = ttk.LabelFrame(opts_container, text="Audio")
        aud_frame.pack(fill="x", padx=2, pady=4)
        ag = ttk.Frame(aud_frame); ag.pack(fill="x", padx=6, pady=4)

        self.audio_codec_var = tk.StringVar(value=AUDIO_CODECS[0])
        self._field(ag, 0, 0, "-c:a", "Audio codec:", ttk.Combobox(ag, textvariable=self.audio_codec_var,
                    values=AUDIO_CODECS, width=16, state="readonly"))

        self.audio_bitrate_var = tk.StringVar()
        self._field(ag, 0, 3, "-b:a", "Audio bitrate:", ttk.Entry(ag, textvariable=self.audio_bitrate_var, width=16))

        self.af_var = tk.StringVar()
        self._field(ag, 1, 0, "-af", "Audio filter:", ttk.Entry(ag, textvariable=self.af_var, width=18))

        # --- Streams / trimming section ---
        strm_frame = ttk.LabelFrame(opts_container, text="Streams & Trimming")
        strm_frame.pack(fill="x", padx=2, pady=4)
        sg = ttk.Frame(strm_frame); sg.pack(fill="x", padx=6, pady=4)

        self.start_var = tk.StringVar()
        self._field(sg, 0, 0, "-ss", "Trim start:", ttk.Entry(sg, textvariable=self.start_var, width=18))

        self.end_var = tk.StringVar()
        self._field(sg, 0, 3, "-to", "Trim end:", ttk.Entry(sg, textvariable=self.end_var, width=16))

        self.duration_var = tk.StringVar()
        self._field(sg, 1, 0, "-t", "Duration (instead of end):", ttk.Entry(sg, textvariable=self.duration_var, width=18))

        self.map_var = tk.StringVar()
        self._field(sg, 1, 3, "-map", "Stream map:", ttk.Entry(sg, textvariable=self.map_var, width=16))

        self.threads_var = tk.StringVar()
        self._field(sg, 2, 0, "-threads", "CPU threads:", ttk.Entry(sg, textvariable=self.threads_var, width=18))

        self.metadata_var = tk.StringVar()
        self._field(sg, 2, 3, "-metadata", "Metadata (k=v,k2=v2):", ttk.Entry(sg, textvariable=self.metadata_var, width=16))

        self.movflags_var = tk.StringVar()
        self._field(sg, 3, 0, "-movflags", "MOV/MP4 flags:", ttk.Entry(sg, textvariable=self.movflags_var, width=18))

        gpu_lbl = ttk.Label(sg, text="GPU accel:")
        gpu_lbl.grid(row=3, column=3, sticky="w", padx=(0, 4), pady=3)
        self.gpu_var = tk.StringVar(value="none")
        ttk.Combobox(sg, textvariable=self.gpu_var, values=["none", "nvidia", "amd", "intel"],
                     width=14, state="readonly").grid(row=3, column=4, sticky="w", padx=(0, 4), pady=3)

        # --- Toggles section ---
        tog_frame = ttk.LabelFrame(opts_container, text="Toggles")
        tog_frame.pack(fill="x", padx=2, pady=4)
        tg = ttk.Frame(tog_frame); tg.pack(fill="x", padx=6, pady=6)

        self.audio_only_var = tk.BooleanVar()
        self.no_audio_var = tk.BooleanVar()
        self.no_subs_var = tk.BooleanVar()
        self.shortest_var = tk.BooleanVar()
        self.overwrite_var = tk.BooleanVar(value=True)

        def _toggle(col, flag, text, var, command=None):
            cb = ttk.Checkbutton(tg, text=text, variable=var, command=command)
            cb.grid(row=0, column=col * 2, sticky="w", padx=(0, 2), pady=3)
            icon = ttk.Label(tg, text="ⓘ", foreground="#3366cc", cursor="question_arrow")
            icon.grid(row=0, column=col * 2 + 1, sticky="w", padx=(0, 14), pady=3)
            Tooltip(icon, f"{flag}\n{FLAG_HELP.get(flag, '')}")

        _toggle(0, "-vn", "Audio only (extract)", self.audio_only_var, self._sync_audio_toggles)
        _toggle(1, "-an", "No audio (mute)", self.no_audio_var, self._sync_audio_toggles)
        _toggle(2, "-sn", "No subtitles", self.no_subs_var)
        _toggle(3, "-shortest", "Stop at shortest stream", self.shortest_var)

        tg2 = ttk.Frame(tog_frame); tg2.pack(fill="x", padx=6, pady=(0, 6))
        _toggle2_lbl = ttk.Checkbutton(tg2, text="Overwrite output (-y, else -n)", variable=self.overwrite_var)
        _toggle2_lbl.grid(row=0, column=0, sticky="w", padx=(0, 2))
        icon = ttk.Label(tg2, text="ⓘ", foreground="#3366cc", cursor="question_arrow")
        icon.grid(row=0, column=1, sticky="w", padx=(0, 14))
        Tooltip(icon, f"-y / -n\n{FLAG_HELP['-y']}\n{FLAG_HELP['-n']}")

        extra_row = ttk.Frame(opts_container)
        extra_row.pack(fill="x", padx=6, pady=6)
        ttk.Label(extra_row, text="Extra raw ffmpeg args:").pack(side="left")
        self.extra_var = tk.StringVar()
        ttk.Entry(extra_row, textvariable=self.extra_var).pack(side="left", fill="x", expand=True, padx=4)

        # ---- Buttons ----
        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", padx=8, pady=5)
        self.convert_btn = ttk.Button(btn_row, text="Convert", command=self.start_convert)
        self.convert_btn.pack(side="left")
        self.cancel_btn = ttk.Button(btn_row, text="Cancel", command=self.cancel_convert, state="disabled")
        self.cancel_btn.pack(side="left", padx=6)
        ttk.Button(btn_row, text="Preview command", command=self.preview_command).pack(side="left", padx=6)

        self.progress = ttk.Progressbar(btn_row, mode="determinate", maximum=100, value=0)
        self.progress.pack(side="right", fill="x", expand=True, padx=6)

        # ---- Progress info (% done, elapsed, remaining time, speed, size) ----
        progress_info_row = ttk.Frame(self)
        progress_info_row.pack(fill="x", padx=8, pady=(0, 4))
        self.progress_info_var = tk.StringVar(value="Idle.")
        ttk.Label(progress_info_row, textvariable=self.progress_info_var, foreground="#555").pack(side="left")

        # ---- Log ----
        log_frame = ttk.LabelFrame(self, text="Log")
        log_frame.pack(fill="both", expand=False, padx=8, pady=(0, 8))
        self.log_text = tk.Text(log_frame, height=10, wrap="word", state="disabled",
                                 bg="#111", fg="#ddd", insertbackground="#ddd")
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)

    def _sync_audio_toggles(self):
        if self.audio_only_var.get():
            self.no_audio_var.set(False)

    def _on_container_changed(self, _event=None):
        """Keep the Output filename's extension in sync with the Container
        dropdown the moment it changes, so what's shown is always accurate —
        no need to wait until Convert is clicked."""
        current = self.output_var.get()
        if not current:
            return
        ext = CONTAINER_EXT_MAP.get(self.container_var.get(), self.container_var.get())
        self.output_var.set(str(Path(current).with_suffix("." + ext)))

    # ---------- file dialogs ----------
    def browse_input(self):
        path = filedialog.askopenfilename(title="Select input video/audio file")
        if path:
            self.input_var.set(path)
            if not self.output_var.get():
                p = Path(path)
                ext = CONTAINER_EXT_MAP.get(self.container_var.get(), self.container_var.get())
                self.output_var.set(str(p.with_name(p.stem + "_converted." + ext)))

    def browse_output(self):
        ext = CONTAINER_EXT_MAP.get(self.container_var.get(), self.container_var.get())
        path = filedialog.asksaveasfilename(title="Save output as", defaultextension=f".{ext}")
        if path:
            self.output_var.set(path)

    # ---------- command building ----------
    def build_command(self):
        if not self.ffmpeg_path:
            raise RuntimeError("ffmpeg binary not set. Place it in ./bin.")
        if not self.input_var.get():
            raise RuntimeError("Please choose an input file.")
        if not self.output_var.get():
            raise RuntimeError("Please choose an output file.")

        cmd = [self.ffmpeg_path]
        cmd.append("-y" if self.overwrite_var.get() else "-n")

        if self.start_var.get().strip():
            cmd += ["-ss", self.start_var.get().strip()]

        cmd += ["-i", self.input_var.get()]

        if self.end_var.get().strip():
            cmd += ["-to", self.end_var.get().strip()]
        elif self.duration_var.get().strip():
            cmd += ["-t", self.duration_var.get().strip()]

        if self.map_var.get().strip():
            for spec in self.map_var.get().strip().split():
                cmd += ["-map", spec]

        if self.audio_only_var.get():
            cmd += ["-vn"]

            if self.audio_codec_var.get() != "(copy/auto)":
                cmd += ["-c:a", self.audio_codec_var.get()]

            if self.audio_bitrate_var.get().strip():
                cmd += ["-b:a", self.audio_bitrate_var.get().strip()]

            if self.af_var.get().strip():
                cmd += ["-af", self.af_var.get().strip()]

        else:
            gpu = self.gpu_var.get()
            gpu_map = {
                "nvidia": "h264_nvenc",
                "amd": "h264_amf",
                "intel": "h264_qsv"
            }

            if gpu != "none":
                cmd += ["-c:v", gpu_map[gpu]]
            elif self.video_codec_var.get() != "(copy/auto)":
                cmd += ["-c:v", self.video_codec_var.get()]

            if self.resolution_var.get().strip():
                cmd += ["-s", self.resolution_var.get().strip()]

            if self.aspect_var.get().strip():
                cmd += ["-aspect", self.aspect_var.get().strip()]

            if self.pix_fmt_var.get() != "(default)":
                cmd += ["-pix_fmt", self.pix_fmt_var.get()]

            if self.vf_var.get().strip():
                cmd += ["-vf", self.vf_var.get().strip()]

            if self.fps_var.get().strip():
                cmd += ["-r", self.fps_var.get().strip()]

            if self.crf_var.get().strip():
                cmd += ["-crf", self.crf_var.get().strip()]

            if self.qv_var.get().strip():
                cmd += ["-q:v", self.qv_var.get().strip()]

            if self.preset_var.get() != "(default)":
                cmd += ["-preset", self.preset_var.get()]

            if self.bitrate_var.get().strip():
                cmd += ["-b:v", self.bitrate_var.get().strip()]

            if self.audio_codec_var.get() != "(copy/auto)":
                cmd += ["-c:a", self.audio_codec_var.get()]

            if self.audio_bitrate_var.get().strip():
                cmd += ["-b:a", self.audio_bitrate_var.get().strip()]

            if self.af_var.get().strip():
                cmd += ["-af", self.af_var.get().strip()]

            if self.no_audio_var.get():
                cmd += ["-an"]

        if self.no_subs_var.get():
            cmd += ["-sn"]

        if self.threads_var.get().strip():
            cmd += ["-threads", self.threads_var.get().strip()]

        if self.metadata_var.get().strip():
            for pair in self.metadata_var.get().strip().split(","):
                pair = pair.strip()
                if pair:
                    cmd += ["-metadata", pair]

        if self.movflags_var.get().strip():
            cmd += ["-movflags", self.movflags_var.get().strip()]

        if self.shortest_var.get():
            cmd += ["-shortest"]

        if self.extra_var.get().strip():
            cmd += self.extra_var.get().strip().split()

        # ==========================================================
        # Automatic MPEG Presets
        # ==========================================================
        container = self.container_var.get()
        output_file = self.output_var.get()

        if container == "mpeg1":
            # Container dropdown is the source of truth: if the Output filename
            # doesn't already end in .mpg/.mpeg, fix it so what's on disk
            # actually matches what was selected.
            if not output_file.lower().endswith((".mpg", ".mpeg")):
                output_file = str(Path(output_file).with_suffix(".mpg"))
                self.output_var.set(output_file)

        apply_mpeg_preset = container == "mpeg1" or output_file.lower().endswith((".mpg", ".mpeg"))

        if apply_mpeg_preset:

            # Detect selected codec
            codec = self.video_codec_var.get()

            if container == "mpeg1":
                # "MPEG-1" container explicitly chosen — always force mpeg1video,
                # even if a different codec is selected in the dropdown.
                codec = "mpeg1video"
                self._pending_preset_note = "Applying MPEG-1 preset: forcing -c:v mpeg1video"
            elif codec == "(copy/auto)":
                codec = "mpeg1video"
                self._pending_preset_note = "Applying MPEG preset (.mpg/.mpeg output): defaulting -c:v to mpeg1video"
            else:
                self._pending_preset_note = f"Applying MPEG preset (.mpg/.mpeg output) with -c:v {codec}"

            # Video Codec
            if container == "mpeg1" or "-c:v" not in cmd:
                # Strip any codec already added earlier so the forced choice wins.
                if "-c:v" in cmd:
                    idx = cmd.index("-c:v")
                    del cmd[idx:idx + 2]
                cmd += ["-c:v", codec]

            # Audio Codec
            if "-c:a" not in cmd:
                cmd += ["-c:a", "mp2"]

            # Default Bitrates
            if "-b:v" not in cmd:
                if codec == "mpeg2video":
                    cmd += ["-b:v", "4000k"]
                else:
                    cmd += ["-b:v", "2000k"]

            if "-b:a" not in cmd:
                cmd += ["-b:a", "224k"]

            # Frame Rate
            if "-r" not in cmd:
                cmd += ["-r", "25"]

            # Pixel Format
            if "-pix_fmt" not in cmd:
                cmd += ["-pix_fmt", "yuv420p"]

        cmd.append(output_file)

        return cmd

    def preview_command(self):
        self._pending_preset_note = None
        try:
            cmd = self.build_command()
        except RuntimeError as e:
            messagebox.showerror("Cannot preview", str(e))
            return
        if self._pending_preset_note:
            self._log(self._pending_preset_note + "\n")
        self._log(" ".join(cmd) + "\n")

    # ---------- logging ----------
    def _log(self, text):
        self.log_text.config(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    # ---------- convert control ----------
    def start_convert(self):
        self._pending_preset_note = None
        try:
            cmd = self.build_command()
        except RuntimeError as e:
            messagebox.showerror("Cannot convert", str(e))
            return

        self._clear_log()
        if self._pending_preset_note:
            self._log(self._pending_preset_note + "\n")
        self._log("Running:\n" + " ".join(cmd) + "\n\n")

        self.convert_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.progress.config(mode="determinate", value=0)
        self.progress_info_var.set("Probing input duration…")

        self.worker_thread = threading.Thread(
            target=self._run_ffmpeg, args=(cmd, self.input_var.get()), daemon=True
        )
        self.worker_thread.start()

    def _run_ffmpeg(self, cmd, input_path):
        total_duration = probe_duration(self.ffmpeg_path, input_path)
        if total_duration:
            self.after(0, self.progress_info_var.set,
                       f"Input duration: {seconds_to_hms(total_duration)} — starting…")
        else:
            # Unknown duration (e.g. live/odd input) — fall back to indeterminate bar.
            self.after(0, lambda: self.progress.config(mode="indeterminate"))
            self.after(0, self.progress.start, 12)
            self.after(0, self.progress_info_var.set, "Converting… (duration unknown)")

        start_time = time.time()

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
            )
            for line in self.process.stdout:
                self.after(0, self._log, line)
                if total_duration:
                    self._handle_progress_line(line, total_duration, start_time)
            self.process.wait()
            code = self.process.returncode
        except Exception as e:
            code = -1
            self.after(0, self._log, f"\nError launching ffmpeg: {e}\n")

        self.after(0, self._on_finish, code, total_duration)

    def _handle_progress_line(self, line, total_duration, start_time):
        """Parses an ffmpeg stderr line like:
        'frame=  120 fps=30 size=  2048kB time=00:00:04.00 bitrate=... speed=1.02x'
        and updates the progress bar + a status line with % / elapsed / ETA / size / speed."""
        time_match = _PROGRESS_TIME_RE.search(line)
        if not time_match:
            return

        current = _hms_to_seconds(*time_match.groups())
        percent = max(0.0, min(100.0, (current / total_duration) * 100 if total_duration else 0))
        elapsed = time.time() - start_time

        speed_match = _PROGRESS_SPEED_RE.search(line)
        speed = float(speed_match.group(1)) if speed_match else None

        if speed and speed > 0:
            remaining = max(0.0, (total_duration - current) / speed)
        elif current > 0:
            # Fallback: extrapolate from encode rate seen so far.
            remaining = max(0.0, (total_duration - current) * (elapsed / current))
        else:
            remaining = None

        size_match = _PROGRESS_SIZE_RE.search(line)
        size_text = size_match.group(1) if size_match else "?"
        speed_text = f"{speed:.2f}x" if speed else "?"

        info = (
            f"{percent:5.1f}% done — elapsed {seconds_to_hms(elapsed)} — "
            f"remaining {seconds_to_hms(remaining)} — size {size_text} — speed {speed_text}"
        )
        self.after(0, self.progress.config, {"value": percent})
        self.after(0, self.progress_info_var.set, info)

    def _on_finish(self, code, total_duration=None):
        self.progress.stop()  # no-op if it was never in indeterminate mode
        self.convert_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        self.process = None

        if code == 0:
            self.progress.config(mode="determinate", value=100)
            self.progress_info_var.set("100% done.")
            self._log("\n✅ Done.\n")
            messagebox.showinfo("Success", f"Saved to:\n{self.output_var.get()}")
        elif code is None or code == -9:
            self.progress_info_var.set("Cancelled.")
            self._log("\n⏹ Cancelled.\n")
        else:
            self.progress_info_var.set(f"Failed (exit code {code}).")
            self._log(f"\n❌ ffmpeg exited with code {code}\n")
            messagebox.showerror("Conversion failed", f"ffmpeg exited with code {code}. See log for details.")

    def cancel_convert(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self._log("\nCancelling…\n")


def main():
    app = VideoConverterGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
