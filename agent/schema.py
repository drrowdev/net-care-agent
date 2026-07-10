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


def now_stamp() -> str:
    """Wall-clock ISO timestamp (seconds precision) for when an item was first
    recorded in the profile.

    Consumed by the dashboard "new since acknowledged" counter (``_count_new``
    in app.py). Because it reflects *ingestion* time rather than an item's
    clinical date, a back-dated document fed today still surfaces as new.
    """
    return datetime.datetime.now().isoformat(timespec="seconds")


# ── enum-like literals ────────────────────────────────────────────────────────
# These are *documented* sets; we don't enforce them strictly because real-world
# data drifts and we'd rather accept a bad value than reject a valid profile.
Sex = Literal["female", "male", "other"]
SstrStatus = Literal["positive", "negative", "unknown"]
BiomarkerFlag = Literal["high", "low", "normal"]
ImagingModality = Literal["CT", "MRI", "PET-CT", "ultrasound", "other"]
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
SymptomSource = Literal["manual", "ai"]
QuestionCategory = Literal["Treatment", "Diagnostics", "Symptoms", "Trials", "Monitoring", "Other"]
QuestionPriority = Literal["urgent", "high", "medium"]
QuestionSource = Literal["ai", "manual"]


# ── shared base ───────────────────────────────────────────────────────────────
class _Lenient(BaseModel):
    """Base for all profile sub-models: accept extras, validate by name."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


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


class Biomarker(_Lenient):
    """A single lab result row (CgA, NSE, 5-HIAA, creatinine, etc.)."""

    date: str | None = Field(None, description="YYYY-MM-DD")
    marker: str | None = None
    value: Any = Field(None, description="number or string")
    unit: str | None = None
    reference_range: str | None = None
    flag: BiomarkerFlag | None = None
    added_at: str | None = Field(
        None, description="Ingestion timestamp; drives the 'new since acknowledged' counter."
    )


class Imaging(_Lenient):
    date: str | None = Field(None, description="YYYY-MM-DD")
    modality: ImagingModality | None = None
    findings: str | None = None
    impression: str | None = None
    new_lesions: bool | None = None
    added_at: str | None = Field(
        None, description="Ingestion timestamp; drives the 'new since acknowledged' counter."
    )


class Document(_Lenient):
    """Every fed document, kept for audit and downstream re-analysis."""

    date: str | None = None
    type: DocumentType | None = None
    summary: str | None = Field(None, description="1–2 sentence intake-agent summary")
    key_findings: list[str] = Field(default_factory=list)
    raw_text: str | None = Field(None, description="First ~3000 chars of input")
    added_at: str | None = Field(
        None, description="Ingestion timestamp; drives the 'new since acknowledged' counter."
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
    date_added: str | None = None
    eligibility_notes: str | None = ""


class LiteratureWatched(_Lenient):
    pmid: str | None = Field(None, description="PubMed ID, primary key")
    title: str | None = None
    authors: str | None = None
    journal: str | None = None
    date: str | None = None
    url: str | None = None
    query: str | None = None
    date_added: str | None = None
    relevance_notes: str | None = ""


class Alert(_Lenient):
    date: str | None = None
    priority: AlertPriority | None = None
    message: str | None = None
    action_required: str | None = None
    resolved: bool = False
    added_at: str | None = Field(
        None, description="Ingestion timestamp; drives the 'new since acknowledged' counter."
    )


class TreatmentClassified(_Lenient):
    """Built by agent.classify.classify_treatments — deduped + categorised."""

    text: str | None = Field(None, description="Canonical merged description")
    category: TreatmentCategory | None = None
    label: str | None = None
    date: str | None = Field(None, description="YYYY-MM, YYYY, or null")


class ClinicalJudgment(_Lenient):
    """Hard constraints captured from oncologist consultations."""

    id: str | None = None
    date: str | None = None
    category: JudgmentCategory | None = None
    text: str | None = None
    source: JudgmentSource | None = None
    added_at: str | None = Field(
        None, description="Ingestion timestamp; drives the 'new since acknowledged' counter."
    )


class Symptom(_Lenient):
    """Patient-reported symptom or side effect.

    Bridges the gap between objective biomarkers and the oncologist's
    consultation notes — the day-to-day experiential data that informs
    appointment prep.
    """

    id: str | None = None
    date: str | None = Field(None, description="YYYY-MM-DD")
    symptom: str | None = None
    severity: int | None = Field(None, ge=1, le=5, description="1=mild .. 5=severe")
    note: str | None = None
    related_treatment: str | None = Field(
        None, description="Optional link to a treatment name in current_treatments"
    )
    source: SymptomSource | None = None
    added_at: str | None = Field(
        None, description="Ingestion timestamp; drives the 'new since acknowledged' counter."
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


class Appointment(_Lenient):
    date: str | None = None
    time: str | None = None
    with_: str | None = Field(None, alias="with")
    location: str | None = None
    notes: str | None = None
    description: str | None = None
    type: str | None = None


class ExecutiveSummary(_Lenient):
    """Most recent JSON output of agent.exec_summary.generate_executive_summary."""

    generated_at: str | None = None
    generated_at_timestamp: str | None = None
    summary_revision: int | None = None
    stale: bool = True
    summary_error: str | None = None
    model: str | None = None
    summary: Any = None  # free-form structure varies by run


# ── top-level model ───────────────────────────────────────────────────────────
class PatientProfile(_Lenient):
    """The complete patient profile. Lives at ${DATA_DIR}/patient_profile.json."""

    profile_revision: int = 0
    profile_updated_at: str | None = None
    profile_saved_at: str | None = None
    summary_stale: bool = True
    patient: Patient = Field(default_factory=Patient)
    biomarkers: list[Biomarker] = Field(default_factory=list)
    imaging: list[Imaging] = Field(default_factory=list)
    appointments: list[Appointment] = Field(default_factory=list)
    documents: list[Document] = Field(default_factory=list)
    trials_tracked: list[TrialTracked] = Field(default_factory=list)
    literature_watched: list[LiteratureWatched] = Field(default_factory=list)
    alerts: list[Alert] = Field(default_factory=list)
    treatments_classified: list[TreatmentClassified] = Field(default_factory=list)
    clinical_judgments: list[ClinicalJudgment] = Field(default_factory=list)
    symptoms: list[Symptom] = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list)
    executive_summary: ExecutiveSummary | None = None
    acknowledged_at: str | None = Field(
        None,
        description="ISO timestamp of the last user 'mark all read' action; "
        "items dated after this are 'new since last login' for the delta view.",
    )


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
        log.warning("profile validation failed; returning raw dict: %s", e)
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
        ("questions[]", Question),
        ("appointments[]", Appointment),
        ("executive_summary", ExecutiveSummary),
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
    "Symptom",
    "TrialTracked",
    "TreatmentClassified",
    "normalize_profile",
    "render_schema_markdown",
    "validate_profile",
]


# Touch datetime so the import isn't dead — kept for future use of date types.
_ = datetime
