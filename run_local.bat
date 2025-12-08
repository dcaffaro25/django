@echo off
REM ============================================
REM Run Django in Local Development Mode
REM ============================================
REM This script starts Django server using the homologation database
REM (configured in local_credentials.ini)
REM
REM CELERY TASKS RUN SYNCHRONOUSLY - No Redis or Celery worker needed!
REM All task.delay() calls execute immediately in the Django process.
REM
REM Prerequisites:
REM 1. Copy local_credentials.example.ini to local_credentials.ini
REM 2. Fill in the database credentials
REM
REM Usage:
REM   run_local.bat                  - Start Django dev server
REM   run_local.bat migrate          - Run migrations
REM   run_local.bat shell            - Open Django shell
REM   run_local.bat clone            - Clone production to homolog
REM   run_local.bat test             - Run tests
REM ============================================

echo.
echo ============================================
echo    NORD BACKEND - LOCAL DEVELOPMENT
echo ============================================
echo.

REM Check if local_credentials.ini exists
if not exist "local_credentials.ini" (
    echo ERROR: local_credentials.ini not found!
    echo.
    echo Please copy local_credentials.example.ini to local_credentials.ini
    echo and fill in the required credentials.
    echo.
    pause
    exit /b 1
)

REM Set environment
set DJANGO_SETTINGS_MODULE=nord_backend.settings

REM Check for arguments
if "%1"=="migrate" (
    echo Running migrations on homologation database...
    python manage.py migrate
    goto :end
)

if "%1"=="shell" (
    echo Opening Django shell...
    python manage.py shell
    goto :end
)

if "%1"=="clone" (
    echo.
    echo ============================================
    echo    CLONE PRODUCTION TO HOMOLOGATION
    echo ============================================
    echo.
    echo This will copy data from production to your local homologation database.
    echo Make sure you have configured both databases in local_credentials.ini
    echo.
    
    if "%2"=="--dry-run" (
        python manage.py clone_to_homolog --dry-run --verbose
    ) else if "%2"=="--reset" (
        python manage.py clone_to_homolog --reset --verbose
    ) else (
        python manage.py clone_to_homolog --verbose
    )
    goto :end
)

if "%1"=="test" (
    echo Running tests...
    python manage.py test %2 %3 %4 %5
    goto :end
)

if "%1"=="check" (
    echo Running system checks...
    python manage.py check
    python manage.py showmigrations
    goto :end
)

REM Default: start server
echo Starting Django development server...
echo.
echo Server will be available at: http://localhost:8000
echo.
echo Press Ctrl+C to stop
echo.
python manage.py runserver 0.0.0.0:8000

:end

