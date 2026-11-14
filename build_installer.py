import os
import sys
import shutil
import zipfile
import subprocess

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PORTABLE_DIR = os.path.join(PROJECT_DIR, "UniversalVideoDownloader-Portable")
PAYLOAD_ZIP = os.path.join(PROJECT_DIR, "payload.zip")
OUTPUT_SETUP_EXE = os.path.join(PROJECT_DIR, "UniversalVideoDownloader_Setup.exe")

print("=" * 65)
print("Building Standalone Single-File Windows Setup Installer (.exe)")
print("=" * 65)

# Step 1: Verify portable folder exists and clean dependencies
if not os.path.exists(PORTABLE_DIR):
    print(f"[ERROR] Portable directory not found at: {PORTABLE_DIR}")
    sys.exit(1)

# Ensure dependencies (core) are NEVER bundled into installer payload
core_dir = os.path.join(PORTABLE_DIR, "core")
if os.path.exists(core_dir):
    print("Removing dependencies from core directory to ensure clean first-launch download...")
    shutil.rmtree(core_dir, ignore_errors=True)

# Step 2: Create compressed payload.zip
print("\nCompressing lean application payload into payload.zip...")
if os.path.exists(PAYLOAD_ZIP):
    os.remove(PAYLOAD_ZIP)

with zipfile.ZipFile(PAYLOAD_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
    for root, dirs, files in os.walk(PORTABLE_DIR):
        # Strictly exclude core, downloads, and cache folders
        dirs[:] = [d for d in dirs if d.lower() not in ("core", "downloads", "__pycache__")]
        for file in files:
            if file.lower().endswith((".whl", ".tmp")):
                continue
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, PORTABLE_DIR)
            zf.write(full_path, rel_path)

zip_size_mb = os.path.getsize(PAYLOAD_ZIP) / (1024 * 1024)
print(f"Compressed payload.zip successfully: {zip_size_mb:.2f} MB")

# Step 3: Run PyInstaller in --onefile mode to create the standalone installer
print("\nCompiling standalone setup wizard with PyInstaller...")

# Clean setup build directory to force fresh icon injection
setup_build = os.path.join(PROJECT_DIR, "build", "UniversalVideoDownloader_Setup")
if os.path.exists(setup_build):
    try:
        shutil.rmtree(setup_build)
    except Exception:
        pass

icon_ico = os.path.join(PROJECT_DIR, "app_icon.ico")
cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm",
    "--onefile",
    "--windowed",
    "--name", "UniversalVideoDownloader_Setup",
    "--icon", icon_ico,
    "--add-data", f"{PAYLOAD_ZIP};.",
    "--add-data", f"{icon_ico};.",
    "--collect-all", "customtkinter",
    os.path.join(PROJECT_DIR, "installer.py")
]

proc = subprocess.run(cmd, cwd=PROJECT_DIR)
if proc.returncode != 0:
    print(f"\n[ERROR] PyInstaller failed with code {proc.returncode}")
    sys.exit(proc.returncode)

built_setup = os.path.join(PROJECT_DIR, "dist", "UniversalVideoDownloader_Setup.exe")
if os.path.exists(built_setup):
    copied = False
    for attempt in range(3):
        try:
            if os.path.exists(OUTPUT_SETUP_EXE):
                os.remove(OUTPUT_SETUP_EXE)
            shutil.copy2(built_setup, OUTPUT_SETUP_EXE)
            copied = True
            break
        except Exception:
            import time
            time.sleep(1)
    if not copied:
        subprocess.run(["powershell", "-NoProfile", "-Command", f'Copy-Item "{built_setup}" "{OUTPUT_SETUP_EXE}" -Force'])

    setup_size_mb = os.path.getsize(OUTPUT_SETUP_EXE) / (1024 * 1024)
    print("\n" + "=" * 65)
    print("STANDALONE SETUP INSTALLER CREATED SUCCESSFULLY!")
    print(f"Installer Executable: {OUTPUT_SETUP_EXE}")
    print(f"Installer File Size: {setup_size_mb:.2f} MB")
    print("=" * 65)
else:
    print(f"\n[ERROR] Expected output not found at: {built_setup}")
    sys.exit(1)
