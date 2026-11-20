@echo off
REM NEWS OUSSAMA Auto Repost — run one monitor check, or pass a post URL:
REM   .\run.bat
REM   .\run.bat --url https://www.facebook.com/reel/123/
cd /d %~dp0
python -m src.monitor %*
