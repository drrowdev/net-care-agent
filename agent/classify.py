"""Compatibility shim — the deterministic treatment identity library moved.

The LLM treatment classification pass was retired; only the deterministic
identity/splitting helpers survive, and they now live in
``agent.treatment_identity`` so they carry no ``agent.profile`` dependency.

This module re-exports them because ``agent.profile.sync_treatment_records``
and the frozen v6 migration have imported ``split_treatment_components`` from
``agent.classify`` since schema v6. Prefer importing from
``agent.treatment_identity`` in new code.
"""

from __future__ import annotations

from .treatment_identity import (
    split_treatment_components,
    treatment_identity_set,
    treatment_text_is_certifiable,
)

__all__ = [
    "split_treatment_components",
    "treatment_identity_set",
    "treatment_text_is_certifiable",
]
