@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0app\LRXe8-Media-Optimizer.exe" (
    start "" "%~dp0app\LRXe8-Media-Optimizer.exe"
) else (
    echo Windows paketi eksik. README.md dosyasindaki kaynaktan calistirma adimlarini izleyin.
    pause
)
