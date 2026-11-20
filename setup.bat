@echo off
REM NEWS OUSSAMA Auto Repost — Windows one-command setup (PowerShell / cmd)
REM   .\setup.bat            — checks everything, installs deps, runs one monitor check
REM   .\setup.bat --auto     — monitor loop every 30 minutes (Ctrl+C to stop)
REM   .\setup.bat --dashboard — start the local dashboard on http://127.0.0.1:8080 (opens in your browser)
cd /d %~dp0
echo == NEWS OUSSAMA Auto Repost — readiness check ==
python --version 2>nul || (echo [X] Python 3 is missing — install it from https://www.python.org/downloads/ and tick "Add python to PATH" & exit /b 1)
where ffmpeg >nul 2>nul || (echo [X] ffmpeg is missing — run: winget install Gyan.FFmpeg & exit /b 1)
where yt-dlp >nul 2>nul || (echo [i] yt-dlp missing — installing... & pip install yt-dlp)
echo   [OK] Python
echo   [OK] ffmpeg
echo   [OK] yt-dlp
if not exist config.yaml (echo [X] config.yaml is missing & exit /b 1)
if not exist assets\watermark-320.png (echo [X] logo is missing & exit /b 1)
echo   [OK] config.yaml
echo   [OK] logo
echo.
pip install -q -r requirements.txt
echo.
if "%1"=="--auto" (python -m src.scheduler & goto :eof)
if "%1"=="--dashboard" (echo Dashboard: http://127.0.0.1:8080  (Ctrl+C to stop) & start http://127.0.0.1:8080 & python -m src.dashboard & goto :eof)
python -m src.monitor %*
echo.
echo [i] To open the web dashboard, run: .\setup.bat --dashboard   (or .\dashboard.bat)
