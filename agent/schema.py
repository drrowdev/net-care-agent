"""
Pydantic models for the patient profile.

Goals:
- Document the canonical shape in code (single source of truth)
- Provide light validation on save (type errors caught early)
- Stay lenient on load: existing JSON in production must keep loading even if
  fields are missing, extras are present, or enums drift. Validation failures
  log a warning and return the raw dict — never block the app.
- Enable auto-regeneration of `docs/profile_schema.md` from the model.

Run `python -m agent.schema dump-md` to regenerate the schema doc.
"""

from __future__ import annotations

import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Collection keys that must be lists (or None/missing → coercible to []).
# Used by structural_check and the coercion step in load_profile.
_COLLECTION_KEYS: tuple[str, ...] = (
    "biomarkers",
    "imaging",
    "appointments",
    "documents",
    "source_documents",
    "document_imports",
    "trials_tracked",
    "literature_watched",
    "alerts",
    "treatments_classified",
    "clinical_judgments",
    "symptoms",
    "symptom_episodes",
    "treatment_courses",
    "treatment_discrepancies",
    "questions",
    "appointment_questions",
    "feedback",
    "caregiver_actions",
    "visits",
)


def structural_check(data: object) -> bool:
    """Return True if *data* is structurally usable as a patient profile.

    A profile is structurally valid when:

    - It is a ``dict``.
    - The ``patient`` key, if present, is either ``None`` or a ``dict``.
    - Each collection key, if present, is either ``None`` or a ``list``.

    ``None`` values are *safely coercible* (``None → {}`` / ``None → []``) and
    pass this check.  Type mismatches (e.g. ``patient = 42``) return ``False``
    and trigger quarantine in ``load_profile``.

    This check is intentionally permissive on missing keys — they are filled in
    by migrations and Pydantic defaults.  It only rejects data that cannot be
    safely coerced into a usable profile shape.
    """
    if not isinstance(data, dict):
        return False
    patient = data.get("patient")
    if patient is not None and not isinstance(patient, dict):
        return False
    for key in _COLLECTION_KEYS:
        val = data.get(key)
        if val is not None and not isinstance(val, list):
            return False
    return True


def clinically_empty_profile(data: object) -> bool:
    """Return True when a profile-shaped dict contains no patient/clinical data."""
    if not isinstance(data, dict) or not data:
        return True
    patient = data.get("patient")
    if isinstance(patient, dict) and any(
        value not in (None, "", [], {}) for value in patient.values()
    ):
        return False
    if any(isinstance(data.get(key), list) and bool(data[key]) for key in _COLLECTION_KEYS):
        return False
    return not bool(data.get("executive_summary"))


def now_stamp() -> str:
    """Wall-clock ISO timestamp (seconds precision) for when an item was first
    recorded in the profile.

    Because it reflects *ingestion* time rather than an item's clinical date,
    it preserves when a back-dated document or finding entered the record.
    """
    return datetime.datetime.now().isoformat(timespec="seconds")


def derive_date_precision(value: object) -> BiomarkerDatePrecision:
    """Classify strict ISO date text without inventing missing components."""
    if not isinstance(value, str):
        return "unknown"
    if len(value) == 10:
        try:
            datetime.date.fromisoformat(value)
        except ValueError:
            return "unknown"
        return "day"
    if len(value) == 7 and value[4] == "-":
        year, month = value.split("-", 1)
        if year.isdigit() and len(year) == 4 and month.isdigit() and 1 <= int(month) <= 12:
            return "month"
        return "unknown"
    if len(value) == 4 and value.isdigit() and 1 <= int(value) <= 9999:
        return "year"
    return "unknown"


# ── enum-like literals ────────────────────────────────────────────────────────
# These are *documented* sets; we don't enforce them strictly because real-world
# data drifts and we'd rather accept a bad value than reject a valid profile.
Sex = Literal["female", "male", "other"]
SstrStatus = Literal["positive", "negative", "unknown"]
BiomarkerFlag = Literal["high", "low", "normal"]
BiomarkerFlagAuthority = Literal[
    "source_reported",
    "caregiver_corrected",
    "legacy_unknown",
    "unknown",
]
BiomarkerDatePrecision = Literal["day", "month", "year", "unknown"]
BiomarkerDateKind = Literal[
    "collection",
    "result",
    "clinical_unspecified",
    "source_document",
    "unknown",
]
ImagingDateKind = Literal["study", "legacy_unknown", "unknown"]
SymptomObservationDateKind = Literal["clinical", "legacy_unknown", "unknown"]
SymptomEpisodeDateKind = Literal["caregiver_entered", "unknown"]
SymptomEpisodeStatus = Literal["current", "resolved"]
SymptomSeverityLevel = Literal["mild", "moderate", "severe"]
SymptomReportedSubject = Literal["patient", "caregiver", "unspecified"]
DocumentType = Literal[
    "lab_result",
    "imaging_report",
    "doctor_note",
    "research_paper",
    "appointment_summary",
    "pathology_report",
    "other",
]
AlertPriority = Literal["urgent", "high", "medium", "low"]
TreatmentCategory = Literal["active", "planned", "completed"]
JudgmentCategory = Literal["constraint", "preference", "outcome", "context"]
JudgmentSource = Literal["manual", "ai"]
JudgmentStatus = Literal["active", "superseded", "needs_review"]
SymptomSource = Literal["manual", "ai"]
QuestionCategory = Literal["Treatment", "Diagnostics", "Symptoms", "Trials", "Monitoring", "Other"]
QuestionPriority = Literal["urgent", "high", "medium"]
QuestionSource = Literal["ai", "manual"]
ActionStatus = Literal["open", "in_progress", "completed", "cancelled"]
VisitStatus = Literal["planned", "in_progress", "completed", "cancelled"]
DecisionStatus = Literal["active", "superseded", "retracted", "needs_confirmation"]
OutcomeKind = Literal["administrative", "caregiver_reported", "clinician_attributed"]
TreatmentCourseStatus = Literal["current", "past", "planned"]
TreatmentCourseDateKind = Literal["caregiver_entered", "unknown"]
TreatmentTerminalQualifier = Literal[
    "ended", "not_started", "cancelled", "other", "legacy_unspecified"
]
TreatmentDiscrepancyCategory = Literal[
    "name_or_type",
    "status",
    "dose_or_schedule",
    "date",
    "source_wording",
    "other",
]
TreatmentDiscrepancyStatus = Literal["open", "resolved"]
TreatmentConfirmationOutcome = Literal[
    "confirmed_as_recorded",
    "caregiver_record_corrected",
    "source_clarification_needed",
    "no_change_documented",
]


# ── shared base ───────────────────────────────────────────────────────────────
class _Lenient(BaseModel):
    """Base for all profile sub-models: accept extras, validate by name."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class _EvidenceFields(_Lenient):
    """Provenance shared by facts extracted from a fed source document."""

    source_document_id: str | None = None
    source_quote: str | None = Field(None, description="Exact immutable source text span")
    evidence_status: Literal["verified", "missing", "invalid"] | None = None
    evidence_start: int | None = Field(None, ge=0)
    evidence_end: int | None = Field(None, ge=0)


# ── sub-models ────────────────────────────────────────────────────────────────
class Patient(_Lenient):
    """Demographics + diagnosis. The only non-list top-level branch."""

    birth_year: int | None = Field(None, description="Birth year, used to derive age")
    age: int | None = Field(None, description="Derived from birth_year")
    sex: Sex | None = None
    diagnosis: str | None = None
    ki67_percent: float | None = Field(None, description="Ki-67 / MIB-1 proliferation index")
    sstr_status: SstrStatus | None = Field(None, description="Somatostatin receptor status")
    sstr_score: int | None = Field(None, description="Krenning score 0–4", ge=0, le=4)
    current_treatments: list[str] = Field(
        default_factory=list,
        description="Raw treatment strings; deduped by classify step",
    )
    current_treatment_records: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Stable component/source mapping for composite-safe treatment edits",
    )
    allergies: list[str] = Field(default_factory=list)
    comorbidities: list[str] = Field(default_factory=list)
    oncologist: str | None = None
    treating_center: str | None = None
    location: str | None = Field(
        None,
        description="Patient's city/country, e.g. 'Berlin, Germany'. Used to "
        "compose the identifying context in agent system prompts so the repo "
        "itself ships no patient-identifying details.",
    )
    caregiver_relationship: str | None = Field(
        None,
        description="Relationship of the caregiver to the patient (e.g. 'partner', "
        "'parent'). Drives wording in agent system prompts; defaults to 'caregiver'.",
    )
    language: str | None = Field(
        None,
        description="Output language for caregiver-facing artifacts such as "
        "appointment questions, e.g. 'German'. Defaults to 'English'.",
    )
    regions_of_interest: list[str] = Field(
        default_factory=list,
        description="Countries to prioritise in clinical-trial searches, e.g. "
        "['Germany', 'Switzerland']. Empty list = no region filter.",
    )


class Biomarker(_EvidenceFields):
    """A single lab result row (CgA, NSE, 5-HIAA, creatinine, etc.)."""

    id: str | None = Field(None, description="Stable identity for imported rows")
    date: str | None = Field(None, description="Exact source-derived YYYY-MM-DD, YYYY-MM, or YYYY")
    date_precision: BiomarkerDatePrecision = "unknown"
    date_kind: BiomarkerDateKind = "unknown"
    source_document_date: str | None = Field(
        None, description="Source document date when explicitly stated"
    )
    source_document_date_precision: BiomarkerDatePrecision = "unknown"
    marker: str | None = None
    value: Any = Field(None, description="number or string")
    unit: str | None = None
    reference_range: str | None = None
    flag: BiomarkerFlag | None = None
    flag_authority: BiomarkerFlagAuthority = "unknown"
    specimen: str | None = None
    assay: str | None = None
    method: str | None = None
    added_at: str | None = Field(
        None, description="Timestamp when the item first entered the patient profile."
    )


class Imaging(_EvidenceFields):
    id: str | None = Field(None, description="Stable identity for imported rows")
    date: str | None = Field(None, description="Exact stored study date text")
    date_precision: BiomarkerDatePrecision = "unknown"
    date_kind: ImagingDateKind = "unknown"
    source_document_date: str | None = Field(
        None, description="Source document date when explicitly stated"
    )
    source_document_date_precision: BiomarkerDatePrecision = "unknown"
    modality: str | None = Field(None, description="Exact stored modality wording")
    findings: str | None = None
    impression: str | None = None
    new_lesions: bool | None = None
    added_at: str | None = Field(
        None, description="Timestamp when the item first entered the patient profile."
    )


class Document(_Lenient):
    """Every fed document, kept for audit and downstream re-analysis."""

    id: str | None = Field(None, description="Stable identity for imported rows")
    date: str | None = None
    type: DocumentType | None = None
    summary: str | None = Field(None, description="1–2 sentence intake-agent summary")
    key_findings: list[str] = Field(default_factory=list)
    raw_text: str | None = Field(None, description="First ~3000 chars of input")
    source_document_id: str | None = None
    excluded_from_clinical_context: bool = Field(
        False,
        description="True after a caregiver removes or undoes this import's clinical effects",
    )
    evidence: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Anchored evidence for document-level findings not stored as structured rows",
    )
    added_at: str | None = Field(
        None, description="Timestamp when the item first entered the patient profile."
    )


class TrialTracked(_Lenient):
    nct_id: str | None = Field(None, description="ClinicalTrials.gov ID, primary key")
    title: str | None = None
    status: str | None = None
    phase: str | None = None
    countries: list[str] = Field(default_factory=list)
    url: str | None = None
    brief_summary: str | None = None
    eligibility_excerpt: str | None = None
    date_added: str | None = Field(None, description="Timestamp when the trial was first tracked")
    eligibility_notes: str | None = ""


class LiteratureWatched(_Lenient):
    pmid: str | None = Field(None, description="PubMed ID, primary key")
    title: str | None = None
    authors: str | None = None
    journal: str | None = None
    date: str | None = None
    url: str | None = None
    query: str | None = None
    date_added: str | None = Field(None, description="Timestamp when the paper was first tracked")
    relevance_notes: str | None = ""


class Alert(_Lenient):
    id: str | None = Field(None, description="Stable identity for imported rows")
    date: str | None = None
    priority: AlertPriority | None = None
    message: str | None = None
    action_required: str | None = None
    resolved: bool = False
    source_document_id: str | None = None
    source_job_id: str | None = None
    generation_profile_revision: int | None = None
    dependency_kind: Literal["durable", "source", "profile_snapshot"] = "profile_snapshot"
    source_dependency_active: bool = True
    source_invalidated_at: str | None = None
    inactive_reason: str | None = None
    resolution: dict[str, Any] | None = None
    history: list[WorkflowAuditEvent] = Field(default_factory=list)
    added_at: str | None = Field(
        None, description="Timestamp when the item first entered the patient profile."
    )


class TreatmentClassified(_Lenient):
    """Built by agent.classify.classify_treatments — deduped + categorised."""

    id: str | None = None
    text: str | None = Field(None, description="Canonical merged description")
    category: TreatmentCategory | None = None
    label: str | None = None
    date: str | None = Field(None, description="YYYY-MM, YYYY, or null")
    source_treatment_ids: list[str] = Field(default_factory=list)


class ClinicalJudgment(_Lenient):
    """Hard constraints captured from oncologist consultations."""

    id: str | None = None
    date: str | None = None
    category: JudgmentCategory | None = None
    text: str | None = None
    source: JudgmentSource | None = None
    scope: str | None = Field(None, description="Clinical topic or decision this judgment governs")
    status: JudgmentStatus = "active"
    review_after: str | None = Field(None, description="YYYY-MM-DD; review due on/after this date")
    valid_until: str | None = Field(
        None, description="YYYY-MM-DD; ceases to constrain after this date"
    )
    supersedes: str | None = Field(None, description="ID of the prior judgment this replaces")
    updated_at: str | None = None
    added_at: str | None = Field(
        None, description="Timestamp when the item first entered the patient profile."
    )


class Symptom(_EvidenceFields):
    """Patient-reported symptom or side effect.

    Bridges the gap between objective biomarkers and the oncologist's
    consultation notes — the day-to-day experiential data that informs
    appointment prep.
    """

    id: str | None = None
    date: str | None = Field(None, description="Exact stored symptom-event date text")
    date_precision: BiomarkerDatePrecision = "unknown"
    date_kind: SymptomObservationDateKind = "unknown"
    source_document_date: str | None = Field(
        None, description="Document-level date, never symptom-event chronology"
    )
    source_document_date_precision: BiomarkerDatePrecision = "unknown"
    symptom: str | None = None
    severity: int | None = Field(None, ge=1, le=5, description="1=mild .. 5=severe")
    note: str | None = None
    related_treatment: str | None = Field(
        None, description="Optional link to a treatment name in current_treatments"
    )
    source: SymptomSource | None = None
    added_at: str | None = Field(
        None, description="Timestamp when the item first entered the patient profile."
    )


class Question(_Lenient):
    id: str | None = None
    text: str | None = None
    category: QuestionCategory | None = None
    priority: QuestionPriority | None = None
    rationale: str | None = None
    source: QuestionSource | None = None
    asked: bool = False
    created_at: str | None = None
    source_profile_revision: int | None = None
    stale: bool = False
    stale_reason: str | None = None
    stale_at: str | None = None
    generation_job_id: str | None = None


class Appointment(_EvidenceFields):
    id: str | None = Field(None, description="Stable identity for imported rows")
    date: str | None = None
    time: str | None = None
    with_: str | None = Field(None, alias="with")
    location: str | None = None
    notes: str | None = None
    description: str | None = None
    type: str | None = None
    added_at: str | None = None


class SourceArtifact(_Lenient):
    path: str
    sha256: str
    length: int = Field(ge=0)


class SourceDocument(_Lenient):
    id: str
    ingested_at: str
    filename: str | None = None
    media_type: str | None = None
    source: SourceArtifact
    text: SourceArtifact


class ImportTarget(_Lenient):
    """Server-owned locator used for compare-and-swap receipt mutations."""

    kind: Literal["collection", "scalar", "treatment", "none"]
    collection: str | None = None
    record_id: str | None = None
    path: list[str] = Field(default_factory=list)


class ImportHistoryEvent(_Lenient):
    """Immutable before/after record for a caregiver correction, removal, or undo."""

    event: Literal["corrected", "removed", "undone"]
    at: str
    before: Any = None
    after: Any = None


class ImportChange(_Lenient):
    """One direct or derived outcome shown in a document reconciliation receipt."""

    id: str
    category: str
    label: str
    operation: Literal["added", "updated", "unchanged", "conflict", "derived"]
    target: ImportTarget
    before: Any = None
    after: Any = None
    effective_value: Any = None
    evidence_status: Literal["verified", "missing", "invalid"] | None = None
    evidence_start: int | None = Field(None, ge=0)
    evidence_end: int | None = Field(None, ge=0)
    source_document_id: str | None = None
    editable_fields: list[str] = Field(default_factory=list)
    state: Literal["active", "corrected", "removed", "unchanged", "derived", "undone"]
    history: list[ImportHistoryEvent] = Field(default_factory=list)


class DocumentImport(_Lenient):
    """Profile-backed receipt tying one feed job to its immutable source and audit history."""

    id: str
    job_id: str
    source_document_id: str
    ingested_at: str
    filename: str | None = None
    media_type: str | None = None
    document_type: str | None = None
    document_date: str | None = None
    document_summary: str | None = None
    applied_revision: int
    receipt_revision: int = 1
    status: Literal["active", "corrected", "partially_removed", "undone"] = "active"
    changes: list[ImportChange] = Field(default_factory=list)


class Feedback(_Lenient):
    id: str
    target: str
    item_id: str
    assessment: Literal["agreed", "corrected", "acted", "helpful", "incorrect", "missed"]
    note: str | None = None
    outcome: str | None = None
    created_at: str
    updated_at: str


class WorkflowAuditEvent(_Lenient):
    """Append-only mutation event supporting idempotent target-level updates."""

    id: str
    mutation_id: str
    endpoint: str | None = None
    operation: str
    target: str | None = None
    at: str
    request_hash: str
    before_token: str | None = None
    after_token: str | None = None
    changes: dict[str, Any] = Field(default_factory=dict)
    result_hash: str | None = None
    result_snapshot: dict[str, Any] | None = None


class SymptomEpisodeProvenance(_Lenient):
    """Immutable trust boundary for a caregiver-maintained episode."""

    capture_method: Literal["caregiver_entered"] = "caregiver_entered"
    source_verification: Literal["unverified"] = "unverified"


class SymptomEpisode(_Lenient):
    """Explicit caregiver-maintained symptom lifecycle, separate from observations."""

    id: str
    status: SymptomEpisodeStatus = "current"
    symptom_text: str
    severity_level: SymptomSeverityLevel | None = None
    severity_detail: str | None = None
    reported_subject: SymptomReportedSubject = "unspecified"
    timing_text: str | None = None
    frequency_text: str | None = None
    triggers_text: str | None = None
    notes: str | None = None
    onset_date: str | None = None
    onset_date_precision: BiomarkerDatePrecision = "unknown"
    onset_date_kind: SymptomEpisodeDateKind = "unknown"
    resolved_date: str | None = None
    resolved_date_precision: BiomarkerDatePrecision = "unknown"
    resolved_date_kind: SymptomEpisodeDateKind = "unknown"
    provenance: SymptomEpisodeProvenance = Field(default_factory=SymptomEpisodeProvenance)
    caregiver_action_id: str | None = None
    created_at: str
    updated_at: str
    resolved_at: str | None = None
    history: list[WorkflowAuditEvent] = Field(default_factory=list)


class TreatmentCourseProvenance(_Lenient):
    """Immutable trust boundary for a caregiver-maintained treatment course."""

    capture_method: Literal["caregiver_entered"] = "caregiver_entered"
    source_verification: Literal["unverified"] = "unverified"


class TreatmentCourse(_Lenient):
    """Explicit caregiver-maintained treatment episode, separate from source facts."""

    id: str
    status: TreatmentCourseStatus
    treatment_text: str
    treatment_type_text: str | None = None
    dose_text: str | None = None
    route_text: str | None = None
    frequency_text: str | None = None
    cycle_text: str | None = None
    schedule_text: str | None = None
    formulation_text: str | None = None
    indication_text: str | None = None
    notes: str | None = None
    legacy_component_ids: list[str] = Field(default_factory=list)
    start_date: str | None = None
    start_date_precision: BiomarkerDatePrecision = "unknown"
    start_date_kind: TreatmentCourseDateKind = "unknown"
    stop_date: str | None = None
    stop_date_precision: BiomarkerDatePrecision = "unknown"
    stop_date_kind: TreatmentCourseDateKind = "unknown"
    planned_date: str | None = None
    planned_date_precision: BiomarkerDatePrecision = "unknown"
    planned_date_kind: TreatmentCourseDateKind = "unknown"
    terminal_qualifier: TreatmentTerminalQualifier | None = None
    terminal_detail: str | None = None
    previous_course_id: str | None = None
    provenance: TreatmentCourseProvenance = Field(default_factory=TreatmentCourseProvenance)
    created_at: str
    updated_at: str
    history: list[WorkflowAuditEvent] = Field(default_factory=list)


class TreatmentConfirmationProvenance(_Lenient):
    """Visible trust boundary for caregiver-entered clinician attribution."""

    capture_method: Literal["caregiver_entered"] = "caregiver_entered"
    attributed_to: Literal["clinician"] = "clinician"
    source_verification: Literal["unverified"] = "unverified"


class TreatmentConfirmation(_Lenient):
    outcome: TreatmentConfirmationOutcome
    note: str
    clinician_text: str | None = None
    context_text: str | None = None
    date: str | None = None
    date_precision: BiomarkerDatePrecision = "unknown"
    date_kind: TreatmentCourseDateKind = "unknown"
    provenance: TreatmentConfirmationProvenance = Field(
        default_factory=TreatmentConfirmationProvenance
    )
    recorded_at: str


class TreatmentDiscrepancy(_Lenient):
    """Caregiver-created neutral comparison that never rewrites source history."""

    id: str
    status: TreatmentDiscrepancyStatus = "open"
    category: TreatmentDiscrepancyCategory
    comparison_text: str
    citation_kind: Literal["source_vs_source", "source_vs_course"] | None = None
    course_id: str | None = None
    source_fact_ref: str
    source_fact_snapshot: dict[str, Any]
    comparison_source_fact_ref: str | None = None
    comparison_source_fact_snapshot: dict[str, Any] | None = None
    course_snapshot: dict[str, Any] | None = None
    recurs_from_id: str | None = None
    confirmations: list[TreatmentConfirmation] = Field(default_factory=list)
    caregiver_action_id: str | None = None
    provenance: TreatmentCourseProvenance = Field(default_factory=TreatmentCourseProvenance)
    created_at: str
    updated_at: str
    resolved_at: str | None = None
    history: list[WorkflowAuditEvent] = Field(default_factory=list)


class ActionOriginSnapshot(_Lenient):
    """Immutable source snapshot captured when a caregiver accepts an action."""

    kind: Literal["manual", "executive_summary_action", "alert", "visit_decision"]
    source_id: str | None = None
    source_job_id: str | None = None
    source_profile_revision: int | None = None
    generation_id: str | None = None
    text: str
    snapshot: dict[str, Any] = Field(default_factory=dict)


class ActionOutcome(_Lenient):
    kind: OutcomeKind
    text: str
    recorded_at: str
    provenance: dict[str, str] = Field(default_factory=dict)


class CaregiverAction(_Lenient):
    """Durable caregiver-owned follow-up independent of generated artifacts."""

    id: str
    origin_snapshot: ActionOriginSnapshot
    text: str
    owner: str | None = None
    due_date: str | None = None
    status: ActionStatus = "open"
    outcome: ActionOutcome | None = None
    visit_id: str | None = None
    decision_id: str | None = None
    alert_id: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None
    cancelled_at: str | None = None
    history: list[WorkflowAuditEvent] = Field(default_factory=list)


class CaptureProvenance(_Lenient):
    """Visible trust boundary for caregiver-entered clinician attribution."""

    capture_method: Literal["caregiver_entered"] = "caregiver_entered"
    attributed_to: Literal["clinician"] = "clinician"
    source_verification: Literal["unverified"] = "unverified"


class VisitAnswer(_Lenient):
    status: Literal["answered", "unknown"]
    text: str | None = None
    recorded_at: str
    provenance: CaptureProvenance = Field(default_factory=CaptureProvenance)


class VisitQuestionSnapshot(_Lenient):
    id: str
    text: str
    category: str | None = None
    priority: str | None = None
    rationale: str | None = None
    source_kind: Literal["manual", "generated"]
    source_question_id: str | None = None
    source_generation_id: str | None = None
    source_profile_revision: int | None = None
    pinned: bool = False
    order: int = 0
    answer: VisitAnswer | None = None
    created_at: str


class VisitDecision(_Lenient):
    id: str
    text: str
    status: DecisionStatus = "active"
    provenance: CaptureProvenance = Field(default_factory=CaptureProvenance)
    supersedes_id: str | None = None
    created_at: str
    updated_at: str


class Visit(_Lenient):
    """Caregiver working record, optionally linked to an imported appointment."""

    id: str
    title: str
    date: str | None = None
    time: str | None = None
    clinician: str | None = None
    location: str | None = None
    status: VisitStatus = "planned"
    source_appointment_id: str | None = None
    question_snapshots: list[VisitQuestionSnapshot] = Field(default_factory=list)
    decisions: list[VisitDecision] = Field(default_factory=list)
    follow_up_ids: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str
    completed_at: str | None = None
    cancelled_at: str | None = None
    history: list[WorkflowAuditEvent] = Field(default_factory=list)


class ExecutiveSummary(_Lenient):
    """Most recent JSON output of agent.exec_summary.generate_executive_summary."""

    generated_at: str | None = None
    generated_at_timestamp: str | None = None
    generation_id: str | None = None
    summary_revision: int | None = None
    stale: bool = True
    summary_error: str | None = None
    model: str | None = None
    summary: Any = None  # free-form structure varies by run


class ResearchUpdate(_Lenient):
    """Exact net-new research records added by the latest discovery batch."""

    job_id: str | None = Field(None, description="Run identifier that produced this batch")
    trigger: str | None = Field(None, description="Discovery source: digest or feed")
    completed_at: str | None = Field(None, description="ISO timestamp when the batch was recorded")
    trial_ids: list[str] = Field(
        default_factory=list, description="Canonical NCT IDs newly added by this batch"
    )
    paper_ids: list[str] = Field(
        default_factory=list, description="Canonical numeric PubMed IDs newly added by this batch"
    )


# ── top-level model ───────────────────────────────────────────────────────────
class PatientProfile(_Lenient):
    """The complete patient profile. Lives at ${DATA_DIR}/patient_profile.json."""

    schema_version: int = Field(
        default=13,
        description="Profile schema version. Incremented when a structural migration runs.",
    )
    profile_revision: int = 0
    workflow_revision: int = 0
    profile_updated_at: str | None = None
    profile_saved_at: str | None = None
    summary_stale: bool = True
    patient: Patient = Field(default_factory=Patient)
    biomarkers: list[Biomarker] = Field(default_factory=list)
    imaging: list[Imaging] = Field(default_factory=list)
    appointments: list[Appointment] = Field(default_factory=list)
    documents: list[Document] = Field(default_factory=list)
    source_documents: list[SourceDocument] = Field(default_factory=list)
    document_imports: list[DocumentImport] = Field(default_factory=list)
    trials_tracked: list[TrialTracked] = Field(default_factory=list)
    literature_watched: list[LiteratureWatched] = Field(default_factory=list)
    alerts: list[Alert] = Field(default_factory=list)
    treatments_classified: list[TreatmentClassified] = Field(default_factory=list)
    treatments_classification_revision: int | None = None
    treatments_classification_job_id: str | None = None
    clinical_judgments: list[ClinicalJudgment] = Field(default_factory=list)
    symptoms: list[Symptom] = Field(default_factory=list)
    symptom_episodes: list[SymptomEpisode] = Field(default_factory=list)
    treatment_courses: list[TreatmentCourse] = Field(default_factory=list)
    treatment_discrepancies: list[TreatmentDiscrepancy] = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list)
    appointment_questions: list[Question] = Field(default_factory=list)
    questions_generation_id: str | None = None
    feedback: list[Feedback] = Field(default_factory=list)
    caregiver_actions: list[CaregiverAction] = Field(default_factory=list)
    visits: list[Visit] = Field(default_factory=list)
    executive_summary: ExecutiveSummary | None = None
    latest_research_update: ResearchUpdate | None = None


# ── public helpers ────────────────────────────────────────────────────────────
def validate_profile(data: dict) -> PatientProfile:
    """Strict validation. Raises pydantic.ValidationError on any type mismatch."""
    return PatientProfile.model_validate(data)


def normalize_profile(data: dict) -> dict:
    """
    Validate `data` and return a clean dict with default fields filled in.

    On validation failure, logs a warning and returns `data` unchanged so the
    app keeps working with the original (possibly malformed) profile.
    """
    import logging

    log = logging.getLogger(__name__)
    try:
        model = PatientProfile.model_validate(data)
    except Exception as e:
        log.warning("profile validation failed type=%s", type(e).__name__)
        return data
    return model.model_dump(by_alias=True, exclude_none=False)


# ── docs generator ────────────────────────────────────────────────────────────
def render_schema_markdown() -> str:
    """Generate docs/profile_schema.md content from the Pydantic model."""

    sections: list[str] = []
    sections.append(
        "# Patient profile schema\n\n"
        "_Auto-generated from `agent/schema.py` — run `python -m agent.schema "
        "dump-md` after changing the model._\n\n"
        "The patient profile lives at `${DATA_DIR}/patient_profile.json` "
        "(defaults to `/home/data/patient_profile.json` on Azure). It is the "
        "single source of truth for the entire app — every other artefact "
        "(reports, backups, dashboards) is derivable from this file.\n\n"
        "All sub-models accept **extra** fields (forward-compat) and treat "
        "every documented field as optional — `load_profile()` never rejects "
        "real-world data, only logs a warning on type mismatch.\n"
    )

    # Top-level shape
    top_lines = ["## Top-level shape\n", "```jsonc", "{"]
    for name, field in PatientProfile.model_fields.items():
        ann = _short_type(field.annotation)
        top_lines.append(f"  {name!r}: {ann},")
    top_lines.append("}")
    top_lines.append("```\n")
    sections.append("\n".join(top_lines))

    # Per sub-model section
    submodels: list[tuple[str, type[BaseModel]]] = [
        ("patient", Patient),
        ("biomarkers[]", Biomarker),
        ("imaging[]", Imaging),
        ("documents[]", Document),
        ("trials_tracked[]", TrialTracked),
        ("literature_watched[]", LiteratureWatched),
        ("alerts[]", Alert),
        ("treatments_classified[]", TreatmentClassified),
        ("clinical_judgments[]", ClinicalJudgment),
        ("symptoms[]", Symptom),
        ("symptom_episodes[]", SymptomEpisode),
        ("symptom_episodes[].provenance", SymptomEpisodeProvenance),
        ("questions[]", Question),
        ("appointments[]", Appointment),
        ("source_documents[]", SourceDocument),
        ("document_imports[]", DocumentImport),
        ("document_imports[].changes[]", ImportChange),
        ("document_imports[].changes[].target", ImportTarget),
        ("document_imports[].changes[].history[]", ImportHistoryEvent),
        ("feedback[]", Feedback),
        ("caregiver_actions[]", CaregiverAction),
        ("caregiver_actions[].origin_snapshot", ActionOriginSnapshot),
        ("caregiver_actions[].outcome", ActionOutcome),
        ("visits[]", Visit),
        ("visits[].question_snapshots[]", VisitQuestionSnapshot),
        ("visits[].question_snapshots[].answer", VisitAnswer),
        ("visits[].decisions[]", VisitDecision),
        ("workflow_history[]", WorkflowAuditEvent),
        ("executive_summary", ExecutiveSummary),
        ("latest_research_update", ResearchUpdate),
    ]
    for label, cls in submodels:
        lines = [f"## `{label}`\n"]
        if cls.__doc__:
            lines.append(cls.__doc__.strip() + "\n")
        lines.append("| Field | Type | Description |")
        lines.append("|-------|------|-------------|")
        for name, field in cls.model_fields.items():
            display = field.alias or name
            ann = _short_type(field.annotation).replace("|", "\\|")
            desc = (field.description or "").replace("|", "\\|")
            lines.append(f"| `{display}` | `{ann}` | {desc} |")
        sections.append("\n".join(lines) + "\n")

    sections.append(
        "## Notes\n\n"
        '- `extra="allow"` on every sub-model — unknown keys are preserved on '
        "round-trip through `normalize_profile()`.\n"
        "- Enum-like fields (e.g. `sex`, `priority`, `modality`) document the "
        "expected values via `Literal[...]` but are not strictly enforced — "
        "drift is logged, not blocked.\n"
        "- `Patient.sstr_score` is the only field with a numeric range "
        "constraint (0–4, the Krenning scale).\n"
        "- `document_imports[]` is append-only audit provenance. Corrections and "
        "undo update active clinical state and append history events; they never "
        "delete immutable `source_documents[]` artifacts.\n"
    )
    return "\n".join(sections)


def _short_type(annotation: Any) -> str:
    """Render a type annotation as a short readable string."""
    import typing

    if annotation is None or annotation is type(None):
        return "null"
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is list:
        return f"list[{_short_type(args[0])}]" if args else "list"
    if origin is typing.Literal:
        return " | ".join(repr(a) for a in args)
    # Union / Optional
    if origin is type(None) or str(origin) in ("typing.Union", "types.UnionType"):
        non_none = [_short_type(a) for a in args if a is not type(None)]
        nullable = type(None) in args
        rendered = " | ".join(non_none)
        return f"{rendered} | null" if nullable else rendered
    if isinstance(annotation, type):
        return annotation.__name__
    # Fallback: strip module prefix from things like __main__.ExecutiveSummary
    name = str(annotation)
    return name.rsplit(".", 1)[-1]


def _cli() -> None:
    import sys
    from pathlib import Path

    if len(sys.argv) >= 2 and sys.argv[1] == "dump-md":
        out = Path(sys.argv[2]) if len(sys.argv) >= 3 else Path("docs/profile_schema.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_schema_markdown(), encoding="utf-8")
        print(f"Wrote {out} ({out.stat().st_size} bytes)")
        return
    if len(sys.argv) >= 2 and sys.argv[1] == "dump-json-schema":
        import json

        print(json.dumps(PatientProfile.model_json_schema(), indent=2))
        return
    print("usage: python -m agent.schema {dump-md [path] | dump-json-schema}")
    sys.exit(2)


if __name__ == "__main__":
    _cli()


__all__ = [
    "Alert",
    "Appointment",
    "Biomarker",
    "ClinicalJudgment",
    "Document",
    "ExecutiveSummary",
    "Imaging",
    "LiteratureWatched",
    "Patient",
    "PatientProfile",
    "Question",
    "ResearchUpdate",
    "Symptom",
    "SymptomEpisode",
    "SymptomEpisodeProvenance",
    "TrialTracked",
    "TreatmentClassified",
    "_COLLECTION_KEYS",
    "derive_date_precision",
    "normalize_profile",
    "render_schema_markdown",
    "structural_check",
    "validate_profile",
]


# Touch datetime so the import isn't dead — kept for future use of date types.
_ = datetime
