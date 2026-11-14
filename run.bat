@echo off
title Universal Video Downloader
cd /d "%~dp0"

echo Launching Universal Video Downloader...
start "" pythonw app.py
if errorlevel 1 (
    echo Pythonw failed, falling back to python...
    python app.py
)
exit
