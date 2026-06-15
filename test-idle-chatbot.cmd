@echo off
rem Akilu changed this because the complete chatbot test should run through one simple command.
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0scripts\test_all.py"
) else (
  python "%~dp0scripts\test_all.py"
)
exit /b %ERRORLEVEL%
