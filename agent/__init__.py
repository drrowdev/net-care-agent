"""NET/Care agent package.

Public symbols are re-exported here so existing callers (`app.py`, tests,
`net_agent.py` shim) can `from agent import …` without knowing the
internal module layout.
"""

from __future__ import annotations

from .biomarker_series import BiomarkerProjectionError, project_biomarker_series

# Agents
from .chat import build_chat_system, handle_chat
from .classify import (
    TreatmentClassificationError,
    classify_treatments,
    treatment_identity_set,
    treatment_text_is_certifiable,
)

# Configuration & paths
from .config import (
    DATA_DIR,
    MODEL,
    MODEL_CHAT,
    MODEL_CLASSIFY,
    MODEL_EXEC_SUMMARY,
    MODEL_INTAKE,
    MODEL_ORCHESTRATOR,
    MODEL_QUESTIONS,
    PROFILE_PATH,
    REPORTS_DIR,
)
from .deep_sweep import run_deep_sweep
from .evidence import build_evidence_catalog, evidence_catalog_prompt, resolve_summary_evidence
from .exec_summary import generate_executive_summary
from .follow_through import (
    ACTION_STATUSES,
    DECISION_STATUSES,
    OUTCOME_KINDS,
    VISIT_STATUSES,
    FollowThroughConflict,
    FollowThroughError,
    RecapIntegrityError,
    action_transition_allowed,
    append_history,
    capture_provenance,
    check_idempotency,
    clinical_outcome,
    ensure_summary_action_ids,
    find_question,
    find_record,
    find_summary_action,
    increment_workflow_revision,
    invalidate_generated_context,
    new_workflow_id,
    project_question,
    project_summary_actions,
    project_visit_recap,
    project_visit_recap_with_authority,
    public_action,
    public_alert,
    public_visit,
    question_source_token,
    request_hash,
    semantic_token,
    validate_current_generated_source,
    validate_date,
    validate_expected_token,
    validate_follow_up_text,
    validate_mutation_id,
    validate_optional_text,
    validate_owner,
    validate_status,
    validate_text,
    visit_transition_allowed,
)
from .imaging_series import (
    ImagingProjectionError,
    imaging_record_text,
    project_imaging_series,
)
from .intake import _treatment_similarity, run_intake
from .judgments import clinical_judgments_fingerprint, get_clinical_judgments_context

# LLM client (used by app.py for the legacy direct-client chat call site)
from .llm import client, first_text, render_prompt, strip_code_fences
from .orchestrator import run_orchestrator

# Profile
from .profile import (
    DEFAULT_PROFILE,
    CorruptProfileError,
    IOProfileError,
    ProfileLoadError,
    active_alerts,
    active_documents,
    alert_token,
    current_treatment_records,
    get_patient_summary,
    get_research_ids,
    invalidate_treatment_classification,
    load_profile,
    public_latest_research_update,
    rebuild_raw_treatments,
    record_latest_research_update,
    save_profile,
    summary_is_current,
    sync_treatment_records,
    treatment_classification_is_current,
    treatment_edit_token,
)
from .provenance import anchor_source_quote, preserve_source_document, remove_source_document
from .questions import generate_appointment_questions, generate_questions_for_profile
from .reconciliation import (
    ImportConflict,
    ReconciliationError,
    add_derived_research,
    build_import_record,
    correct_change,
    public_receipt,
    remove_change,
    sync_alert_system_state,
    undo_import,
)
from .recovery import get_recovery_state
from .serialize import mutating_lock, serialized_mutation
from .symptom_episodes import (
    MAX_SYMPTOM_ACTIONS,
    SYMPTOM_EPISODE_STATUSES,
    SYMPTOM_REPORTED_SUBJECTS,
    SYMPTOM_SAFETY_GUIDANCE,
    SYMPTOM_SEVERITY_LEVELS,
    SymptomProjectionError,
    derive_symptom_observation_id,
    new_symptom_episode_id,
    project_symptom_episodes,
    symptom_episode_provenance,
    symptom_observation_identity_base,
    symptom_observation_text,
)

# Tools (registry + dispatcher + relevance + individual tool fns)
from .tools import (
    TOOLS,
    _is_relevant,
    analyze_biomarker_trends,
    execute_tool,
    search_clinical_trials,
    search_pubmed,
)
from .trials_poll import poll_tracked_trials
from .verify import verification_note, verify_references

__all__ = [
    # config
    "DATA_DIR",
    "PROFILE_PATH",
    "REPORTS_DIR",
    "MODEL",
    "MODEL_INTAKE",
    "MODEL_ORCHESTRATOR",
    "MODEL_EXEC_SUMMARY",
    "MODEL_QUESTIONS",
    "MODEL_CLASSIFY",
    "MODEL_CHAT",
    # llm
    "client",
    "first_text",
    "render_prompt",
    "strip_code_fences",
    # profile
    "DEFAULT_PROFILE",
    "load_profile",
    "save_profile",
    "active_documents",
    "active_alerts",
    "alert_token",
    "current_treatment_records",
    "invalidate_treatment_classification",
    "rebuild_raw_treatments",
    "get_patient_summary",
    "summary_is_current",
    "sync_treatment_records",
    "treatment_edit_token",
    "treatment_classification_is_current",
    "get_research_ids",
    "record_latest_research_update",
    "public_latest_research_update",
    "CorruptProfileError",
    "IOProfileError",
    "ProfileLoadError",
    "BiomarkerProjectionError",
    "project_biomarker_series",
    "ImagingProjectionError",
    "project_imaging_series",
    "imaging_record_text",
    "MAX_SYMPTOM_ACTIONS",
    "SYMPTOM_EPISODE_STATUSES",
    "SYMPTOM_REPORTED_SUBJECTS",
    "SYMPTOM_SAFETY_GUIDANCE",
    "SYMPTOM_SEVERITY_LEVELS",
    "SymptomProjectionError",
    "derive_symptom_observation_id",
    "new_symptom_episode_id",
    "project_symptom_episodes",
    "symptom_episode_provenance",
    "symptom_observation_identity_base",
    "symptom_observation_text",
    "ACTION_STATUSES",
    "VISIT_STATUSES",
    "DECISION_STATUSES",
    "OUTCOME_KINDS",
    "FollowThroughError",
    "FollowThroughConflict",
    "RecapIntegrityError",
    "semantic_token",
    "new_workflow_id",
    "validate_mutation_id",
    "validate_text",
    "validate_optional_text",
    "validate_follow_up_text",
    "validate_owner",
    "validate_date",
    "validate_status",
    "validate_expected_token",
    "validate_current_generated_source",
    "ensure_summary_action_ids",
    "find_summary_action",
    "question_source_token",
    "project_question",
    "request_hash",
    "find_question",
    "check_idempotency",
    "public_alert",
    "append_history",
    "increment_workflow_revision",
    "invalidate_generated_context",
    "public_action",
    "public_visit",
    "project_summary_actions",
    "project_visit_recap",
    "project_visit_recap_with_authority",
    "find_record",
    "action_transition_allowed",
    "visit_transition_allowed",
    "clinical_outcome",
    "capture_provenance",
    "anchor_source_quote",
    "preserve_source_document",
    "remove_source_document",
    "build_import_record",
    "add_derived_research",
    "public_receipt",
    "correct_change",
    "remove_change",
    "sync_alert_system_state",
    "undo_import",
    "ReconciliationError",
    "ImportConflict",
    "get_recovery_state",
    "mutating_lock",
    "serialized_mutation",
    # tools
    "TOOLS",
    "_is_relevant",
    "execute_tool",
    "search_pubmed",
    "search_clinical_trials",
    "analyze_biomarker_trends",
    # judgments
    "get_clinical_judgments_context",
    "clinical_judgments_fingerprint",
    # agents
    "run_intake",
    "_treatment_similarity",
    "run_orchestrator",
    "run_deep_sweep",
    "build_evidence_catalog",
    "evidence_catalog_prompt",
    "resolve_summary_evidence",
    "poll_tracked_trials",
    "verify_references",
    "verification_note",
    "classify_treatments",
    "TreatmentClassificationError",
    "treatment_identity_set",
    "treatment_text_is_certifiable",
    "generate_executive_summary",
    "generate_appointment_questions",
    "generate_questions_for_profile",
    "build_chat_system",
    "handle_chat",
]
