@echo off
cd /d "%~dp0"

:: Try common Anaconda locations
set "CONDA_PATH="
if exist "%USERPROFILE%\Anaconda3\Scripts\activate.bat" set "CONDA_PATH=%USERPROFILE%\Anaconda3"
if exist "%USERPROFILE%\miniconda3\Scripts\activate.bat" set "CONDA_PATH=%USERPROFILE%\miniconda3"
if exist "%LOCALAPPDATA%\Continuum\anaconda3\Scripts\activate.bat" set "CONDA_PATH=%LOCALAPPDATA%\Continuum\anaconda3"

if defined CONDA_PATH (
    echo Found Anaconda at: %CONDA_PATH%
    call "%CONDA_PATH%\Scripts\activate.bat" nordenv
) else (
    echo Anaconda not found, using system Python...
    echo Installing required dependencies (this may take a few minutes)...
    pip install celery django-celery-results pgvector django-crum django-mptt meilisearch python-dotenv --quiet
)

echo.
echo Starting Django server...
python manage.py runserver

pause
