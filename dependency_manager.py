import os
import sys
import json
import shutil
import zipfile
import urllib.request
import time
from typing import Optional, Callable, Tuple

def get_app_dir() -> str:
    """Returns the base application directory safely across frozen executables and dev scripts."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

def get_core_dir() -> str:
    """
    Returns the path to the local 'core' dependency directory.
    Does NOT create the directory here; it is created only when installing dependencies.
    """
    return os.path.join(get_app_dir(), "core")

def ensure_core_in_sys_path():
    """Ensures the core directory is at the top of sys.path if it exists."""
    core_dir = get_core_dir()
    if os.path.isdir(core_dir) and core_dir not in sys.path:
        sys.path.insert(0, core_dir)

def get_ffmpeg_executable() -> Optional[str]:
    """
    Returns the path to ffmpeg.exe if found in core, local directory, or system.
    """
    core_dir = get_core_dir()
    app_dir = get_app_dir()

    candidates = [
        os.path.join(core_dir, "ffmpeg.exe"),
        os.path.join(app_dir, "ffmpeg.exe"),
        os.path.join(app_dir, "ffmpeg", "ffmpeg.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c) and os.path.getsize(c) > 1000000:
            return c

    # If running as standalone frozen exe, require the local core/ folder
    if getattr(sys, "frozen", False):
        return None

    # Check system PATH (development mode)
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg

    # Check imageio_ffmpeg if installed (development mode)
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.isfile(exe):
            return exe
    except Exception:
        pass

    return None

def is_ytdlp_available() -> bool:
    """Checks if yt_dlp is installed and importable."""
    ensure_core_in_sys_path()
    core_dir = get_core_dir()
    if os.path.isdir(os.path.join(core_dir, "yt_dlp")):
        return True
    
    # If not running as frozen exe, check dev python environment
    if not getattr(sys, "frozen", False):
        try:
            import yt_dlp
            return True
        except ImportError:
            return False

    return False

def are_dependencies_ready() -> bool:
    """
    Returns True if BOTH yt-dlp and ffmpeg are ready.
    If True, the startup setup popup is completely skipped.
    """
    core_dir = get_core_dir()
    if not os.path.isdir(core_dir):
        return False
    return is_ytdlp_available() and (get_ffmpeg_executable() is not None)

def _download_file(url: str, dest_path: str, progress_callback: Optional[Callable[[float, int, int, float], None]] = None):
    """Downloads a file with streaming progress updates."""
    req = urllib.request.Request(url, headers={"User-Agent": "UniversalDownloader/Setup"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        total_size = int(resp.headers.get("content-length", 0))
        downloaded = 0
        chunk_size = 65536 # 64 KB
        start_time = time.time()

        with open(dest_path, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)

                elapsed = time.time() - start_time
                speed = downloaded / elapsed if elapsed > 0 else 0
                pct = (downloaded / total_size * 100.0) if total_size > 0 else 0.0

                if progress_callback:
                    progress_callback(pct, downloaded, total_size, speed)

def install_dependencies(
    force_ytdlp: bool = False,
    force_ffmpeg: bool = False,
    status_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Tuple[bool, str]:
    """
    Downloads and extracts yt-dlp and FFmpeg into the core directory.
    Reports progress cleanly to caller.
    """
    core_dir = get_core_dir()
    temp_dir = os.path.join(core_dir, "_temp_setup")
    os.makedirs(temp_dir, exist_ok=True)

    try:
        # ==========================================
        # STEP 1: Download & Extract yt-dlp (~3.2 MB)
        # ==========================================
        if force_ytdlp or not is_ytdlp_available():
            if status_callback:
                status_callback("Fetching latest yt-dlp release info from PyPI...")
            
            pypi_url = "https://pypi.org/pypi/yt-dlp/json"
            req = urllib.request.Request(pypi_url, headers={"User-Agent": "UniversalDownloader/Setup"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                whl_url = None
                for u in data.get("urls", []):
                    if u.get("packagetype") == "bdist_wheel":
                        whl_url = u["url"]
                        break

            if not whl_url:
                raise Exception("Could not locate yt-dlp wheel package on PyPI.")

            ytdlp_whl = os.path.join(temp_dir, "ytdlp.whl")
            if status_callback:
                status_callback("Downloading yt-dlp engine (~3 MB)...")

            def ytdlp_progress(pct, downloaded, total, speed):
                mb_down = downloaded / (1024 * 1024)
                mb_tot = total / (1024 * 1024)
                mb_speed = speed / (1024 * 1024)
                text = f"yt-dlp: {mb_down:.1f} MB / {mb_tot:.1f} MB ({pct:.1f}%) • {mb_speed:.1f} MB/s"
                if progress_callback:
                    progress_callback(pct * 0.25, text) # 0% - 25%

            _download_file(whl_url, ytdlp_whl, ytdlp_progress)

            if status_callback:
                status_callback("Extracting yt-dlp package into core directory...")

            with zipfile.ZipFile(ytdlp_whl, "r") as zf:
                zf.extractall(core_dir)

            ensure_core_in_sys_path()
            if not is_ytdlp_available():
                raise Exception("Failed to configure yt-dlp after extraction.")

        if progress_callback:
            progress_callback(25.0, "yt-dlp engine ready!")

        # ==========================================
        # STEP 2: Download & Extract FFmpeg (~38 MB)
        # ==========================================
        if force_ffmpeg or get_ffmpeg_executable() is None:
            if status_callback:
                status_callback("Fetching FFmpeg Windows package info...")

            ffmpeg_pypi = "https://pypi.org/pypi/imageio-ffmpeg/json"
            req = urllib.request.Request(ffmpeg_pypi, headers={"User-Agent": "UniversalDownloader/Setup"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                whl_url = None
                for u in data.get("urls", []):
                    if "win_amd64" in u.get("filename", ""):
                        whl_url = u["url"]
                        break

            if not whl_url:
                raise Exception("Could not locate FFmpeg binary wheel package on PyPI.")

            ffmpeg_whl = os.path.join(temp_dir, "ffmpeg.whl")
            if status_callback:
                status_callback("Downloading FFmpeg engine (~38 MB)...")

            def ffmpeg_progress(pct, downloaded, total, speed):
                mb_down = downloaded / (1024 * 1024)
                mb_tot = total / (1024 * 1024)
                mb_speed = speed / (1024 * 1024)
                text = f"FFmpeg: {mb_down:.1f} MB / {mb_tot:.1f} MB ({pct:.1f}%) • {mb_speed:.1f} MB/s"
                if progress_callback:
                    progress_callback(25.0 + (pct * 0.70), text) # 25% - 95%

            _download_file(whl_url, ffmpeg_whl, ffmpeg_progress)

            if status_callback:
                status_callback("Extracting FFmpeg binary...")

            final_ffmpeg = os.path.join(core_dir, "ffmpeg.exe")
            with zipfile.ZipFile(ffmpeg_whl, "r") as zf:
                for member in zf.namelist():
                    if member.endswith(".exe"):
                        zf.extract(member, temp_dir)
                        extracted = os.path.join(temp_dir, member)
                        shutil.copy2(extracted, final_ffmpeg)
                        break

            if not os.path.isfile(final_ffmpeg):
                raise Exception("Failed to locate ffmpeg.exe inside package.")

        # Cleanup temp directory
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

        if progress_callback:
            progress_callback(100.0, "All dependencies installed successfully!")
        if status_callback:
            status_callback("✓ All dependencies are installed and verified!")

        return True, "Installation complete"

    except Exception as e:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
        return False, str(e)
