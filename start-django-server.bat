@echo off
echo Starting Django Development Server...
echo.

REM Navigate to project directory
cd /d "%~dp0"

REM Try to find Python - check multiple locations
set PYTHON_CMD=

REM First, try python in PATH (system Python or activated conda)
python --version >nul 2>&1
if %ERRORLEVEL% == 0 (
    set PYTHON_CMD=python
    echo Using Python from PATH
    goto :run_server
)

REM Try conda environment Python
if exist "C:\Users\dcaffaro\Anaconda3\envs\nordenv\python.exe" (
    set PYTHON_CMD=C:\Users\dcaffaro\Anaconda3\envs\nordenv\python.exe
    echo Using Python from conda environment: nordenv
    goto :run_server
)

REM Try py launcher (Windows Python launcher)
py --version >nul 2>&1
if %ERRORLEVEL% == 0 (
    set PYTHON_CMD=py
    echo Using Python launcher (py)
    goto :run_server
)

REM If we get here, Python wasn't found
echo ERROR: Python not found!
echo.
echo Please ensure Python is:
echo 1. Installed and in your PATH, OR
echo 2. Conda environment is activated, OR
echo 3. Use 'py' launcher
echo.
pause
exit /b 1

:run_server
echo.
echo Starting Django server...
echo.
%PYTHON_CMD% manage.py runserver

pause

