import os
import sys
import time
import zipfile
import winreg
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

# Configure modern appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

APP_NAME = "Universal Video Downloader"
APP_VERSION = "1.0"
DEVELOPER = "Mr. Dipendu Das"
DEFAULT_INSTALL_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "Programs",
    "UniversalVideoDownloader"
)

def get_bundle_dir():
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def get_desktop_directories():
    """Returns all candidate Desktop directories including OneDrive redirected Desktop."""
    candidates = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
            val, _ = winreg.QueryValueEx(k, "Desktop")
            exp = os.path.expandvars(val)
            if exp and exp not in candidates:
                candidates.append(exp)
    except Exception:
        pass

    userprofile = os.environ.get("USERPROFILE", os.path.expanduser("~"))
    std_desktop = os.path.join(userprofile, "Desktop")
    if std_desktop not in candidates:
        candidates.append(std_desktop)

    for env_var in ["OneDrive", "OneDriveConsumer", "OneDriveCommercial"]:
        od = os.environ.get(env_var)
        if od:
            od_desk = os.path.join(od, "Desktop")
            if od_desk not in candidates:
                candidates.append(od_desk)

    pub = os.environ.get("PUBLIC")
    if pub:
        pub_desk = os.path.join(pub, "Desktop")
        if pub_desk not in candidates:
            candidates.append(pub_desk)

    return candidates

def get_start_menu_directories():
    """Returns Start Menu programs directory candidates."""
    candidates = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
            val, _ = winreg.QueryValueEx(k, "Programs")
            exp = os.path.expandvars(val)
            if exp and exp not in candidates:
                candidates.append(exp)
    except Exception:
        pass

    appdata = os.environ.get("APPDATA")
    if appdata:
        std = os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs")
        if std not in candidates:
            candidates.append(std)

    return candidates

def create_windows_shortcut(target_path: str, shortcut_path: str, working_dir: str = "", desc: str = ""):
    """Creates a Windows .lnk shortcut with native icon using VBScript with PowerShell fallback."""
    try:
        os.makedirs(os.path.dirname(shortcut_path), exist_ok=True)
        vbs_path = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "_make_sc.vbs")
        clean_target = target_path.replace('"', '""')
        clean_sc = shortcut_path.replace('"', '""')
        clean_wd = working_dir.replace('"', '""')
        clean_desc = desc.replace('"', '""')

        ico_file = os.path.join(working_dir or os.path.dirname(target_path), "app_icon.ico")
        if os.path.isfile(ico_file):
            clean_icon = ico_file.replace('"', '""')
        else:
            clean_icon = clean_target

        vbs_code = f'''Set ws = CreateObject("WScript.Shell")
Set sc = ws.CreateShortcut("{clean_sc}")
sc.TargetPath = "{clean_target}"
sc.WorkingDirectory = "{clean_wd}"
sc.Description = "{clean_desc}"
sc.IconLocation = "{clean_icon},0"
sc.Save
'''
        with open(vbs_path, "w", encoding="utf-8") as f:
            f.write(vbs_code)

        subprocess.run(["cscript.exe", "//Nologo", vbs_path], creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            os.remove(vbs_path)
        except Exception:
            pass

        if os.path.exists(shortcut_path):
            return True
    except Exception as e:
        print(f"VBS shortcut error: {e}")

    try:
        clean_target = target_path.replace('"', '`"')
        clean_sc = shortcut_path.replace('"', '`"')
        clean_wd = working_dir.replace('"', '`"')
        clean_desc = desc.replace('"', '`"')
        clean_icon = clean_icon.replace('"', '`"')
        ps_script = f'''
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut("{clean_sc}")
$s.TargetPath = "{clean_target}"
$s.WorkingDirectory = "{clean_wd}"
$s.Description = "{clean_desc}"
$s.IconLocation = "{clean_icon},0"
$s.Save()
'''
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        return os.path.exists(shortcut_path)
    except Exception as e:
        print(f"PowerShell shortcut error: {e}")
        return False

def register_in_add_remove_programs(install_dir: str, uninstaller_path: str):
    """Registers the app in Windows HKCU Uninstall registry for standard Add/Remove Programs."""
    try:
        reg_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\UniversalVideoDownloader"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, DEVELOPER)
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, install_dir)
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{uninstaller_path}"')
            winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, os.path.join(install_dir, "UniversalVideoDownloader.exe"))
            winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
    except Exception as e:
        print(f"Registry registration error: {e}")

def create_uninstaller_script(install_dir: str):
    """Creates an uninstaller script inside the installation directory."""
    uninstaller_bat = os.path.join(install_dir, "uninstall.bat")
    desktop_dirs = get_desktop_directories()
    del_shortcuts_lines = "\n".join([f'if exist "{os.path.join(d, f"{APP_NAME}.lnk")}" del /f /q "{os.path.join(d, f"{APP_NAME}.lnk")}"' for d in desktop_dirs])
    
    sm_dirs = get_start_menu_directories()
    del_sm_lines = "\n".join([f'if exist "{os.path.join(sm, "Universal Video Downloader")}" rmdir /s /q "{os.path.join(sm, "Universal Video Downloader")}"' for sm in sm_dirs])

    bat_content = f'''@echo off
title Uninstall {APP_NAME}
echo ========================================================
echo Uninstalling {APP_NAME}...
echo ========================================================
echo.

:: 1. Delete Shortcuts
{del_shortcuts_lines}
{del_sm_lines}

:: 2. Remove Registry Key
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\UniversalVideoDownloader" /f >nul 2>&1

:: 3. Self-delete install directory after batch exit
echo Removing files...
cd \\
start /b "" cmd /c "timeout /t 1 /nobreak >nul & rmdir /s /q \\"{install_dir}\\""
echo.
echo {APP_NAME} has been completely uninstalled.
timeout /t 3
exit
'''
    with open(uninstaller_bat, "w", encoding="utf-8") as f:
        f.write(bat_content)

    return uninstaller_bat


class SetupWizard(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"Setup - {APP_NAME}")
        self.geometry("620x460")
        self.resizable(False, False)

        # Center window
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"620x460+{(sw - 620)//2}+{(sh - 460)//2}")

        icon_path = os.path.join(get_bundle_dir(), "app_icon.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        self.current_step = 0
        self.install_dir = DEFAULT_INSTALL_DIR
        self.create_desktop = tk.BooleanVar(value=True)
        self.create_start = tk.BooleanVar(value=True)
        self.launch_after = tk.BooleanVar(value=True)

        self._build_container()
        self._show_step(0)

    def _build_container(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=1)

        # Content area
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=(20, 10))

        # Bottom navigation bar
        nav_frame = ctk.CTkFrame(self, height=55, fg_color=("#e5e7eb", "#181825"))
        nav_frame.grid(row=1, column=0, sticky="ew")
        nav_frame.grid_columnconfigure(0, weight=1)

        self.btn_cancel = ctk.CTkButton(
            nav_frame,
            text="Cancel",
            width=85,
            height=32,
            fg_color=("gray70", "gray30"),
            command=self.destroy
        )
        self.btn_cancel.grid(row=0, column=1, padx=(0, 10), pady=12)

        self.btn_back = ctk.CTkButton(
            nav_frame,
            text="< Back",
            width=85,
            height=32,
            fg_color=("gray70", "gray30"),
            command=self._go_back
        )
        self.btn_back.grid(row=0, column=2, padx=(0, 6), pady=12)

        self.btn_next = ctk.CTkButton(
            nav_frame,
            text="Next >",
            width=95,
            height=32,
            fg_color="#0d6efd",
            hover_color="#0b5ed7",
            font=ctk.CTkFont(weight="bold"),
            command=self._go_next
        )
        self.btn_next.grid(row=0, column=3, padx=(0, 20), pady=12)

    def _clear_content(self):
        for w in self.content_frame.winfo_children():
            w.destroy()

    def _show_step(self, step: int):
        self.current_step = step
        self._clear_content()

        if step == 0:
            self._render_welcome()
        elif step == 1:
            self._render_dest_folder()
        elif step == 2:
            self._render_options()
        elif step == 3:
            self._render_installing()
        elif step == 4:
            self._render_finished()

    # --- STEP 0: Welcome ---
    def _render_welcome(self):
        self.btn_back.configure(state="disabled")
        self.btn_next.configure(text="Next >", state="normal")
        self.btn_cancel.configure(state="normal")

        lbl_header = ctk.CTkLabel(
            self.content_frame,
            text=f"Welcome to the {APP_NAME} Setup Wizard",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w"
        )
        lbl_header.pack(fill="x", pady=(10, 8))

        lbl_author = ctk.CTkLabel(
            self.content_frame,
            text=f"Architected & Developed by {DEVELOPER}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#3a86ff",
            anchor="w"
        )
        lbl_author.pack(fill="x", pady=(0, 15))

        desc = (
            f"This wizard will install {APP_NAME} v{APP_VERSION} on your computer.\n\n"
            "Key Highlights:\n"
            "• Download high-definition videos up to 8K, 4K, 1080p, 60fps & HDR.\n"
            "• Extract high-fidelity audio tracks in MP3, M4A, FLAC, and WAV.\n"
            "• Full support for YouTube, playlists, channels, Instagram, TikTok & 1000+ sites.\n"
            "• Integrated core updater keeping you synchronized with platform protocol changes.\n\n"
            "Click 'Next' to continue, or 'Cancel' to exit Setup."
        )
        lbl_desc = ctk.CTkLabel(
            self.content_frame,
            text=desc,
            font=ctk.CTkFont(size=12),
            justify="left",
            anchor="w"
        )
        lbl_desc.pack(fill="both", expand=True)

    # --- STEP 1: Destination Folder ---
    def _render_dest_folder(self):
        self.btn_back.configure(state="normal")
        self.btn_next.configure(text="Next >", state="normal")

        lbl_header = ctk.CTkLabel(
            self.content_frame,
            text="Select Destination Location",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w"
        )
        lbl_header.pack(fill="x", pady=(10, 4))

        lbl_sub = ctk.CTkLabel(
            self.content_frame,
            text="Where should Universal Video Downloader be installed?",
            font=ctk.CTkFont(size=12),
            text_color="gray",
            anchor="w"
        )
        lbl_sub.pack(fill="x", pady=(0, 20))

        dest_card = ctk.CTkFrame(self.content_frame, corner_radius=8)
        dest_card.pack(fill="x", pady=10)
        dest_card.grid_columnconfigure(0, weight=1)

        lbl_card = ctk.CTkLabel(
            dest_card,
            text="Installation directory:",
            font=ctk.CTkFont(size=11, weight="bold"),
            anchor="w"
        )
        lbl_card.grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 4))

        self.entry_dir = ctk.CTkEntry(
            dest_card,
            font=ctk.CTkFont(size=11),
            height=32
        )
        self.entry_dir.insert(0, self.install_dir)
        self.entry_dir.grid(row=1, column=0, sticky="ew", padx=(12, 6), pady=(0, 12))

        btn_browse = ctk.CTkButton(
            dest_card,
            text="Browse...",
            width=80,
            height=32,
            fg_color=("gray75", "gray30"),
            command=self._browse_dest
        )
        btn_browse.grid(row=1, column=1, sticky="e", padx=(0, 12), pady=(0, 12))

        lbl_space = ctk.CTkLabel(
            self.content_frame,
            text="At least 60 MB of free disk space is required.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w"
        )
        lbl_space.pack(fill="x", pady=(10, 0))

    def _browse_dest(self):
        chosen = filedialog.askdirectory(initialdir=self.entry_dir.get(), title="Select Install Folder")
        if chosen:
            self.entry_dir.delete(0, "end")
            self.entry_dir.insert(0, os.path.normpath(chosen))

    # --- STEP 2: Options ---
    def _render_options(self):
        self.btn_back.configure(state="normal")
        self.btn_next.configure(text="Install", state="normal")

        lbl_header = ctk.CTkLabel(
            self.content_frame,
            text="Select Additional Shortcuts",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w"
        )
        lbl_header.pack(fill="x", pady=(10, 4))

        lbl_sub = ctk.CTkLabel(
            self.content_frame,
            text="Which additional shortcuts should be created?",
            font=ctk.CTkFont(size=12),
            text_color="gray",
            anchor="w"
        )
        lbl_sub.pack(fill="x", pady=(0, 20))

        opt_card = ctk.CTkFrame(self.content_frame, corner_radius=8)
        opt_card.pack(fill="x", pady=10)

        chk_desktop = ctk.CTkCheckBox(
            opt_card,
            text="Create a Desktop shortcut",
            variable=self.create_desktop,
            onvalue=True,
            offvalue=False,
            font=ctk.CTkFont(size=12)
        )
        chk_desktop.pack(anchor="w", padx=16, pady=(16, 10))
        if self.create_desktop.get():
            chk_desktop.select()

        chk_start = ctk.CTkCheckBox(
            opt_card,
            text="Create a Start Menu folder & shortcut",
            variable=self.create_start,
            onvalue=True,
            offvalue=False,
            font=ctk.CTkFont(size=12)
        )
        chk_start.pack(anchor="w", padx=16, pady=(0, 16))
        if self.create_start.get():
            chk_start.select()

    # --- STEP 3: Installing ---
    def _render_installing(self):
        self.btn_back.configure(state="disabled")
        self.btn_next.configure(state="disabled")
        self.btn_cancel.configure(state="disabled")

        lbl_header = ctk.CTkLabel(
            self.content_frame,
            text="Installing Universal Video Downloader...",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w"
        )
        lbl_header.pack(fill="x", pady=(10, 4))

        self.lbl_status = ctk.CTkLabel(
            self.content_frame,
            text="Extracting application files...",
            font=ctk.CTkFont(size=12),
            text_color="#3a86ff",
            anchor="w"
        )
        self.lbl_status.pack(fill="x", pady=(0, 15))

        self.progress_bar = ctk.CTkProgressBar(self.content_frame)
        self.progress_bar.pack(fill="x", pady=10)
        self.progress_bar.set(0.0)

        # Log console
        self.log_txt = ctk.CTkTextbox(
            self.content_frame,
            font=ctk.CTkFont(family="Consolas", size=10),
            height=160,
            fg_color=("#f4f4f4", "#11111b")
        )
        self.log_txt.pack(fill="both", expand=True, pady=(5, 0))

        # Start thread
        threading.Thread(target=self._perform_installation, daemon=True).start()

    def _perform_installation(self):
        try:
            bundle_dir = get_bundle_dir()
            payload_zip = os.path.join(bundle_dir, "payload.zip")

            if not os.path.exists(payload_zip):
                # Fallback check next to script
                payload_zip = os.path.join(os.path.dirname(os.path.abspath(__file__)), "payload.zip")

            if not os.path.exists(payload_zip):
                raise FileNotFoundError("Embedded application payload.zip not found in setup package.")

            # Ensure any running instance of the app is closed so files can be cleanly overwritten
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", "UniversalVideoDownloader.exe"],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                )
                time.sleep(0.5)
            except Exception:
                pass

            self._update_log(f"Destination: {self.install_dir}\n")
            os.makedirs(self.install_dir, exist_ok=True)

            with zipfile.ZipFile(payload_zip, "r") as zf:
                members = zf.infolist()
                total = len(members)

                for i, m in enumerate(members):
                    zf.extract(m, self.install_dir)
                    pct = (i + 1) / total
                    filename = os.path.basename(m.filename) or m.filename

                    if i % 15 == 0 or i == total - 1:
                        self.after(0, lambda p=pct, fn=filename: self._set_install_progress(p, f"Extracting: {fn}"))

            self.after(0, lambda: self._update_log("✓ Files extracted successfully.\n"))
            self.after(0, lambda: self._set_install_progress(0.9, "Configuring shortcuts and registration..."))

            target_exe = os.path.join(self.install_dir, "UniversalVideoDownloader.exe")

            # Shortcuts
            if self.create_desktop.get():
                for d in get_desktop_directories():
                    try:
                        sc_path = os.path.join(d, f"{APP_NAME}.lnk")
                        if create_windows_shortcut(target_exe, sc_path, self.install_dir, f"{APP_NAME} by {DEVELOPER}"):
                            self.after(0, lambda p=sc_path: self._update_log(f"✓ Desktop shortcut created: {p}\n"))
                    except Exception as e:
                        print(f"Desktop shortcut error: {e}")

            if self.create_start.get():
                for sm in get_start_menu_directories():
                    try:
                        app_sm_dir = os.path.join(sm, "Universal Video Downloader")
                        os.makedirs(app_sm_dir, exist_ok=True)
                        start_lnk = os.path.join(app_sm_dir, f"{APP_NAME}.lnk")
                        if create_windows_shortcut(target_exe, start_lnk, self.install_dir, f"{APP_NAME} by {DEVELOPER}"):
                            self.after(0, lambda p=start_lnk: self._update_log(f"✓ Start Menu shortcut created: {p}\n"))
                    except Exception as e:
                        print(f"Start menu shortcut error: {e}")

            # Uninstaller
            uninstaller_bat = create_uninstaller_script(self.install_dir)
            register_in_add_remove_programs(self.install_dir, uninstaller_bat)
            self.after(0, lambda: self._update_log("✓ Registered in Windows Apps & Features.\n"))

            # Notify Windows Shell of updated desktop & start menu icons
            try:
                import ctypes
                ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
            except Exception:
                pass

            time.sleep(0.5)
            self.after(0, lambda: self._show_step(4))

        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Installation Failed", f"Setup encountered an error:\n{e}"))
            self.after(0, self.destroy)

    def _set_install_progress(self, pct: float, msg: str):
        self.progress_bar.set(pct)
        self.lbl_status.configure(text=msg)
        self._update_log(msg + "\n")

    def _update_log(self, text: str):
        self.log_txt.insert("end", text)
        self.log_txt.see("end")

    # --- STEP 4: Finished ---
    def _render_finished(self):
        self.btn_back.configure(state="disabled")
        self.btn_next.configure(text="Finish", state="normal", command=self._finish_and_exit)
        self.btn_cancel.configure(state="disabled")

        lbl_header = ctk.CTkLabel(
            self.content_frame,
            text=f"Completing {APP_NAME} Setup",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w"
        )
        lbl_header.pack(fill="x", pady=(10, 8))

        lbl_sub = ctk.CTkLabel(
            self.content_frame,
            text=f"{APP_NAME} has been successfully installed on your computer.",
            font=ctk.CTkFont(size=12),
            text_color="#198754",
            anchor="w"
        )
        lbl_sub.pack(fill="x", pady=(0, 20))

        info_card = ctk.CTkFrame(self.content_frame, corner_radius=8)
        info_card.pack(fill="x", pady=10)

        lbl_card_dev = ctk.CTkLabel(
            info_card,
            text=f"Developed & Architected by: {DEVELOPER}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#3a86ff",
            anchor="w"
        )
        lbl_card_dev.pack(anchor="w", padx=16, pady=(14, 4))

        lbl_card_dir = ctk.CTkLabel(
            info_card,
            text=f"Installed to: {self.install_dir}",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w"
        )
        lbl_card_dir.pack(anchor="w", padx=16, pady=(0, 14))

        chk_launch = ctk.CTkCheckBox(
            self.content_frame,
            text=f"Launch {APP_NAME} now",
            variable=self.launch_after,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        chk_launch.pack(anchor="w", padx=4, pady=(20, 10))

    def _finish_and_exit(self):
        if self.launch_after.get():
            target_exe = os.path.join(self.install_dir, "UniversalVideoDownloader.exe")
            if os.path.exists(target_exe):
                subprocess.Popen([target_exe], cwd=self.install_dir)
        self.destroy()

    def _go_next(self):
        if self.current_step == 1:
            dest = self.entry_dir.get().strip()
            if not dest:
                messagebox.showwarning("Invalid Path", "Please select or enter an installation folder.")
                return
            self.install_dir = os.path.normpath(dest)

        self._show_step(self.current_step + 1)

    def _go_back(self):
        if self.current_step > 0:
            self._show_step(self.current_step - 1)


if __name__ == "__main__":
    app = SetupWizard()
    app.mainloop()
