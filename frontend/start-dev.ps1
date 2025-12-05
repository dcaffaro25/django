# React Development Server Startup Script
Write-Host "Starting React Development Server..." -ForegroundColor Green
Write-Host ""

# Check if node_modules exists
if (-not (Test-Path "node_modules")) {
    Write-Host "Installing dependencies first..." -ForegroundColor Yellow
    npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "ERROR: npm install failed. Make sure Node.js is installed." -ForegroundColor Red
        Write-Host "Download Node.js from: https://nodejs.org/" -ForegroundColor Yellow
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Host ""
    Write-Host "Dependencies installed successfully!" -ForegroundColor Green
    Write-Host ""
}

# Check if .env exists
if (-not (Test-Path ".env")) {
    Write-Host "Creating .env file..." -ForegroundColor Yellow
    "VITE_API_BASE_URL=http://localhost:8000" | Out-File -FilePath ".env" -Encoding utf8
    Write-Host ""
    Write-Host ".env file created with default API URL." -ForegroundColor Green
    Write-Host "Edit .env if you need to change the API URL." -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "Starting development server..." -ForegroundColor Green
Write-Host ""
npm run dev

