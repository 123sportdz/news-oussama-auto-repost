@echo off
REM NEWS OUSSAMA Auto Repost — start automatically with Windows
REM   .\autostart.bat         — register the auto loop at logon
REM   .\autostart.bat remove  — remove it again
REM
REM Registers a Scheduled Task "NEWS OUSSAMA Auto Repost" that runs
REM   setup.bat --auto  (discover + monitor every 30 min)
REM at every logon. No admin rights needed for a task of your own user.
REM The console window stays open while the loop runs; closing it stops
REM the loop until the next logon. The dashboard is NOT started here —
REM open it separately with .\setup.bat --dashboard when you need it.
cd /d %~dp0
set TASKNAME=NEWS OUSSAMA Auto Repost
if /i "%1"=="remove" goto :remove
if /i "%1"=="delete" goto :remove
if /i "%1"=="uninstall" goto :remove

echo Registering "%TASKNAME%" to run at logon...
schtasks /create /tn "%TASKNAME%" /tr "cmd /c \"%~dp0setup.bat --auto\"" /sc onlogon /f
if errorlevel 1 (
  echo [X] Could not create the task — try running this file as administrator.
  exit /b 1
)
echo [OK] Registered. The auto loop will start at your next logon.
echo     To check it: schtasks /query /tn "%TASKNAME%"
echo     To remove it: .\autostart.bat remove
goto :eof

:remove
echo Removing "%TASKNAME%"...
schtasks /delete /tn "%TASKNAME%" /f
if errorlevel 1 (
  echo [i] No such task — nothing to remove.
  exit /b 0
)
echo [OK] Removed.
