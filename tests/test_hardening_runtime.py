"""Regression tests for bounded jobs, hosted auth, artifacts, and PDF isolation."""

from __future__ import annotations

import base64
import json
import os
import threading
import time

import pytest


@pytest.fixture
def hardened_app(tmp_path, monkeypatch):
    import importlib
    import sys

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ALLOW_LOCAL_AUTH_BYPASS", "1")
    monkeypatch.setenv("LEGACY_SYNC_JOB_RESPONSES", "0")
    for name in list(sys.modules):
        if name == "app" or name == "agent" or name.startswith("agent."):
            del sys.modules[name]
    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config["TESTING"] = True
    yield app_mod
    app_mod._shutdown_executors()


def test_bounded_executor_counts_active_work_as_capacity():
    from agent.job_runtime import BoundedExecutor, SaturatedError

    entered = threading.Event()
    release = threading.Event()
    executor = BoundedExecutor(workers=1, queue_size=0, name="test")
    executor.submit(lambda: (entered.set(), release.wait(2)))
    assert entered.wait(1)
    with pytest.raises(SaturatedError):
        executor.submit(lambda: None)
    release.set()
    executor.shutdown()


def test_executor_survives_unhandled_task_exception():
    from agent.job_runtime import BoundedExecutor

    completed = threading.Event()
    executor = BoundedExecutor(workers=1, queue_size=1, name="survival")
    executor.submit(lambda: (_ for _ in ()).throw(RuntimeError("task failed")))
    executor.submit(completed.set)
    assert completed.wait(1)
    executor.shutdown()


def test_saturation_returns_429_without_creating_job(hardened_app, monkeypatch):
    class Full:
        def submit(self, *_args, **_kwargs):
            from agent.job_runtime import SaturatedError

            raise SaturatedError

    client = hardened_app.app.test_client()
    client.get("/api/health")
    before = list(hardened_app._jobs)
    monkeypatch.setattr(hardened_app, "_get_executor", lambda feed=False: Full())

    response = client.post("/api/digest")

    assert response.status_code == 429
    assert response.headers["Retry-After"]
    assert hardened_app._jobs == before


def test_submission_does_not_source_prune(hardened_app, monkeypatch):
    class CaptureExecutor:
        def submit(self, func):
            self.func = func

    executor = CaptureExecutor()
    pruned = []
    monkeypatch.setattr(hardened_app, "_get_executor", lambda feed=False: executor)
    monkeypatch.setattr(hardened_app, "_prune_retention", lambda: None)
    monkeypatch.setattr(hardened_app, "_prune_sources_safely", lambda: pruned.append(True))

    job, rejection = hardened_app._submit_job("digest", lambda _job_id: None)

    assert rejection is None
    assert job["status"] == "queued"
    assert pruned == []


def test_duplicate_active_digest_is_rejected(hardened_app):
    hardened_app.app.test_client().get("/api/health")
    hardened_app._add_job(
        {
            "id": "active",
            "type": "digest",
            "status": "running",
            "stage": "orchestrating",
            "created_at": "2026-07-11T08:00:00",
        }
    )
    response = hardened_app.app.test_client().post("/api/digest")
    assert response.status_code == 409
    assert response.get_json()["job_id"] == "active"


def _principal(value: object) -> str:
    return base64.b64encode(json.dumps(value).encode()).decode()


_OBJECT_ID_CLAIM = "http://schemas.microsoft.com/identity/claims/objectidentifier"
_NAME_ID_CLAIM = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"


def test_hosted_api_requires_valid_easy_auth(hardened_app, monkeypatch):
    monkeypatch.setenv("WEBSITE_SITE_NAME", "hosted")
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    client = hardened_app.app.test_client()

    assert client.get("/api/status").status_code == 401
    assert (
        client.get("/api/status", headers={"X-MS-CLIENT-PRINCIPAL": "not-base64"}).status_code
        == 401
    )
    valid = _principal(
        {"claims": [{"typ": _OBJECT_ID_CLAIM, "val": "00000000-0000-4000-8000-000000000000"}]}
    )
    assert client.get("/api/status", headers={"X-MS-CLIENT-PRINCIPAL": valid}).status_code == 200


def test_hosted_object_id_claim_overrides_email_header_and_matches_allowlist(
    hardened_app, monkeypatch
):
    object_id = "00000000-0000-4000-8000-000000000001"
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_ALLOWED_PRINCIPAL_IDS", object_id)
    principal = _principal({"claims": [{"typ": _OBJECT_ID_CLAIM, "val": object_id}]})

    response = hardened_app.app.test_client().get(
        "/api/status",
        headers={
            "X-MS-CLIENT-PRINCIPAL-ID": "caregiver@example.invalid",
            "X-MS-CLIENT-PRINCIPAL": principal,
        },
    )

    assert response.status_code == 200


def test_hosted_object_id_claim_precedes_all_lower_priority_values(hardened_app, monkeypatch):
    object_id = "00000000-0000-4000-8000-000000000002"
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_ALLOWED_PRINCIPAL_IDS", object_id)
    principal = _principal(
        {
            "userId": "different-user-id",
            "userDetails": "different-user-details",
            "claims": [
                {"typ": "sub", "val": "different-subject"},
                {"typ": _NAME_ID_CLAIM, "val": "different-name-id"},
                {"typ": _OBJECT_ID_CLAIM, "val": object_id},
            ],
        }
    )

    response = hardened_app.app.test_client().get(
        "/api/status",
        headers={
            "X-MS-CLIENT-PRINCIPAL-ID": "different-header-id",
            "X-MS-CLIENT-PRINCIPAL": principal,
        },
    )

    assert response.status_code == 200


def test_hosted_oid_claim_is_used_without_canonical_object_id(hardened_app, monkeypatch):
    object_id = "00000000-0000-4000-8000-000000000003"
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_ALLOWED_PRINCIPAL_IDS", object_id)
    principal = _principal(
        {
            "claims": [
                {"typ": _NAME_ID_CLAIM, "val": "different-name-id"},
                {"typ": "oid", "val": object_id},
            ]
        }
    )

    response = hardened_app.app.test_client().get(
        "/api/status", headers={"X-MS-CLIENT-PRINCIPAL": principal}
    )

    assert response.status_code == 200


def test_hosted_nameidentifier_precedes_sub_deterministically(hardened_app, monkeypatch):
    name_id = "stable-name-identifier"
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_ALLOWED_PRINCIPAL_IDS", name_id)
    principal = _principal(
        {
            "claims": [
                {"typ": "sub", "val": "different-subject"},
                {"typ": _NAME_ID_CLAIM, "val": name_id},
            ]
        }
    )

    response = hardened_app.app.test_client().get(
        "/api/status", headers={"X-MS-CLIENT-PRINCIPAL": principal}
    )

    assert response.status_code == 200


def test_hosted_sub_claim_is_used_without_higher_priority_claims(hardened_app, monkeypatch):
    subject = "stable-subject"
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_ALLOWED_PRINCIPAL_IDS", subject)
    principal = _principal({"claims": [{"typ": "sub", "val": subject}]})

    response = hardened_app.app.test_client().get(
        "/api/status", headers={"X-MS-CLIENT-PRINCIPAL": principal}
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("header_id", "principal_fields", "configured_id"),
    [
        ("provider-header-id", {"userId": "encoded-user-id"}, "provider-header-id"),
        (None, {"userId": "encoded-user-id"}, "encoded-user-id"),
        (None, {"userDetails": "encoded-user-details"}, "encoded-user-details"),
    ],
)
def test_static_web_apps_principal_fields_are_never_identity(
    hardened_app, monkeypatch, header_id, principal_fields, configured_id
):
    """`userId`/`userDetails` belong to Static Web Apps, not App Service Easy Auth."""
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_ALLOWED_PRINCIPAL_IDS", configured_id)
    headers = {"X-MS-CLIENT-PRINCIPAL": _principal({**principal_fields, "claims": []})}
    if header_id:
        headers["X-MS-CLIENT-PRINCIPAL-ID"] = header_id

    response = hardened_app.app.test_client().get("/api/status", headers=headers)

    # The provider header still authenticates; the wrong-schema fields never do.
    assert response.status_code == (200 if header_id else 401)


def test_hosted_duplicate_identical_object_id_claims_are_accepted(hardened_app, monkeypatch):
    object_id = "00000000-0000-4000-8000-000000000004"
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_ALLOWED_PRINCIPAL_IDS", object_id)
    principal = _principal(
        {
            "claims": [
                {"typ": _OBJECT_ID_CLAIM, "val": object_id},
                {"typ": _OBJECT_ID_CLAIM, "val": f" {object_id} "},
            ]
        }
    )

    response = hardened_app.app.test_client().get(
        "/api/status", headers={"X-MS-CLIENT-PRINCIPAL": principal}
    )

    assert response.status_code == 200


def test_hosted_conflicting_selected_claim_values_fail_authentication(hardened_app, monkeypatch):
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    principal = _principal(
        {
            "claims": [
                {
                    "typ": _OBJECT_ID_CLAIM,
                    "val": "00000000-0000-4000-8000-000000000005",
                },
                {
                    "typ": _OBJECT_ID_CLAIM,
                    "val": "00000000-0000-4000-8000-000000000006",
                },
            ]
        }
    )

    response = hardened_app.app.test_client().get(
        "/api/status",
        headers={
            "X-MS-CLIENT-PRINCIPAL-ID": "fallback-id",
            "X-MS-CLIENT-PRINCIPAL": principal,
        },
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "encoded",
    [
        "not-base64",
        _principal([]),
        _principal({"claims": {}}),
        _principal({"claims": None}),
        _principal({"claims": ["not-a-claim"]}),
        _principal({"claims": [{"typ": [], "val": "value"}]}),
        _principal({"claims": [{"typ": _OBJECT_ID_CLAIM, "val": {}}]}),
        _principal({"claims": [{"typ": "oid", "val": "  "}]}),
    ],
)
def test_hosted_malformed_principal_cannot_fall_back_to_header(hardened_app, monkeypatch, encoded):
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_ALLOWED_PRINCIPAL_IDS", "fallback-id")

    response = hardened_app.app.test_client().get(
        "/api/status",
        headers={
            "X-MS-CLIENT-PRINCIPAL-ID": "fallback-id",
            "X-MS-CLIENT-PRINCIPAL": encoded,
        },
    )

    assert response.status_code == 401


def test_hosted_nonmatching_object_id_is_denied_even_with_plausible_email_header(
    hardened_app, monkeypatch
):
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_ALLOWED_PRINCIPAL_IDS", "00000000-0000-4000-8000-000000000007")
    principal = _principal(
        {
            "claims": [
                {
                    "typ": _OBJECT_ID_CLAIM,
                    "val": "00000000-0000-4000-8000-000000000008",
                }
            ]
        }
    )

    response = hardened_app.app.test_client().get(
        "/api/status",
        headers={
            "X-MS-CLIENT-PRINCIPAL-ID": "caregiver@example.invalid",
            "X-MS-CLIENT-PRINCIPAL": principal,
        },
    )

    assert response.status_code == 403


def test_hosted_allowlist_fails_closed(hardened_app, monkeypatch):
    monkeypatch.setenv("WEBSITE_INSTANCE_ID", "instance")
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_ALLOWED_PRINCIPAL_IDS", "allowed-id")
    client = hardened_app.app.test_client()
    assert (
        client.get("/api/status", headers={"X-MS-CLIENT-PRINCIPAL-ID": "other-id"}).status_code
        == 403
    )
    assert (
        client.get("/api/status", headers={"X-MS-CLIENT-PRINCIPAL-ID": "allowed-id"}).status_code
        == 200
    )


_ACCOUNT_GUID = "00000000-0000-4000-8000-00000000000a"
_ACCOUNT_EMAIL = "caregiver@example.invalid"


def _hosted(monkeypatch, *, ids: str | None = None, names: str | None = None) -> None:
    monkeypatch.setenv("WEBSITE_SITE_NAME", "hosted")
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    for variable, value in (
        ("AUTH_ALLOWED_PRINCIPAL_IDS", ids),
        ("AUTH_ALLOWED_PRINCIPAL_NAMES", names),
    ):
        if value is None:
            monkeypatch.delenv(variable, raising=False)
        else:
            monkeypatch.setenv(variable, value)


def test_blob_absent_email_id_header_matches_legacy_id_allowlist(hardened_app, monkeypatch):
    """Transition step 0: the production bridge (GUID + email in IDs) keeps working."""
    _hosted(monkeypatch, ids=f"{_ACCOUNT_GUID},{_ACCOUNT_EMAIL}")

    response = hardened_app.app.test_client().get(
        "/api/status", headers={"X-MS-CLIENT-PRINCIPAL-ID": _ACCOUNT_EMAIL}
    )

    assert response.status_code == 200


def test_blob_absent_email_id_header_matches_split_name_allowlist(hardened_app, monkeypatch):
    """Transition step 2: GUID in IDs, exact email in NAMES, no blob, no name header."""
    _hosted(monkeypatch, ids=_ACCOUNT_GUID, names=_ACCOUNT_EMAIL)

    response = hardened_app.app.test_client().get(
        "/api/status", headers={"X-MS-CLIENT-PRINCIPAL-ID": _ACCOUNT_EMAIL}
    )

    assert response.status_code == 200


def test_transition_overlap_config_accepts_both_platform_shapes(hardened_app, monkeypatch):
    """Transition step 1: overlapping settings never require both gates to match."""
    _hosted(monkeypatch, ids=f"{_ACCOUNT_GUID},{_ACCOUNT_EMAIL}", names=_ACCOUNT_EMAIL)
    client = hardened_app.app.test_client()

    id_only = client.get("/api/status", headers={"X-MS-CLIENT-PRINCIPAL-ID": _ACCOUNT_EMAIL})
    claim_only = client.get(
        "/api/status",
        headers={
            "X-MS-CLIENT-PRINCIPAL": _principal(
                {"claims": [{"typ": _OBJECT_ID_CLAIM, "val": _ACCOUNT_GUID}]}
            )
        },
    )
    name_only = client.get(
        "/api/status",
        headers={
            "X-MS-CLIENT-PRINCIPAL-NAME": _ACCOUNT_EMAIL,
            "X-MS-CLIENT-PRINCIPAL": _principal(
                {
                    "claims": [
                        {"typ": _OBJECT_ID_CLAIM, "val": "00000000-0000-4000-8000-0000000000ff"}
                    ]
                }
            ),
        },
    )

    assert (id_only.status_code, claim_only.status_code, name_only.status_code) == (200, 200, 200)


def test_principal_name_header_is_preferred_over_email_id_compat(hardened_app, monkeypatch):
    _hosted(monkeypatch, ids=_ACCOUNT_GUID, names=_ACCOUNT_EMAIL)

    response = hardened_app.app.test_client().get(
        "/api/status",
        headers={
            "X-MS-CLIENT-PRINCIPAL-NAME": _ACCOUNT_EMAIL,
            "X-MS-CLIENT-PRINCIPAL-ID": _ACCOUNT_GUID,
        },
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("configured", "presented"),
    [
        (_ACCOUNT_EMAIL.upper(), _ACCOUNT_EMAIL),
        (f"  {_ACCOUNT_EMAIL}  ", _ACCOUNT_EMAIL),
        ("Caregiver@Example.Invalid", _ACCOUNT_EMAIL),
        ("Ünicode@example.invalid", "ünicode@example.invalid"),
    ],
)
def test_name_allowlist_uses_unicode_safe_casefold_and_trimming(
    hardened_app, monkeypatch, configured, presented
):
    _hosted(monkeypatch, names=configured)

    response = hardened_app.app.test_client().get(
        "/api/status", headers={"X-MS-CLIENT-PRINCIPAL-NAME": presented}
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    "presented",
    [
        "care.giver@example.invalid",
        "caregiver+net@example.invalid",
        "caregiver@example.invalid.example",
        "caregiver",
    ],
)
def test_name_allowlist_never_widens_dot_plus_or_domain_equivalence(
    hardened_app, monkeypatch, presented
):
    _hosted(monkeypatch, names=_ACCOUNT_EMAIL)

    response = hardened_app.app.test_client().get(
        "/api/status", headers={"X-MS-CLIENT-PRINCIPAL-NAME": presented}
    )

    assert response.status_code == 403


def test_conflicting_email_name_sources_fail_the_name_path_closed(hardened_app, monkeypatch):
    _hosted(monkeypatch, names=f"{_ACCOUNT_EMAIL},other@example.invalid")

    response = hardened_app.app.test_client().get(
        "/api/status",
        headers={
            "X-MS-CLIENT-PRINCIPAL-NAME": "other@example.invalid",
            "X-MS-CLIENT-PRINCIPAL-ID": _ACCOUNT_EMAIL,
        },
    )

    assert response.status_code == 403
    assert response.get_json()["reason"] == "principal_not_allowed"


def test_id_allowlist_entry_never_authorizes_the_name_candidate(hardened_app, monkeypatch):
    _hosted(monkeypatch, ids=_ACCOUNT_EMAIL)

    response = hardened_app.app.test_client().get(
        "/api/status",
        headers={
            "X-MS-CLIENT-PRINCIPAL-NAME": _ACCOUNT_EMAIL,
            "X-MS-CLIENT-PRINCIPAL": _principal(
                {"claims": [{"typ": _OBJECT_ID_CLAIM, "val": _ACCOUNT_GUID}]}
            ),
        },
    )

    assert response.status_code == 403


def test_name_allowlist_entry_never_authorizes_the_id_candidate(hardened_app, monkeypatch):
    _hosted(monkeypatch, names=_ACCOUNT_GUID)

    response = hardened_app.app.test_client().get(
        "/api/status",
        headers={
            "X-MS-CLIENT-PRINCIPAL": _principal(
                {"claims": [{"typ": _OBJECT_ID_CLAIM, "val": _ACCOUNT_GUID}]}
            )
        },
    )

    assert response.status_code == 403


def test_id_allowlist_stays_case_sensitive(hardened_app, monkeypatch):
    _hosted(monkeypatch, ids="Stable-Object-Id")

    response = hardened_app.app.test_client().get(
        "/api/status", headers={"X-MS-CLIENT-PRINCIPAL-ID": "stable-object-id"}
    )

    assert response.status_code == 403


def test_both_allowlists_empty_preserve_easy_auth_only_access(hardened_app, monkeypatch):
    """Documented, unchanged posture: no allowlist means Easy Auth is the only gate."""
    _hosted(monkeypatch)
    client = hardened_app.app.test_client()

    assert client.get("/api/status").status_code == 401
    assert (
        client.get(
            "/api/status", headers={"X-MS-CLIENT-PRINCIPAL-ID": "any-authenticated-id"}
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/api/status", headers={"X-MS-CLIENT-PRINCIPAL-NAME": "someone@example.invalid"}
        ).status_code
        == 200
    )


def _encode(value: object, *, urlsafe: bool = False, padded: bool = True) -> str:
    raw = json.dumps(value).encode()
    encoded = (base64.urlsafe_b64encode(raw) if urlsafe else base64.b64encode(raw)).decode()
    return encoded if padded else encoded.rstrip("=")


@pytest.mark.parametrize("urlsafe", [False, True])
@pytest.mark.parametrize("padded", [False, True])
def test_standard_and_urlsafe_base64_principals_decode_with_or_without_padding(
    hardened_app, monkeypatch, urlsafe, padded
):
    # "?" and ">" force bytes that encode to the differing "+/" vs "-_" alphabet.
    object_id = "00000000-0000-4000-8000-00000000000b"
    _hosted(monkeypatch, ids=object_id)
    principal = _encode(
        {"claims": [{"typ": _OBJECT_ID_CLAIM, "val": object_id}], "pad": "??>>?"},
        urlsafe=urlsafe,
        padded=padded,
    )

    response = hardened_app.app.test_client().get(
        "/api/status", headers={"X-MS-CLIENT-PRINCIPAL": principal}
    )

    assert response.status_code == 200


def _oversized_blob() -> str:
    filler = "x" * 13000
    return base64.b64encode(json.dumps({"claims": [], "filler": filler}).encode()).decode()


def _too_many_claims() -> str:
    claims = [{"typ": f"filler-{index}", "val": "v"} for index in range(513)]
    return base64.b64encode(json.dumps({"claims": claims}).encode()).decode()


@pytest.mark.parametrize(
    "encoded",
    [
        "A",
        "not base64",
        "YWJj=ZGVm",
        "e30-e30_+/",
        _oversized_blob(),
        _too_many_claims(),
        base64.b64encode(b"not json at all").decode(),
    ],
)
def test_corrupt_oversized_or_overbroad_principals_fail_closed(hardened_app, monkeypatch, encoded):
    _hosted(monkeypatch, ids=_ACCOUNT_EMAIL, names=_ACCOUNT_EMAIL)

    response = hardened_app.app.test_client().get(
        "/api/status",
        headers={
            "X-MS-CLIENT-PRINCIPAL": encoded,
            "X-MS-CLIENT-PRINCIPAL-ID": _ACCOUNT_EMAIL,
            "X-MS-CLIENT-PRINCIPAL-NAME": _ACCOUNT_EMAIL,
        },
    )

    assert response.status_code == 401
    assert response.get_json()["reason"] == "principal_malformed"


def test_oversized_convenience_headers_are_ignored_rather_than_trusted(hardened_app, monkeypatch):
    _hosted(monkeypatch, ids="short-id")

    response = hardened_app.app.test_client().get(
        "/api/status", headers={"X-MS-CLIENT-PRINCIPAL-ID": "x" * 513}
    )

    assert response.status_code == 401
    assert response.get_json()["reason"] == "principal_absent"


_ALLOWED_AUTH_REASONS = {
    "principal_absent",
    "principal_malformed",
    "principal_not_allowed",
    "cross_origin",
    "hosted_auth_unavailable",
}
_ALLOWED_PRINCIPAL_SOURCES = {
    "encoded_claim",
    "provider_id_header",
    "principal_name_header",
    "provider_id_name_compat",
    "absent",
}


def _auth_bodies(client, monkeypatch) -> list[tuple[int, dict]]:
    _hosted(monkeypatch, ids=_ACCOUNT_GUID, names=_ACCOUNT_EMAIL)
    monkeypatch.setenv("WEBSITE_HOSTNAME", "care.example")
    monkeypatch.delenv("APP_ORIGIN", raising=False)
    claim_denied = _principal(
        {"claims": [{"typ": _OBJECT_ID_CLAIM, "val": "00000000-0000-4000-8000-0000000000cd"}]}
    )
    responses = [
        client.get("/api/status"),
        client.get("/api/status", headers={"X-MS-CLIENT-PRINCIPAL": "!!!"}),
        client.get("/api/status", headers={"X-MS-CLIENT-PRINCIPAL": claim_denied}),
        client.get("/api/status", headers={"X-MS-CLIENT-PRINCIPAL-ID": "rejected-marker-id"}),
        client.get(
            "/api/status", headers={"X-MS-CLIENT-PRINCIPAL-NAME": "rejected-marker@example.invalid"}
        ),
        client.post(
            "/api/digest",
            headers={
                "Origin": "https://attacker.example",
                "X-MS-CLIENT-PRINCIPAL-ID": _ACCOUNT_GUID,
            },
        ),
    ]
    return [(response.status_code, response.get_json()) for response in responses]


def test_auth_failure_bodies_expose_only_fixed_phi_free_discriminators(hardened_app, monkeypatch):
    results = _auth_bodies(hardened_app.app.test_client(), monkeypatch)

    assert [status for status, _ in results] == [401, 401, 403, 403, 403, 403]
    assert [body["reason"] for _, body in results] == [
        "principal_absent",
        "principal_malformed",
        "principal_not_allowed",
        "principal_not_allowed",
        "principal_not_allowed",
        "cross_origin",
    ]
    assert [body.get("principal_source") for _, body in results] == [
        "absent",
        "absent",
        "encoded_claim",
        "provider_id_header",
        "principal_name_header",
        None,
    ]
    serialized = json.dumps([body for _, body in results])
    for leaked in (
        _ACCOUNT_GUID,
        _ACCOUNT_EMAIL,
        "rejected-marker",
        "attacker",
        "schemas.microsoft.com",
        "X-MS-CLIENT",
    ):
        assert leaked not in serialized
    for _, body in results:
        assert set(body) <= {"error", "reason", "principal_source"}
        assert body["reason"] in _ALLOWED_AUTH_REASONS
        assert body.get("principal_source", "absent") in _ALLOWED_PRINCIPAL_SOURCES


def test_provider_id_name_compat_is_reported_as_its_own_source(hardened_app, monkeypatch):
    _hosted(monkeypatch, names="someone-else@example.invalid")

    response = hardened_app.app.test_client().get(
        "/api/status", headers={"X-MS-CLIENT-PRINCIPAL-ID": _ACCOUNT_EMAIL}
    )

    assert response.status_code == 403
    # The ID candidate wins the source label; the compat name is still evaluated.
    assert response.get_json()["principal_source"] == "provider_id_header"


def test_hosted_auth_unavailable_body_carries_its_own_reason(hardened_app, monkeypatch):
    monkeypatch.setenv("WEBSITE_SITE_NAME", "hosted")
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "false")

    response = hardened_app.app.test_client().get("/api/status")

    assert response.status_code == 503
    assert response.get_json() == {
        "error": "Hosted authentication is not enabled.",
        "reason": "hosted_auth_unavailable",
    }


def test_allowed_principal_is_still_blocked_on_a_cross_origin_mutation(hardened_app, monkeypatch):
    """Authorization now runs before the origin check; CSRF must still hold."""
    _hosted(monkeypatch, ids=_ACCOUNT_GUID)
    monkeypatch.setenv("WEBSITE_HOSTNAME", "care.example")
    monkeypatch.delenv("APP_ORIGIN", raising=False)

    response = hardened_app.app.test_client().post(
        "/api/digest",
        headers={
            "Origin": "https://attacker.example",
            "X-MS-CLIENT-PRINCIPAL-ID": _ACCOUNT_GUID,
        },
    )

    assert response.status_code == 403
    assert response.get_json() == {
        "error": "Cross-origin request denied.",
        "reason": "cross_origin",
    }


def test_denied_principal_is_reported_as_denial_not_as_a_cross_origin_problem(
    hardened_app, monkeypatch
):
    """A denied account must keep the eviction-triggering reason."""
    _hosted(monkeypatch, ids=_ACCOUNT_GUID)
    monkeypatch.setenv("WEBSITE_HOSTNAME", "care.example")

    response = hardened_app.app.test_client().post(
        "/api/digest",
        headers={
            "Origin": "https://attacker.example",
            "X-MS-CLIENT-PRINCIPAL-ID": "not-the-allowed-id",
        },
    )

    assert response.status_code == 403
    assert response.get_json()["reason"] == "principal_not_allowed"


def test_protect_api_precedes_lazy_init_and_denied_requests_touch_no_storage(
    hardened_app, monkeypatch
):
    handlers = [
        getattr(handler, "__name__", "") for handler in hardened_app.app.before_request_funcs[None]
    ]
    assert handlers.index("_protect_api") < handlers.index("_lazy_init")

    calls: list[str] = []
    monkeypatch.setattr(hardened_app, "_initialized", False)
    monkeypatch.setattr(hardened_app, "_load_jobs", lambda: calls.append("load_jobs") or True)
    monkeypatch.setattr(hardened_app, "_prune_retention", lambda: calls.append("retention"))
    monkeypatch.setattr(hardened_app, "_prune_sources_safely", lambda: calls.append("sources"))
    _hosted(monkeypatch, ids=_ACCOUNT_GUID)
    monkeypatch.setenv("WEBSITE_HOSTNAME", "care.example")
    client = hardened_app.app.test_client()

    assert client.get("/api/status").status_code == 401
    assert (
        client.get("/api/status", headers={"X-MS-CLIENT-PRINCIPAL-ID": "denied-id"}).status_code
        == 403
    )
    assert (
        client.post(
            "/api/digest",
            headers={
                "Origin": "https://attacker.example",
                "X-MS-CLIENT-PRINCIPAL-ID": _ACCOUNT_GUID,
            },
        ).status_code
        == 403
    )
    assert calls == []
    assert hardened_app._initialized is False

    allowed = client.get("/api/status", headers={"X-MS-CLIENT-PRINCIPAL-ID": _ACCOUNT_GUID})

    assert allowed.status_code == 200
    assert calls == ["load_jobs", "retention", "sources"]


def test_unhosted_principal_header_does_not_replace_explicit_bypass(hardened_app, monkeypatch):
    monkeypatch.delenv("ALLOW_LOCAL_AUTH_BYPASS", raising=False)
    response = hardened_app.app.test_client().get(
        "/api/status",
        headers={"X-MS-CLIENT-PRINCIPAL-ID": "spoofed-id"},
    )
    assert response.status_code == 401


def test_hosted_auth_disabled_fails_closed_and_ignores_fabricated_principal(
    hardened_app, monkeypatch
):
    monkeypatch.setenv("WEBSITE_SITE_NAME", "hosted")
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "false")
    response = hardened_app.app.test_client().get(
        "/api/status",
        headers={"X-MS-CLIENT-PRINCIPAL-ID": "spoofed-id"},
    )
    assert response.status_code == 503


def test_cross_origin_mutation_is_denied(hardened_app):
    response = hardened_app.app.test_client().post(
        "/api/digest", headers={"Origin": "https://attacker.example"}
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    ("origin_env", "hostname", "origin"),
    [
        ("https://care.example", "ignored.azurewebsites.net", "https://care.example"),
        (None, "care.azurewebsites.net", "https://care.azurewebsites.net"),
    ],
)
def test_hosted_same_origin_uses_canonical_https_origin(
    hardened_app, monkeypatch, origin_env, hostname, origin
):
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    monkeypatch.setenv("WEBSITE_HOSTNAME", hostname)
    if origin_env:
        monkeypatch.setenv("APP_ORIGIN", origin_env)
    else:
        monkeypatch.delenv("APP_ORIGIN", raising=False)
    monkeypatch.setattr(
        hardened_app,
        "_submit_job",
        lambda *_args, **_kwargs: ({"id": "accepted"}, None),
    )
    response = hardened_app.app.test_client().post(
        "/api/digest",
        base_url="http://internal:8000",
        headers={
            "Origin": origin,
            "X-MS-CLIENT-PRINCIPAL-ID": "trusted-id",
        },
    )
    assert response.status_code == 202


def test_hosted_mutation_fails_closed_without_trusted_origin(hardened_app, monkeypatch):
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    monkeypatch.delenv("WEBSITE_HOSTNAME", raising=False)
    monkeypatch.delenv("APP_ORIGIN", raising=False)
    response = hardened_app.app.test_client().post(
        "/api/digest",
        headers={"X-MS-CLIENT-PRINCIPAL-ID": "trusted-id"},
    )
    assert response.status_code == 403


def test_hosted_mutation_requires_origin_even_with_trusted_hostname(hardened_app, monkeypatch):
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    monkeypatch.setenv("WEBSITE_HOSTNAME", "care.azurewebsites.net")
    response = hardened_app.app.test_client().post(
        "/api/digest",
        headers={"X-MS-CLIENT-PRINCIPAL-ID": "trusted-id"},
    )
    assert response.status_code == 403


def test_prepare_failure_always_releases_admitted_worker(hardened_app, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    executor = hardened_app.BoundedExecutor(workers=1, queue_size=0, name="admission")
    monkeypatch.setattr(hardened_app, "_get_executor", lambda feed=False: executor)
    monkeypatch.setattr(
        hardened_app,
        "_save_jobs",
        lambda: (_ for _ in ()).throw(OSError("storage unavailable")),
    )

    with pytest.raises(OSError):
        hardened_app._submit_job(
            "digest",
            lambda _job_id: entered.set(),
            prepare=lambda _job: (_ for _ in ()).throw(RuntimeError("prepare failed")),
        )

    deadline = time.time() + 1
    while executor.counts() != (0, 0) and time.time() < deadline:
        time.sleep(0.01)
    assert executor.counts() == (0, 0)
    executor.submit(lambda: (entered.set(), release.wait(1)))
    assert entered.wait(1)
    release.set()
    executor.shutdown()


def test_pdf_subprocess_does_not_use_thread_unsafe_preexec():
    from agent import job_runtime

    source = __import__("inspect").getsource(job_runtime.extract_pdf_subprocess)
    assert "preexec_fn" not in source


def test_failed_job_quarantine_keeps_admission_disabled(hardened_app, monkeypatch):
    hardened_app.JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    hardened_app.JOBS_PATH.write_text("{bad", encoding="utf-8")
    monkeypatch.setattr(hardened_app, "_quarantine_jobs", lambda **_kwargs: False)

    assert hardened_app._load_jobs() is False
    assert hardened_app._jobs_healthy is False
    assert hardened_app.JOBS_PATH.read_text(encoding="utf-8") == "{bad"


def test_job_file_contains_only_metadata_and_detail_hydrates(hardened_app):
    report = hardened_app.DATA_DIR / "reports" / "r.txt"
    report.parent.mkdir(parents=True)
    report.write_text("private report", encoding="utf-8")
    profile_revision = hardened_app.agent.load_profile().get("profile_revision")
    hardened_app._add_job(
        {
            "id": "job1",
            "type": "digest",
            "status": "done",
            "stage": "done",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "report": "must not persist",
            "input_preview": "must not persist",
            "traceback": "must not persist",
            "report_file": "reports/r.txt",
            "profile_revision": profile_revision,
        }
    )
    stored = hardened_app.JOBS_PATH.read_text(encoding="utf-8")
    assert "private report" not in stored
    assert "preview" not in stored
    assert "traceback" not in stored
    detail = hardened_app.app.test_client().get("/api/jobs/job1").get_json()
    assert detail["report"] == "private report"
    assert detail["artifact"] == {
        "kind": "report",
        "state": "available",
        "freshness": "current",
    }
    assert "report_file" not in detail
    assert "result_file" not in detail
    assert "artifact_state" not in detail


def test_job_artifact_contract_is_bounded_and_backward_compatible(hardened_app):
    profile_revision = hardened_app.agent.load_profile().get("profile_revision")
    jobs = [
        {
            "id": "active",
            "type": "digest",
            "status": "running",
            "stage": "running",
            "created_at": "2026-08-01T10:00:00",
            "artifact_state": "none",
        },
        {
            "id": "expired",
            "type": "feed",
            "status": "done",
            "stage": "done",
            "created_at": "2026-01-01T10:00:00",
            "artifact_state": "expired",
            "profile_revision": profile_revision,
        },
        {
            "id": "missing",
            "type": "summary",
            "status": "done",
            "stage": "done",
            "created_at": "2026-08-01T10:00:00",
            "artifact_state": "available",
            "result_file": "job_results/missing.json",
            "profile_revision": profile_revision,
        },
        {
            "id": "legacy",
            "type": "digest",
            "status": "done",
            "stage": "done",
            "created_at": "2025-01-01T10:00:00",
            "profile_revision": profile_revision,
        },
        {
            "id": "unknown-kind",
            "type": "future-safe-job",
            "status": "done",
            "stage": "done",
            "created_at": "2026-08-01T10:00:00",
        },
    ]

    payloads = [
        hardened_app._job_response(job, profile={"profile_revision": profile_revision})
        for job in jobs
    ]

    assert [payload["artifact"] for payload in payloads] == [
        {"kind": "report", "state": "none", "freshness": "unknown"},
        {"kind": "report", "state": "expired", "freshness": "unknown"},
        {"kind": "result", "state": "unavailable", "freshness": "unknown"},
        {"kind": "report", "state": "legacy_unknown", "freshness": "unknown"},
        {"kind": "none", "state": "none", "freshness": "unknown"},
    ]
    assert all("report_file" not in payload for payload in payloads)
    assert all("result_file" not in payload for payload in payloads)


def test_job_list_rejects_existing_but_corrupt_artifacts(hardened_app):
    report = hardened_app.DATA_DIR / "reports" / "corrupt.txt"
    result = hardened_app.DATA_DIR / "job_results" / "corrupt.json"
    report.parent.mkdir(parents=True)
    result.parent.mkdir(parents=True)
    report.write_bytes(b"\xff\xfe")
    result.write_text("{invalid", encoding="utf-8")
    profile_revision = hardened_app.agent.load_profile().get("profile_revision")
    jobs = [
        {
            "id": "corrupt-report",
            "type": "digest",
            "status": "done",
            "stage": "done",
            "created_at": "2026-08-01T10:00:00",
            "artifact_state": "available",
            "report_file": "reports/corrupt.txt",
            "profile_revision": profile_revision,
        },
        {
            "id": "corrupt-result",
            "type": "chat",
            "status": "done",
            "stage": "done",
            "created_at": "2026-08-01T10:00:00",
            "artifact_state": "available",
            "result_file": "job_results/corrupt.json",
            "profile_revision": profile_revision,
        },
    ]

    listed = [
        hardened_app._job_response(job, profile={"profile_revision": profile_revision})
        for job in jobs
    ]
    detailed = [
        hardened_app._job_response(
            job,
            include_artifacts=True,
            profile={"profile_revision": profile_revision},
        )
        for job in jobs
    ]

    assert [item["artifact"]["state"] for item in listed] == ["unavailable", "unavailable"]
    assert [item["artifact"]["freshness"] for item in listed] == ["unknown", "unknown"]
    assert all(item["artifact"]["state"] == "unavailable" for item in detailed)
    assert all(item["artifact_unavailable"] is True for item in detailed)
    assert "report" not in detailed[0]
    assert "result" not in detailed[1]


def test_stale_corrupt_report_list_and_detail_remain_unavailable(hardened_app):
    report = hardened_app.DATA_DIR / "reports" / "stale-corrupt.txt"
    report.parent.mkdir(parents=True)
    report.write_bytes(b"\xff\xfe")
    job = {
        "id": "stale-corrupt-report",
        "type": "digest",
        "status": "done",
        "stage": "done",
        "created_at": "2026-08-01T10:00:00",
        "artifact_state": "available",
        "report_file": "reports/stale-corrupt.txt",
        "profile_revision": 1,
    }
    profile = {"profile_revision": 2}

    listed = hardened_app._job_response(job, profile=profile)
    detailed = hardened_app._job_response(job, include_artifacts=True, profile=profile)

    assert listed["artifact"] == {
        "kind": "report",
        "state": "unavailable",
        "freshness": "unknown",
    }
    assert detailed["artifact"] == listed["artifact"]
    assert detailed["report_stale"] is True
    assert detailed["report_available_for_audit"] is False
    assert detailed["artifact_unavailable"] is True
    assert "report" not in detailed

    stored_unavailable = {
        **job,
        "id": "stale-stored-unavailable",
        "artifact_state": "unavailable",
        "report_file": "reports/missing.txt",
    }
    unavailable_list = hardened_app._job_response(stored_unavailable, profile=profile)
    unavailable_detail = hardened_app._job_response(
        stored_unavailable,
        include_artifacts=True,
        profile=profile,
    )
    assert unavailable_list["artifact"] == listed["artifact"]
    assert unavailable_detail["artifact"] == listed["artifact"]
    assert unavailable_detail["report_available_for_audit"] is False
    assert unavailable_detail["artifact_unavailable"] is True
    assert "report" not in unavailable_detail


def test_current_unavailable_state_never_hydrates_readable_artifacts(hardened_app):
    report = hardened_app.DATA_DIR / "reports" / "readable.txt"
    result = hardened_app.DATA_DIR / "job_results" / "readable.json"
    report.parent.mkdir(parents=True)
    result.parent.mkdir(parents=True)
    report.write_text("must stay hidden", encoding="utf-8")
    result.write_text(json.dumps({"reply": "must stay hidden"}), encoding="utf-8")
    profile = {"profile_revision": 2}
    jobs = [
        {
            "id": "unavailable-report",
            "type": "digest",
            "status": "done",
            "stage": "done",
            "created_at": "2026-08-01T10:00:00",
            "artifact_state": "unavailable",
            "report_file": "reports/readable.txt",
            "profile_revision": 2,
        },
        {
            "id": "unavailable-result",
            "type": "chat",
            "status": "done",
            "stage": "done",
            "created_at": "2026-08-01T10:00:00",
            "artifact_state": "unavailable",
            "result_file": "job_results/readable.json",
            "profile_revision": 2,
        },
    ]

    detailed = [
        hardened_app._job_response(job, include_artifacts=True, profile=profile) for job in jobs
    ]

    assert all(item["artifact"]["state"] == "unavailable" for item in detailed)
    assert all(item["artifact_unavailable"] is True for item in detailed)
    assert "report" not in detailed[0]
    assert "result" not in detailed[1]
    assert "must stay hidden" not in json.dumps(detailed)


def test_legacy_job_history_is_sanitized_and_atomically_rewritten(hardened_app):
    hardened_app.JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    hardened_app.JOBS_PATH.write_text(
        json.dumps(
            [
                {
                    "id": "completed",
                    "type": "digest",
                    "status": "done",
                    "stage": "done",
                    "created_at": "2025-01-01T00:00:00",
                    "report": "legacy private report",
                    "input": "legacy private input",
                    "traceback": "legacy private trace",
                    "error": "legacy private error",
                    "error_code": "private_code",
                },
                {
                    "id": "failed",
                    "type": "digest",
                    "status": "error",
                    "stage": "error",
                    "created_at": "2025-01-01T00:00:00",
                    "error": "provider leaked details",
                    "error_code": "provider_internal",
                },
            ]
        ),
        encoding="utf-8",
    )

    assert hardened_app._load_jobs() is True

    stored_text = hardened_app.JOBS_PATH.read_text(encoding="utf-8")
    stored = json.loads(stored_text)
    assert "legacy private" not in stored_text
    assert "provider leaked" not in stored_text
    assert stored[0]["error"] is None
    assert "error_code" not in stored[0]
    assert stored[1]["error_code"] == "job_failed"
    assert stored[1]["error"] == "The job failed. Please retry."


def test_pdf_worker_uses_extractor_and_removes_upload(hardened_app, monkeypatch):
    job_id = "pdfjob"
    upload = hardened_app.DATA_DIR / "uploads" / job_id / "input.bin"
    upload.parent.mkdir(parents=True)
    upload.write_bytes(b"%PDF fake")
    hardened_app._add_job(
        {
            "id": job_id,
            "type": "feed",
            "status": "queued",
            "stage": "queued",
            "created_at": "2026-07-11T08:00:00",
        }
    )
    called = []
    monkeypatch.setattr(
        hardened_app,
        "extract_pdf_subprocess",
        lambda *args, **kwargs: called.append((args, kwargs)) or "safe extracted text",
    )
    monkeypatch.setattr(hardened_app.agent, "load_profile", lambda: {"profile_revision": 0})
    monkeypatch.setattr(
        hardened_app.agent,
        "run_intake",
        lambda text, profile, **kwargs: (
            profile,
            {"document_type": "other", "source_document_id": "doc_test"},
        ),
    )
    monkeypatch.setattr(hardened_app.agent, "save_profile", lambda *args, **kwargs: None)
    monkeypatch.setattr(hardened_app.agent, "run_orchestrator", lambda *_args: "report")
    monkeypatch.setattr(hardened_app.agent, "classify_treatments", lambda _profile: [])
    monkeypatch.setattr(hardened_app, "_refresh_summary", lambda _profile, **_kwargs: None)
    monkeypatch.setattr(hardened_app, "_prune_retention", lambda: None)

    hardened_app._run_feed_job(job_id, None, "job-upload", "document.pdf", "application/pdf")

    assert called
    assert not upload.parent.exists()
    assert hardened_app._jobs[0]["status"] == "done"


def test_retention_never_prunes_profile_referenced_source(hardened_app, monkeypatch):
    source_root = hardened_app.DATA_DIR / "source_documents"
    protected = source_root / "doc_protected"
    orphan = source_root / "doc_orphan"
    protected.mkdir(parents=True)
    orphan.mkdir()
    old = time.time() - 10 * 86400
    os.utime(protected, (old, old))
    os.utime(orphan, (old, old))
    hardened_app.agent.PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    hardened_app.agent.PROFILE_PATH.write_text(
        json.dumps({"patient": {}, "source_documents": [{"id": "doc_protected"}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("SOURCE_ORPHAN_RETENTION_DAYS", "1")
    monkeypatch.setenv("SOURCE_ORPHAN_RETENTION_COUNT", "0")

    hardened_app._prune_sources_safely()

    assert protected.exists()
    assert not orphan.exists()


def test_source_pruning_waits_for_ingestion_profile_commit(hardened_app, monkeypatch):
    source = hardened_app.DATA_DIR / "source_documents" / "doc_ingesting"
    source.mkdir(parents=True)
    old = time.time() - 10 * 86400
    os.utime(source, (old, old))
    hardened_app.agent.PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    hardened_app.agent.PROFILE_PATH.write_text(
        json.dumps({"patient": {}, "source_documents": []}), encoding="utf-8"
    )
    monkeypatch.setenv("SOURCE_ORPHAN_RETENTION_DAYS", "1")
    monkeypatch.setenv("SOURCE_ORPHAN_RETENTION_COUNT", "0")
    entered = threading.Event()
    finish_ingestion = threading.Event()

    def ingest() -> None:
        with hardened_app.agent.serialized_mutation():
            entered.set()
            assert finish_ingestion.wait(2)
            hardened_app.agent.PROFILE_PATH.write_text(
                json.dumps(
                    {
                        "patient": {},
                        "source_documents": [{"id": "doc_ingesting"}],
                    }
                ),
                encoding="utf-8",
            )

    ingest_thread = threading.Thread(target=ingest)
    prune_thread = threading.Thread(target=hardened_app._prune_sources_safely)
    ingest_thread.start()
    assert entered.wait(1)
    prune_thread.start()
    time.sleep(0.05)
    assert prune_thread.is_alive()
    assert source.exists()
    finish_ingestion.set()
    ingest_thread.join(2)
    prune_thread.join(2)
    assert not ingest_thread.is_alive()
    assert not prune_thread.is_alive()
    assert source.exists()


def test_report_retention_clears_index_before_pruning(hardened_app, monkeypatch):
    report = hardened_app.DATA_DIR / "reports" / "old.txt"
    report.parent.mkdir(parents=True)
    report.write_text("sensitive output", encoding="utf-8")
    hardened_app._add_job(
        {
            "id": "old-report",
            "type": "digest",
            "status": "done",
            "stage": "done",
            "created_at": "2020-01-01T00:00:00",
            "report_file": "reports/old.txt",
        }
    )
    monkeypatch.setenv("REPORT_RETENTION_DAYS", "1")
    monkeypatch.setenv("JOB_RETENTION_DAYS", "36500")

    hardened_app._prune_retention()

    assert not report.exists()
    assert "report_file" not in hardened_app._jobs[0]
    assert hardened_app._jobs[0]["artifact_state"] == "expired"
    assert "reports/old.txt" not in hardened_app.JOBS_PATH.read_text(encoding="utf-8")
    public = hardened_app._job_response(hardened_app._jobs[0])
    assert public["artifact"] == {
        "kind": "report",
        "state": "expired",
        "freshness": "unknown",
    }


def test_report_count_retention_records_not_retained(hardened_app, monkeypatch):
    reports = hardened_app.DATA_DIR / "reports"
    reports.mkdir(parents=True)
    for name in ("new.txt", "old.txt"):
        (reports / name).write_text(name, encoding="utf-8")
    for job_id, name, created_at in (
        ("old-report", "old.txt", "2026-08-01T00:00:00"),
        ("new-report", "new.txt", "2026-08-02T00:00:00"),
    ):
        hardened_app._add_job(
            {
                "id": job_id,
                "type": "digest",
                "status": "done",
                "stage": "done",
                "created_at": created_at,
                "report_file": f"reports/{name}",
                "artifact_state": "available",
            }
        )
    monkeypatch.setenv("REPORT_RETENTION_DAYS", "36500")
    monkeypatch.setenv("REPORT_RETENTION_COUNT", "1")
    monkeypatch.setenv("JOB_RETENTION_DAYS", "36500")
    monkeypatch.setenv("JOB_RETENTION_COUNT", "200")

    hardened_app._prune_retention()

    older = next(item for item in hardened_app._jobs if item["id"] == "old-report")
    assert older["artifact_state"] == "not_retained"
    assert "report_file" not in older
    assert not (reports / "old.txt").exists()


def test_timeout_failure_is_sanitized_in_job_metadata(hardened_app, monkeypatch):
    hardened_app._add_job(
        {
            "id": "timeout-job",
            "type": "chat",
            "status": "queued",
            "stage": "queued",
            "created_at": "2026-07-11T08:00:00",
        }
    )
    monkeypatch.setattr(hardened_app.agent, "load_profile", lambda: {"profile_revision": 0})
    monkeypatch.setattr(
        hardened_app.agent,
        "handle_chat",
        lambda *_args: (_ for _ in ()).throw(TimeoutError("private upstream detail")),
    )

    hardened_app._run_chat_job("timeout-job", "question", [], 0)

    job = hardened_app._jobs[0]
    assert job["status"] == "error"
    assert job["error_code"] == "upstream_timeout"
    assert job["error"] == "The AI service timed out. Please retry."
    assert "private upstream detail" not in hardened_app.JOBS_PATH.read_text(encoding="utf-8")


def test_anthropic_defaults_use_bounded_operation_and_overall_timeouts(monkeypatch):
    import importlib

    import agent.llm as llm

    captured = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(llm.anthropic, "Anthropic", fake_client)
    for name in (
        "ANTHROPIC_CONNECT_TIMEOUT_SECONDS",
        "ANTHROPIC_READ_TIMEOUT_SECONDS",
        "ANTHROPIC_OVERALL_TIMEOUT_SECONDS",
        "ANTHROPIC_MAX_RETRIES",
    ):
        monkeypatch.delenv(name, raising=False)
    importlib.reload(llm)

    assert captured["max_retries"] == 0
    assert captured["timeout"].connect == 5.0
    assert captured["timeout"].read == 120.0
    assert captured["timeout"].write == 10.0
    assert captured["timeout"].pool == 5.0
    assert isinstance(captured["http_client"], llm.httpx.Client)
    assert isinstance(captured["http_client"]._transport, llm.OverallTimeoutTransport)
    assert captured["http_client"]._transport._timeout_seconds == 180.0
    assert all(
        timeout <= captured["http_client"]._transport._timeout_seconds
        for timeout in (
            captured["timeout"].connect,
            captured["timeout"].read,
            captured["timeout"].write,
            captured["timeout"].pool,
        )
    )
    captured["http_client"].close()
