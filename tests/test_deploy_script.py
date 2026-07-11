"""Source-level deployment safety regressions (the deploy script is never executed here)."""

from __future__ import annotations

import re
from pathlib import Path

SCRIPT = (Path(__file__).parents[1] / "Scripts" / "deploy.ps1").read_text(encoding="utf-8")
GITIGNORE = (Path(__file__).parents[1] / ".gitignore").read_text(encoding="utf-8")


def _function(name: str) -> str:
    match = re.search(
        rf"(?ms)^function {re.escape(name)} \{{(.*?)(?=^function |\nif \(\$Rollback\))",
        SCRIPT,
    )
    assert match, f"missing PowerShell function {name}"
    return match.group(1)


def test_quality_and_secret_gates_fail_closed():
    assert "git status --porcelain" in SCRIPT
    assert "Working tree must be clean" in SCRIPT
    assert "python -m pytest -q" in SCRIPT
    assert "python -m ruff check" in SCRIPT
    assert "Get-Command gitleaks" in SCRIPT
    assert 'if (-not $gitleaks) { throw "gitleaks is required' in SCRIPT
    assert "gitleaks.Source detect --no-banner" in SCRIPT
    assert "SkipGitleaks" not in SCRIPT


def test_upload_requires_http_success_and_async_kudu_terminal_success():
    assert "/api/zipdeploy?isAsync=true" in SCRIPT
    upload = _function("Send-KuduPackage")
    assert 'Assert-HttpSuccess $response "Kudu package upload"' in upload
    assert "Wait-KuduDeployment" in upload
    assert "did not return an exact deployment status URI" in SCRIPT
    assert "/api/deployments/latest" not in SCRIPT

    poll = _function("Wait-KuduDeployment")
    assert "while ([DateTimeOffset]::UtcNow -lt $deadline)" in poll
    assert "$status -eq 4" in poll
    assert "$status -eq 3" in poll
    assert "deployment timed out" in poll


def test_health_is_authenticated_scm_readiness_and_never_accepts_401():
    health = _function("Wait-VerifiedHealth")
    assert '"$scmBase/api/processes"' in health
    assert "-Headers (Get-AuthHeaders)" in health
    assert 'Assert-HttpSuccess $response "Authenticated SCM readiness check"' in health
    assert "gunicorn|startup" in health
    assert "azurewebsites.net/api/health" in health
    assert 'Assert-HttpSuccess $health "Application health check"' in health
    assert '$healthBody.status -notin @("ok", "degraded")' in health
    assert "$healthBody.release_commit -ne $commit" in health
    assert "401" not in SCRIPT


def test_release_records_commit_and_sha256():
    assert "git rev-parse HEAD" in SCRIPT
    assert "Get-FileHash -Path $buildZip -Algorithm SHA256" in SCRIPT
    assert '"$releaseStem.sha256"' in SCRIPT
    assert '"$releaseStem.commit"' in SCRIPT
    assert "Confirm-PackageHash -Package $releaseZip -ShaRecord $releaseSha" in SCRIPT
    assert "zipfile.ZipFile" in SCRIPT
    assert "'.deployment'" in SCRIPT
    assert "archive.writestr('RELEASE_COMMIT', '$commit')" in SCRIPT
    assert "Confirm-PackageIdentity -Package $releaseZip" in SCRIPT


def test_deploy_state_and_build_are_ignored_and_project_local():
    assert ".deploy/" in GITIGNORE
    assert '$buildDir = Join-Path $stateDir "build"' in SCRIPT
    assert "$env:TEMP" not in SCRIPT


def test_current_promotion_preserves_distinct_previous_after_health():
    candidate_try = SCRIPT.index("try {\n    Send-KuduPackage -Package $releaseZip")
    deploy = SCRIPT.index("Send-KuduPackage -Package $releaseZip", candidate_try)
    health = SCRIPT.index("Wait-VerifiedHealth", deploy)
    preserve = SCRIPT.index("-DestinationZip $previousZip", health)
    promote = SCRIPT.index("-DestinationZip $currentZip", preserve)
    assert deploy < health < preserve < promote


def test_rollback_verifies_previous_hash_commit_deployment_and_health():
    rollback = SCRIPT[SCRIPT.index("if ($Rollback)") : SCRIPT.index("# All gates")]
    assert "No complete previous-known-good release" in rollback
    assert "Confirm-PackageHash -Package $previousZip -ShaRecord $previousSha" in rollback
    assert "Confirm-PackageIdentity -Package $previousZip -CommitRecord $previousCommit" in rollback
    deploy = rollback.index("Send-KuduPackage -Package $previousZip")
    health = rollback.index("Wait-VerifiedHealth", deploy)
    assert deploy < health


def test_candidate_failure_restores_current_verified_before_failing():
    candidate_try = SCRIPT.index("try {\n    Send-KuduPackage -Package $releaseZip")
    candidate_catch = SCRIPT.index("catch {", candidate_try)
    restore = SCRIPT.index("Send-KuduPackage -Package $currentZip", candidate_catch)
    expected_commit = SCRIPT.index(
        "$commit = Confirm-PackageIdentity -Package $currentZip",
        candidate_catch,
    )
    restored_health = SCRIPT.index("Wait-VerifiedHealth", restore)
    rethrow = SCRIPT.index("throw $candidateFailure", restored_health)
    preserve = SCRIPT.index("-DestinationZip $previousZip", rethrow)

    assert candidate_try < candidate_catch < expected_commit < restore < restored_health < rethrow
    assert rethrow < preserve
    assert "no current verified package exists" in SCRIPT
    assert "automatic restore of the current verified release also failed" in SCRIPT
    assert "$deployment.message" not in SCRIPT
