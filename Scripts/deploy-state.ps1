# Durable deployment state for Scripts/deploy.ps1.
#
# Release packages and the record of which one is live must outlive the working
# copy that produced them. Deployments are run from throwaway git worktrees, so
# state kept inside the working copy is empty on every run and the rollback and
# automatic-restore safety nets never have a baseline. This module keeps that
# state in one stable per-machine location, keyed by App Service name.
#
# Layout, under <state-root>/apps/<app>/:
#   state.json                    single manifest naming current/previous/history
#   releases/<stem>.zip           immutable, content-addressed release packages
#   releases/<stem>.sha256        SHA-256 record for the package
#   releases/<stem>.commit        packaged commit record
#   build/                        scratch build output
#   deploy.lock                   exclusive lock held for a whole deployment
#   deploy.lock.owner             readable description of the lock holder
#   in-progress.json              journal describing a deployment in flight
#
# A stem is "<40-hex-commit>-<64-hex-sha256>", so a package's identity is its
# name. Releases are never mutated; only the manifest changes, and it is
# replaced atomically. That is what makes a partially written baseline
# impossible: current and previous always move together in a single rename.
#
# This file is dot-sourced by deploy.ps1 and by Scripts/Test-DeployState.ps1.
# It performs no network access and knows nothing about Azure or Kudu.

# Deliberately no Set-StrictMode here: this file is dot-sourced into deploy.ps1,
# and silently changing that script's evaluation rules would be a side effect of
# an unrelated refactor. The functions below are written defensively instead.

$script:DeployStemPattern = '^[0-9a-f]{40}-[0-9a-f]{64}$'
$script:DeployCommitPattern = '^[0-9a-f]{40}$'

# App Service site names, which is also what keeps two apps from colliding.
# Rejected rather than sanitised: a lossy rewrite could silently merge apps.
$script:DeployAppPattern = '^[A-Za-z0-9][A-Za-z0-9-]{0,58}[A-Za-z0-9]$'

function Get-DeployAppKey {
    param([Parameter(Mandatory = $true)][string]$App)

    $key = $App.Trim()
    if ($key -notmatch $script:DeployAppPattern) {
        throw "App name '$App' is not a valid App Service site name; refusing to guess a state directory."
    }
    return $key.ToLowerInvariant()
}

function Get-DeployStateRoot {
    param([string]$StateRoot)

    $candidate = $StateRoot
    $source = "-StateRoot parameter"
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        $candidate = $env:NET_CARE_DEPLOY_STATE_ROOT
        $source = "NET_CARE_DEPLOY_STATE_ROOT"
    }
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        $source = "default"
        if ($IsWindows) {
            if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
                throw "LOCALAPPDATA is not set; pass -StateRoot or set NET_CARE_DEPLOY_STATE_ROOT."
            }
            $candidate = Join-Path $env:LOCALAPPDATA "net-care-agent\deploy"
        }
        else {
            $base = $env:XDG_STATE_HOME
            if ([string]::IsNullOrWhiteSpace($base)) {
                if ([string]::IsNullOrWhiteSpace($env:HOME)) {
                    throw "HOME is not set; pass -StateRoot or set NET_CARE_DEPLOY_STATE_ROOT."
                }
                $base = Join-Path $env:HOME ".local/state"
            }
            $candidate = Join-Path $base "net-care-agent/deploy"
        }
    }

    if (-not [System.IO.Path]::IsPathRooted($candidate)) {
        throw "Deployment state root must be an absolute path (from $source): '$candidate'."
    }
    return [System.IO.Path]::GetFullPath($candidate)
}

function Get-DeployStatePaths {
    param(
        [Parameter(Mandatory = $true)][string]$App,
        [string]$StateRoot
    )

    $key = Get-DeployAppKey -App $App
    $root = Get-DeployStateRoot -StateRoot $StateRoot
    $appDir = Join-Path (Join-Path $root "apps") $key
    $releases = Join-Path $appDir "releases"
    $build = Join-Path $appDir "build"

    return @{
        App       = $key
        Root      = $root
        AppDir    = $appDir
        Releases  = $releases
        Build     = $build
        BuildZip  = Join-Path $build "net-care-deploy.zip"
        Manifest  = Join-Path $appDir "state.json"
        Lock      = Join-Path $appDir "deploy.lock"
        LockOwner = Join-Path $appDir "deploy.lock.owner"
        Journal   = Join-Path $appDir "in-progress.json"
    }
}

function Initialize-DeployState {
    param([Parameter(Mandatory = $true)][hashtable]$Paths)

    foreach ($dir in @($Paths.AppDir, $Paths.Releases, $Paths.Build)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

function Lock-DeployState {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Paths,
        [string]$Purpose = "deploy"
    )

    try {
        $stream = [System.IO.File]::Open(
            $Paths.Lock,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None)
    }
    catch {
        $holder = "unknown holder"
        if (Test-Path $Paths.LockOwner -PathType Leaf) {
            try { $holder = (Get-Content $Paths.LockOwner -Raw).Trim() } catch { $holder = "unreadable owner record" }
        }
        throw "Another deployment already holds $($Paths.Lock). Holder: $holder"
    }

    $owner = "pid=$PID host=$([System.Net.Dns]::GetHostName()) user=$([Environment]::UserName) purpose=$Purpose started=$([DateTimeOffset]::UtcNow.ToString('o'))"
    Set-Content -Path $Paths.LockOwner -Value $owner -Encoding ascii
    return $stream
}

function Unlock-DeployState {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Paths,
        $Handle
    )

    if ($null -ne $Handle) { $Handle.Dispose() }
    if (Test-Path $Paths.LockOwner -PathType Leaf) {
        Remove-Item $Paths.LockOwner -Force -ErrorAction SilentlyContinue
    }
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
    if ($expected -notmatch $script:DeployCommitPattern) {
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

function Test-DeployStem {
    param([string]$Stem)

    if ([string]::IsNullOrWhiteSpace($Stem)) { return $false }
    return ([string]$Stem -match $script:DeployStemPattern)
}

function Get-DeployStemCommit {
    param([Parameter(Mandatory = $true)][string]$Stem)

    if (-not (Test-DeployStem -Stem $Stem)) { throw "Release identifier '$Stem' is malformed." }
    return $Stem.Substring(0, 40)
}

function Get-ReleaseFileSet {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Paths,
        [Parameter(Mandatory = $true)][string]$Stem
    )

    if (-not (Test-DeployStem -Stem $Stem)) { throw "Release identifier '$Stem' is malformed." }
    return @{
        Stem   = $Stem
        Zip    = Join-Path $Paths.Releases "$Stem.zip"
        Sha    = Join-Path $Paths.Releases "$Stem.sha256"
        Commit = Join-Path $Paths.Releases "$Stem.commit"
    }
}

function Test-ReleaseStored {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Paths,
        [string]$Stem
    )

    if (-not (Test-DeployStem -Stem $Stem)) { return $false }
    $files = Get-ReleaseFileSet -Paths $Paths -Stem $Stem
    foreach ($file in @($files.Zip, $files.Sha, $files.Commit)) {
        if (-not (Test-Path $file -PathType Leaf)) { return $false }
    }
    return $true
}

# Every consumer goes through here, so no package is ever deployed, restored or
# rolled back without both its SHA-256 and its embedded RELEASE_COMMIT checked.
function Resolve-VerifiedRelease {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Paths,
        [Parameter(Mandatory = $true)][string]$Stem
    )

    if (-not (Test-ReleaseStored -Paths $Paths -Stem $Stem)) {
        throw "Release $Stem is not completely stored in $($Paths.Releases)."
    }
    $files = Get-ReleaseFileSet -Paths $Paths -Stem $Stem
    Confirm-PackageHash -Package $files.Zip -ShaRecord $files.Sha
    $commit = Confirm-PackageIdentity -Package $files.Zip -CommitRecord $files.Commit
    if ($commit -ne (Get-DeployStemCommit -Stem $Stem)) {
        throw "Release $Stem records commit $commit; the stored identity is inconsistent."
    }
    $digest = (Get-FileHash -Path $files.Zip -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($digest -ne $Stem.Substring(41)) {
        throw "Release $Stem does not match its content-addressed name."
    }
    return @{
        Stem   = $Stem
        Zip    = $files.Zip
        Sha    = $files.Sha
        Commit = $files.Commit
        Id     = $commit
    }
}

function Add-DeployRelease {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Paths,
        [Parameter(Mandatory = $true)][string]$SourceZip,
        [Parameter(Mandatory = $true)][string]$CommitId
    )

    $commit = $CommitId.Trim().ToLowerInvariant()
    if ($commit -notmatch $script:DeployCommitPattern) { throw "Release commit '$CommitId' is invalid." }
    $digest = (Get-FileHash -Path $SourceZip -Algorithm SHA256).Hash.ToLowerInvariant()
    $stem = "$commit-$digest"
    $files = Get-ReleaseFileSet -Paths $Paths -Stem $stem

    Copy-Item $SourceZip "$($files.Zip).new" -Force
    Set-Content -Path "$($files.Sha).new" -Value "$digest  $stem.zip" -Encoding ascii
    Set-Content -Path "$($files.Commit).new" -Value $commit -Encoding ascii
    Move-Item "$($files.Zip).new" $files.Zip -Force
    Move-Item "$($files.Sha).new" $files.Sha -Force
    Move-Item "$($files.Commit).new" $files.Commit -Force

    return Resolve-VerifiedRelease -Paths $Paths -Stem $stem
}

function New-DeployManifest {
    param([Parameter(Mandatory = $true)][string]$App)

    return [pscustomobject]@{
        version     = 1
        app         = $App
        current     = $null
        previous    = $null
        history     = @()
        updated_utc = $null
    }
}

function Read-DeployManifest {
    param([Parameter(Mandatory = $true)][hashtable]$Paths)

    if (-not (Test-Path $Paths.Manifest -PathType Leaf)) {
        return New-DeployManifest -App $Paths.App
    }
    $raw = Get-Content $Paths.Manifest -Raw
    if ([string]::IsNullOrWhiteSpace($raw)) {
        throw "Deployment state manifest $($Paths.Manifest) is empty; refusing to guess the verified release."
    }
    try { $parsed = $raw | ConvertFrom-Json }
    catch { throw "Deployment state manifest $($Paths.Manifest) is not valid JSON; refusing to guess the verified release." }

    $manifest = New-DeployManifest -App $Paths.App
    foreach ($field in @("current", "previous")) {
        $value = $parsed.PSObject.Properties[$field]
        if ($null -ne $value -and -not [string]::IsNullOrWhiteSpace([string]$value.Value)) {
            if (-not (Test-DeployStem -Stem ([string]$value.Value))) {
                throw "Deployment state manifest records a malformed $field release identifier."
            }
            $manifest.$field = [string]$value.Value
        }
    }
    $historyProperty = $parsed.PSObject.Properties["history"]
    if ($null -ne $historyProperty -and $null -ne $historyProperty.Value) {
        $history = @()
        foreach ($stem in @($historyProperty.Value)) {
            $text = [string]$stem
            if (-not (Test-DeployStem -Stem $text)) {
                throw "Deployment state manifest records a malformed history release identifier."
            }
            if ($history -notcontains $text) { $history += $text }
        }
        $manifest.history = $history
    }
    return $manifest
}

# Single-file atomic replace. current and previous can never disagree because
# they are never written separately.
function Write-DeployManifest {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Paths,
        [Parameter(Mandatory = $true)]$Manifest
    )

    $Manifest.updated_utc = [DateTimeOffset]::UtcNow.ToString("o")
    $temp = "$($Paths.Manifest).new"
    $json = $Manifest | ConvertTo-Json -Depth 5
    Set-Content -Path $temp -Value $json -Encoding utf8
    Move-Item $temp $Paths.Manifest -Force
    return $Manifest
}

function Set-DeployPromotion {
    param(
        [Parameter(Mandatory = $true)]$Manifest,
        [Parameter(Mandatory = $true)][string]$Stem
    )

    if (-not (Test-DeployStem -Stem $Stem)) { throw "Release identifier '$Stem' is malformed." }
    $promoted = New-DeployManifest -App $Manifest.app
    $promoted.current = $Stem
    # Redeploying the identical package must not discard the distinct baseline.
    if ($Manifest.current -and $Manifest.current -ne $Stem) {
        $promoted.previous = $Manifest.current
    }
    else {
        $promoted.previous = $Manifest.previous
    }
    if ($promoted.previous -eq $Stem) { $promoted.previous = $null }

    $history = @($Stem)
    foreach ($entry in @($Manifest.history)) {
        if ($entry -and $history -notcontains $entry) { $history += $entry }
    }
    $promoted.history = $history
    return $promoted
}

function Set-DeployRollback {
    param(
        [Parameter(Mandatory = $true)]$Manifest,
        [Parameter(Mandatory = $true)][string]$Stem
    )

    if (-not (Test-DeployStem -Stem $Stem)) { throw "Release identifier '$Stem' is malformed." }
    $rolled = New-DeployManifest -App $Manifest.app
    $rolled.current = $Stem
    # A rollback consumes its baseline, matching the long-standing behaviour that
    # one verified rollback is offered rather than an unbounded walk backwards.
    $rolled.previous = $null
    $history = @($Stem)
    foreach ($entry in @($Manifest.history)) {
        if ($entry -and $history -notcontains $entry) { $history += $entry }
    }
    $rolled.history = $history
    return $rolled
}

# A restore redeploys a package that was already verified rather than promoting a
# new one, so the previous baseline is left exactly as it was.
function Set-DeployRestore {
    param(
        [Parameter(Mandatory = $true)]$Manifest,
        [Parameter(Mandatory = $true)][string]$Stem
    )

    if (-not (Test-DeployStem -Stem $Stem)) { throw "Release identifier '$Stem' is malformed." }
    $restored = New-DeployManifest -App $Manifest.app
    $restored.current = $Stem
    $restored.previous = $Manifest.previous
    if ($restored.previous -eq $Stem) { $restored.previous = $null }
    $history = @($Stem)
    foreach ($entry in @($Manifest.history)) {
        if ($entry -and $history -notcontains $entry) { $history += $entry }
    }
    $restored.history = $history
    return $restored
}

function Get-RollbackRelease {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Paths,
        [Parameter(Mandatory = $true)]$Manifest
    )

    if (-not $Manifest.previous) {
        throw "No complete previous-known-good release is available for rollback."
    }
    if (-not (Test-ReleaseStored -Paths $Paths -Stem $Manifest.previous)) {
        throw "No complete previous-known-good release is available for rollback."
    }
    return Resolve-VerifiedRelease -Paths $Paths -Stem $Manifest.previous
}

# Which stored package may be redeployed if this deployment fails. A package
# that is merely well-formed is not enough: restoring a release that is not the
# one actually running would be a silent, unrequested downgrade.
function Select-RestoreBaseline {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Paths,
        [Parameter(Mandatory = $true)]$Manifest,
        [string]$LiveCommit
    )

    if (-not $Manifest.current) {
        return @{ Stem = $null; Coherent = $false; Reason = "no current verified package exists" }
    }
    if (-not (Test-ReleaseStored -Paths $Paths -Stem $Manifest.current)) {
        return @{ Stem = $null; Coherent = $false; Reason = "the recorded current verified package is missing from the release store" }
    }

    $live = ""
    if (-not [string]::IsNullOrWhiteSpace($LiveCommit)) { $live = $LiveCommit.Trim().ToLowerInvariant() }
    if ([string]::IsNullOrWhiteSpace($live)) {
        return @{
            Stem     = $Manifest.current
            Coherent = $false
            Reason   = "the running release could not be identified; using the recorded current verified package"
        }
    }
    if ((Get-DeployStemCommit -Stem $Manifest.current) -eq $live) {
        return @{ Stem = $Manifest.current; Coherent = $true; Reason = "the recorded current verified package is the running release" }
    }

    foreach ($stem in @($Manifest.history)) {
        if ((Get-DeployStemCommit -Stem $stem) -eq $live -and (Test-ReleaseStored -Paths $Paths -Stem $stem)) {
            return @{
                Stem     = $stem
                Coherent = $true
                Reason   = "the recorded current verified package is not running; using the stored package for running release $live"
            }
        }
    }
    return @{
        Stem     = $null
        Coherent = $false
        Reason   = "no stored package matches running release $live"
    }
}

# Bounded, but the current/previous pair is protected unconditionally: retention
# must never be able to delete the safety net it exists to keep affordable.
function Remove-StaleReleases {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Paths,
        [Parameter(Mandatory = $true)]$Manifest,
        [int]$Retain = 10
    )

    if ($Retain -lt 2) { $Retain = 2 }
    $protected = @()
    foreach ($stem in @($Manifest.current, $Manifest.previous)) {
        if ($stem -and $protected -notcontains $stem) { $protected += $stem }
    }
    $keep = @($protected)
    foreach ($stem in @($Manifest.history)) {
        if ($keep.Count -ge ($Retain + $protected.Count)) { break }
        if ($stem -and $keep -notcontains $stem) { $keep += $stem }
    }

    $pruned = @()
    if (-not (Test-Path $Paths.Releases -PathType Container)) { return , $pruned }
    foreach ($zip in Get-ChildItem -Path $Paths.Releases -Filter "*.zip" -File) {
        $stem = [System.IO.Path]::GetFileNameWithoutExtension($zip.Name)
        if (-not (Test-DeployStem -Stem $stem)) { continue }
        if ($keep -contains $stem) { continue }
        foreach ($suffix in @("zip", "sha256", "commit")) {
            $path = Join-Path $Paths.Releases "$stem.$suffix"
            if (Test-Path $path -PathType Leaf) { Remove-Item $path -Force -ErrorAction SilentlyContinue }
        }
        $pruned += $stem
    }
    # Comma-wrapped so an empty result stays an array instead of unrolling to $null.
    return , $pruned
}

function Set-DeployJournal {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Paths,
        [Parameter(Mandatory = $true)][string]$Phase,
        [string]$Stem
    )

    $entry = [pscustomobject]@{
        phase       = $Phase
        release     = $Stem
        app         = $Paths.App
        pid         = $PID
        host        = [System.Net.Dns]::GetHostName()
        started_utc = [DateTimeOffset]::UtcNow.ToString("o")
    }
    Set-Content -Path $Paths.Journal -Value ($entry | ConvertTo-Json -Depth 4) -Encoding utf8
}

function Clear-DeployJournal {
    param([Parameter(Mandatory = $true)][hashtable]$Paths)

    if (Test-Path $Paths.Journal -PathType Leaf) {
        Remove-Item $Paths.Journal -Force -ErrorAction SilentlyContinue
    }
}

function Read-DeployJournal {
    param([Parameter(Mandatory = $true)][hashtable]$Paths)

    if (-not (Test-Path $Paths.Journal -PathType Leaf)) { return $null }
    try { return (Get-Content $Paths.Journal -Raw | ConvertFrom-Json) } catch { return $null }
}

# Adopt state written by an older, working-copy-local layout. The legacy
# directory is only ever read and copied from; an operator's artefacts are never
# moved or deleted. Adoption is refused once the durable store has its own
# current release, because a stale working copy must not overwrite newer truth.
function Import-LegacyDeployState {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Paths,
        [Parameter(Mandatory = $true)][string]$LegacyDir,
        [Parameter(Mandatory = $true)]$Manifest
    )

    $result = @{ Adopted = $false; Manifest = $Manifest; Notes = @() }
    if (-not (Test-Path $LegacyDir -PathType Container)) { return $result }

    $sets = @{}
    foreach ($name in @("current-verified", "previous-known-good")) {
        $zip = Join-Path $LegacyDir "$name.zip"
        $sha = Join-Path $LegacyDir "$name.sha256"
        $commit = Join-Path $LegacyDir "$name.commit"
        $present = @($zip, $sha, $commit | Where-Object { Test-Path $_ -PathType Leaf }).Count
        if ($present -eq 3) { $sets[$name] = @{ Zip = $zip; Sha = $sha; Commit = $commit } }
        elseif ($present -gt 0) { $result.Notes += "Legacy $name state in $LegacyDir is incomplete and was ignored." }
    }
    if ($sets.Count -eq 0) { return $result }

    if ($Manifest.current) {
        $result.Notes += "Legacy deployment state exists in $LegacyDir but was left untouched because $($Paths.Manifest) already records a current verified release."
        return $result
    }

    # Legacy state carries no app identity, so say plainly what it is being
    # attributed to rather than assuming the operator only ever had one app.
    $result.Notes += "Adopting legacy deployment state from $LegacyDir for app '$($Paths.App)'; the original files are left in place."

    $adopted = @{}
    foreach ($name in @("current-verified", "previous-known-good")) {
        if (-not $sets.ContainsKey($name)) { continue }
        $set = $sets[$name]
        try {
            Confirm-PackageHash -Package $set.Zip -ShaRecord $set.Sha
            $commitId = Confirm-PackageIdentity -Package $set.Zip -CommitRecord $set.Commit
            $release = Add-DeployRelease -Paths $Paths -SourceZip $set.Zip -CommitId $commitId
            $adopted[$name] = $release.Stem
            $result.Notes += "Adopted legacy $name as release $($release.Stem)."
        }
        catch {
            $result.Notes += "Legacy $name in $LegacyDir failed verification and was ignored: $($_.Exception.Message)"
        }
    }
    if ($adopted.Count -eq 0) { return $result }

    $migrated = New-DeployManifest -App $Paths.App
    if ($adopted.ContainsKey("current-verified")) { $migrated.current = $adopted["current-verified"] }
    if ($adopted.ContainsKey("previous-known-good")) { $migrated.previous = $adopted["previous-known-good"] }
    if ($migrated.previous -and $migrated.previous -eq $migrated.current) { $migrated.previous = $null }
    if (-not $migrated.current) {
        # Only a previous package survived verification. It is a real rollback
        # baseline, but it must not masquerade as the running release.
        $result.Notes += "Legacy state provided only a previous-known-good package; it was stored but no current verified release was recorded."
        $migrated.previous = $null
        return $result
    }

    $history = @()
    foreach ($stem in @($migrated.current, $migrated.previous)) {
        if ($stem -and $history -notcontains $stem) { $history += $stem }
    }
    $migrated.history = $history

    $result.Manifest = Write-DeployManifest -Paths $Paths -Manifest $migrated
    $result.Adopted = $true
    return $result
}
