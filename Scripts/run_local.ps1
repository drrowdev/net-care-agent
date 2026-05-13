# Local development launcher.
# Loads .env, ensures data dir exists, starts Flask in debug mode.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path .env)) {
    Write-Host "No .env found. Copy .env.example to .env and set ANTHROPIC_API_KEY." -ForegroundColor Yellow
    exit 1
}

# Default DATA_DIR for local dev so the app does not try to write to /home/data.
if (-not $env:DATA_DIR) { $env:DATA_DIR = (Join-Path $root "data") }
New-Item -ItemType Directory -Force -Path $env:DATA_DIR | Out-Null

$env:FLASK_DEBUG = "1"
python app.py --port ($env:PORT ?? 8000)
