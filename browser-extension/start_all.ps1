# ---------------------------------------------------------------------------
# Starts the four TrustLens services, each in its own window so you can see its
# logs and stop it individually.
#
#   Ctrl+C in a window stops that service. Closing this window does not stop them.
#
# Run:  powershell -ExecutionPolicy Bypass -File start_all.ps1
# ---------------------------------------------------------------------------

$ErrorActionPreference = "Stop"

$Transcriber = "D:\video-to-text transcriber"
$PostChecker = "D:\trustlens_post_checker"
$Gateway     = "D:\trustlens-extension\gateway"

function Start-Service-Window($Title, $WorkDir, $Command) {
    if (-not (Test-Path $WorkDir)) {
        Write-Host "  SKIP  $Title  — not found at $WorkDir" -ForegroundColor Yellow
        return
    }
    Write-Host "  start $Title" -ForegroundColor Green
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "`$Host.UI.RawUI.WindowTitle='TrustLens - $Title'; Set-Location '$WorkDir'; $Command"
    )
}

Write-Host "`nStarting TrustLens services...`n" -ForegroundColor Cyan

# 1. Video-to-text transcriber (port 8000) — its own venv.
Start-Service-Window "transcriber :8000" $Transcriber ".\.venv\Scripts\python.exe run.py"

# 2. Misinformation / post checker (port 8001) — its own venv, loads a 1 GB model.
Start-Service-Window "classifier :8001" "$PostChecker\app" `
    "..\venv\Scripts\python.exe -m uvicorn main:app --port 8001"

# 3. Fake-follower account model (port 8002) — reads the artifacts in place.
Start-Service-Window "account model :8002" $Gateway `
    "py -3 -m uvicorn follower_api:app --port 8002"

# 4. The gateway the extension talks to (port 8100).
Start-Service-Window "gateway :8100" $Gateway `
    "py -3 -m uvicorn main:app --port 8100"

Write-Host "`nGive them ~30s (the classifier loads a 1 GB model), then check:" -ForegroundColor Cyan
Write-Host "  http://127.0.0.1:8100/health`n"
Write-Host "The extension popup shows the same status with a dot per service.`n"
