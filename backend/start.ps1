# One command to start everything: activates the virtual environment,
# then starts the backend server (which loads the database and all AI
# models automatically on startup).
#
# Run from the backend folder:  .\start.ps1
# Or from anywhere:              powershell -File backend\start.ps1
#
# No --reload (changed 2026-09-29). Auto-reload restarts the server whenever
# a .py file is saved, but on this Windows setup the restarted copy never
# came up: measured, the server stopped completely about 100 seconds after
# any file change. A demo never needs auto-reload, and without it the
# backend is one process instead of two. After editing backend code, stop
# the server (Ctrl+C) and run this script again.

Set-Location $PSScriptRoot

# Port 8000 already taken? If it's an older TrustLens backend from this
# folder (e.g. one left running in another window), stop it so this one can
# start, instead of failing with "only one usage of each socket address".
# Anything else on port 8000 is left alone and explained.
$busy = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
foreach ($conn in $busy) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($conn.OwningProcess)" -ErrorAction SilentlyContinue
    if ($proc -and $proc.CommandLine -like "*$PSScriptRoot*" -and $proc.CommandLine -like "*main:app*") {
        Write-Host "An older TrustLens backend was already running on port 8000. Stopping it and starting fresh..." -ForegroundColor Yellow
        Stop-Process -Id $conn.OwningProcess -Force
        Start-Sleep -Seconds 2
    } elseif ($proc) {
        Write-Host "Port 8000 is being used by another program: $($proc.Name) (process $($conn.OwningProcess))." -ForegroundColor Red
        Write-Host "Close that program, then run .\start.ps1 again." -ForegroundColor Red
        exit 1
    }
}

& "$PSScriptRoot\venv\Scripts\Activate.ps1"
uvicorn main:app --port 8000
