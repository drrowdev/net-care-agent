# Test-gated, asynchronous Kudu deployment with verified rollback.
#
# Usage:
#   pwsh Scripts/deploy.ps1 -App <app-service>
#   pwsh Scripts/deploy.ps1 -App <app-service> -Rollback
#
# Requires an authenticated Azure CLI session, Python, ruff, and gitleaks.
#
# Verified release packages are kept in a stable per-machine, per-app location
# (see Scripts/deploy-state.ps1), not inside the working copy, because
# deployments are run from throwaway git worktrees. Override the location with
# -StateRoot or NET_CARE_DEPLOY_STATE_ROOT.

param(
    [Parameter(Mandatory = $true)][string]$App,
    [switch]$Rollback,
    [string]$StateRoot,
    [int]$RetainReleases = 10,
    [int]$DeploymentTimeoutSeconds = 900,
    [int]$HealthTimeoutSeconds = 300
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

. (Join-Path $PSScriptRoot "deploy-state.ps1")

$paths = Get-DeployStatePaths -App $App -StateRoot $StateRoot
$legacyStateDir = Join-Path $root ".deploy"
$buildZip = $paths.BuildZip
$scmBase = "https://$App.scm.azurewebsites.net"
$zipDeployUri = "$scmBase/api/zipdeploy?isAsync=true"
$appHealthUri = "https://$App.azurewebsites.net/api/health"

function Get-AuthHeaders {
    $token = az account get-access-token --resource https://management.azure.com `
        --query accessToken -o tsv
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($token)) {
        throw "Unable to obtain an Azure access token."
    }
    return @{ Authorization = "******" }
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
    param([Parameter(Mandatory = $true)][string]$ExpectedCommit)

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($HealthTimeoutSeconds)
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
            if ($healthBody.release_commit -ne $ExpectedCommit) {
                throw "Application health belongs to release '$($healthBody.release_commit)', not '$ExpectedCommit'."
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

# Advisory only, and never allowed to fail a deployment: it answers "which
# release is actually serving right now", so an automatic restore cannot push out
# a stored package that was never the running one.
function Get-LiveReleaseCommit {
    try {
        $response = Invoke-WebRequest -Uri $appHealthUri -Method GET -TimeoutSec 20 -UseBasicParsing
        $status = [int]$response.StatusCode
        if ($status -lt 200 -or $status -ge 300) { return $null }
        $value = [string]($response.Content | ConvertFrom-Json).release_commit
        if ($value -match "^[0-9a-f]{40}$") { return $value.ToLowerInvariant() }
        return $null
    }
    catch {
        return $null
    }
}

function Write-StateNotes {
    param($Notes)

    foreach ($note in @($Notes)) {
        if ($note) { Write-Host $note -ForegroundColor Yellow }
    }
}

function Write-JournalWarning {
    param($Journal)

    if ($null -eq $Journal) { return }
    Write-Host ("A previous deployment did not finish: phase '$($Journal.phase)' for release " +
        "'$($Journal.release)' started $($Journal.started_utc) by pid $($Journal.pid) on " +
        "$($Journal.host). Confirm what is running before continuing.") -ForegroundColor Yellow
}

Initialize-DeployState -Paths $paths
Write-Host "Deployment state: $($paths.AppDir)"

if ($Rollback) {
    $lock = Lock-DeployState -Paths $paths -Purpose "rollback"
    try {
        Write-JournalWarning (Read-DeployJournal -Paths $paths)
        $manifest = Read-DeployManifest -Paths $paths
        $legacy = Import-LegacyDeployState -Paths $paths -LegacyDir $legacyStateDir -Manifest $manifest
        Write-StateNotes $legacy.Notes
        $manifest = $legacy.Manifest

        # Verified before it is sent, exactly as a normal deployment verifies its
        # own package. Drift is reported but never blocks a rollback: rollback is
        # the tool of last resort during an outage.
        $release = Get-RollbackRelease -Paths $paths -Manifest $manifest
        $live = Get-LiveReleaseCommit
        if ($live) { Write-Host "Running release before rollback: $live" }
        else { Write-Host "The running release could not be identified." -ForegroundColor Yellow }
        Write-Host "Rolling back to commit $($release.Id)." -ForegroundColor Yellow

        Set-DeployJournal -Paths $paths -Phase "rollback-upload" -Stem $release.Stem
        Send-KuduPackage -Package $release.Zip
        Set-DeployJournal -Paths $paths -Phase "rollback-health" -Stem $release.Stem
        Wait-VerifiedHealth -ExpectedCommit $release.Id
        [void](Write-DeployManifest -Paths $paths `
                -Manifest (Set-DeployRollback -Manifest $manifest -Stem $release.Stem))
        Clear-DeployJournal -Paths $paths
        Write-Host "Rollback deployed and health verified." -ForegroundColor Green
    }
    finally {
        Unlock-DeployState -Paths $paths -Handle $lock
    }
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

# The lock covers the shared build directory, baseline selection, the remote
# deployment window and promotion, so two deployments cannot interleave over one
# app's state. It is taken after the local gates so a long test run does not
# block another operator.
$lock = Lock-DeployState -Paths $paths -Purpose "deploy"
try {
    Write-JournalWarning (Read-DeployJournal -Paths $paths)
    $manifest = Read-DeployManifest -Paths $paths
    $legacy = Import-LegacyDeployState -Paths $paths -LegacyDir $legacyStateDir -Manifest $manifest
    Write-StateNotes $legacy.Notes
    $manifest = $legacy.Manifest

    if (Test-Path $buildZip) { Remove-Item $buildZip -Force }

    $commit = (git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($commit)) {
        throw "Unable to record the release commit."
    }

    Write-Host "== building Python deployment zip ==" -ForegroundColor Cyan
    # The target path and commit are passed as arguments rather than interpolated
    # into the source: the build directory now lives under a user profile path,
    # which can legitimately contain an apostrophe.
    $buildSource = @'
import os
import sys
import zipfile

target, commit = sys.argv[1], sys.argv[2]
archive = zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED)
archive.writestr('RELEASE_COMMIT', commit)
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
'@
    $buildSource | python - $buildZip $commit
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $buildZip -PathType Leaf)) {
        throw "Python zip build failed."
    }

    # Stored content-addressed, then verified by SHA-256 and embedded
    # RELEASE_COMMIT before anything is uploaded.
    $release = Add-DeployRelease -Paths $paths -SourceZip $buildZip -CommitId $commit

    Write-Host "== deploying commit $commit to $App ==" -ForegroundColor Cyan
    if ($manifest.current -and -not (Test-ReleaseStored -Paths $paths -Stem $manifest.current)) {
        throw "Current verified package state is incomplete; automatic restore is unavailable."
    }
    $live = Get-LiveReleaseCommit
    $baseline = Select-RestoreBaseline -Paths $paths -Manifest $manifest -LiveCommit $live
    $restore = $null
    if ($baseline.Stem) {
        $restore = Resolve-VerifiedRelease -Paths $paths -Stem $baseline.Stem
        Write-Host "Automatic restore is armed with $($restore.Id): $($baseline.Reason)."
    }
    else {
        Write-Host "Automatic restore is unavailable: $($baseline.Reason)." -ForegroundColor Yellow
    }

    try {
        Set-DeployJournal -Paths $paths -Phase "upload" -Stem $release.Stem
        Send-KuduPackage -Package $release.Zip
        Set-DeployJournal -Paths $paths -Phase "health" -Stem $release.Stem
        Wait-VerifiedHealth -ExpectedCommit $release.Id
    }
    catch {
        $candidateFailure = $_.Exception
        if ($null -eq $restore) {
            throw "Candidate deployment failed; automatic restore is unavailable because no current verified package exists."
        }

        Write-Host "Candidate deployment failed; restoring current verified release." `
            -ForegroundColor Yellow
        try {
            $verified = Resolve-VerifiedRelease -Paths $paths -Stem $restore.Stem
            if ($verified.Id -ne $restore.Id) {
                throw "Current verified package identity changed before automatic restore."
            }
            Set-DeployJournal -Paths $paths -Phase "restore" -Stem $verified.Stem
            Send-KuduPackage -Package $verified.Zip
            Wait-VerifiedHealth -ExpectedCommit $verified.Id
            [void](Write-DeployManifest -Paths $paths `
                    -Manifest (Set-DeployRestore -Manifest $manifest -Stem $verified.Stem))
            Clear-DeployJournal -Paths $paths
            Write-Host "Current verified release was restored and health verified." `
                -ForegroundColor Green
        }
        catch {
            throw "Candidate deployment failed and automatic restore of the current verified release also failed."
        }
        throw $candidateFailure
    }

    # One atomic manifest write both promotes this release and preserves the
    # distinct prior verified package, so a partially written baseline cannot
    # exist for -Rollback to find.
    $manifest = Write-DeployManifest -Paths $paths `
        -Manifest (Set-DeployPromotion -Manifest $manifest -Stem $release.Stem)
    Clear-DeployJournal -Paths $paths
    $pruned = @(Remove-StaleReleases -Paths $paths -Manifest $manifest -Retain $RetainReleases)
    if ($pruned.Count -gt 0) { Write-Host "Pruned $($pruned.Count) superseded release package(s)." }
    Remove-Item $buildZip -Force
    Write-Host "Deployment is healthy and recorded as current-verified." -ForegroundColor Green
    if ($manifest.previous) {
        Write-Host "Rollback if needed: pwsh Scripts/deploy.ps1 -App $App -Rollback"
    }
    else {
        Write-Host "No distinct previous release is stored yet, so -Rollback is not available."
    }
}
finally {
    Unlock-DeployState -Paths $paths -Handle $lock
}
