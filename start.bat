@echo off
REM Bluetooth Mesh Broadcast Application - Startup Script for Windows
REM Note: This application is designed for Ubuntu/Linux. Windows support is limited.

echo ==========================================
echo Bluetooth Mesh Broadcast Application
echo ==========================================
echo.

REM Get the script directory
cd /d "%~dp0"

REM Check if virtual environment exists
if not exist "venv" (
    echo Virtual environment not found. Creating it...
    python -m venv venv
    echo Virtual environment created
    echo.
    
    echo Installing dependencies...
    call venv\Scripts\activate.bat
    pip install --upgrade pip
    pip install -r requirements.txt
    echo Dependencies installed
    echo.
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Check if dependencies are installed
python -c "import flask" 2>nul
if errorlevel 1 (
    echo Dependencies not installed. Installing...
    pip install --upgrade pip
    pip install -r requirements.txt
    echo Dependencies installed
    echo.
)

REM Change to backend directory
cd backend

REM Start the application
echo ==========================================
echo Starting Application...
echo ==========================================
echo.
echo Application will be available at: http://localhost:5000
echo Press Ctrl+C to stop
echo.

REM Run the application
python main.py

pause
