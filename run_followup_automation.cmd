@echo off
setlocal
cd /d "%~dp0"
if not exist "logs" mkdir "logs"
"%~dp0.venv\Scripts\python.exe" manage.py automate_followups >> "logs\followup_automation.log" 2>&1
exit /b %ERRORLEVEL%
