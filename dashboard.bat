@echo off
REM NEWS OUSSAMA Auto Repost — open the local web dashboard.
REM Double-click this file, or run: .\dashboard.bat
REM It starts the dashboard and opens http://127.0.0.1:8080 in your browser.
cd /d %~dp0
echo Starting dashboard on http://127.0.0.1:8080 ...
start http://127.0.0.1:8080
python -m src.dashboard
pause
