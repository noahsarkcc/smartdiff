@echo off
title SmartDiff - Build
echo ========================================
echo   SmartDiff - PyInstaller Build
echo ========================================
echo.

cd /d "%~dp0"

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found!
    pause
    exit /b 1
)

REM Install build dependencies
echo [1/3] Installing dependencies...
pip install flask pyinstaller >nul 2>&1

REM Clean previous build
echo [2/3] Cleaning previous build...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist SmartDiff.spec del SmartDiff.spec

REM Build
echo [3/3] Building executable...
pyinstaller --noconfirm --onefile --console ^
    --name SmartDiff ^
    --add-data "static;static" ^
    --add-data "xml_parser.py;." ^
    --add-data "xml_differ.py;." ^
    --add-data "svn_helper.py;." ^
    --hidden-import=xml_parser ^
    --hidden-import=xml_differ ^
    --hidden-import=svn_helper ^
    server.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Build complete!
echo   Output: dist\SmartDiff.exe
echo ========================================
echo.
echo To distribute, copy dist\SmartDiff.exe to the target machine.
echo The exe is fully standalone - no Python needed.
echo.
pause
