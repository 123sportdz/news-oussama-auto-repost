@echo off
REM NEWS OUSSAMA Auto Repost — open the local web dashboard.
REM Double-click this file, or run: .\dashboard.bat
REM It starts the dashboard and opens http://127.0.0.1:8080 in your browser.
cd /d %~dp0
echo Starting dashboard on http://127.0.0.1:8080 ...
echo (The browser opens automatically once the server is ready. Press Ctrl+C to stop.)
python -m src.dashboard
pause
