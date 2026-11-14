import os
import sys
import shutil
import subprocess

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(PROJECT_DIR, "dist")
BUILD_DIR = os.path.join(PROJECT_DIR, "build")
FINAL_OUTPUT = os.path.join(PROJECT_DIR, "UniversalVideoDownloader-Portable")

print("=" * 60)
print("Building Lean Standalone Universal Video Downloader App...")
print("Core engines (yt-dlp & FFmpeg) will be downloaded on first launch!")
print("=" * 60)

# 1. Clean previous build folders
for d in [BUILD_DIR, DIST_DIR, FINAL_OUTPUT]:
    if os.path.exists(d):
        print(f"Cleaning {os.path.basename(d)}...")
        shutil.rmtree(d, ignore_errors=True)

# 2. Run PyInstaller (excluding yt_dlp and ffmpeg to keep package lightweight,
# but ensuring standard library runtime modules needed by dynamically loaded yt-dlp are bundled)
icon_ico = os.path.join(PROJECT_DIR, "app_icon.ico")

submodules_to_collect = [
    "http", "email", "urllib", "xml", "html", "asyncio", "ctypes",
    "logging", "concurrent", "sqlite3", "multiprocessing"
]
hidden_imports = [
    "PIL", "tkinter",
    "getpass", "bz2", "lzma", "ssl", "socket", "hashlib", "hmac",
    "mimetypes", "netrc", "optparse", "calendar", "fileinput", "secrets",
    "uuid", "inspect", "dis", "ast", "codeop", "csv", "tarfile", "zipfile",
    "quopri", "binascii", "base64", "bisect", "heapq", "shlex", "textwrap",
    "dataclasses", "enum", "typing", "copy", "platform", "shutil"
]

pyinstaller_cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm",
    "--onedir",
    "--windowed",
    "--name", "UniversalVideoDownloader",
    "--icon", icon_ico,
    "--add-data", f"{icon_ico};.",
    "--collect-all", "customtkinter",
    "--exclude-module", "yt_dlp",
    "--exclude-module", "imageio_ffmpeg",
]

for sm in submodules_to_collect:
    pyinstaller_cmd.extend(["--collect-submodules", sm])
for hi in hidden_imports:
    pyinstaller_cmd.extend(["--hidden-import", hi])

pyinstaller_cmd.append(os.path.join(PROJECT_DIR, "app.py"))

print("\nRunning PyInstaller...")
proc = subprocess.run(pyinstaller_cmd, cwd=PROJECT_DIR)

if proc.returncode != 0:
    print(f"\n[ERROR] PyInstaller failed with code {proc.returncode}")
    sys.exit(proc.returncode)

built_folder = os.path.join(DIST_DIR, "UniversalVideoDownloader")
if not os.path.exists(built_folder):
    print(f"\n[ERROR] Built folder not found at: {built_folder}")
    sys.exit(1)

# 3. Create downloads folder and copy icon
downloads_dir = os.path.join(built_folder, "downloads")
os.makedirs(downloads_dir, exist_ok=True)
if os.path.exists(icon_ico):
    shutil.copy2(icon_ico, os.path.join(built_folder, "app_icon.ico"))

readme_content = """Universal Video Downloader v1.0 (Lean Portable Edition)
======================================================
Architected & Developed by: Mr. Dipendu Das

How it works:
1. Double-click 'UniversalVideoDownloader.exe' to launch.
2. On the FIRST startup, the application will automatically
   download the required core engines (yt-dlp and FFmpeg) into
   the local 'core' folder.
3. On all FUTURE startups, the app detects the downloaded engines
   and opens immediately, skipping the setup screen completely!
"""
with open(os.path.join(built_folder, "README.txt"), "w", encoding="utf-8") as f:
    f.write(readme_content)

# 4. Move to clean final release folder
if os.path.exists(FINAL_OUTPUT):
    try:
        shutil.rmtree(FINAL_OUTPUT)
    except Exception:
        pass
shutil.copytree(built_folder, FINAL_OUTPUT, dirs_exist_ok=True)

# Ensure dependencies (core) are NEVER pre-bundled
core_path = os.path.join(FINAL_OUTPUT, "core")
if os.path.exists(core_path):
    shutil.rmtree(core_path, ignore_errors=True)

print("\n" + "=" * 60)
print("LEAN BUILD SUCCESSFUL!")
print(f"Portable Release Folder: {FINAL_OUTPUT}")
print(f"Executable: {os.path.join(FINAL_OUTPUT, 'UniversalVideoDownloader.exe')}")
print("=" * 60)
