@echo off
echo ===================================================
echo OpenVLC System Suite - Windows Setup and Launcher
echo ===================================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to your system PATH.
    echo Please download and install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure to check the box "Add Python to PATH" during installation.
    pause
    exit /b
)

:: Create virtual environment if it doesn't exist
if not exist "venv" (
    echo [INFO] Creating Python virtual environment...
    python -m venv venv
)

:: Activate the virtual environment
call venv\Scripts\activate.bat

:: Install requirements
echo [INFO] Installing required dependencies...
pip install -r requirements.txt

:: Launch the application
echo [INFO] Launching OpenVLC...
python run_v3.py

:: Deactivate when done
deactivate
