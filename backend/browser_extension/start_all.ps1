# ---------------------------------------------------------------------------
# Starts everything the TrustLens browser extension needs, each in its own
# window so you can see its logs.
#
#   Close a window to stop that part. Closing THIS window stops nothing.
#
# Run:  powershell -ExecutionPolicy Bypass -File start_all.ps1
#
# WHAT RUNS (changed 2026-09-28)
# ------------------------------
# 1. The TrustLens website backend (port 8000). It holds the misinformation
#    model and the fake-account model, and serves them to the extension too.
#    If it's already running (you started the website with start.ps1), it is
#    reused, not started twice.
# 2. The extension gateway (port 8100): reads the reel, fetches Instagram data
#    through RapidAPI, listens to the audio, and builds the badge.
#
# Before this change the extension started its own two model services (ports
# 8001 and 8002), each loading a SECOND copy of models the website already had
# in memory. On a friend's 8 GB laptop that ran Windows out of memory and the
# misinformation service was killed a few reels in. Now there is one copy of
# each model, shared by the website and the extension.
#
# If a window's program ever stops (for example it crashed), it restarts by
# itself instead of silently staying down.
# ---------------------------------------------------------------------------

$ErrorActionPreference = "Stop"

# This file lives in backend/browser_extension, so the backend is one level
# up. Resolved from the script's own location, so it works from any clone.
$Gateway = Join-Path $PSScriptRoot "gateway"
$Backend = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python  = Join-Path $Backend "venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "Could not find the backend venv at $Python" -ForegroundColor Red
    Write-Host "Create it first, or fix the path at the top of this script."
    exit 1
}

function Start-Service-Window($Title, $WorkDir, $Command) {
    Write-Host "  start $Title" -ForegroundColor Green
    $Loop = "while (`$true) { $Command; Write-Host 'Stopped - restarting in 3 seconds (close this window to stop it for good).' -ForegroundColor Yellow; Start-Sleep 3 }"
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "`$Host.UI.RawUI.WindowTitle='TrustLens - $Title'; Set-Location '$WorkDir'; $Loop"
    )
}

function Test-Url($Url) {
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return $r.StatusCode -lt 400
    } catch {
        return $false
    }
}

Write-Host "`nStarting TrustLens for the browser extension...`n" -ForegroundColor Cyan

# 1. Website backend (holds the models).
if (Test-Url "http://127.0.0.1:8000/ext/classifier/health") {
    Write-Host "  reuse the TrustLens website backend that's already running on port 8000" -ForegroundColor Green
} elseif (Test-Url "http://127.0.0.1:8000/") {
    Write-Host "  Something is already running on port 8000 but it's an OLDER TrustLens backend" -ForegroundColor Yellow
    Write-Host "  (it doesn't share its models with the extension yet). Close that window," -ForegroundColor Yellow
    Write-Host "  then run this script again." -ForegroundColor Yellow
    exit 1
} else {
    Start-Service-Window "website backend :8000" $Backend `
        "& '$Python' -m uvicorn main:app --port 8000"
}

# 2. The gateway the extension talks to.
if (Test-Url "http://127.0.0.1:8100/") {
    Write-Host "  the gateway is already running on port 8100 (close its window first to restart it)" -ForegroundColor Yellow
} else {
    Start-Service-Window "extension gateway :8100" $Gateway `
        "& '$Python' -m uvicorn main:app --port 8100"
}

Write-Host "`nGive it about 30 seconds (the models are loading), then open the extension" -ForegroundColor Cyan
Write-Host "popup: every dot should be green. Yellow 'loading...' means wait a little longer."
Write-Host "The very first start on a new laptop also downloads the speech model (~150 MB).`n"
