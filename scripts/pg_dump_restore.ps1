# PostgreSQL Database Dump and Restore Script
# Dumps production database and restores to homologation database

$ErrorActionPreference = "Stop"

# PostgreSQL bin path
$pgDumpPath = "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe"
$pgRestorePath = "C:\Program Files\PostgreSQL\18\bin\pg_restore.exe"
$psqlPath = "C:\Program Files\PostgreSQL\18\bin\psql.exe"

# Database credentials
$prodHost = "switchback.proxy.rlwy.net"
$prodPort = 17976
$prodUser = "postgres"
$prodPassword = "a9X9kk28TgaZC_HCHo9iMawHs.ywEbvK"
$prodDatabase = "railway"

$homologHost = "shuttle.proxy.rlwy.net"
$homologPort = 24040
$homologUser = "postgres"
$homologPassword = "sSA2Muz8HZRL9CEzk0B1bEXfQkd84hRj"
$homologDatabase = "railway"

# Dump file
$dumpFile = "production_dump_$(Get-Date -Format 'yyyyMMdd_HHmmss').dump"

Write-Host ""
Write-Host ("="*70) -ForegroundColor Cyan
Write-Host "  PostgreSQL Database Dump and Restore" -ForegroundColor Cyan
Write-Host "  Production -> Homologation" -ForegroundColor Cyan
Write-Host ("="*70) -ForegroundColor Cyan

# Step 1: Dump production database
Write-Host "`n[Step 1/3] Dumping production database..." -ForegroundColor Yellow
Write-Host "  Source: $prodHost`:$prodPort/$prodDatabase" -ForegroundColor Gray
Write-Host "  Output: $dumpFile" -ForegroundColor Gray

$env:PGPASSWORD = $prodPassword
$dumpArgs = @(
    "-h", $prodHost,
    "-p", $prodPort,
    "-U", $prodUser,
    "-d", $prodDatabase,
    "-F", "c",  # Custom format
    "-f", $dumpFile
)

try {
    Write-Host "  Running pg_dump (this may take a while)..." -ForegroundColor DarkGray
    $dumpProcess = Start-Process -FilePath $pgDumpPath -ArgumentList $dumpArgs -Wait -PassThru -NoNewWindow -RedirectStandardError "dump_errors.txt"
    
    if ($dumpProcess.ExitCode -ne 0) {
        $errorContent = Get-Content "dump_errors.txt" -ErrorAction SilentlyContinue
        if ($errorContent) {
            Write-Host "  Error output:" -ForegroundColor Red
            $errorContent | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
        }
        throw "pg_dump failed with exit code $($dumpProcess.ExitCode)"
    }
    
    Remove-Item "dump_errors.txt" -ErrorAction SilentlyContinue
    
    $dumpSize = (Get-Item $dumpFile).Length / 1MB
    $dumpSizeMB = [math]::Round($dumpSize, 2)
    Write-Host "  [OK] Dump completed successfully! ($dumpSizeMB MB)" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] Dump failed: $_" -ForegroundColor Red
    if (Test-Path $dumpFile) {
        Remove-Item $dumpFile -Force
    }
    exit 1
}

# Step 2: Drop and recreate homologation database (clean restore)
Write-Host "`n[Step 2/3] Preparing homologation database..." -ForegroundColor Yellow
Write-Host "  Target: $homologHost`:$homologPort/$homologDatabase" -ForegroundColor Gray

$env:PGPASSWORD = $homologPassword

# Connect to postgres database to drop/recreate
try {
    # Terminate existing connections
    Write-Host "  Terminating existing connections..." -ForegroundColor DarkGray
    $terminateQuery = "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$homologDatabase' AND pid != pg_backend_pid();"
    & $psqlPath -h $homologHost -p $homologPort -U $homologUser -d postgres -c $terminateQuery 2>&1 | Out-Null
    
    # Drop database
    Write-Host "  Dropping existing database..." -ForegroundColor DarkGray
    & $psqlPath -h $homologHost -p $homologPort -U $homologUser -d postgres -c "DROP DATABASE IF EXISTS $homologDatabase;" 2>&1 | Out-Null
    
    # Create database
    Write-Host "  Creating new database..." -ForegroundColor DarkGray
    & $psqlPath -h $homologHost -p $homologPort -U $homologUser -d postgres -c "CREATE DATABASE $homologDatabase;" 2>&1 | Out-Null
    
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to prepare database"
    }
    
    Write-Host "  [OK] Database prepared successfully!" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] Failed to prepare database: $_" -ForegroundColor Red
    if (Test-Path $dumpFile) {
        Remove-Item $dumpFile -Force
    }
    exit 1
}

# Step 3: Restore to homologation database
Write-Host "`n[Step 3/3] Restoring to homologation database..." -ForegroundColor Yellow

$restoreArgs = @(
    "-h", $homologHost,
    "-p", $homologPort,
    "-U", $homologUser,
    "-d", $homologDatabase,
    "--no-owner",
    "--no-acl",
    $dumpFile
)

try {
    Write-Host "  Running pg_restore (this may take a while)..." -ForegroundColor DarkGray
    $restoreProcess = Start-Process -FilePath $pgRestorePath -ArgumentList $restoreArgs -Wait -PassThru -NoNewWindow -RedirectStandardError "restore_errors.txt"
    
    if ($restoreProcess.ExitCode -ne 0) {
        $errorContent = Get-Content "restore_errors.txt" -ErrorAction SilentlyContinue
        if ($errorContent) {
            Write-Host "  Error output:" -ForegroundColor Red
            $errorContent | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
        }
        throw "pg_restore failed with exit code $($restoreProcess.ExitCode)"
    }
    
    Remove-Item "restore_errors.txt" -ErrorAction SilentlyContinue
    
    Write-Host "  [OK] Restore completed successfully!" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] Restore failed: $_" -ForegroundColor Red
    exit 1
}

# Cleanup
Write-Host "`n[Cleanup] Removing dump file..." -ForegroundColor Yellow
if (Test-Path $dumpFile) {
    Remove-Item $dumpFile -Force
    Write-Host "  [OK] Dump file removed" -ForegroundColor Green
}

Write-Host ""
Write-Host ("="*70) -ForegroundColor Cyan
Write-Host "  COMPLETE! Database successfully cloned." -ForegroundColor Green
Write-Host ("="*70) -ForegroundColor Cyan
Write-Host ""

