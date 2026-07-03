# Test-gated deploy with rollback (architecture-review P8-minimal).
# Refuses to build/ship unless pytest + ruff (+ gitleaks if present) pass, retains
# the previous deployed zip for a one-command rollback, and verifies health.
#
# Usage:
#   pwsh scripts/deploy.ps1 -App <app-service> -SkipGitleaks   # deploy
#   pwsh scripts/deploy.ps1 -App <app-service> -Rollback       # re-ship last-good zip
#
# The Azure resource group / app name live in your private operator runbook, not
# the repo. Requires: az CLI logged in, Python venv active.

param(
    [Parameter(Mandatory = $true)][string]$App,
    [switch]$Rollback,
    [switch]$SkipGitleaks
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$zip = Join-Path $env:TEMP "net-care-deploy.zip"
$prev = Join-Path $root "deploy.prev.zip"
$scm = "https://$App.scm.azurewebsites.net/api/zipdeploy?isAsync=false"

function Get-MgmtToken { az account get-access-token --resource https://management.azure.com --query accessToken -o tsv }

if ($Rollback) {
    if (-not (Test-Path $prev)) { throw "No deploy.prev.zip to roll back to." }
    Write-Host "Rolling back: re-shipping $prev" -ForegroundColor Yellow
    $tok = Get-MgmtToken
    Invoke-WebRequest -Uri $scm -Method POST -Headers @{Authorization = "Bearer $tok" } `
        -InFile $prev -ContentType "application/zip" -TimeoutSec 600 -UseBasicParsing | Out-Null
    Write-Host "Rollback deployed. Verify /api/health from a signed-in browser." -ForegroundColor Green
    exit 0
}

# ---- Gate: tests + lint must pass BEFORE we build a zip ----
Write-Host "== pytest ==" -ForegroundColor Cyan
python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "pytest failed — refusing to deploy." }

Write-Host "== ruff ==" -ForegroundColor Cyan
ruff check agent tests
if ($LASTEXITCODE -ne 0) { throw "ruff failed — refusing to deploy." }

if (-not $SkipGitleaks -and (Get-Command gitleaks -ErrorAction SilentlyContinue)) {
    Write-Host "== gitleaks ==" -ForegroundColor Cyan
    gitleaks detect --no-banner
    if ($LASTEXITCODE -ne 0) { throw "gitleaks found secrets — refusing to deploy." }
}

# ---- Retain the previous deployed zip, then build the new one ----
if (Test-Path $zip) { Copy-Item $zip $prev -Force; Write-Host "Kept previous zip as deploy.prev.zip" }

Write-Host "== building deploy.zip ==" -ForegroundColor Cyan
python -c @"
import zipfile, os
z = zipfile.ZipFile(r'$zip', 'w', zipfile.ZIP_DEFLATED)
incl = ['app.py', 'net_agent.py', 'requirements.txt', 'startup.sh']
dirs = ['agent', 'static', 'templates']
[z.write(f, f) for f in incl if os.path.exists(f)]
[z.write(os.path.join(r, f), os.path.join(r, f))
 for d in dirs for r, _, fs in os.walk(d)
 if '__pycache__' not in r and '.pytest_cache' not in r
 for f in fs if not f.endswith('.pyc')]
z.close()
print('files in zip:', len(z.namelist()))
"@
if ($LASTEXITCODE -ne 0) { throw "zip build failed." }

# ---- Deploy via Kudu ----
Write-Host "== deploying to $App ==" -ForegroundColor Cyan
$tok = Get-MgmtToken
$resp = Invoke-WebRequest -Uri $scm -Method POST -Headers @{Authorization = "Bearer $tok" } `
    -InFile $zip -ContentType "application/zip" -TimeoutSec 600 -UseBasicParsing
Write-Host "Kudu status: $($resp.StatusCode)"

# ---- Verify ----
Start-Sleep -Seconds 20
$code = (Invoke-WebRequest -Uri "https://$App.azurewebsites.net/api/health" -UseBasicParsing -SkipHttpErrorCheck).StatusCode
Write-Host "Deployed. /api/health returned $code (200 = up; 401 = Easy Auth up)." -ForegroundColor Green
Write-Host "Rollback if needed: pwsh scripts/deploy.ps1 -App $App -Rollback"
