@echo off
echo Starting React Development Server...
echo.

REM Check if node_modules exists
if not exist "node_modules" (
    echo Installing dependencies first...
    call npm install
    if errorlevel 1 (
        echo.
        echo ERROR: npm install failed. Make sure Node.js is installed.
        echo Download Node.js from: https://nodejs.org/
        pause
        exit /b 1
    )
    echo.
    echo Dependencies installed successfully!
    echo.
)

REM Check if .env exists
if not exist ".env" (
    echo Creating .env file...
    echo VITE_API_BASE_URL=http://localhost:8000 > .env
    echo.
    echo .env file created with default API URL.
    echo Edit .env if you need to change the API URL.
    echo.
)

echo Starting development server...
echo.
call npm run dev

pause

