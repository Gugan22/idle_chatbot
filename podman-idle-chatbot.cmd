@echo off
rem Akilu changed this because the complete chatbot stack should use Podman only.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\podman-stack.ps1" %*
exit /b %ERRORLEVEL%
