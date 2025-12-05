# Django Development Server Startup Script for PowerShell
Write-Host "Starting Django Development Server..." -ForegroundColor Green
Write-Host ""

# Try to find Python - check multiple locations
$pythonCmd = $null

# First, try python in PATH (system Python or activated conda)
try {
    $null = python --version 2>&1
    $pythonCmd = "python"
    Write-Host "Using Python from PATH" -ForegroundColor Green
} catch {
    # Try conda environment Python
    $condaPath = "C:\Users\dcaffaro\Anaconda3\envs\nordenv\python.exe"
    if (Test-Path $condaPath) {
        $pythonCmd = $condaPath
        Write-Host "Using Python from conda environment: nordenv" -ForegroundColor Green
    } else {
        # Try py launcher (Windows Python launcher)
        try {
            $null = py --version 2>&1
            $pythonCmd = "py"
            Write-Host "Using Python launcher (py)" -ForegroundColor Green
        } catch {
            # Try to find Python in common locations
            $commonPaths = @(
                "$env:LOCALAPPDATA\Programs\Python\Python*\python.exe",
                "C:\Python*\python.exe",
                "C:\Program Files\Python*\python.exe"
            )
            
            foreach ($pattern in $commonPaths) {
                $found = Get-ChildItem -Path $pattern -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($found) {
                    $pythonCmd = $found.FullName
                    Write-Host "Found Python at: $pythonCmd" -ForegroundColor Green
                    break
                }
            }
        }
    }
}

if ($null -eq $pythonCmd) {
    Write-Host ""
    Write-Host "ERROR: Python not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please ensure Python is:" -ForegroundColor Yellow
    Write-Host "1. Installed and in your PATH, OR" -ForegroundColor Yellow
    Write-Host "2. Conda environment is activated, OR" -ForegroundColor Yellow
    Write-Host "3. Use 'py' launcher" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Or use Command Prompt: start-django-server.bat" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "Starting Django server..." -ForegroundColor Yellow
Write-Host ""

# Start Django server
& $pythonCmd manage.py runserver

