# 🎞️ Video Converter 
<img width="810" height="600" alt="image" src="https://github.com/user-attachments/assets/1a85a715-5032-4bef-be7f-e9631023113d" />


A desktop GUI front-end for FFmpeg, built with Python's standard Tkinter library. Pick an input file, choose codecs, bitrate, resolution, trimming, and other flags through dropdowns and fields, then run the conversion with a live progress bar, ETA and log — no command line needed.

---

## ✨ Features

- 🎛️ Full-featured options UI covering the most common FFmpeg flags:
  - Video: codec, preset, CRF, quality (`-q:v`), bitrate, frame rate, resolution, aspect ratio, pixel format, video filter
  - Audio: codec, bitrate, audio filter
  - Streams & trimming: start/end time, duration, stream map, thread count, metadata, MP4/MOV flags, GPU acceleration (NVIDIA/AMD/Intel)
  - Toggles: audio-only extraction, mute, drop subtitles, stop at shortest stream, overwrite behavior
  - A free-text field for any extra raw FFmpeg arguments
- ⓘ Hover tooltips on every option explaining what the underlying FFmpeg flag does
- 📼 Container dropdown (mp4, mkv, mov, webm, avi, gif, mp3, m4a, wav, mpeg, mpg) that keeps the output filename's extension in sync automatically
- 🎬 Built-in **MPEG-1/MPEG-2 preset**: choosing `.mpg`/`.mpeg` output (or the "mpeg1" container) auto-fills sensible codec, bitrate, frame rate and pixel format defaults
- 📊 Live progress bar with percent complete, elapsed time, ETA, output size and encode speed, parsed straight from FFmpeg's own output
- 👁️ **Preview command** button to see the exact FFmpeg command before running it
- 📝 Scrolling log panel showing FFmpeg's raw output
- ⏹️ Cancel a running conversion at any time
- 🖥️ Works with a bundled FFmpeg binary or one already on your system PATH

---

## ⚙️ Requirements

- Python 3.8+ (Tkinter ships with standard Python on Windows/Mac; on Linux install it separately, e.g. `sudo apt install python3-tk`)
- No third-party pip packages required — only the standard library
- **FFmpeg**, either:
  - bundled in a `bin/` folder next to the script (see below), or
  - installed and available on your system PATH

---

## 📁 Project Structure

```
your_project/
├── video_converter_gui.py   # The whole app
├── ico2.ico                 # Window/taskbar icon
└── bin/
    └── ffmpeg.exe            # Bundled FFmpeg (Windows). Use `ffmpeg` (no extension) on Mac/Linux.
```

If `ffmpeg`/`ffmpeg.exe` isn't found in `./bin`, the app automatically falls back to whatever `ffmpeg` it finds on your system PATH.

---

## 🚀 Running from source

1. Put `ffmpeg` (or `ffmpeg.exe` on Windows) in a `bin/` folder next to `video_converter_gui.py`, or make sure `ffmpeg` is on your PATH.
2. Run:

   ```bash
   python video_converter_gui.py
   ```

No `pip install` step is needed since the app only uses Python's standard library.

---

## 🧠 How It Works

- **`find_ffmpeg()`** looks for a bundled binary in `./bin` first, then falls back to `ffmpeg` on PATH.
- **`build_command()`** assembles the full FFmpeg command line from whatever options are filled in the UI, only adding a flag if the corresponding field isn't left at its default/empty state.
- **MPEG preset**: if the output extension is `.mpg`/`.mpeg`, or the "mpeg1" container is chosen, sensible defaults (codec, bitrate, frame rate, pixel format) are injected automatically so the file actually plays back correctly.
- **`probe_duration()`** runs `ffmpeg -i <input>` once up front to read the source duration, which powers the percentage and ETA in the progress bar.
- **Progress parsing** (`_handle_progress_line`) reads FFmpeg's own `time=`, `size=` and `speed=` output line by line while the conversion runs in a background thread, so the UI never freezes.
- **`_set_app_icon()`** applies `ico2.ico` as the window/taskbar icon, resolving the path correctly whether run from source or packaged into an exe.

---

## 🛠️ Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| "ffmpeg binary not set. Place it in ./bin." | No FFmpeg found in `./bin` or on PATH | Add `ffmpeg`/`ffmpeg.exe` to `./bin`, or install FFmpeg and add it to PATH |
| Conversion fails immediately | Invalid combination of options (e.g. unsupported codec for the chosen container) | Click **Preview command** to inspect the exact FFmpeg call, then check the Log panel for FFmpeg's error output |
| Progress bar stays indeterminate | Input duration couldn't be probed (e.g. unusual/corrupt input) | This is expected for some inputs; the conversion still runs, just without a percentage |
| GUI icon doesn't change | `ico2.ico` missing next to the script | Confirm the file exists in the project folder |
| No window appears / Tkinter error on Linux | Tkinter not installed | `sudo apt install python3-tk` (Debian/Ubuntu) or your distro's equivalent |

---

## ⚖️ Disclaimer

This tool simply builds and runs FFmpeg commands based on your choices. Make sure you have the rights to convert and use any media you process with it.

---

## 📄 License

MIT: free to use, modify, and distribute.
