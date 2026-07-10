@echo off
setlocal
cd /d "%~dp0"
py -3 main.py
if errorlevel 1 (
    echo.
    echo The game could not start. Install Python 3 with Tcl/Tk support.
    pause
)
