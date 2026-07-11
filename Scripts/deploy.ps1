# Test-gated, asynchronous Kudu deployment with verified rollback.
#
# Usage:
#   pwsh Scripts/deploy.ps1 -App <app-service>
#   pwsh Scripts/deploy.ps1 -App <app-service> -Rollback
#
# Requires an authenticated Azure CLI session, Python, ruff, and gitleaks.

param(
    [Parameter(Mandatory = $true)][string]$App,
    [switch]$Rollback,
    [int]$DeploymentTimeoutSeconds = 900,
    [int]$HealthTimeoutSeconds = 300
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$stateDir = Join-Path $root ".deploy"
$releaseDir = Join-Path $stateDir "releases"
$buildDir = Join-Path $stateDir "build"
$buildZip = Join-Path $buildDir "net-care-deploy.zip"
$currentZip = Join-Path $stateDir "current-verified.zip"
$currentSha = Join-Path $stateDir "current-verified.sha256"
$currentCommit = Join-Path $stateDir "current-verified.commit"
$previousZip = Join-Path $stateDir "previous-known-good.zip"
$previousSha = Join-Path $stateDir "previous-known-good.sha256"
$previousCommit = Join-Path $stateDir "previous-known-good.commit"
$scmBase = "https://$App.scm.azurewebsites.net"
$zipDeployUri = "$scmBase/api/zipdeploy?isAsync=true"

function Get-AuthHeaders {
    $token = az account get-access-token --resource https://management.azure.com `
        --query accessToken -o tsv
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($token)) {
        throw "Unable to obtain an Azure access token."
    }
    return @{ Authorization = "Bearer $($token.Trim())" }
}

function Assert-HttpSuccess {
    param(
        [Parameter(Mandatory = $true)]$Response,
        [Parameter(Mandatory = $true)][string]$Operation
    )

    $statusCode = [int]$Response.StatusCode
    if ($statusCode -lt 200 -or $statusCode -ge 300) {
        throw "$Operation returned HTTP $statusCode."
    }
}

function Resolve-DeploymentUri {
    param([Parameter(Mandatory = $true)]$Response)

    $location = $Response.Headers["Location"]
    if ($location -is [array]) { $location = $location[0] }
    if ([string]::IsNullOrWhiteSpace([string]$location)) {
        throw "Kudu did not return an exact deployment status URI."
    }
    return ([Uri]::new([Uri]$scmBase, [string]$location)).AbsoluteUri
}

function Wait-KuduDeployment {
    param(
        [Parameter(Mandatory = $true)][string]$DeploymentUri,
        [Parameter(Mandatory = $true)][hashtable]$Headers
    )

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($DeploymentTimeoutSeconds)
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        $response = Invoke-WebRequest -Uri $DeploymentUri -Method GET -Headers $Headers `
            -TimeoutSec 60 -UseBasicParsing
        Assert-HttpSuccess $response "Kudu deployment status"
        $deployment = $response.Content | ConvertFrom-Json
        $status = [int]$deployment.status

        if ($status -eq 4) {
            Write-Host "Kudu deployment succeeded." -ForegroundColor Green
            return
        }
        if ($status -eq 3) {
            throw "Kudu deployment failed."
        }
        if ($status -lt 0 -or $status -gt 4) {
            throw "Kudu returned unknown deployment status $status."
        }

        Start-Sleep -Seconds 5
    }
    throw "Kudu deployment timed out after $DeploymentTimeoutSeconds seconds."
}

function Send-KuduPackage {
    param([Parameter(Mandatory = $true)][string]$Package)

    $headers = Get-AuthHeaders
    $response = Invoke-WebRequest -Uri $zipDeployUri -Method POST -Headers $headers `
        -InFile $Package -ContentType "application/zip" -TimeoutSec 600 -UseBasicParsing
    Assert-HttpSuccess $response "Kudu package upload"
    Write-Host "Kudu accepted package upload with HTTP $($response.StatusCode)."
    $deploymentUri = Resolve-DeploymentUri $response
    Wait-KuduDeployment -DeploymentUri $deploymentUri -Headers $headers
}

function Wait-VerifiedHealth {
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($HealthTimeoutSeconds)
    $appHealthUri = "https://$App.azurewebsites.net/api/health"
    $lastError = "No readiness response received."

    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        try {
            $health = Invoke-WebRequest -Uri $appHealthUri -Method GET `
                -TimeoutSec 60 -UseBasicParsing
            Assert-HttpSuccess $health "Application health check"
            $healthBody = $health.Content | ConvertFrom-Json
            if ($healthBody.status -notin @("ok", "degraded") -or
                -not $healthBody.data_dir_writable -or
                -not $healthBody.jobs_healthy) {
                throw "Application health check returned status '$($healthBody.status)'."
            }
            if ($healthBody.release_commit -ne $commit) {
                throw "Application health belongs to release '$($healthBody.release_commit)', not '$commit'."
            }
            # Send-KuduPackage already required authenticated terminal Kudu status.
            # The exact release_commit proves this response came from the new app
            # process; Kudu process enumeration is unsupported on Linux stacks.
            Write-Host "Authenticated Kudu deployment and exact application health passed." `
                -ForegroundColor Green
            return
        }
        catch {
            $lastError = $_.Exception.Message
            Start-Sleep -Seconds 5
        }
    }
    throw "Post-deploy health timed out after $HealthTimeoutSeconds seconds: $lastError"
}

function Confirm-PackageHash {
    param(
        [Parameter(Mandatory = $true)][string]$Package,
        [Parameter(Mandatory = $true)][string]$ShaRecord
    )

    $expected = ((Get-Content $ShaRecord -Raw).Trim() -split "\s+")[0]
    $actual = (Get-FileHash -Path $Package -Algorithm SHA256).Hash.ToLowerInvariant()
    if ([string]::IsNullOrWhiteSpace($expected) -or $actual -ne $expected.ToLowerInvariant()) {
        throw "Package SHA256 verification failed."
    }
}

function Confirm-PackageIdentity {
    param(
        [Parameter(Mandatory = $true)][string]$Package,
        [Parameter(Mandatory = $true)][string]$CommitRecord
    )

    $expected = (Get-Content $CommitRecord -Raw).Trim().ToLowerInvariant()
    if ($expected -notmatch "^[0-9a-f]{40}$") {
        throw "Package commit record is invalid."
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($Package)
    try {
        $entry = $archive.GetEntry("RELEASE_COMMIT")
        if ($null -eq $entry) { throw "Package does not contain RELEASE_COMMIT." }
        $reader = [System.IO.StreamReader]::new($entry.Open())
        try { $actual = $reader.ReadToEnd().Trim().ToLowerInvariant() }
        finally { $reader.Dispose() }
    }
    finally {
        $archive.Dispose()
    }
    if ($actual -ne $expected) {
        throw "Package commit verification failed."
    }
    return $expected
}

function Copy-VerifiedPackageSet {
    param(
        [Parameter(Mandatory = $true)][string]$SourceZip,
        [Parameter(Mandatory = $true)][string]$SourceSha,
        [Parameter(Mandatory = $true)][string]$SourceCommit,
        [Parameter(Mandatory = $true)][string]$DestinationZip,
        [Parameter(Mandatory = $true)][string]$DestinationSha,
        [Parameter(Mandatory = $true)][string]$DestinationCommit
    )

    Confirm-PackageHash -Package $SourceZip -ShaRecord $SourceSha
    [void](Confirm-PackageIdentity -Package $SourceZip -CommitRecord $SourceCommit)
    Copy-Item $SourceZip "$DestinationZip.new" -Force
    Copy-Item $SourceSha "$DestinationSha.new" -Force
    Copy-Item $SourceCommit "$DestinationCommit.new" -Force
    Move-Item "$DestinationZip.new" $DestinationZip -Force
    Move-Item "$DestinationSha.new" $DestinationSha -Force
    Move-Item "$DestinationCommit.new" $DestinationCommit -Force
}

if ($Rollback) {
    foreach ($required in @($previousZip, $previousSha, $previousCommit)) {
        if (-not (Test-Path $required -PathType Leaf)) {
            throw "No complete previous-known-good release is available for rollback."
        }
    }
    Confirm-PackageHash -Package $previousZip -ShaRecord $previousSha
    $commit = Confirm-PackageIdentity -Package $previousZip -CommitRecord $previousCommit
    Write-Host "Rolling back to commit $commit." `
        -ForegroundColor Yellow
    Send-KuduPackage -Package $previousZip
    Wait-VerifiedHealth
    Copy-VerifiedPackageSet `
        -SourceZip $previousZip -SourceSha $previousSha -SourceCommit $previousCommit `
        -DestinationZip $currentZip -DestinationSha $currentSha `
        -DestinationCommit $currentCommit
    Remove-Item @($previousZip, $previousSha, $previousCommit) -Force
    Write-Host "Rollback deployed and health verified." -ForegroundColor Green
    exit 0
}

# All gates are mandatory and run before a package is built.
$dirty = git status --porcelain
if ($LASTEXITCODE -ne 0 -or -not [string]::IsNullOrWhiteSpace(($dirty -join ""))) {
    throw "Working tree must be clean so the recorded commit exactly identifies the package."
}

Write-Host "== pytest ==" -ForegroundColor Cyan
python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "pytest failed - refusing to deploy." }

Write-Host "== ruff ==" -ForegroundColor Cyan
python -m ruff check agent tests app.py net_agent.py
if ($LASTEXITCODE -ne 0) { throw "ruff failed - refusing to deploy." }

$gitleaks = Get-Command gitleaks -ErrorAction SilentlyContinue
if (-not $gitleaks) { throw "gitleaks is required - refusing to deploy." }
Write-Host "== gitleaks ==" -ForegroundColor Cyan
& $gitleaks.Source detect --no-banner
if ($LASTEXITCODE -ne 0) { throw "gitleaks failed - refusing to deploy." }

New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
if (Test-Path $buildZip) { Remove-Item $buildZip -Force }

$commit = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($commit)) {
    throw "Unable to record the release commit."
}

Write-Host "== building Python deployment zip ==" -ForegroundColor Cyan
python -c @"
import os
import zipfile

archive = zipfile.ZipFile(r'$buildZip', 'w', zipfile.ZIP_DEFLATED)
archive.writestr('RELEASE_COMMIT', '$commit')
files = ['app.py', 'net_agent.py', 'requirements.txt', 'startup.sh', '.deployment']
directories = ['agent', 'static', 'templates']
for path in files:
    if os.path.exists(path):
        archive.write(path, path)
for directory in directories:
    for root, _, names in os.walk(directory):
        if '__pycache__' in root or '.pytest_cache' in root:
            continue
        for name in names:
            if not name.endswith('.pyc'):
                path = os.path.join(root, name)
                archive.write(path, path)
archive.close()
"@
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $buildZip -PathType Leaf)) {
    throw "Python zip build failed."
}

$sha256 = (Get-FileHash -Path $buildZip -Algorithm SHA256).Hash.ToLowerInvariant()
$releaseStem = "$commit-$sha256"
$releaseZip = Join-Path $releaseDir "$releaseStem.zip"
$releaseSha = Join-Path $releaseDir "$releaseStem.sha256"
$releaseCommit = Join-Path $releaseDir "$releaseStem.commit"
Copy-Item $buildZip $releaseZip -Force
Set-Content -Path $releaseSha -Value "$sha256  $releaseStem.zip" -Encoding ascii
Set-Content -Path $releaseCommit -Value $commit -Encoding ascii
Confirm-PackageHash -Package $releaseZip -ShaRecord $releaseSha
[void](Confirm-PackageIdentity -Package $releaseZip -CommitRecord $releaseCommit)

Write-Host "== deploying commit $commit to $App ==" -ForegroundColor Cyan
$currentFiles = @($currentZip, $currentSha, $currentCommit)
$currentCount = @($currentFiles | Where-Object { Test-Path $_ -PathType Leaf }).Count
if ($currentCount -notin @(0, 3)) {
    throw "Current verified package state is incomplete; automatic restore is unavailable."
}
if ($currentCount -eq 3) {
    Confirm-PackageHash -Package $currentZip -ShaRecord $currentSha
    $currentRestoreCommit = Confirm-PackageIdentity `
        -Package $currentZip -CommitRecord $currentCommit
}

try {
    Send-KuduPackage -Package $releaseZip
    Wait-VerifiedHealth
}
catch {
    $candidateFailure = $_.Exception
    if ($currentCount -ne 3) {
        throw "Candidate deployment failed; automatic restore is unavailable because no current verified package exists."
    }

    Write-Host "Candidate deployment failed; restoring current verified release." `
        -ForegroundColor Yellow
    try {
        Confirm-PackageHash -Package $currentZip -ShaRecord $currentSha
        $commit = Confirm-PackageIdentity -Package $currentZip -CommitRecord $currentCommit
        if ($commit -ne $currentRestoreCommit) {
            throw "Current verified package identity changed before automatic restore."
        }
        Send-KuduPackage -Package $currentZip
        Wait-VerifiedHealth
        Write-Host "Current verified release was restored and health verified." `
            -ForegroundColor Green
    }
    catch {
        throw "Candidate deployment failed and automatic restore of the current verified release also failed."
    }
    throw $candidateFailure
}

# Preserve the distinct prior verified package only after promoting this release.
if ($currentCount -eq 3) {
    $currentDigest = (Get-FileHash -Path $currentZip -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($currentDigest -ne $sha256) {
        Copy-VerifiedPackageSet `
            -SourceZip $currentZip -SourceSha $currentSha -SourceCommit $currentCommit `
            -DestinationZip $previousZip -DestinationSha $previousSha `
            -DestinationCommit $previousCommit
    }
}
Copy-VerifiedPackageSet `
    -SourceZip $releaseZip -SourceSha $releaseSha -SourceCommit $releaseCommit `
    -DestinationZip $currentZip -DestinationSha $currentSha -DestinationCommit $currentCommit
Remove-Item $buildZip -Force
Write-Host "Deployment is healthy and recorded as current-verified." -ForegroundColor Green
Write-Host "Rollback if needed: pwsh Scripts/deploy.ps1 -App $App -Rollback"
