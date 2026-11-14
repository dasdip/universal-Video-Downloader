# ⚡ Universal Video Downloader (Desktop App)

A modern, fast, and feature-rich desktop application to download videos and audio from **YouTube** and **over 1,000+ supported sites** (TikTok, Twitter/X, Instagram, Reddit, Vimeo, Facebook, Twitch, etc.) powered by **yt-dlp** and **CustomTkinter**.

> **Architected & Developed by:** **Mr. Dipendu Das**  
> **Edition:** Version 1.0 - Standard edition

<img width="972" height="789" alt="Untitled" src="https://github.com/user-attachments/assets/d6903a83-59b7-41e3-9d52-52dc019cb689" />








## ✨ Features

- **Multi-Site Support**: YouTube, Instagram, TikTok, Twitter/X, Reddit, Vimeo, Facebook, Dailymotion, Twitch, and more.
- **Smart Metadata Inspection**: Paste any video link to inspect the title, channel/creator, duration, views, and thumbnail preview.
- **Video & Audio Modes**:
  - **Video (MP4)**: Best Available, 1080p Full HD, 720p HD, 480p, 360p.
  - **Audio Only (MP3)**: High Quality (320 kbps), Standard Quality (192 kbps).
- **Embedded FFmpeg Engine**: Automatically detected and bundled with `imageio-ffmpeg` — no complex external system configurations required. Automatically merges high-resolution video streams and converts audio to MP3.
- **Live Progress & Stats**:
  - Real-time progress bar.
  - Live download speed (MB/s).
  - Downloaded bytes / total bytes.
  - Estimated time remaining (ETA).
- **One-Click Core Updater**: Built-in updater window to upgrade `yt-dlp` and `imageio-ffmpeg` to the latest releases directly from within the application, ensuring compatibility whenever streaming sites update their protocols.
- **One-Click Actions**:
  - `🔄 Update Core` to upgrade extractor engines and ffmpeg.
  - `📋 Paste` button for quick URL entry.
  - `▶ Play File` to watch immediately after download.
  - `📁 Show in Folder` to jump straight to the downloaded file.
- **Download History**: Session list of completed downloads with quick playback and folder shortcuts.
- **Dark & Light Mode**: Built-in toggle to match your personal preference.

---

## ✨ How the On-Demand Engine Architecture Works



1. **Ultra-Lightweight Initial Package**:
   - The application package is lean and small because heavy media engines (`yt-dlp` and `ffmpeg.exe`) are **not bundled** inside the download package.
2. **Automatic First-Run Setup**:
   - On the very first launch, the app detects that dependencies are missing and opens a friendly **First-Time Setup** screen.
   - It automatically downloads and installs `yt-dlp` (~3 MB) and `FFmpeg` (~38 MB) into the local `core/` folder.
3. **Instant Future Launches (Zero Setup Popup)**:
   - On every subsequent startup, the app checks if the engines exist in `core/`.
   - Once found, **the setup screen is completely skipped** and the main downloader window opens immediately!

---

## 🚀 How to Run

1. Donwload the Setup from Release page
2. Run it and instal it.
3.  on first start it may downlaod ffmpeg and yt-dlp

```bash
python app.py
```

---

## 🛠 Rebuilding the Executable
If you ever edit or update the source code, you can regenerate the standalone `.exe` anytime by running:
```bash
python build_exe.py
```

---

## 📦 Requirements

All required dependencies are already installed in your Python environment:
- `yt-dlp`
- `customtkinter`
- `pillow`
- `imageio-ffmpeg`

If you ever move to another machine, install dependencies using:
```bash
pip install -r requirements.txt
```
