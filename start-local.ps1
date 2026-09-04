$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendRoot = Join-Path $ProjectRoot "backend"
$VenvRoot = Join-Path $BackendRoot ".venv"
$PythonExe = Join-Path $VenvRoot "Scripts\python.exe"
$LocalUrl = "http://127.0.0.1:8765/?v=scanner-avatar-final"

try {
    $Existing = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/health" -TimeoutSec 2
    if ($Existing.ok -and $Existing.api_version -eq "4.2.0") {
        Write-Host "Bling local wardrobe is already running." -ForegroundColor Green
        Write-Host "Opening the correct local page..." -ForegroundColor Cyan
        Start-Process $LocalUrl | Out-Null
        exit 0
    }
    if ($Existing.ok) {
        Write-Host "Replacing an older Bling local service..." -ForegroundColor Cyan
        $Listener = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($Listener) {
            $ListenerProcess = Get-Process -Id $Listener.OwningProcess -ErrorAction SilentlyContinue
            if ($ListenerProcess -and $ListenerProcess.ProcessName -match "^python(w)?$") {
                Stop-Process -Id $Listener.OwningProcess -Force
                Start-Sleep -Milliseconds 600
            } else {
                throw "Port 8765 is occupied by another program. Close that program, then run this launcher again."
            }
        }
    }
} catch { }

if (-not (Test-Path -LiteralPath $PythonExe)) {
    Write-Host "Creating the Bling local environment..." -ForegroundColor Magenta
    $BootstrapPython = $null
    if (Get-Command py -ErrorAction SilentlyContinue) { $BootstrapPython = "py" }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { $BootstrapPython = "python" }
    else {
        $CodexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
        if (Test-Path -LiteralPath $CodexPython) { $BootstrapPython = $CodexPython }
    }
    if (-not $BootstrapPython) { throw "Python 3.12 was not found. Install 64-bit Python from python.org and run this launcher again." }
    if ($BootstrapPython -eq "py") { & py -3 -m venv $VenvRoot } else { & $BootstrapPython -m venv $VenvRoot }
}

$RequirementsFile = Join-Path $BackendRoot "requirements.txt"
$InstallMarker = Join-Path $VenvRoot ".bling-dependencies-ready"
if (-not (Test-Path -LiteralPath $InstallMarker) -or (Get-Item $RequirementsFile).LastWriteTimeUtc -gt (Get-Item $InstallMarker -ErrorAction SilentlyContinue).LastWriteTimeUtc) {
    Write-Host "Installing local image-processing components. The first run can take several minutes." -ForegroundColor Cyan
    & $PythonExe -m pip install --disable-pip-version-check -r $RequirementsFile
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed. Check the messages above and run the launcher again." }
    New-Item -ItemType File -Path $InstallMarker -Force | Out-Null
    Write-Host "Local components installed successfully." -ForegroundColor Green
}
$env:BLING_DATA_DIR = Join-Path $ProjectRoot "data"
$env:BLING_MODEL_DIR = Join-Path $BackendRoot "model_data"
$env:BLING_LOCAL_ORIGIN = "http://127.0.0.1:8765"
$env:BLING_PUBLIC_BASE_URL = "http://127.0.0.1:8765"

Set-Location $BackendRoot
$Server = Start-Process -FilePath $PythonExe -ArgumentList @(
    "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8765"
) -WorkingDirectory $BackendRoot -WindowStyle Hidden -PassThru

$Ready = $false
for ($Attempt = 0; $Attempt -lt 60; $Attempt++) {
    if ($Server.HasExited) { throw "The local service stopped during startup. Run this launcher again to see the installation error." }
    try {
        $Health = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/health" -TimeoutSec 2
        if ($Health.ok) { $Ready = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 500
}
if (-not $Ready) {
    Stop-Process -Id $Server.Id -Force -ErrorAction SilentlyContinue
    throw "The local service did not become ready within 30 seconds."
}

Write-Host "Bling local wardrobe is running at http://127.0.0.1:8765" -ForegroundColor Green
Write-Host "Keep this window open while using Bling. Press Ctrl+C to stop." -ForegroundColor DarkGray
Start-Process $LocalUrl | Out-Null
try {
    Wait-Process -Id $Server.Id
} finally {
    if (-not $Server.HasExited) { Stop-Process -Id $Server.Id -Force -ErrorAction SilentlyContinue }
}
