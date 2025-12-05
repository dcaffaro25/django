@echo off
:: Navigate to the Django project root
cd /d "%~dp0"

:: Try to find Python - check multiple locations
set PYTHON_CMD=

:: First, try python in PATH (system Python or activated conda)
python --version >nul 2>&1
if %ERRORLEVEL% == 0 (
    set PYTHON_CMD=python
    goto :run_server
)

:: Try conda environment Python
if exist "C:\Users\dcaffaro\Anaconda3\envs\nordenv\python.exe" (
    set PYTHON_CMD=C:\Users\dcaffaro\Anaconda3\envs\nordenv\python.exe
    goto :run_server
)

:: Try py launcher
py --version >nul 2>&1
if %ERRORLEVEL% == 0 (
    set PYTHON_CMD=py
    goto :run_server
)

:: If conda is available, try to activate and use it
if exist "C:\Users\dcaffaro\Anaconda3\Scripts\activate.bat" (
    start "Django Server" cmd /k "C:\Users\dcaffaro\Anaconda3\Scripts\activate.bat nordenv && python manage.py runserver"
    goto :end
)

:: If we get here, Python wasn't found
echo ERROR: Python not found!
echo Please ensure Python is installed and in your PATH
pause
exit /b 1

:run_server
start "Django Server" cmd /k "%PYTHON_CMD% manage.py runserver"

:end


pause
