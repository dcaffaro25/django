@echo off
REM ============================================
REM Run Celery Worker in Local Development Mode
REM ============================================
REM This script starts a Celery worker that processes tasks
REM from the homologation database (configured in local_credentials.ini)
REM
REM Prerequisites:
REM 1. Copy local_credentials.example.ini to local_credentials.ini
REM 2. Fill in the database and Redis credentials
REM 3. Start Redis locally: docker run -d -p 6379:6379 redis:alpine
REM    OR install Redis for Windows
REM
REM Usage:
REM   run_celery_local.bat           - Start with default settings
REM   run_celery_local.bat beat      - Start Celery Beat scheduler
REM   run_celery_local.bat flower    - Start Flower monitoring UI
REM ============================================

echo.
echo ============================================
echo    NORD BACKEND - LOCAL CELERY WORKER
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
if "%1"=="beat" (
    echo Starting Celery Beat scheduler...
    celery -A nord_backend beat --loglevel=info
    goto :end
)

if "%1"=="flower" (
    echo Starting Flower monitoring UI...
    echo Open http://localhost:5555 in your browser
    celery -A nord_backend flower --port=5555
    goto :end
)

if "%1"=="all" (
    echo Starting Celery Worker with all queues...
    celery -A nord_backend worker --loglevel=info --queues=celery,recon_legacy,recon_fast --concurrency=4
    goto :end
)

REM Default: start worker
echo Starting Celery Worker...
echo.
echo Queues: celery, recon_legacy, recon_fast
echo Concurrency: 4 workers
echo.
echo Press Ctrl+C to stop
echo.
celery -A nord_backend worker --loglevel=info --queues=celery,recon_legacy,recon_fast --concurrency=4

:end

