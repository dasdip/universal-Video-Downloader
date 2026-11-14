import os
import sys
import subprocess
import threading
import warnings
import urllib.request
import json
import io
from datetime import datetime
from typing import Optional, Dict, Any

warnings.filterwarnings("ignore")

import customtkinter as ctk
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import filedialog, messagebox

from downloader_core import (
    DownloaderCore,
    format_bytes,
    format_duration,
    clean_filename,
    get_ffmpeg_path,
    normalize_video_url
)

from dependency_manager import (
    are_dependencies_ready,
    install_dependencies,
    ensure_core_in_sys_path,
    get_ffmpeg_executable,
    get_core_dir
)

ensure_core_in_sys_path()

def get_config_path() -> str:
    """Returns path to the configuration file."""
    if getattr(sys, "frozen", False):
        app_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(app_dir, "config.json")

def load_config() -> dict:
    """Loads configuration options from disk."""
    default_cfg = {
        "check_updates_startup": True
    }
    path = get_config_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                default_cfg.update(json.load(f))
        except Exception:
            pass
    return default_cfg

def save_config(cfg: dict):
    """Saves configuration options to disk."""
    path = get_config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

def check_pypi_latest(package_name: str) -> Optional[str]:
    """Fetches the latest published release version from PyPI JSON API."""
    url = f"https://pypi.org/pypi/{package_name}/json"
    req = urllib.request.Request(url, headers={"User-Agent": "UniversalDownloader/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("info", {}).get("version")
    except Exception:
        return None

def is_newer_version(latest: Optional[str], current: Optional[str]) -> bool:
    """Compares semver/release strings to check if an update is available."""
    if not latest or not current or "not" in current.lower():
        return False
    try:
        from packaging import version
        return version.parse(latest) > version.parse(current)
    except Exception:
        return latest != current and latest > current

def get_python_interpreter() -> str:
    """Returns the python interpreter executable path even if running frozen."""
    if getattr(sys, "frozen", False):
        import shutil
        py = shutil.which("python") or shutil.which("python3")
        if py:
            return py
    return sys.executable

def get_installed_versions() -> Dict[str, str]:
    """Retrieves versions of core dependencies."""
    ensure_core_in_sys_path()
    versions = {}
    try:
        import yt_dlp
        versions["yt-dlp"] = getattr(yt_dlp.version, "__version__", "Installed")
    except Exception:
        versions["yt-dlp"] = "Not found"
    
    ffmpeg_exe = get_ffmpeg_executable()
    if ffmpeg_exe and os.path.exists(ffmpeg_exe):
        versions["imageio-ffmpeg"] = "Installed (Ready)"
    else:
        versions["imageio-ffmpeg"] = "Not found"
        
    try:
        import customtkinter
        versions["customtkinter"] = getattr(customtkinter, "__version__", "Installed")
    except Exception:
        versions["customtkinter"] = "Not found"
        
    return versions

# Configuration and Theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

def get_default_download_dir() -> str:
    """Finds or creates a suitable download directory with fallback."""
    candidate = os.path.join(os.path.expanduser("~"), "Downloads", "UniversalDownloader")
    try:
        os.makedirs(candidate, exist_ok=True)
        return candidate
    except Exception:
        local_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
        os.makedirs(local_dir, exist_ok=True)
        return local_dir

class VideoDownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Universal Video Downloader (yt-dlp)")
        self.geometry("860x680")
        self.minsize(640, 480)

        # Set default download directory safely
        self.download_dir = get_default_download_dir()

        self.downloader = DownloaderCore()
        self.current_info: Optional[Dict[str, Any]] = None
        self.thumbnail_image: Optional[ctk.CTkImage] = None
        self.last_downloaded_file: Optional[str] = None
        self.history_items = []

        # Load user settings
        self.config = load_config()

        self._build_ui()
        self._check_ffmpeg_status()

        # Automatic update check at startup (non-blocking)
        if self.config.get("check_updates_startup", True):
            self.after(1200, self._start_background_update_check)

    def _build_ui(self):
        # Configure root grid:
        # Row 0: Top Header (fixed)
        # Row 1: Update Notification Banner (fixed, visible only when update detected)
        # Row 2: Middle scrollable content (expands)
        # Row 3: Bottom Sticky Action & Progress Dock (fixed & always visible)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=0)

        # Configure app icon
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.ico")
        if getattr(sys, "frozen", False):
            base_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
            frozen_icon = os.path.join(base_dir, "app_icon.ico")
            if os.path.exists(frozen_icon):
                icon_path = frozen_icon
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        # 1. Header Frame
        header_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray85", "gray14"))
        header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 6))
        header_frame.grid_columnconfigure(1, weight=1)

        app_title = ctk.CTkLabel(
            header_frame,
            text="⚡ Universal Video Downloader",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        app_title.grid(row=0, column=0, padx=16, pady=10, sticky="w")

        # Top-right controls: Theme toggle, update button & FFmpeg status pill
        header_controls = ctk.CTkFrame(header_frame, fg_color="transparent")
        header_controls.grid(row=0, column=1, padx=16, pady=6, sticky="e")

        self.ffmpeg_badge = ctk.CTkLabel(
            header_controls,
            text="Checking FFmpeg...",
            font=ctk.CTkFont(size=11),
            fg_color=("gray75", "gray25"),
            corner_radius=6,
            padx=8,
            pady=2
        )
        self.ffmpeg_badge.pack(side="left", padx=6)

        self.update_btn = ctk.CTkButton(
            header_controls,
            text="🔄 Update Core",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=105,
            height=26,
            fg_color="#0d6efd",
            hover_color="#0b5ed7",
            command=self._open_update_dialog
        )
        self.update_btn.pack(side="left", padx=5)

        self.about_btn = ctk.CTkButton(
            header_controls,
            text="ℹ️ About",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=75,
            height=26,
            fg_color=("gray75", "gray28"),
            hover_color=("gray65", "gray35"),
            text_color=("gray10", "gray95"),
            command=self._open_about_dialog
        )
        self.about_btn.pack(side="left", padx=5)

        self.theme_switch = ctk.CTkSwitch(
            header_controls,
            text="Dark Mode",
            command=self._toggle_theme,
            onvalue="Dark",
            offvalue="Light"
        )
        self.theme_switch.select()
        self.theme_switch.pack(side="left", padx=(4, 0))

        # 1.5 Update Notification Banner (Hidden by default, shown if newer version is found)
        self.update_banner = ctk.CTkFrame(
            self,
            corner_radius=8,
            fg_color=("#fff3cd", "#2c2200"),
            border_width=1,
            border_color=("#ffe69c", "#855d00")
        )
        self.update_banner.grid_columnconfigure(0, weight=1)

        self.update_banner_lbl = ctk.CTkLabel(
            self.update_banner,
            text="🔔 Update Available: A newer version of yt-dlp is available!",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#664d03", "#ffd43b")
        )
        self.update_banner_lbl.grid(row=0, column=0, sticky="w", padx=14, pady=8)

        banner_btns = ctk.CTkFrame(self.update_banner, fg_color="transparent")
        banner_btns.grid(row=0, column=1, padx=10, pady=6, sticky="e")

        self.banner_update_btn = ctk.CTkButton(
            banner_btns,
            text="⚡ Update Now",
            width=95,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#0d6efd",
            hover_color="#0b5ed7",
            command=self._open_update_dialog
        )
        self.banner_update_btn.pack(side="left", padx=4)

        self.banner_dismiss_btn = ctk.CTkButton(
            banner_btns,
            text="✕",
            width=28,
            height=28,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="transparent",
            hover_color=("gray80", "gray30"),
            text_color=("gray40", "gray70"),
            command=self._dismiss_update_banner
        )
        self.banner_dismiss_btn.pack(side="left")

        # 2. Main Scrollable Container (Center)
        self.main_container = ctk.CTkScrollableFrame(self, corner_radius=8)
        self.main_container.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 6))
        self.main_container.grid_columnconfigure(0, weight=1)

        # --- Section A: URL Input Box ---
        url_card = ctk.CTkFrame(self.main_container, corner_radius=8)
        url_card.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 10))
        url_card.grid_columnconfigure(0, weight=1)

        url_label = ctk.CTkLabel(
            url_card,
            text="Video or Playlist Link (YouTube, X/Twitter, TikTok, Instagram, Reddit, Vimeo, etc.)",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        url_label.grid(row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(10, 5))

        input_row = ctk.CTkFrame(url_card, fg_color="transparent")
        input_row.grid(row=1, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 10))
        input_row.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(
            input_row,
            placeholder_text="https://www.youtube.com/watch?v=...",
            font=ctk.CTkFont(size=12),
            height=36
        )
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.url_entry.bind("<Return>", lambda e: self._on_fetch_clicked())

        self.paste_btn = ctk.CTkButton(
            input_row,
            text="📋 Paste",
            width=75,
            height=36,
            command=self._paste_clipboard
        )
        self.paste_btn.grid(row=0, column=1, padx=(0, 6))

        self.fetch_btn = ctk.CTkButton(
            input_row,
            text="🔍 Fetch Info",
            width=100,
            height=36,
            fg_color="#1f538d",
            hover_color="#14375e",
            command=self._on_fetch_clicked
        )
        self.fetch_btn.grid(row=0, column=2)

        # --- Section B: Video Metadata Card ---
        self.meta_card = ctk.CTkFrame(self.main_container, corner_radius=8)
        self.meta_card.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 10))
        self.meta_card.grid_columnconfigure(1, weight=1)

        self.thumb_label = ctk.CTkLabel(
            self.meta_card,
            text="🎬\nNo video loaded",
            width=180,
            height=100,
            corner_radius=6,
            fg_color=("gray80", "gray20"),
            font=ctk.CTkFont(size=13)
        )
        self.thumb_label.grid(row=0, column=0, rowspan=4, padx=12, pady=10)

        self.meta_title = ctk.CTkLabel(
            self.meta_card,
            text="Video Title will appear here",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
            wraplength=480,
            justify="left"
        )
        self.meta_title.grid(row=0, column=1, sticky="w", padx=10, pady=(10, 2))

        self.meta_channel = ctk.CTkLabel(
            self.meta_card,
            text="Channel / Creator: -",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w"
        )
        self.meta_channel.grid(row=1, column=1, sticky="w", padx=10, pady=1)

        self.meta_details = ctk.CTkLabel(
            self.meta_card,
            text="Duration: - | Site: -",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w"
        )
        self.meta_details.grid(row=2, column=1, sticky="w", padx=10, pady=1)

        self.fetch_status_label = ctk.CTkLabel(
            self.meta_card,
            text="Paste a video link above and click 'Fetch Info' to inspect options",
            font=ctk.CTkFont(size=11, slant="italic"),
            text_color=("gray40", "gray60")
        )
        self.fetch_status_label.grid(row=3, column=1, sticky="w", padx=10, pady=(2, 10))

        # --- Section C: Download Settings Card ---
        opts_card = ctk.CTkFrame(self.main_container, corner_radius=8)
        opts_card.grid(row=2, column=0, sticky="ew", padx=6, pady=(0, 10))
        opts_card.grid_columnconfigure(1, weight=1)

        opts_title = ctk.CTkLabel(
            opts_card,
            text="⚙️ Download Settings",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        opts_title.grid(row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(8, 6))

        # Row 1: Mode & Quality
        mode_label = ctk.CTkLabel(opts_card, text="Format:", font=ctk.CTkFont(size=11))
        mode_label.grid(row=1, column=0, sticky="w", padx=12, pady=4)

        self.mode_segmented = ctk.CTkSegmentedButton(
            opts_card,
            values=["🎬 Video (MP4)", "🎵 Audio Only (MP3)"],
            command=self._on_mode_changed
        )
        self.mode_segmented.set("🎬 Video (MP4)")
        self.mode_segmented.grid(row=1, column=1, sticky="w", padx=5, pady=4)

        quality_label = ctk.CTkLabel(opts_card, text="Quality:", font=ctk.CTkFont(size=11))
        quality_label.grid(row=2, column=0, sticky="w", padx=12, pady=4)

        self.quality_menu = ctk.CTkOptionMenu(
            opts_card,
            values=["Best Available", "1080p (Full HD)", "720p (HD)", "480p (SD)", "360p"],
            width=200
        )
        self.quality_menu.set("Best Available")
        self.quality_menu.grid(row=2, column=1, sticky="w", padx=5, pady=4)

        # Row 2: Destination Folder
        folder_label = ctk.CTkLabel(opts_card, text="Save To:", font=ctk.CTkFont(size=11))
        folder_label.grid(row=3, column=0, sticky="w", padx=12, pady=(4, 10))

        folder_frame = ctk.CTkFrame(opts_card, fg_color="transparent")
        folder_frame.grid(row=3, column=1, columnspan=2, sticky="ew", padx=5, pady=(4, 10))
        folder_frame.grid_columnconfigure(0, weight=1)

        self.folder_entry = ctk.CTkEntry(folder_frame, font=ctk.CTkFont(size=11), height=30)
        self.folder_entry.insert(0, self.download_dir)
        self.folder_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.browse_btn = ctk.CTkButton(
            folder_frame,
            text="📂 Browse...",
            width=85,
            height=30,
            command=self._browse_folder
        )
        self.browse_btn.grid(row=0, column=1, padx=(0, 10))

        # --- Section D: Session Download History ---
        history_card = ctk.CTkFrame(self.main_container, corner_radius=8)
        history_card.grid(row=3, column=0, sticky="ew", padx=6, pady=(0, 10))
        history_card.grid_columnconfigure(0, weight=1)

        hist_header = ctk.CTkLabel(
            history_card,
            text="📜 Session Download History",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        hist_header.grid(row=0, column=0, sticky="w", padx=12, pady=(8, 4))

        self.history_container = ctk.CTkFrame(history_card, fg_color="transparent")
        self.history_container.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        self.history_container.grid_columnconfigure(0, weight=1)

        self.no_history_label = ctk.CTkLabel(
            self.history_container,
            text="No completed downloads yet in this session.",
            text_color="gray",
            font=ctk.CTkFont(size=11, slant="italic")
        )
        self.no_history_label.pack(pady=6)

        # --- Section E: Developer Showcase & About Strip ---
        about_strip = ctk.CTkFrame(self.main_container, corner_radius=8, fg_color=("gray88", "gray15"))
        about_strip.grid(row=4, column=0, sticky="ew", padx=6, pady=(0, 10))
        about_strip.grid_columnconfigure(0, weight=1)

        dev_lbl = ctk.CTkLabel(
            about_strip,
            text="Crafted with ✨ by Mr. Dipendu Das  •  Universal Downloader v1.0",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("gray40", "gray70")
        )
        dev_lbl.grid(row=0, column=0, sticky="w", padx=12, pady=6)

        about_link_btn = ctk.CTkButton(
            about_strip,
            text="ℹ️ About Developer",
            width=135,
            height=24,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="transparent",
            text_color=("#1f538d", "#3a86ff"),
            hover_color=("gray80", "gray25"),
            command=self._open_about_dialog
        )
        about_link_btn.grid(row=0, column=1, sticky="e", padx=10, pady=4)

        # 3. Sticky Bottom Action & Progress Dock (Fixed, Never Hidden)
        progress_card = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray85", "gray17"))
        progress_card.grid(row=3, column=0, sticky="ew", padx=14, pady=(4, 10))
        progress_card.grid_columnconfigure(0, weight=1)

        # Action Buttons row
        action_row = ctk.CTkFrame(progress_card, fg_color="transparent")
        action_row.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 6))
        action_row.grid_columnconfigure(0, weight=1)

        self.download_btn = ctk.CTkButton(
            action_row,
            text="⬇️ Start Download",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40,
            fg_color="#28a745",
            hover_color="#218838",
            command=self._start_download
        )
        self.download_btn.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.cancel_btn = ctk.CTkButton(
            action_row,
            text="✖ Cancel",
            font=ctk.CTkFont(size=12),
            width=90,
            height=40,
            fg_color="#dc3545",
            hover_color="#c82333",
            state="disabled",
            command=self._cancel_download
        )
        self.cancel_btn.grid(row=0, column=1)

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(progress_card, height=10)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=14, pady=(2, 4))

        # Progress stats label
        stats_row = ctk.CTkFrame(progress_card, fg_color="transparent")
        stats_row.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 4))
        stats_row.grid_columnconfigure(1, weight=1)

        self.percent_label = ctk.CTkLabel(stats_row, text="0.0%", font=ctk.CTkFont(size=11, weight="bold"))
        self.percent_label.grid(row=0, column=0, sticky="w")

        self.stats_label = ctk.CTkLabel(
            stats_row,
            text="Speed: - | Size: - | ETA: -",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.stats_label.grid(row=0, column=1, sticky="e")

        # Status text line & quick actions
        status_action_row = ctk.CTkFrame(progress_card, fg_color="transparent")
        status_action_row.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 10))
        status_action_row.grid_columnconfigure(0, weight=1)

        self.status_msg_label = ctk.CTkLabel(
            status_action_row,
            text="Ready to download",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w"
        )
        self.status_msg_label.grid(row=0, column=0, sticky="w")

        self.open_file_btn = ctk.CTkButton(
            status_action_row,
            text="▶ Play File",
            width=85,
            height=26,
            font=ctk.CTkFont(size=11),
            command=self._open_downloaded_file
        )
        self.open_file_btn.grid(row=0, column=1, padx=(0, 6))
        self.open_file_btn.grid_remove() # hidden until downloaded

        self.open_folder_btn = ctk.CTkButton(
            status_action_row,
            text="📁 Show in Folder",
            width=105,
            height=26,
            font=ctk.CTkFont(size=11),
            fg_color=("gray70", "gray30"),
            command=self._open_download_folder
        )
        self.open_folder_btn.grid(row=0, column=2)
        self.open_folder_btn.grid_remove() # hidden until downloaded

    def _check_ffmpeg_status(self):
        ffmpeg_path = get_ffmpeg_path()
        if ffmpeg_path:
            self.ffmpeg_badge.configure(
                text="✓ FFmpeg Enabled (Best Quality & Audio Conversion)",
                fg_color=("#198754", "#157347"),
                text_color="white"
            )
        else:
            self.ffmpeg_badge.configure(
                text="⚠️ FFmpeg Not Found (Single Stream Only)",
                fg_color=("#ffc107", "#b38600"),
                text_color="black"
            )

    def _toggle_theme(self):
        mode = self.theme_switch.get()
        ctk.set_appearance_mode(mode)

    def _paste_clipboard(self):
        try:
            clipboard_text = self.clipboard_get().strip()
            if clipboard_text:
                self.url_entry.delete(0, tk.END)
                self.url_entry.insert(0, clipboard_text)
                self._on_fetch_clicked()
        except Exception:
            pass

    def _browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.download_dir)
        if folder:
            self.download_dir = folder
            self.folder_entry.delete(0, tk.END)
            self.folder_entry.insert(0, folder)

    def _on_mode_changed(self, choice: str):
        if "Audio" in choice:
            self.quality_menu.configure(
                values=["High Quality (320 kbps MP3)", "Standard Quality (192 kbps MP3)"]
            )
            self.quality_menu.set("High Quality (320 kbps MP3)")
        else:
            resolutions = ["Best Available", "1080p (Full HD)", "720p (HD)", "480p (SD)", "360p"]
            if self.current_info and self.current_info.get("available_resolutions"):
                detected = [f"{r}p" for r in self.current_info["available_resolutions"]]
                resolutions = ["Best Available"] + detected
            self.quality_menu.configure(values=resolutions)
            self.quality_menu.set("Best Available")

    def _on_fetch_clicked(self):
        raw_url = self.url_entry.get().strip()
        if not raw_url:
            messagebox.showwarning("Missing URL", "Please enter or paste a valid video URL.")
            return

        # Auto-clean playlist params from single video links (e.g. youtu.be/ID?list=...)
        url = normalize_video_url(raw_url)
        if url != raw_url:
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, url)

        self.fetch_btn.configure(state="disabled", text="⏳ Analyzing...")
        self.fetch_status_label.configure(
            text="Extracting video details & streams from site...",
            text_color="#3a86ff"
        )

        threading.Thread(target=self._fetch_info_worker, args=(url,), daemon=True).start()

    def _fetch_info_worker(self, url: str):
        try:
            info = self.downloader.fetch_info(url)
            self.after(0, lambda: self._apply_fetched_info(info))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._apply_fetch_error(err))

    def _apply_fetched_info(self, info: Dict[str, Any]):
        self.current_info = info
        self.fetch_btn.configure(state="normal", text="🔍 Fetch Info")

        title = info.get("title", "Unknown Title")
        uploader = info.get("uploader", "Unknown Creator")
        duration_str = format_duration(info.get("duration", 0))
        site = info.get("extractor", "Web")

        if info.get("is_playlist"):
            count = info.get("count", 0)
            self.meta_title.configure(text=f"📂 Playlist: {title}")
            self.meta_channel.configure(text=f"Creator: {uploader}")
            self.meta_details.configure(text=f"Videos: {count} items | Total Duration: ~{duration_str} | Site: {site}")
            self.fetch_status_label.configure(
                text=f"✓ Playlist verified ({count} videos found)",
                text_color="#28a745"
            )
        else:
            views = f"{info.get('view_count', 0):,}" if info.get('view_count') else "N/A"
            self.meta_title.configure(text=title)
            self.meta_channel.configure(text=f"Channel / Creator: {uploader}")
            self.meta_details.configure(text=f"Duration: {duration_str} | Views: {views} | Site: {site}")
            self.fetch_status_label.configure(
                text="✓ Video stream verified and ready for download",
                text_color="#28a745"
            )

        # Update available resolutions in dropdown if in video mode
        if "Video" in self.mode_segmented.get():
            opts = ["Best Available"]
            if info.get("available_resolutions"):
                opts += [f"{r}p" for r in info["available_resolutions"]]
            else:
                opts += ["1080p", "720p", "480p", "360p"]
            self.quality_menu.configure(values=opts)
            self.quality_menu.set("Best Available")

        # Load thumbnail asynchronously
        thumb_url = info.get("thumbnail")
        if thumb_url:
            threading.Thread(target=self._load_thumbnail, args=(thumb_url,), daemon=True).start()

    def _load_thumbnail(self, url: str):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read()
                image = Image.open(io.BytesIO(data))
                image.thumbnail((220, 130))
                ctk_img = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
                self.after(0, lambda: self._apply_thumbnail(ctk_img))
        except Exception:
            pass

    def _apply_thumbnail(self, ctk_img: ctk.CTkImage):
        self.thumbnail_image = ctk_img
        self.thumb_label.configure(image=ctk_img, text="")

    def _apply_fetch_error(self, err_msg: str):
        self.fetch_btn.configure(state="normal", text="🔍 Fetch Info")
        
        # Translate technical errors into clear, friendly explanations
        lower_err = err_msg.lower()
        if "private video" in lower_err:
            friendly_explanation = (
                "🔒 Private Video\n\n"
                "The creator has set this video to Private on YouTube.\n"
                "Private videos cannot be viewed or downloaded without the owner's account permissions."
            )
        elif "video unavailable" in lower_err or "this video has been removed" in lower_err:
            friendly_explanation = (
                "❌ Video Unavailable\n\n"
                "This video has been removed, deleted, or made unavailable on the platform."
            )
        elif "sign in to confirm your age" in lower_err:
            friendly_explanation = (
                "🔞 Age-Restricted Content\n\n"
                "This video requires YouTube account login to verify age."
            )
        elif "georestricted" in lower_err or "not available in your country" in lower_err:
            friendly_explanation = (
                "🌍 Region Blocked\n\n"
                "This video is not available in your geographical region."
            )
        else:
            friendly_explanation = err_msg

        short_err = friendly_explanation.split("\n")[0]
        if len(short_err) > 80:
            short_err = short_err[:80] + "..."
        self.fetch_status_label.configure(
            text=f"⚠️ {short_err}",
            text_color="#dc3545"
        )
        messagebox.showerror("URL Error", f"Unable to fetch video information:\n\n{friendly_explanation}")

    def _start_download(self):
        raw_url = self.url_entry.get().strip()
        if not raw_url:
            messagebox.showwarning("Missing URL", "Please enter a URL to download.")
            return

        url = normalize_video_url(raw_url)

        target_dir = self.folder_entry.get().strip()
        if not target_dir:
            target_dir = self.download_dir
        os.makedirs(target_dir, exist_ok=True)

        mode_choice = "audio" if "Audio" in self.mode_segmented.get() else "video"
        quality_choice = self.quality_menu.get()

        # Update UI states
        self.download_btn.configure(state="disabled", text="⏳ Downloading...")
        self.cancel_btn.configure(state="normal")
        self.fetch_btn.configure(state="disabled")
        self.open_file_btn.grid_remove()
        self.open_folder_btn.grid_remove()

        self.progress_bar.set(0)
        self.percent_label.configure(text="0.0%")
        self.stats_label.configure(text="Connecting to video source...")
        self.status_msg_label.configure(text="Starting download task...", text_color="#3a86ff")

        threading.Thread(
            target=self.downloader.download,
            kwargs={
                "url": url,
                "output_dir": target_dir,
                "mode": mode_choice,
                "quality": quality_choice,
                "progress_callback": self._on_download_progress,
                "status_callback": self._on_download_status,
                "completion_callback": self._on_download_complete
            },
            daemon=True
        ).start()

    def _cancel_download(self):
        if self.downloader.is_downloading:
            self.cancel_btn.configure(state="disabled", text="Stopping...")
            self.status_msg_label.configure(text="Cancelling download...", text_color="#ffc107")
            self.downloader.cancel()

    def _on_download_progress(self, d: Dict[str, Any]):
        self.after(0, lambda: self._update_progress_ui(d))

    def _update_progress_ui(self, d: Dict[str, Any]):
        percent = d.get("percent", 0.0)
        self.progress_bar.set(percent / 100.0)
        self.percent_label.configure(text=f"{percent:.1f}%")

        if d.get("status") == "downloading":
            downloaded = format_bytes(d.get("downloaded_bytes", 0))
            total = format_bytes(d.get("total_bytes", 0))
            speed = f"{format_bytes(d.get('speed', 0))}/s"
            eta = f"{d.get('eta', 0)}s" if d.get('eta') else "--"
            self.stats_label.configure(
                text=f"Speed: {speed}  |  {downloaded} / {total}  |  ETA: {eta}"
            )
        elif d.get("status") == "processing":
            self.stats_label.configure(text="Merging video/audio and converting format...")

    def _on_download_status(self, msg: str):
        self.after(0, lambda: self.status_msg_label.configure(text=msg, text_color="#3a86ff"))

    def _on_download_complete(self, success: bool, message: str, file_path: Optional[str]):
        self.after(0, lambda: self._handle_complete_ui(success, message, file_path))

    def _handle_complete_ui(self, success: bool, message: str, file_path: Optional[str]):
        self.download_btn.configure(state="normal", text="⬇️ Start Download")
        self.cancel_btn.configure(state="disabled", text="✖ Cancel")
        self.fetch_btn.configure(state="normal")

        if success:
            self.progress_bar.set(1.0)
            self.percent_label.configure(text="100%")
            self.status_msg_label.configure(text=f"✓ {message}", text_color="#28a745")
            self.stats_label.configure(text="Download and processing complete!")

            self.last_downloaded_file = file_path
            if file_path and os.path.exists(file_path):
                self.open_file_btn.grid()
                self.open_folder_btn.grid()
                self._add_to_history(file_path)
            else:
                self.open_folder_btn.grid()

            messagebox.showinfo("Success", f"Download finished successfully!\n\nSaved to: {file_path or self.folder_entry.get()}")
        else:
            self.status_msg_label.configure(text=f"⚠️ {message}", text_color="#dc3545")
            if "cancelled" in message.lower():
                self.stats_label.configure(text="Download stopped by user.")
            else:
                self.stats_label.configure(text="An error occurred during download.")
                messagebox.showerror("Download Error", message)

    def _add_to_history(self, file_path: str):
        if self.no_history_label.winfo_exists():
            self.no_history_label.pack_forget()

        fname = os.path.basename(file_path)
        size_str = ""
        try:
            size_str = format_bytes(os.path.getsize(file_path))
        except Exception:
            pass

        item_frame = ctk.CTkFrame(self.history_container, fg_color=("gray90", "gray17"), corner_radius=6)
        item_frame.pack(fill="x", pady=4)
        item_frame.grid_columnconfigure(0, weight=1)

        info_text = f"📁 {fname}"
        if size_str:
            info_text += f" ({size_str})"

        lbl = ctk.CTkLabel(
            item_frame,
            text=info_text,
            font=ctk.CTkFont(size=11),
            anchor="w",
            wraplength=520,
            justify="left"
        )
        lbl.grid(row=0, column=0, sticky="w", padx=10, pady=8)

        btn_box = ctk.CTkFrame(item_frame, fg_color="transparent")
        btn_box.grid(row=0, column=1, padx=8, pady=4, sticky="e")

        play_btn = ctk.CTkButton(
            btn_box,
            text="▶ Play",
            width=65,
            height=26,
            font=ctk.CTkFont(size=10),
            command=lambda p=file_path: self._safe_open_file(p)
        )
        play_btn.pack(side="left", padx=3)

        dir_btn = ctk.CTkButton(
            btn_box,
            text="📂 Folder",
            width=65,
            height=26,
            font=ctk.CTkFont(size=10),
            fg_color=("gray75", "gray30"),
            command=lambda p=file_path: self._safe_open_folder(os.path.dirname(p))
        )
        dir_btn.pack(side="left", padx=3)

    def _safe_open_file(self, path: str):
        try:
            if os.path.exists(path):
                os.startfile(path)
            else:
                messagebox.showwarning("File Missing", f"File could not be found:\n{path}")
        except Exception as e:
            messagebox.showerror("Error Opening File", str(e))

    def _safe_open_folder(self, folder: str):
        try:
            if os.path.exists(folder):
                os.startfile(folder)
            else:
                messagebox.showwarning("Folder Missing", f"Directory could not be found:\n{folder}")
        except Exception as e:
            messagebox.showerror("Error Opening Folder", str(e))

    def _open_downloaded_file(self):
        if self.last_downloaded_file:
            self._safe_open_file(self.last_downloaded_file)

    def _open_download_folder(self):
        folder = self.folder_entry.get().strip() or self.download_dir
        self._safe_open_folder(folder)

    def _open_about_dialog(self):
        AboutDialog(self)

    def _open_update_dialog(self):
        CoreUpdaterDialog(self)

    def _refresh_dependencies_info(self):
        self._check_ffmpeg_status()

    def _start_background_update_check(self):
        """Launches startup update inspection in a lightweight background thread."""
        threading.Thread(target=self._check_pypi_updates_worker, daemon=True).start()

    def _check_pypi_updates_worker(self):
        try:
            vers = get_installed_versions()
            current_ytdlp = vers.get("yt-dlp")
            latest_ytdlp = check_pypi_latest("yt-dlp")

            if latest_ytdlp and current_ytdlp and is_newer_version(latest_ytdlp, current_ytdlp):
                self.after(0, lambda: self._show_update_alert(latest_ytdlp, current_ytdlp))
        except Exception:
            pass

    def _show_update_alert(self, latest_ver: str, current_ver: str):
        self.update_btn.configure(
            text="🔥 Update Available!",
            fg_color="#fd7e14",
            hover_color="#e8590c"
        )
        self.update_banner_lbl.configure(
            text=f"🔔 New yt-dlp release available: v{latest_ver} (current: v{current_ver})"
        )
        self.update_banner.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 6))

    def _dismiss_update_banner(self):
        self.update_banner.grid_forget()

class AboutDialog(ctk.CTkToplevel):
    def __init__(self, parent: VideoDownloaderApp):
        super().__init__(parent)
        self.parent = parent
        self.title("About • Universal Video Downloader")
        self.geometry("560x590")
        self.minsize(500, 520)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)

        # 1. Header Hero
        hero_frame = ctk.CTkFrame(self, fg_color="transparent")
        hero_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 8))
        hero_frame.grid_columnconfigure(0, weight=1)

        logo_lbl = ctk.CTkLabel(
            hero_frame,
            text="⚡",
            font=ctk.CTkFont(size=40)
        )
        logo_lbl.pack()

        app_title = ctk.CTkLabel(
            hero_frame,
            text="Universal Video Downloader",
            font=ctk.CTkFont(size=19, weight="bold")
        )
        app_title.pack(pady=(2, 2))

        version_pill = ctk.CTkLabel(
            hero_frame,
            text="Version 1.0 - Standard edition",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#e0e7ff", "#1e293b"),
            text_color=("#3730a3", "#a5b4fc"),
            corner_radius=12,
            padx=12,
            pady=3
        )
        version_pill.pack(pady=4)

        # 2. Signature Developer Showcase Card
        dev_card = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=("#f0f7ff", "#0f172a"),
            border_width=1.5,
            border_color=("#3b82f6", "#1d4ed8")
        )
        dev_card.grid(row=1, column=0, sticky="ew", padx=20, pady=(4, 10))
        dev_card.grid_columnconfigure(0, weight=1)

        role_badge = ctk.CTkLabel(
            dev_card,
            text="★ LEAD ARCHITECT & DEVELOPER ★",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#3b82f6"
        )
        role_badge.pack(pady=(12, 2))

        dev_name = ctk.CTkLabel(
            dev_card,
            text="Mr. Dipendu Das",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=("#1e3a8a", "#60a5fa")
        )
        dev_name.pack(pady=(0, 4))

        dev_tagline = ctk.CTkLabel(
            dev_card,
            text="“Architected with passion for speed, seamless UX, and reliable media extraction.”",
            font=ctk.CTkFont(size=11, slant="italic"),
            text_color=("gray35", "gray70"),
            wraplength=460
        )
        dev_tagline.pack(pady=(0, 10))

        # Skill / Feature badges
        badge_frame = ctk.CTkFrame(dev_card, fg_color="transparent")
        badge_frame.pack(pady=(0, 12))

        badges = ["🚀 Clean Architecture", "⚡ High-Performance", "💎 Modern GUI"]
        for b in badges:
            b_lbl = ctk.CTkLabel(
                badge_frame,
                text=b,
                font=ctk.CTkFont(size=10, weight="bold"),
                fg_color=("#dbeafe", "#1e293b"),
                text_color=("#1d4ed8", "#93c5fd"),
                corner_radius=6,
                padx=8,
                pady=2
            )
            b_lbl.pack(side="left", padx=4)

        # 3. Core Engine Credits Card
        tech_card = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray92", "gray16"))
        tech_card.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        tech_card.grid_columnconfigure(0, weight=1)

        tech_title = ctk.CTkLabel(
            tech_card,
            text="Built With World-Class Open Source Engines",
            font=ctk.CTkFont(size=11, weight="bold")
        )
        tech_title.pack(anchor="w", padx=14, pady=(8, 4))

        techs = [
            ("yt-dlp", "Multi-platform extraction engine supporting 1,000+ video sites"),
            ("FFmpeg", "High-definition video multiplexer & lossless MP3 audio encoder"),
            ("CustomTkinter", "Modern, fluent high-DPI responsive desktop interface framework"),
            ("Python 3.14", "Core runtime and asynchronous execution engine")
        ]
        for name, desc in techs:
            row_frame = ctk.CTkFrame(tech_card, fg_color="transparent")
            row_frame.pack(fill="x", padx=14, pady=2)
            lbl_n = ctk.CTkLabel(row_frame, text=f"• {name}:", font=ctk.CTkFont(size=10, weight="bold"), width=100, anchor="w")
            lbl_n.pack(side="left")
            lbl_d = ctk.CTkLabel(row_frame, text=desc, font=ctk.CTkFont(size=10), text_color="gray", anchor="w")
            lbl_d.pack(side="left")

        tech_spacer = ctk.CTkFrame(tech_card, height=6, fg_color="transparent")
        tech_spacer.pack()

        # 4. Bottom Footer with Copyright & Close
        footer_frame = ctk.CTkFrame(self, fg_color="transparent")
        footer_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(4, 15))
        footer_frame.grid_columnconfigure(0, weight=1)

        copyright_lbl = ctk.CTkLabel(
            footer_frame,
            text="© 2026 Mr. Dipendu Das  •  All Rights Reserved",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        copyright_lbl.grid(row=0, column=0, sticky="w")

        close_btn = ctk.CTkButton(
            footer_frame,
            text="Close",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=85,
            height=30,
            fg_color="#0d6efd",
            hover_color="#0b5ed7",
            command=self.destroy
        )
        close_btn.grid(row=0, column=1, sticky="e")

class CoreUpdaterDialog(ctk.CTkToplevel):
    def __init__(self, parent: VideoDownloaderApp):
        super().__init__(parent)
        self.parent = parent
        self.title("Update Core Dependencies (yt-dlp & FFmpeg)")
        self.geometry("640x560")
        self.minsize(560, 480)
        self.transient(parent)
        self.grab_set()

        self._is_checking = False
        self._is_updating = False
        self._current_ytdlp_ver = None
        self._latest_ytdlp_ver = None

        self._build_ui()
        self._load_current_versions()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # 1. Header Frame
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(15, 8))
        header.grid_columnconfigure(0, weight=1)

        lbl_title = ctk.CTkLabel(
            header,
            text="🚀 Engine & Dependency Updater",
            font=ctk.CTkFont(size=17, weight="bold")
        )
        lbl_title.grid(row=0, column=0, sticky="w")

        lbl_desc = ctk.CTkLabel(
            header,
            text="YouTube and other video platforms frequently change streaming protocols.\nKeeping yt-dlp and FFmpeg updated fixes signature errors, throttling, and broken downloads.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            justify="left"
        )
        lbl_desc.grid(row=1, column=0, sticky="w", pady=(4, 0))

        # 2. Installed Versions Info Card
        ver_card = ctk.CTkFrame(self, corner_radius=8)
        ver_card.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        ver_card.grid_columnconfigure(1, weight=1)

        lbl_card_title = ctk.CTkLabel(
            ver_card,
            text="Installed Versions",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        lbl_card_title.grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 4))

        self.lbl_ver_ytdlp = ctk.CTkLabel(
            ver_card,
            text="• yt-dlp: Detecting...",
            font=ctk.CTkFont(size=11),
            anchor="w"
        )
        self.lbl_ver_ytdlp.grid(row=1, column=0, sticky="w", padx=12, pady=1)

        self.lbl_ver_ffmpeg = ctk.CTkLabel(
            ver_card,
            text="• imageio-ffmpeg (FFmpeg): Detecting...",
            font=ctk.CTkFont(size=11),
            anchor="w"
        )
        self.lbl_ver_ffmpeg.grid(row=2, column=0, sticky="w", padx=12, pady=(1, 8))

        # 3. Component Selection & Preferences Card
        sel_card = ctk.CTkFrame(self, corner_radius=8)
        sel_card.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        sel_card.grid_columnconfigure(0, weight=1)

        lbl_sel = ctk.CTkLabel(
            sel_card,
            text="Engine Information & Preferences:",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        lbl_sel.grid(row=0, column=0, sticky="w", padx=12, pady=(8, 4))

        self.lbl_engine_info = ctk.CTkLabel(
            sel_card,
            text="• Core: yt-dlp & FFmpeg are managed locally in the 'core/' directory.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w"
        )
        self.lbl_engine_info.grid(row=1, column=0, sticky="w", padx=12, pady=2)

        self.chk_startup = ctk.CTkCheckBox(
            sel_card,
            text="Check for core updates automatically at startup",
            font=ctk.CTkFont(size=11),
            command=self._on_toggle_startup_check
        )
        if self.parent.config.get("check_updates_startup", True):
            self.chk_startup.select()
        else:
            self.chk_startup.deselect()
        self.chk_startup.grid(row=2, column=0, sticky="w", padx=12, pady=(4, 10))

        # 4. Live Log Console
        console_frame = ctk.CTkFrame(self, corner_radius=8)
        console_frame.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 10))
        console_frame.grid_columnconfigure(0, weight=1)
        console_frame.grid_rowconfigure(1, weight=1)

        lbl_console = ctk.CTkLabel(
            console_frame,
            text="Update Status & Console Output",
            font=ctk.CTkFont(size=11, weight="bold")
        )
        lbl_console.grid(row=0, column=0, sticky="w", padx=12, pady=(6, 2))

        self.log_textbox = ctk.CTkTextbox(
            console_frame,
            font=ctk.CTkFont(family="Consolas", size=10),
            fg_color=("#f4f4f4", "#11111b"),
            text_color=("#222222", "#cdd6f4"),
            wrap="word"
        )
        self.log_textbox.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.log_textbox.insert("end", "Universal Video Downloader • Core Engine Manager\n")
        self.log_textbox.insert("end", "Click '⚡ Update Now' below to check for core updates.\n")
        self.log_textbox.insert("end", "• If your engine is already up to date, a confirmation popup will notify you.\n")
        self.log_textbox.insert("end", "• If a newer version is found, it will automatically download and install.\n")

        # 5. Bottom Action Bar
        action_bar = ctk.CTkFrame(self, fg_color="transparent")
        action_bar.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 15))
        action_bar.grid_columnconfigure(0, weight=1)

        self.status_lbl = ctk.CTkLabel(
            action_bar,
            text="Ready. Click '⚡ Update Now' to check for updates.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w"
        )
        self.status_lbl.grid(row=0, column=0, sticky="w")

        btn_box = ctk.CTkFrame(action_bar, fg_color="transparent")
        btn_box.grid(row=0, column=1, sticky="e")

        self.btn_restart = ctk.CTkButton(
            btn_box,
            text="🔄 Restart App",
            font=ctk.CTkFont(size=12, weight="bold"),
            width=110,
            height=32,
            fg_color="#0d6efd",
            hover_color="#0b5ed7",
            command=self._restart_app
        )
        # Hidden until success

        self.btn_update = ctk.CTkButton(
            btn_box,
            text="⚡ Update Now",
            font=ctk.CTkFont(size=12, weight="bold"),
            width=165,
            height=32,
            fg_color="#0d6efd",
            hover_color="#0b5ed7",
            state="normal",
            command=self._on_update_now_clicked
        )
        self.btn_update.pack(side="left", padx=4)

        self.btn_close = ctk.CTkButton(
            btn_box,
            text="Close",
            font=ctk.CTkFont(size=12),
            width=75,
            height=32,
            fg_color=("gray75", "gray30"),
            command=self.destroy
        )
        self.btn_close.pack(side="left", padx=(4, 0))

    def _load_current_versions(self):
        vers = get_installed_versions()
        self.lbl_ver_ytdlp.configure(text=f"• yt-dlp: {vers.get('yt-dlp', 'Not installed')}")
        self.lbl_ver_ffmpeg.configure(text=f"• FFmpeg: {vers.get('imageio-ffmpeg', 'Not installed')}")

    def _on_update_now_clicked(self):
        if self._is_checking or self._is_updating:
            return

        self._is_checking = True
        self.btn_update.configure(state="disabled", text="⏳ Checking...", fg_color=("gray75", "gray30"))
        self.status_lbl.configure(text="🔍 Connecting to PyPI to inspect latest releases...", text_color="#3a86ff")

        self.log_textbox.delete("1.0", "end")
        self.log_textbox.insert("end", "Checking online repositories for core updates...\n")

        threading.Thread(target=self._check_and_update_worker, daemon=True).start()

    def _check_and_update_worker(self):
        vers = get_installed_versions()
        current_ver = vers.get("yt-dlp", "Not installed")
        latest_ver = check_pypi_latest("yt-dlp")

        if not latest_ver:
            self.after(0, lambda: self._on_check_failed(current_ver))
            return

        is_newer = is_newer_version(latest_ver, current_ver)

        if not is_newer:
            # ALREADY UP TO DATE -> Show already updated and trigger popup
            self.after(0, lambda: self._on_already_up_to_date(current_ver, latest_ver))
        else:
            # NEW VERSION FOUND -> Download immediately and show complete when done
            self.after(0, lambda: self._on_start_download(current_ver, latest_ver))

    def _on_check_failed(self, current_ver: str):
        self._is_checking = False
        self.status_lbl.configure(text="⚠️ Unable to connect to PyPI to verify updates.", text_color="#dc3545")
        self.btn_update.configure(state="normal", text="⚡ Update Now", fg_color="#0d6efd", hover_color="#0b5ed7")
        self._append_log("Could not retrieve latest release info from PyPI.\nPlease verify your internet connection.\n")
        messagebox.showerror(
            "Connection Error",
            "Unable to connect to PyPI to check for updates.\nPlease check your internet connection and try again.",
            parent=self
        )

    def _on_already_up_to_date(self, current_ver: str, latest_ver: str):
        self._is_checking = False
        self._current_ytdlp_ver = current_ver
        self._latest_ytdlp_ver = latest_ver

        self.status_lbl.configure(
            text=f"✓ Already Up to Date! (v{current_ver})",
            text_color="#198754"
        )
        self.btn_update.configure(
            state="normal",
            text="✓ Already Updated",
            fg_color=("#198754", "#157347"),
            hover_color=("#157347", "#0f5132")
        )
        self._append_log(f"Installed yt-dlp version: v{current_ver}\n")
        self._append_log(f"Latest release on PyPI:   v{latest_ver}\n")
        self._append_log("=" * 55 + "\n")
        self._append_log(f"✓ Already up to date! yt-dlp is running the latest available version (v{current_ver}).\nNo download is needed.\n")

        self.parent.update_btn.configure(text="✓ Up to Date", fg_color="#198754", hover_color="#157347")
        self.parent._dismiss_update_banner()

        messagebox.showinfo(
            "Already Up to Date",
            f"yt-dlp is already at the latest version (v{current_ver})!\n\nNo download is needed.",
            parent=self
        )

    def _on_start_download(self, current_ver: str, latest_ver: str):
        self._is_checking = False
        self._is_updating = True
        self._current_ytdlp_ver = current_ver
        self._latest_ytdlp_ver = latest_ver

        self.status_lbl.configure(
            text=f"🔥 New version v{latest_ver} found! Downloading update...",
            text_color="#fd7e14"
        )
        self.btn_update.configure(
            state="disabled",
            text="⏳ Downloading...",
            fg_color=("gray75", "gray30")
        )
        self.btn_close.configure(state="disabled")

        self._append_log(f"Installed yt-dlp version: v{current_ver}\n")
        self._append_log(f"Latest release on PyPI:   v{latest_ver}\n")
        self._append_log("=" * 55 + "\n")
        self._append_log(f"🔥 New version found: v{latest_ver}!\nDownloading and installing core updates now...\n")

        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self):
        def on_status(msg):
            self.after(0, lambda: (self.status_lbl.configure(text=msg), self._append_log(msg + "\n")))

        def on_prog(pct, details):
            self.after(0, lambda: self._append_log(f"{details}\n"))

        success, err = install_dependencies(force_ytdlp=True, status_callback=on_status, progress_callback=on_prog)
        self.after(0, lambda: self._on_download_finished(success, err))

    def _on_download_finished(self, success: bool, err: str):
        self._is_updating = False
        self.btn_close.configure(state="normal")

        if success:
            self._load_current_versions()
            new_ver = self._latest_ytdlp_ver or "Latest"
            self.status_lbl.configure(text=f"✓ Download Complete! (v{new_ver} ready)", text_color="#198754")
            self.btn_update.configure(state="disabled", text="✓ Download Complete", fg_color=("#198754", "#157347"))
            self.btn_restart.pack(side="left", padx=4)
            self.parent._dismiss_update_banner()
            self.parent.update_btn.configure(
                text="✓ Up to Date",
                fg_color="#198754",
                hover_color="#157347"
            )
            self.parent._refresh_dependencies_info()
            self._append_log("\n" + "=" * 55 + f"\n✓ DOWNLOAD COMPLETE! Successfully updated to v{new_ver}.\nClick 'Restart App' to apply changes.\n")

            messagebox.showinfo(
                "Download Complete",
                f"Download complete!\n\nyt-dlp has been updated to v{new_ver}.\n\nPlease click 'Restart App' to apply the update.",
                parent=self
            )
        else:
            self.status_lbl.configure(text="⚠️ Update failed", text_color="#dc3545")
            self.btn_update.configure(state="normal", text="⚡ Retry Download", fg_color="#0d6efd", hover_color="#0b5ed7")
            self._append_log(f"\n⚠️ Update failed: {err}\nPlease check your connection and retry.\n")
            messagebox.showerror(
                "Update Failed",
                f"Failed to download update:\n{err}\n\nPlease check your internet connection and try again.",
                parent=self
            )

    def _append_log(self, text: str):
        self.log_textbox.insert("end", text)
        self.log_textbox.see("end")

    def _on_toggle_startup_check(self):
        enabled = bool(self.chk_startup.get())
        self.parent.config["check_updates_startup"] = enabled
        save_config(self.parent.config)

    def _restart_app(self):
        try:
            subprocess.Popen([sys.executable] + sys.argv)
            self.parent.destroy()
            sys.exit(0)
        except Exception as e:
            messagebox.showerror(
                "Restart Failed",
                f"Could not restart automatically:\n{e}\n\nPlease close and re-open the app.",
                parent=self
            )

class DependencySetupApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Universal Video Downloader • First-Time Setup")
        self.geometry("580x450")
        self.minsize(540, 420)
        self.resizable(False, False)

        self.is_successful = False
        self._is_installing = False

        self._build_ui()
        # Auto-trigger install after 800ms
        self.after(800, self._start_install)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)

        # Header Hero
        hero = ctk.CTkFrame(self, fg_color="transparent")
        hero.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 6))
        hero.grid_columnconfigure(0, weight=1)

        lbl_logo = ctk.CTkLabel(hero, text="⚡", font=ctk.CTkFont(size=36))
        lbl_logo.pack()

        lbl_title = ctk.CTkLabel(
            hero,
            text="Universal Video Downloader",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        lbl_title.pack(pady=(2, 2))

        lbl_badge = ctk.CTkLabel(
            hero,
            text="First-Time Setup • Core Engines Installation",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#e0e7ff", "#1e293b"),
            text_color=("#3730a3", "#a5b4fc"),
            corner_radius=12,
            padx=12,
            pady=3
        )
        lbl_badge.pack(pady=4)

        # Explanatory Card
        info_card = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray90", "gray17"))
        info_card.grid(row=1, column=0, sticky="ew", padx=20, pady=(5, 12))
        info_card.grid_columnconfigure(0, weight=1)

        lbl_info_title = ctk.CTkLabel(
            info_card,
            text="📦 Downloading Required Engines",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        lbl_info_title.pack(anchor="w", padx=14, pady=(10, 4))

        lbl_desc = ctk.CTkLabel(
            info_card,
            text="To keep the application package lightweight, the two essential media engines are automatically downloaded directly to this computer now on first startup:",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=510,
            justify="left"
        )
        lbl_desc.pack(anchor="w", padx=14, pady=(0, 6))

        bullets = [
            ("• yt-dlp (~3 MB):", "High-speed extractor for YouTube, TikTok, Instagram & 1000+ sites"),
            ("• FFmpeg (~38 MB):", "Multiplexes 1080p/4K separate video/audio streams and converts MP3s")
        ]
        for name, desc in bullets:
            row = ctk.CTkFrame(info_card, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=1)
            ctk.CTkLabel(row, text=name, font=ctk.CTkFont(size=10, weight="bold"), width=125, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=desc, font=ctk.CTkFont(size=10), text_color="gray", anchor="w").pack(side="left")

        note_lbl = ctk.CTkLabel(
            info_card,
            text="✨ Note: This download only runs once. All future startups will launch immediately without this setup.",
            font=ctk.CTkFont(size=10, slant="italic"),
            text_color=("#198754", "#20c997"),
            wraplength=510,
            justify="left"
        )
        note_lbl.pack(anchor="w", padx=14, pady=(6, 10))

        # Progress Section
        prog_card = ctk.CTkFrame(self, corner_radius=10)
        prog_card.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 15))
        prog_card.grid_columnconfigure(0, weight=1)

        self.status_lbl = ctk.CTkLabel(
            prog_card,
            text="Connecting to download servers...",
            font=ctk.CTkFont(size=11, weight="bold"),
            anchor="w"
        )
        self.status_lbl.grid(row=0, column=0, sticky="w", padx=14, pady=(10, 4))

        self.progress_bar = ctk.CTkProgressBar(prog_card, height=12)
        self.progress_bar.set(0.0)
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))

        self.details_lbl = ctk.CTkLabel(
            prog_card,
            text="Preparing environment...",
            font=ctk.CTkFont(size=10),
            text_color="gray",
            anchor="w"
        )
        self.details_lbl.grid(row=2, column=0, sticky="w", padx=14, pady=(0, 10))

        # Action Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 15))
        btn_frame.grid_columnconfigure(0, weight=1)

        self.btn_action = ctk.CTkButton(
            btn_frame,
            text="⚡ Start Download",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=32,
            fg_color="#0d6efd",
            hover_color="#0b5ed7",
            command=self._start_install
        )
        self.btn_action.pack(side="right", padx=(8, 0))

        self.btn_exit = ctk.CTkButton(
            btn_frame,
            text="Cancel",
            font=ctk.CTkFont(size=12),
            width=80,
            height=32,
            fg_color=("gray75", "gray30"),
            command=self.destroy
        )
        self.btn_exit.pack(side="right")

    def _start_install(self):
        if self._is_installing:
            return
        self._is_installing = True
        self.btn_action.configure(state="disabled", text="⏳ Installing...")
        self.btn_exit.configure(state="disabled")

        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        def on_status(msg):
            self.after(0, lambda: self.status_lbl.configure(text=msg))

        def on_progress(pct, details):
            self.after(0, lambda: self._update_progress(pct, details))

        success, err = install_dependencies(status_callback=on_status, progress_callback=on_progress)
        self.after(0, lambda: self._on_finish(success, err))

    def _update_progress(self, pct, details):
        self.progress_bar.set(pct / 100.0)
        self.details_lbl.configure(text=details)

    def _on_finish(self, success, err):
        self._is_installing = False
        if success:
            self.is_successful = True
            self.progress_bar.set(1.0)
            self.status_lbl.configure(text="✓ Setup complete! Launching Downloader...", text_color="#198754")
            self.details_lbl.configure(text="All components ready.")
            self.btn_action.configure(text="✓ Ready", state="normal")
            self.after(1000, self.destroy)
        else:
            self.btn_action.configure(state="normal", text="⚡ Retry")
            self.btn_exit.configure(state="normal")
            self.status_lbl.configure(text=f"⚠️ Setup failed: {err}", text_color="#dc3545")
            messagebox.showerror("Setup Error", f"Failed to download components:\n\n{err}\n\nPlease check your internet connection and click Retry.")

def main():
    ensure_core_in_sys_path()
    if are_dependencies_ready():
        # From second startup: dependencies found, skip download popup completely!
        app = VideoDownloaderApp()
        app.mainloop()
    else:
        # First startup: dependencies not found, show setup popup
        setup = DependencySetupApp()
        setup.mainloop()
        if setup.is_successful:
            # Once installed, launch main app directly!
            app = VideoDownloaderApp()
            app.mainloop()

if __name__ == "__main__":
    main()
