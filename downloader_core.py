import os
import re
import sys
import threading
import urllib.parse
from typing import Callable, Optional, Dict, Any

from dependency_manager import ensure_core_in_sys_path, get_ffmpeg_executable

ensure_core_in_sys_path()

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

def get_ffmpeg_path() -> Optional[str]:
    """Returns detected ffmpeg path checking core folder, app directory, or system PATH."""
    return get_ffmpeg_executable()

def normalize_video_url(url: str) -> str:
    """
    If a URL points to a specific video with playlist query params attached
    (e.g., https://youtu.be/XYZ?list=123 or https://www.youtube.com/watch?v=XYZ&list=123),
    extract and normalize to direct video URL so yt-dlp won't fail on private/deleted
    other videos in that playlist.
    """
    try:
        clean = url.strip()
        parsed = urllib.parse.urlparse(clean)
        # youtu.be/VIDEO_ID?list=...
        if "youtu.be" in parsed.netloc:
            v_id = parsed.path.strip("/")
            if v_id and v_id != "watch":
                return f"https://www.youtube.com/watch?v={v_id}"
        # youtube.com/watch?v=VIDEO_ID&list=...
        elif "youtube.com" in parsed.netloc:
            qs = urllib.parse.parse_qs(parsed.query)
            if "v" in qs and qs["v"]:
                return f"https://www.youtube.com/watch?v={qs['v'][0]}"
    except Exception:
        pass
    return url.strip()

def clean_filename(s: str) -> str:
    """Sanitize filename to avoid invalid characters on Windows."""
    return re.sub(r'[\\/*?:"<>|]', "", s)

def format_bytes(size: Optional[float]) -> str:
    """Formats bytes into human readable format."""
    if not size or size <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_idx = 0
    val = float(size)
    while val >= 1024 and unit_idx < len(units) - 1:
        val /= 1024
        unit_idx += 1
    return f"{val:.1f} {units[unit_idx]}"

def format_duration(seconds: Optional[int]) -> str:
    """Formats seconds into HH:MM:SS or MM:SS."""
    if not seconds:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

class DownloaderCore:
    def __init__(self):
        self._cancel_requested = False
        self._is_downloading = False
        self.ffmpeg_location = get_ffmpeg_path()
        self._ensure_ytdlp()

    def _ensure_ytdlp(self):
        global yt_dlp
        if yt_dlp is None:
            ensure_core_in_sys_path()
            try:
                import yt_dlp as _ydl
                yt_dlp = _ydl
            except Exception as e:
                print(f"[DownloaderCore] Notice: yt_dlp import failed: {e}")

    @property
    def is_downloading(self) -> bool:
        return self._is_downloading

    def cancel(self):
        """Signals download cancellation."""
        self._cancel_requested = True

    def fetch_info(self, url: str) -> Dict[str, Any]:
        """
        Extracts information about the video or playlist without downloading.
        """
        self._ensure_ytdlp()
        if yt_dlp is None:
            raise Exception("yt-dlp engine is not yet installed. Please restart the app to run setup.")

        clean_url = normalize_video_url(url)

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": False,
            "noplaylist": True,
            "ignoreerrors": True,
        }
        if self.ffmpeg_location:
            ydl_opts["ffmpeg_location"] = self.ffmpeg_location

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            
            # Check if playlist
            is_playlist = "entries" in info and bool(info.get("entries"))
            if is_playlist:
                entries = list(info.get("entries", []))
                first_entry = entries[0] if entries else {}
                return {
                    "is_playlist": True,
                    "title": info.get("title", "Playlist"),
                    "uploader": info.get("uploader") or info.get("channel") or "Various",
                    "thumbnail": first_entry.get("thumbnail") or info.get("thumbnail"),
                    "duration": sum((e.get("duration") or 0) for e in entries if isinstance(e, dict)),
                    "count": len(entries),
                    "extractor": info.get("extractor_key", "Web"),
                    "url": url,
                    "raw_info": info
                }

            # Single video
            # Collect available resolutions
            formats = info.get("formats", [])
            resolutions = set()
            for f in formats:
                h = f.get("height")
                if h and isinstance(h, int) and h >= 144:
                    resolutions.add(h)
            sorted_res = sorted(list(resolutions), reverse=True)

            return {
                "is_playlist": False,
                "title": info.get("title", "Unknown Title"),
                "uploader": info.get("uploader") or info.get("channel") or "Unknown Creator",
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration", 0),
                "view_count": info.get("view_count", 0),
                "extractor": info.get("extractor_key", "Web"),
                "available_resolutions": sorted_res,
                "url": url,
                "raw_info": info
            }

    def download(
        self,
        url: str,
        output_dir: str,
        mode: str = "video", # "video" or "audio"
        quality: str = "best", # "best", "1080", "720", "480", "360", "mp3_320", "mp3_192"
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        status_callback: Optional[Callable[[str], None]] = None,
        completion_callback: Optional[Callable[[bool, str, Optional[str]], None]] = None
    ):
        """
        Runs the download in the current thread. Should normally be called from a worker thread.
        """
        self._cancel_requested = False
        self._is_downloading = True
        downloaded_file_path = None

        self._ensure_ytdlp()
        if yt_dlp is None:
            self._is_downloading = False
            if completion_callback:
                completion_callback(False, "yt-dlp engine is not installed. Please restart the app.", None)
            return

        os.makedirs(output_dir, exist_ok=True)

        def progress_hook(d):
            if self._cancel_requested:
                raise Exception("Download cancelled by user.")

            status = d.get("status")
            if status == "downloading":
                total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded_bytes = d.get("downloaded_bytes") or 0
                speed = d.get("speed") or 0
                eta = d.get("eta") or 0

                percent = 0.0
                if total_bytes > 0:
                    percent = (downloaded_bytes / total_bytes) * 100.0

                if progress_callback:
                    progress_callback({
                        "status": "downloading",
                        "percent": percent,
                        "downloaded_bytes": downloaded_bytes,
                        "total_bytes": total_bytes,
                        "speed": speed,
                        "eta": eta,
                        "filename": os.path.basename(d.get("filename", "")),
                        "info_dict": d.get("info_dict", {})
                    })
            elif status == "finished":
                if status_callback:
                    status_callback("Processing / converting file...")
                if progress_callback:
                    progress_callback({
                        "status": "processing",
                        "percent": 100.0,
                        "filename": os.path.basename(d.get("filename", ""))
                    })

        # Build format specifier
        if mode == "audio":
            format_spec = "bestaudio/best"
            postprocessors = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320" if "320" in quality else "192",
            }]
            outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")
        else:
            postprocessors = []
            if quality == "best":
                format_spec = "bestvideo+bestaudio/best"
            else:
                try:
                    res_val = int(quality.replace("p", ""))
                    format_spec = f"bestvideo[height<={res_val}]+bestaudio/best[height<={res_val}]/best"
                except Exception:
                    format_spec = "bestvideo+bestaudio/best"
            outtmpl = os.path.join(output_dir, "%(title)s [%(resolution)s].%(ext)s")

        clean_url = normalize_video_url(url)

        ydl_opts: Dict[str, Any] = {
            "format": format_spec,
            "outtmpl": outtmpl,
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "noplaylist": True,
            "ignoreerrors": True,
        }

        if self.ffmpeg_location:
            ydl_opts["ffmpeg_location"] = self.ffmpeg_location
            # If video mode and ffmpeg exists, merge to mp4
            if mode == "video":
                ydl_opts["merge_output_format"] = "mp4"
            if postprocessors:
                ydl_opts["postprocessors"] = postprocessors

        try:
            if status_callback:
                status_callback("Starting download...")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(clean_url, download=True)
                # Determine output filename
                if info:
                    if "requested_downloads" in info and info["requested_downloads"]:
                        downloaded_file_path = info["requested_downloads"][0].get("filepath")
                    if not downloaded_file_path:
                        downloaded_file_path = ydl.prepare_filename(info)
                        # Check extension changes after postprocessing
                        if mode == "audio" and not downloaded_file_path.endswith(".mp3"):
                            base, _ = os.path.splitext(downloaded_file_path)
                            if os.path.exists(base + ".mp3"):
                                downloaded_file_path = base + ".mp3"
                        elif mode == "video" and self.ffmpeg_location and not downloaded_file_path.endswith(".mp4"):
                            base, _ = os.path.splitext(downloaded_file_path)
                            if os.path.exists(base + ".mp4"):
                                downloaded_file_path = base + ".mp4"

            self._is_downloading = False
            if completion_callback:
                completion_callback(True, "Download completed successfully!", downloaded_file_path)

        except Exception as e:
            self._is_downloading = False
            msg = str(e)
            if self._cancel_requested or "cancelled by user" in msg.lower():
                if completion_callback:
                    completion_callback(False, "Download was cancelled.", None)
            else:
                if completion_callback:
                    completion_callback(False, f"Download failed: {msg}", None)

