"""Source-level deployment safety regressions (the deploy script is never executed here).

Two exceptions run PowerShell without deploying anything:
``test_deployment_state_behaviour_harness_passes`` runs Scripts/Test-DeployState.ps1,
and ``test_auth_header_is_built_from_the_real_token_at_runtime`` evaluates the extracted
``Get-AuthHeaders`` definition against a stubbed ``az``. Both perform no network access
and never touch Azure.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = (ROOT / "Scripts" / "deploy.ps1").read_text(encoding="utf-8")
STATE = (ROOT / "Scripts" / "deploy-state.ps1").read_text(encoding="utf-8")
HARNESS = ROOT / "Scripts" / "Test-DeployState.ps1"
GITIGNORE = (ROOT / ".gitignore").read_text(encoding="utf-8")

ROLLBACK_BLOCK = SCRIPT[SCRIPT.index("if ($Rollback) {") : SCRIPT.index("# All gates")]
DEPLOY_BLOCK = SCRIPT[SCRIPT.index("# All gates") :]

# An obviously fake, human-readable stand-in. It is only ever written to a
# pytest tmp_path, never committed as data and never sent anywhere.
STUB_TOKEN = "stub-not-a-real-token-for-tests"


def _function(source: str, name: str) -> str:
    """Return a PowerShell function body by matching braces rather than guessing an end."""
    marker = f"\nfunction {name} {{"
    start = source.index(marker) + len(marker)
    depth = 1
    index = start
    while depth:
        character = source[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
        index += 1
    return source[start : index - 1]


def _definition(source: str, name: str) -> str:
    """Return the complete ``function <name> { ... }`` text, ready to be re-evaluated."""
    return "function " + name + " {" + _function(source, name) + "}"


def _authorization_value(source: str) -> str:
    """The single header value literal assigned inside Get-AuthHeaders."""
    body = _function(source, "Get-AuthHeaders")
    literals = re.findall(r'Authorization[ \t]*=[ \t]*"([^"\n]*)"', body)
    assert len(literals) == 1, f"expected exactly one Authorization literal, got {len(literals)}"
    return literals[0]


# A scrubber redaction was once committed over this literal, so every Kudu request
# carried a masked header and neither deploying nor rolling back was possible. The
# artefact is invisible when the file is displayed, so assert on measurable
# properties of the value rather than trusting a reading of it.
def test_auth_header_is_a_well_formed_bearer_header():
    value = _authorization_value(SCRIPT)
    assert "*" not in value, "the Authorization value contains masking characters"
    assert not re.search(r"(?i)[<\[]\s*redacted\s*[>\]]", value)
    assert value.startswith("Bearer ")

    credential = value[len("Bearer ") :]
    assert credential, "the header carries no credential at all"
    # It must interpolate the token that was just fetched, not a constant, and must
    # be nothing but that expression: no literal prefix may sit in front of it.
    assert credential.startswith("$")
    assert "$token" in credential

    # The fetch and validation in front of it are unchanged.
    body = _function(SCRIPT, "Get-AuthHeaders")
    assert "az account get-access-token" in body
    assert "[string]::IsNullOrWhiteSpace($token)" in body
    assert "Unable to obtain an Azure access token." in body

    # The token never leaves the function that turns it into a header, so no
    # logging or error path anywhere else in the script can echo it.
    assert SCRIPT.count("$token") == body.count("$token")


AUTH_PROBE = """
$ErrorActionPreference = "Stop"
Remove-Item Alias:az -ErrorAction SilentlyContinue

$script:Calls = New-Object System.Collections.ArrayList
$script:Exit = 0
$script:Output = "  __TOKEN__  "

function az {
    [void]$script:Calls.Add((@($args) -join " "))
    $global:LASTEXITCODE = $script:Exit
    return $script:Output
}

__DEFINITION__

Write-Output ("AZ_IS_FUNCTION=" + ((Get-Command az).CommandType -eq "Function"))

# Happy path. The sentinel exit code proves the stub really ran: if it did not,
# the function's own validation throws and this script fails loudly.
$global:LASTEXITCODE = 97
$headers = Get-AuthHeaders
$value = [string]$headers["Authorization"]
Write-Output ("CALLS=" + $script:Calls.Count)
Write-Output ("ARGS_OK=" + ($script:Calls[0] -like "*account get-access-token*"))
Write-Output ("KEYS=" + $headers.Keys.Count)
Write-Output ("STARS=" + ([regex]::Matches($value, "\\*").Count))
Write-Output ("LEN=" + $value.Length)
Write-Output ("EXACT=" + ($value -ceq ("Bearer " + "__TOKEN__")))

# A failed token fetch must still abort rather than send a junk header.
$script:Exit = 3
$script:Output = "__TOKEN__"
try { Get-AuthHeaders | Out-Null; Write-Output "THROWS_ON_EXIT=False" }
catch { Write-Output "THROWS_ON_EXIT=True" }

$script:Exit = 0
$script:Output = "   "
try { Get-AuthHeaders | Out-Null; Write-Output "THROWS_ON_BLANK=False" }
catch { Write-Output "THROWS_ON_BLANK=True" }
"""


def test_auth_header_is_built_from_the_real_token_at_runtime(tmp_path):
    """Evaluate the real Get-AuthHeaders against a stubbed ``az`` — no Azure, no network.

    Source text alone cannot prove the header is well formed, so this builds one and
    measures it. Only booleans and lengths are emitted; the stand-in value is never
    printed, exactly as the deploy script never echoes a real token.
    """
    powershell = shutil.which("pwsh")
    if powershell is None:  # pragma: no cover - depends on the host toolchain
        pytest.skip("pwsh is not available on this host")

    probe = AUTH_PROBE.replace("__DEFINITION__", _definition(SCRIPT, "Get-AuthHeaders")).replace(
        "__TOKEN__", STUB_TOKEN
    )
    script = tmp_path / "auth_probe.ps1"
    script.write_text(probe, encoding="utf-8")

    completed = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(tmp_path),
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    results = dict(
        line.split("=", 1) for line in completed.stdout.splitlines() if "=" in line.strip()
    )

    # The stub, not the real Azure CLI, answered — and it answered exactly once.
    assert results["AZ_IS_FUNCTION"] == "True"
    assert results["CALLS"] == "1"
    assert results["ARGS_OK"] == "True"

    # The header itself: one entry, no masking, and the fetched token carried through.
    assert results["KEYS"] == "1"
    assert results["STARS"] == "0"
    assert results["EXACT"] == "True", "Authorization is not 'Bearer <the fetched token>'"
    assert int(results["LEN"]) == len("Bearer ") + len(STUB_TOKEN)

    # Failure paths still abort instead of sending a malformed header.
    assert results["THROWS_ON_EXIT"] == "True"
    assert results["THROWS_ON_BLANK"] == "True"


def test_quality_and_secret_gates_fail_closed():
    assert "git status --porcelain" in SCRIPT
    assert "Working tree must be clean" in SCRIPT
    assert "python -m pytest -q" in SCRIPT
    assert "python -m ruff check" in SCRIPT
    assert "Get-Command gitleaks" in SCRIPT
    assert 'if (-not $gitleaks) { throw "gitleaks is required' in SCRIPT
    assert "gitleaks.Source detect --no-banner" in SCRIPT
    assert "SkipGitleaks" not in SCRIPT


def test_every_gate_still_runs_before_a_package_is_built():
    clean = DEPLOY_BLOCK.index("git status --porcelain")
    pytest_gate = DEPLOY_BLOCK.index("python -m pytest -q")
    ruff_gate = DEPLOY_BLOCK.index("python -m ruff check")
    gitleaks_gate = DEPLOY_BLOCK.index("gitleaks.Source detect")
    build = DEPLOY_BLOCK.index("building Python deployment zip")
    upload = DEPLOY_BLOCK.index("Send-KuduPackage")
    assert clean < pytest_gate < ruff_gate < gitleaks_gate < build < upload


def test_upload_requires_http_success_and_async_kudu_terminal_success():
    assert "/api/zipdeploy?isAsync=true" in SCRIPT
    upload = _function(SCRIPT, "Send-KuduPackage")
    assert 'Assert-HttpSuccess $response "Kudu package upload"' in upload
    assert "Wait-KuduDeployment" in upload
    assert "did not return an exact deployment status URI" in SCRIPT
    assert "/api/deployments/latest" not in SCRIPT

    poll = _function(SCRIPT, "Wait-KuduDeployment")
    assert "while ([DateTimeOffset]::UtcNow -lt $deadline)" in poll
    assert "$status -eq 4" in poll
    assert "$status -eq 3" in poll
    assert "deployment timed out" in poll


def test_health_verifies_exact_running_release_and_never_accepts_401():
    health = _function(SCRIPT, "Wait-VerifiedHealth")
    assert "/api/processes" not in health
    assert "Send-KuduPackage already required authenticated terminal Kudu status" in SCRIPT
    assert "azurewebsites.net/api/health" in SCRIPT
    assert 'Assert-HttpSuccess $health "Application health check"' in health
    # The /api/health contract is unchanged: these exact fields still gate promotion.
    assert '$healthBody.status -notin @("ok", "degraded")' in health
    assert "-not $healthBody.data_dir_writable" in health
    assert "-not $healthBody.jobs_healthy" in health
    assert "$healthBody.release_commit -ne $ExpectedCommit" in health
    assert "401" not in SCRIPT


def test_release_records_commit_and_sha256():
    assert "git rev-parse HEAD" in SCRIPT
    assert "zipfile.ZipFile" in SCRIPT
    assert "'.deployment'" in SCRIPT
    assert "archive.writestr('RELEASE_COMMIT', commit)" in SCRIPT
    # Interpolating the path into the Python source breaks on an apostrophe, which a
    # user-profile build directory can legitimately contain.
    assert "$buildSource | python - $buildZip $commit" in SCRIPT
    assert "r'$buildZip'" not in SCRIPT
    assert "Add-DeployRelease -Paths $paths -SourceZip $buildZip -CommitId $commit" in SCRIPT
    add_release = _function(STATE, "Add-DeployRelease")
    assert "Get-FileHash -Path $SourceZip -Algorithm SHA256" in add_release
    assert "Resolve-VerifiedRelease -Paths $Paths -Stem $stem" in add_release


def test_every_package_is_hash_and_commit_verified_before_use():
    resolve = _function(STATE, "Resolve-VerifiedRelease")
    assert "Confirm-PackageHash" in resolve
    assert "Confirm-PackageIdentity" in resolve
    assert "content-addressed name" in resolve
    identity = _function(STATE, "Confirm-PackageIdentity")
    assert 'GetEntry("RELEASE_COMMIT")' in identity
    assert "Package commit verification failed" in identity
    assert "Package SHA256 verification failed" in _function(STATE, "Confirm-PackageHash")


def test_verified_state_is_durable_and_not_tied_to_the_working_copy():
    # The whole point: a throwaway worktree must still find the previous release.
    assert "Get-DeployStatePaths -App $App -StateRoot $StateRoot" in SCRIPT
    assert "$buildZip = $paths.BuildZip" in SCRIPT
    assert '$stateDir = Join-Path $root ".deploy"' not in SCRIPT
    assert "$env:TEMP" not in SCRIPT
    assert "$env:TEMP" not in STATE

    root = _function(STATE, "Get-DeployStateRoot")
    assert "NET_CARE_DEPLOY_STATE_ROOT" in root
    assert "LOCALAPPDATA" in root
    assert "XDG_STATE_HOME" in root
    assert "must be an absolute path" in root
    # Keyed by app so a second App Service cannot overwrite this one's baseline.
    assert 'Join-Path (Join-Path $root "apps") $key' in _function(STATE, "Get-DeployStatePaths")
    assert "not a valid App Service site name" in _function(STATE, "Get-DeployAppKey")

    # The legacy location is still ignored by git so an old checkout stays clean.
    assert ".deploy/" in GITIGNORE
    assert '$legacyStateDir = Join-Path $root ".deploy"' in SCRIPT


def test_promotion_is_a_single_atomic_manifest_write_after_health():
    write = _function(STATE, "Write-DeployManifest")
    assert '$temp = "$($Paths.Manifest).new"' in write
    assert "Move-Item $temp $Paths.Manifest -Force" in write

    deploy = DEPLOY_BLOCK.index("Send-KuduPackage -Package $release.Zip")
    health = DEPLOY_BLOCK.index("Wait-VerifiedHealth -ExpectedCommit $release.Id", deploy)
    promote = DEPLOY_BLOCK.index("Set-DeployPromotion", health)
    prune = DEPLOY_BLOCK.index("Remove-StaleReleases", promote)
    assert deploy < health < promote < prune

    promotion = _function(STATE, "Set-DeployPromotion")
    assert "$promoted.current = $Stem" in promotion
    assert "$promoted.previous = $Manifest.current" in promotion


def test_rollback_verifies_previous_hash_commit_deployment_and_health():
    assert "No complete previous-known-good release" in _function(STATE, "Get-RollbackRelease")
    select = ROLLBACK_BLOCK.index("Get-RollbackRelease")
    deploy = ROLLBACK_BLOCK.index("Send-KuduPackage -Package $release.Zip", select)
    health = ROLLBACK_BLOCK.index("Wait-VerifiedHealth -ExpectedCommit $release.Id", deploy)
    record = ROLLBACK_BLOCK.index("Set-DeployRollback", health)
    # Selection resolves and verifies the package, so verification precedes the upload.
    assert select < deploy < health < record


def test_candidate_failure_restores_current_verified_before_failing():
    candidate_try = DEPLOY_BLOCK.index('Set-DeployJournal -Paths $paths -Phase "upload"')
    candidate_catch = DEPLOY_BLOCK.index("catch {", candidate_try)
    verify = DEPLOY_BLOCK.index(
        "$verified = Resolve-VerifiedRelease -Paths $paths -Stem $restore.Stem",
        candidate_catch,
    )
    restore = DEPLOY_BLOCK.index("Send-KuduPackage -Package $verified.Zip", verify)
    restored_health = DEPLOY_BLOCK.index(
        "Wait-VerifiedHealth -ExpectedCommit $verified.Id", restore
    )
    rethrow = DEPLOY_BLOCK.index("throw $candidateFailure", restored_health)
    promote = DEPLOY_BLOCK.index("Set-DeployPromotion", rethrow)

    assert candidate_try < candidate_catch < verify < restore < restored_health < rethrow
    assert rethrow < promote
    assert "Current verified package identity changed before automatic restore." in SCRIPT
    assert "no current verified package exists" in SCRIPT
    assert "automatic restore of the current verified release also failed" in SCRIPT
    assert "Current verified package state is incomplete" in SCRIPT
    assert "$deployment.message" not in SCRIPT


def test_restore_never_redeploys_a_package_that_was_not_running():
    baseline = _function(STATE, "Select-RestoreBaseline")
    assert "no current verified package exists" in baseline
    assert "$Manifest.history" in baseline
    assert "no stored package matches running release" in baseline
    # Losing the health probe must not disarm the restore; the app may simply be down.
    assert "the running release could not be identified" in baseline
    assert "return $null" in _function(SCRIPT, "Get-LiveReleaseCommit")


def test_retention_is_bounded_and_protects_current_and_previous():
    prune = _function(STATE, "Remove-StaleReleases")
    assert "if ($Retain -lt 2) { $Retain = 2 }" in prune
    assert "foreach ($stem in @($Manifest.current, $Manifest.previous))" in prune
    assert "if ($keep -contains $stem) { continue }" in prune
    assert (
        "Remove-StaleReleases -Paths $paths -Manifest $manifest -Retain $RetainReleases" in SCRIPT
    )
    assert "[int]$RetainReleases = 10" in SCRIPT


def test_migration_adopts_legacy_state_without_destroying_it():
    migrate = _function(STATE, "Import-LegacyDeployState")
    assert "Confirm-PackageHash" in migrate
    assert "Confirm-PackageIdentity" in migrate
    assert "left untouched" in migrate
    # Reading and copying only: an operator's existing artefacts are never removed.
    assert "Remove-Item" not in migrate
    assert "Move-Item" not in migrate
    assert "Import-LegacyDeployState -Paths $paths -LegacyDir $legacyStateDir" in SCRIPT


def test_concurrent_deployments_cannot_corrupt_shared_state():
    lock = _function(STATE, "Lock-DeployState")
    assert "[System.IO.FileShare]::None" in lock
    assert "Another deployment already holds" in lock
    assert "Lock-DeployState -Paths $paths -Purpose" in SCRIPT
    assert SCRIPT.count("Unlock-DeployState -Paths $paths -Handle $lock") == 2
    # The lock must span the remote deployment window, not just the local writes.
    acquire = DEPLOY_BLOCK.index('Lock-DeployState -Paths $paths -Purpose "deploy"')
    upload = DEPLOY_BLOCK.index("Send-KuduPackage -Package $release.Zip", acquire)
    promote = DEPLOY_BLOCK.index("Set-DeployPromotion", upload)
    release_lock = DEPLOY_BLOCK.index("Unlock-DeployState", promote)
    assert acquire < upload < promote < release_lock


def test_deployment_state_behaviour_harness_passes():
    """Run the PowerShell harness so `pytest` covers the state logic, not just its text."""
    powershell = shutil.which("pwsh")
    if powershell is None:  # pragma: no cover - depends on the host toolchain
        pytest.skip("pwsh is not available on this host")

    completed = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-File", str(HARNESS)],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(ROOT),
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "checks passed" in completed.stdout
