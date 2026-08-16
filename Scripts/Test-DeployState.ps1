# Behavioural checks for Scripts/deploy-state.ps1.
#
#   pwsh Scripts/Test-DeployState.ps1
#
# The repository has no PowerShell test framework, so this is a self-contained
# harness with a non-zero exit code on failure. tests/test_deploy_script.py runs
# it, so `pytest` covers it too.
#
# Nothing here touches the network, Azure, a real App Service, or patient data.
# Every check runs against throwaway directories and synthetic packages. The
# functions exercised are the ones deploy.ps1 actually calls, not re-implementations.

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "deploy-state.ps1")

$script:Checks = 0
$script:Failures = 0

function Assert-True {
    param([bool]$Condition, [string]$Message)

    $script:Checks++
    if ($Condition) {
        Write-Host "  ok   $Message"
    }
    else {
        $script:Failures++
        Write-Host "  FAIL $Message" -ForegroundColor Red
    }
}

function Assert-Equal {
    param($Expected, $Actual, [string]$Message)

    Assert-True ([string]$Expected -eq [string]$Actual) "$Message (expected '$Expected', got '$Actual')"
}

function Assert-Throws {
    param([scriptblock]$Action, [string]$Message, [string]$Match)

    $script:Checks++
    try {
        & $Action | Out-Null
        $script:Failures++
        Write-Host "  FAIL $Message (no error was raised)" -ForegroundColor Red
    }
    catch {
        if ($Match -and $_.Exception.Message -notmatch $Match) {
            $script:Failures++
            Write-Host "  FAIL $Message (message '$($_.Exception.Message)' did not match '$Match')" -ForegroundColor Red
        }
        else {
            Write-Host "  ok   $Message"
        }
    }
}

function Write-Section {
    param([string]$Name)
    Write-Host ""
    Write-Host "== $Name ==" -ForegroundColor Cyan
}

function New-TestCommit {
    param([Parameter(Mandatory = $true)][string]$Seed)

    $sha = [System.Security.Cryptography.SHA1]::Create()
    try { $bytes = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($Seed)) }
    finally { $sha.Dispose() }
    return (($bytes | ForEach-Object { $_.ToString("x2") }) -join "")
}

function New-TestPackage {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Commit,
        [string]$Payload = "payload"
    )

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    if (Test-Path $Path) { Remove-Item $Path -Force }
    New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force | Out-Null
    $zip = [System.IO.Compression.ZipFile]::Open($Path, [System.IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($pair in @(@{ Name = "RELEASE_COMMIT"; Body = $Commit }, @{ Name = "app.py"; Body = $Payload })) {
            $entry = $zip.CreateEntry($pair.Name)
            $writer = [System.IO.StreamWriter]::new($entry.Open())
            try { $writer.Write($pair.Body) } finally { $writer.Dispose() }
        }
    }
    finally { $zip.Dispose() }
    return $Path
}

function New-Sandbox {
    param([string]$Name)

    $path = Join-Path ([System.IO.Path]::GetTempPath()) ("net-care-deploy-test-$Name-" + [guid]::NewGuid().ToString("n"))
    New-Item -ItemType Directory -Path $path -Force | Out-Null
    return $path
}

$sandboxes = @()
try {
    # ------------------------------------------------------------------
    Write-Section "State root resolves to a stable location, not the working copy"

    $defaultPaths = Get-DeployStatePaths -App "example-app"
    if ($IsWindows) {
        $expectedRoot = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "net-care-agent\deploy"))
        Assert-Equal $expectedRoot $defaultPaths.Root "default root is under LOCALAPPDATA"
    }
    else {
        Assert-True ($defaultPaths.Root -like "*net-care-agent/deploy") "default root is under the user state directory"
    }
    Assert-True ([System.IO.Path]::IsPathRooted($defaultPaths.Root)) "default root is absolute"
    Assert-True ($defaultPaths.AppDir -like "*example-app") "state is keyed by app name"
    Assert-True (-not ($defaultPaths.AppDir -like "*$PSScriptRoot*")) "state does not live inside the working copy"
    Assert-Equal $defaultPaths.AppDir (Split-Path -Parent $defaultPaths.BuildZip | Split-Path -Parent) "build directory is inside the app state directory"

    $envRoot = New-Sandbox "env"; $sandboxes += $envRoot
    $env:NET_CARE_DEPLOY_STATE_ROOT = $envRoot
    try {
        $viaEnv = Get-DeployStatePaths -App "example-app"
        Assert-Equal ([System.IO.Path]::GetFullPath($envRoot)) $viaEnv.Root "NET_CARE_DEPLOY_STATE_ROOT overrides the default"
        $viaParam = Get-DeployStatePaths -App "example-app" -StateRoot $defaultPaths.Root
        Assert-Equal $defaultPaths.Root $viaParam.Root "-StateRoot wins over the environment variable"
    }
    finally { Remove-Item Env:NET_CARE_DEPLOY_STATE_ROOT -ErrorAction SilentlyContinue }

    Assert-Throws { Get-DeployStatePaths -App "example-app" -StateRoot "relative\path" } `
        "a relative state root is rejected" "absolute path"
    Assert-Throws { Get-DeployStatePaths -App "bad app name!" } `
        "an invalid app name is rejected rather than sanitised" "not a valid App Service site name"

    $appOne = Get-DeployStatePaths -App "first-app" -StateRoot $envRoot
    $appTwo = Get-DeployStatePaths -App "second-app" -StateRoot $envRoot
    Assert-True ($appOne.AppDir -ne $appTwo.AppDir) "two apps cannot collide"
    Assert-Equal (Get-DeployStatePaths -App "First-App" -StateRoot $envRoot).AppDir $appOne.AppDir `
        "app keying is case-insensitive"

    # ------------------------------------------------------------------
    Write-Section "A release stored from one worktree is found from another"

    $shared = New-Sandbox "shared"; $sandboxes += $shared
    $worktreeA = New-Sandbox "worktree-a"; $sandboxes += $worktreeA
    $worktreeB = New-Sandbox "worktree-b"; $sandboxes += $worktreeB
    $paths = Get-DeployStatePaths -App "example-app" -StateRoot $shared
    Initialize-DeployState -Paths $paths

    $commitOne = New-TestCommit "release-one"
    $packageOne = New-TestPackage -Path (Join-Path $worktreeA "build.zip") -Commit $commitOne -Payload "one"
    Push-Location $worktreeA
    try { $releaseOne = Add-DeployRelease -Paths $paths -SourceZip $packageOne -CommitId $commitOne }
    finally { Pop-Location }
    $manifest = Write-DeployManifest -Paths $paths -Manifest (Set-DeployPromotion -Manifest (Read-DeployManifest -Paths $paths) -Stem $releaseOne.Stem)

    Push-Location $worktreeB
    try {
        $fromB = Get-DeployStatePaths -App "example-app" -StateRoot $shared
        $manifestFromB = Read-DeployManifest -Paths $fromB
        Assert-Equal $releaseOne.Stem $manifestFromB.current "a fresh worktree sees the release stored by an earlier one"
        Assert-Equal $commitOne (Resolve-VerifiedRelease -Paths $fromB -Stem $manifestFromB.current).Id `
            "the release verifies from the fresh worktree"
    }
    finally { Pop-Location }

    # ------------------------------------------------------------------
    Write-Section "Promotion moves current to previous in one atomic write"

    $commitTwo = New-TestCommit "release-two"
    $packageTwo = New-TestPackage -Path (Join-Path $worktreeB "build.zip") -Commit $commitTwo -Payload "two"
    $releaseTwo = Add-DeployRelease -Paths $paths -SourceZip $packageTwo -CommitId $commitTwo
    $manifest = Write-DeployManifest -Paths $paths -Manifest (Set-DeployPromotion -Manifest $manifest -Stem $releaseTwo.Stem)
    Assert-Equal $releaseTwo.Stem $manifest.current "the new release becomes current"
    Assert-Equal $releaseOne.Stem $manifest.previous "the former current becomes previous"

    $sameAgain = Set-DeployPromotion -Manifest $manifest -Stem $releaseTwo.Stem
    Assert-Equal $releaseTwo.Stem $sameAgain.current "redeploying the same package keeps it current"
    Assert-Equal $releaseOne.Stem $sameAgain.previous "redeploying the same package does not discard the distinct previous"

    Assert-True (Test-Path $paths.Manifest -PathType Leaf) "state is a single manifest file"
    Assert-True (-not (Test-Path "$($paths.Manifest).new")) "no temporary manifest is left behind"
    $onDisk = Read-DeployManifest -Paths $paths
    Assert-Equal $manifest.current $onDisk.current "the persisted manifest matches what was written"
    Assert-Equal $manifest.previous $onDisk.previous "the persisted previous matches what was written"

    # A half-written temporary file must not be mistaken for state.
    Set-Content -Path "$($paths.Manifest).new" -Value "{ this is not json" -Encoding utf8
    $survivor = Read-DeployManifest -Paths $paths
    Assert-Equal $manifest.current $survivor.current "an abandoned temporary file cannot corrupt the manifest"
    Remove-Item "$($paths.Manifest).new" -Force

    # ------------------------------------------------------------------
    Write-Section "Rollback selects and verifies the right package"

    $rollbackTarget = Get-RollbackRelease -Paths $paths -Manifest $manifest
    Assert-Equal $releaseOne.Stem $rollbackTarget.Stem "rollback selects the previous release, not the current one"
    Assert-Equal $commitOne $rollbackTarget.Id "rollback reports the previous release commit"

    $afterRollback = Set-DeployRollback -Manifest $manifest -Stem $rollbackTarget.Stem
    Assert-Equal $releaseOne.Stem $afterRollback.current "a completed rollback makes the restored release current"
    Assert-True ($null -eq $afterRollback.previous) "a completed rollback consumes its baseline"

    $noPrevious = New-DeployManifest -App $paths.App
    $noPrevious.current = $releaseTwo.Stem
    Assert-Throws { Get-RollbackRelease -Paths $paths -Manifest $noPrevious } `
        "rollback refuses when no distinct previous release exists" "No complete previous-known-good release"

    # ------------------------------------------------------------------
    Write-Section "A corrupted or partial baseline is never selected"

    $tamperSandbox = New-Sandbox "tamper"; $sandboxes += $tamperSandbox
    $tamperPaths = Get-DeployStatePaths -App "example-app" -StateRoot $tamperSandbox
    Initialize-DeployState -Paths $tamperPaths
    $commitBad = New-TestCommit "release-bad"
    $packageBad = New-TestPackage -Path (Join-Path $tamperSandbox "build.zip") -Commit $commitBad
    $releaseBad = Add-DeployRelease -Paths $tamperPaths -SourceZip $packageBad -CommitId $commitBad
    $goodManifest = New-DeployManifest -App $tamperPaths.App
    $goodManifest.current = $releaseBad.Stem
    $goodManifest.previous = $releaseBad.Stem
    $goodManifest.history = @($releaseBad.Stem)

    $files = Get-ReleaseFileSet -Paths $tamperPaths -Stem $releaseBad.Stem
    Add-Content -Path $files.Zip -Value "corruption"
    Assert-Throws { Get-RollbackRelease -Paths $tamperPaths -Manifest $goodManifest } `
        "a package whose bytes changed is rejected before it can be sent" "SHA256 verification failed"

    # A package that hashes correctly against its own record but is not the
    # release the manifest names: the case where only the content address saves you.
    [void](New-TestPackage -Path $files.Zip -Commit $commitBad -Payload "substituted")
    $substituteDigest = (Get-FileHash -Path $files.Zip -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -Path $files.Sha -Value "$substituteDigest  $($releaseBad.Stem).zip" -Encoding ascii
    Assert-Throws { Get-RollbackRelease -Paths $tamperPaths -Manifest $goodManifest } `
        "a self-consistent substitute package is rejected by its content-addressed name" "content-addressed name"

    Remove-Item $files.Commit -Force
    Assert-Throws { Get-RollbackRelease -Paths $tamperPaths -Manifest $goodManifest } `
        "an incomplete release triple is treated as no baseline at all" "No complete previous-known-good release"

    $malformed = New-DeployManifest -App $tamperPaths.App
    Assert-Throws { $malformed.current = "not-a-stem"; Get-RollbackRelease -Paths $tamperPaths -Manifest $malformed } `
        "a malformed identifier cannot reach the deploy path" "No complete previous-known-good release"
    Set-Content -Path $tamperPaths.Manifest -Value "{ truncated" -Encoding utf8
    Assert-Throws { Read-DeployManifest -Paths $tamperPaths } `
        "an unreadable manifest fails closed instead of silently resetting" "not valid JSON"

    # ------------------------------------------------------------------
    Write-Section "Retention is bounded but never prunes the protected pair"

    $retentionSandbox = New-Sandbox "retention"; $sandboxes += $retentionSandbox
    $retentionPaths = Get-DeployStatePaths -App "example-app" -StateRoot $retentionSandbox
    Initialize-DeployState -Paths $retentionPaths

    $stems = @()
    foreach ($index in 1..8) {
        $c = New-TestCommit "retention-$index"
        $p = New-TestPackage -Path (Join-Path $retentionSandbox "build-$index.zip") -Commit $c -Payload "body-$index"
        $stems += (Add-DeployRelease -Paths $retentionPaths -SourceZip $p -CommitId $c).Stem
    }
    $retentionManifest = New-DeployManifest -App $retentionPaths.App
    # The protected pair is deliberately the two OLDEST releases, so keeping them
    # can only be the protection rule and never an accident of recency.
    $retentionManifest.current = $stems[0]
    $retentionManifest.previous = $stems[1]
    $retentionManifest.history = @($stems[7], $stems[6], $stems[5], $stems[4], $stems[3], $stems[2], $stems[1], $stems[0])

    $pruned = Remove-StaleReleases -Paths $retentionPaths -Manifest $retentionManifest -Retain 2
    Assert-True ($pruned.Count -gt 0) "retention prunes superseded releases"
    Assert-True (Test-ReleaseStored -Paths $retentionPaths -Stem $retentionManifest.current) "current-verified is never pruned"
    Assert-True (Test-ReleaseStored -Paths $retentionPaths -Stem $retentionManifest.previous) "previous-known-good is never pruned"
    Assert-True ($pruned -notcontains $retentionManifest.current) "current-verified is not reported as pruned"
    Assert-True ($pruned -notcontains $retentionManifest.previous) "previous-known-good is not reported as pruned"
    $remaining = @(Get-ChildItem -Path $retentionPaths.Releases -Filter "*.zip" -File).Count
    Assert-True ($remaining -le 4) "the release store stays bounded (kept $remaining)"
    Assert-True (Test-ReleaseStored -Paths $retentionPaths -Stem $stems[7]) "the newest promoted release is retained"

    $clamped = Remove-StaleReleases -Paths $retentionPaths -Manifest $retentionManifest -Retain 0
    Assert-True (Test-ReleaseStored -Paths $retentionPaths -Stem $retentionManifest.current) `
        "an absurd retention value still cannot delete current-verified"
    Assert-True (Test-ReleaseStored -Paths $retentionPaths -Stem $retentionManifest.previous) `
        "an absurd retention value still cannot delete previous-known-good"
    Assert-True ($null -ne $clamped) "retention returns a result even when nothing is left to prune"

    # ------------------------------------------------------------------
    Write-Section "Restore baseline follows the release that is actually running"

    $liveMatch = Select-RestoreBaseline -Paths $paths -Manifest $manifest -LiveCommit $commitTwo
    Assert-Equal $releaseTwo.Stem $liveMatch.Stem "the recorded current is used when it is what is running"
    Assert-True $liveMatch.Coherent "a matching baseline is reported as coherent"

    $drifted = Select-RestoreBaseline -Paths $paths -Manifest $manifest -LiveCommit $commitOne
    Assert-Equal $releaseOne.Stem $drifted.Stem "a drifted record falls back to the stored package that is running"
    Assert-True $drifted.Coherent "the recovered baseline is reported as coherent"

    $unknownLive = Select-RestoreBaseline -Paths $paths -Manifest $manifest -LiveCommit (New-TestCommit "never-deployed")
    Assert-True ($null -eq $unknownLive.Stem) "no baseline is armed when nothing stored matches the running release"
    Assert-True (-not $unknownLive.Coherent) "an unmatched running release is not reported as coherent"

    $unreachable = Select-RestoreBaseline -Paths $paths -Manifest $manifest -LiveCommit $null
    Assert-Equal $releaseTwo.Stem $unreachable.Stem "an unreachable app still leaves the recorded current available"
    Assert-True (-not $unreachable.Coherent) "an unverified baseline is flagged as not coherent"

    $emptyManifest = New-DeployManifest -App $paths.App
    $firstDeploy = Select-RestoreBaseline -Paths $paths -Manifest $emptyManifest -LiveCommit $commitTwo
    Assert-True ($null -eq $firstDeploy.Stem) "a first deployment has no automatic restore"

    # ------------------------------------------------------------------
    Write-Section "Legacy in-worktree state is adopted, never destroyed"

    $legacySandbox = New-Sandbox "legacy"; $sandboxes += $legacySandbox
    $legacyDir = Join-Path $legacySandbox ".deploy"
    New-Item -ItemType Directory -Path $legacyDir -Force | Out-Null
    $legacyCurrentCommit = New-TestCommit "legacy-current"
    $legacyPreviousCommit = New-TestCommit "legacy-previous"
    foreach ($pair in @(
            @{ Name = "current-verified"; Commit = $legacyCurrentCommit },
            @{ Name = "previous-known-good"; Commit = $legacyPreviousCommit })) {
        $zip = Join-Path $legacyDir "$($pair.Name).zip"
        [void](New-TestPackage -Path $zip -Commit $pair.Commit -Payload $pair.Name)
        $digest = (Get-FileHash -Path $zip -Algorithm SHA256).Hash.ToLowerInvariant()
        Set-Content -Path (Join-Path $legacyDir "$($pair.Name).sha256") -Value "$digest  $($pair.Name).zip" -Encoding ascii
        Set-Content -Path (Join-Path $legacyDir "$($pair.Name).commit") -Value $pair.Commit -Encoding ascii
    }

    $migrateSandbox = New-Sandbox "migrate"; $sandboxes += $migrateSandbox
    $migratePaths = Get-DeployStatePaths -App "example-app" -StateRoot $migrateSandbox
    Initialize-DeployState -Paths $migratePaths
    $migrated = Import-LegacyDeployState -Paths $migratePaths -LegacyDir $legacyDir -Manifest (Read-DeployManifest -Paths $migratePaths)
    Assert-True $migrated.Adopted "legacy state is adopted when the durable store is empty"
    Assert-Equal $legacyCurrentCommit (Get-DeployStemCommit -Stem $migrated.Manifest.current) "the legacy current release is adopted"
    Assert-Equal $legacyPreviousCommit (Get-DeployStemCommit -Stem $migrated.Manifest.previous) "the legacy previous release is adopted"
    Assert-True ((Get-RollbackRelease -Paths $migratePaths -Manifest $migrated.Manifest).Id -eq $legacyPreviousCommit) `
        "rollback works immediately after migration"
    Assert-True (Test-Path (Join-Path $legacyDir "current-verified.zip")) "legacy files are left in place, not moved"
    Assert-True (Test-Path (Join-Path $legacyDir "previous-known-good.zip")) "legacy previous files are left in place"
    Assert-True (@($migrated.Notes).Count -gt 0) "migration is reported rather than silent"

    $again = Import-LegacyDeployState -Paths $migratePaths -LegacyDir $legacyDir -Manifest $migrated.Manifest
    Assert-True (-not $again.Adopted) "legacy state is not re-adopted once the store has a current release"
    Assert-True (@($again.Notes) -join " " -match "left untouched") "an ignored legacy directory is reported clearly"

    $corruptSandbox = New-Sandbox "legacy-corrupt"; $sandboxes += $corruptSandbox
    $corruptLegacy = Join-Path $corruptSandbox ".deploy"
    New-Item -ItemType Directory -Path $corruptLegacy -Force | Out-Null
    $corruptCommit = New-TestCommit "legacy-corrupt"
    $corruptZip = Join-Path $corruptLegacy "current-verified.zip"
    [void](New-TestPackage -Path $corruptZip -Commit $corruptCommit)
    Set-Content -Path (Join-Path $corruptLegacy "current-verified.sha256") -Value "0000  current-verified.zip" -Encoding ascii
    Set-Content -Path (Join-Path $corruptLegacy "current-verified.commit") -Value $corruptCommit -Encoding ascii
    $corruptTarget = Get-DeployStatePaths -App "example-app" -StateRoot (New-Sandbox "legacy-target")
    $sandboxes += $corruptTarget.Root
    Initialize-DeployState -Paths $corruptTarget
    $corruptResult = Import-LegacyDeployState -Paths $corruptTarget -LegacyDir $corruptLegacy -Manifest (Read-DeployManifest -Paths $corruptTarget)
    Assert-True (-not $corruptResult.Adopted) "legacy state that fails verification is not adopted"
    Assert-True ($null -eq $corruptResult.Manifest.current) "a failed migration leaves no current release recorded"
    Assert-True (Test-Path $corruptZip) "a failed migration still leaves the operator's files alone"

    $absentResult = Import-LegacyDeployState -Paths $corruptTarget -LegacyDir (Join-Path $corruptSandbox "missing") -Manifest (Read-DeployManifest -Paths $corruptTarget)
    Assert-True (-not $absentResult.Adopted) "a missing legacy directory is not an error"

    # ------------------------------------------------------------------
    Write-Section "Two deployments cannot share one app's state"

    $lockSandbox = New-Sandbox "lock"; $sandboxes += $lockSandbox
    $lockPaths = Get-DeployStatePaths -App "example-app" -StateRoot $lockSandbox
    Initialize-DeployState -Paths $lockPaths
    $held = Lock-DeployState -Paths $lockPaths -Purpose "harness"
    try {
        Assert-True (Test-Path $lockPaths.LockOwner -PathType Leaf) "the lock records a readable holder"
        Assert-True ((Get-Content $lockPaths.LockOwner -Raw) -match "pid=$PID") "the holder record identifies the process"

        # A real second process, because same-process locking would prove nothing.
        $module = (Join-Path $PSScriptRoot "deploy-state.ps1")
        $probe = @"
. '$module'
`$paths = Get-DeployStatePaths -App 'example-app' -StateRoot '$lockSandbox'
try { `$h = Lock-DeployState -Paths `$paths -Purpose 'probe'; `$h.Dispose(); Write-Output 'ACQUIRED' }
catch { Write-Output "BLOCKED: `$(`$_.Exception.Message)" }
"@
        $probeFile = Join-Path $lockSandbox "probe.ps1"
        Set-Content -Path $probeFile -Value $probe -Encoding utf8
        $output = & (Get-Process -Id $PID).Path -NoProfile -NonInteractive -File $probeFile 2>&1
        $joined = ($output | Out-String)
        Assert-True ($joined -match "BLOCKED") "a second process cannot acquire the lock"
        Assert-True ($joined -match "pid=$PID") "the blocked process is told who holds the lock"
    }
    finally { Unlock-DeployState -Paths $lockPaths -Handle $held }

    $reacquired = Lock-DeployState -Paths $lockPaths -Purpose "harness-again"
    Assert-True ($null -ne $reacquired) "the lock is released when the deployment finishes"
    Unlock-DeployState -Paths $lockPaths -Handle $reacquired
    Assert-True (-not (Test-Path $lockPaths.LockOwner)) "the holder record is cleared on release"

    # ------------------------------------------------------------------
    Write-Section "An interrupted deployment leaves a journal"

    Set-DeployJournal -Paths $lockPaths -Phase "upload" -Stem $releaseOne.Stem
    $journal = Read-DeployJournal -Paths $lockPaths
    Assert-Equal "upload" $journal.phase "the journal records the phase in flight"
    Assert-Equal $releaseOne.Stem $journal.release "the journal records the release in flight"
    Clear-DeployJournal -Paths $lockPaths
    Assert-True ($null -eq (Read-DeployJournal -Paths $lockPaths)) "the journal is cleared once the deployment settles"
}
finally {
    foreach ($sandbox in $sandboxes) {
        if ($sandbox -and (Test-Path $sandbox)) {
            Remove-Item $sandbox -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Host ""
if ($script:Failures -gt 0) {
    Write-Host "$script:Failures of $script:Checks checks FAILED." -ForegroundColor Red
    exit 1
}
Write-Host "All $script:Checks deployment-state checks passed." -ForegroundColor Green
exit 0
