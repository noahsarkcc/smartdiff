@echo off
title SmartDiff
echo ========================================
echo   SmartDiff
echo ========================================
echo.

cd /d "%~dp0"

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found!
    echo.
    echo Please install Python 3.8+:
    echo   https://www.python.org/downloads/
    echo.
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo [OK] Python found
python --version

REM Check and install dependencies
python -c "import flask, openpyxl, xlrd" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [INFO] Installing dependencies...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo.
        echo [ERROR] Failed to install dependencies.
        echo Try running manually: pip install -r requirements.txt
        pause
        exit /b 1
    )
    echo [OK] Dependencies installed
) else (
    echo [OK] Dependencies ready
)

echo.
echo Starting server...
echo Access at: http://localhost:5566
echo.
python server.py
if %errorlevel% neq 0 (
    echo.
    echo Server exited with error.
    pause
)
