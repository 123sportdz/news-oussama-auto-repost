@echo off
REM NEWS OUSSAMA Auto Repost — discover new posts from source pages.
REM One-time setup (run once): pip install playwright
REM                          python -m playwright install chromium
REM                          python -m src.discover --login
REM Then: .\discover.bat   (or: python -m src.monitor --discover)
cd /d %~dp0
python -m src.discover %*
pause
