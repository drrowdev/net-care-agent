# Patient profile schema

_Auto-generated from `agent/schema.py` — run `python -m agent.schema dump-md` after changing the model._

The patient profile lives at `${DATA_DIR}/patient_profile.json` (defaults to `/home/data/patient_profile.json` on Azure). It is the single source of truth for the entire app — every other artefact (reports, backups, dashboards) is derivable from this file.

All sub-models accept **extra** fields (forward-compat) and treat every documented field as optional — `load_profile()` never rejects real-world data, only logs a warning on type mismatch.

## Top-level shape

```jsonc
{
  'schema_version': int,
  'profile_revision': int,
  'workflow_revision': int,
  'profile_updated_at': str | None,
  'profile_saved_at': str | None,
  'summary_stale': bool,
  'patient': Patient,
  'biomarkers': list[Biomarker],
  'imaging': list[Imaging],
  'appointments': list[Appointment],
  'documents': list[Document],
  'source_documents': list[SourceDocument],
  'document_imports': list[DocumentImport],
  'trials_tracked': list[TrialTracked],
  'literature_watched': list[LiteratureWatched],
  'alerts': list[Alert],
  'treatments_classified': list[TreatmentClassified],
  'treatments_classification_revision': int | None,
  'treatments_classification_job_id': str | None,
  'clinical_judgments': list[ClinicalJudgment],
  'symptoms': list[Symptom],
  'questions': list[Question],
  'appointment_questions': list[Question],
  'questions_generation_id': str | None,
  'feedback': list[Feedback],
  'caregiver_actions': list[CaregiverAction],
  'visits': list[Visit],
  'executive_summary': ExecutiveSummary | None,
  'latest_research_update': ResearchUpdate | None,
}
```

## `patient`

Demographics + diagnosis. The only non-list top-level branch.

| Field | Type | Description |
|-------|------|-------------|
| `birth_year` | `int \| None` | Birth year, used to derive age |
| `age` | `int \| None` | Derived from birth_year |
| `sex` | `'female' \| 'male' \| 'other' \| null` |  |
| `diagnosis` | `str \| None` |  |
| `ki67_percent` | `float \| None` | Ki-67 / MIB-1 proliferation index |
| `sstr_status` | `'positive' \| 'negative' \| 'unknown' \| null` | Somatostatin receptor status |
| `sstr_score` | `int \| None` | Krenning score 0–4 |
| `current_treatments` | `list[str]` | Raw treatment strings; deduped by classify step |
| `current_treatment_records` | `list[Any]]` | Stable component/source mapping for composite-safe treatment edits |
| `allergies` | `list[str]` |  |
| `comorbidities` | `list[str]` |  |
| `oncologist` | `str \| None` |  |
| `treating_center` | `str \| None` |  |
| `location` | `str \| None` | Patient's city/country, e.g. 'Berlin, Germany'. Used to compose the identifying context in agent system prompts so the repo itself ships no patient-identifying details. |
| `caregiver_relationship` | `str \| None` | Relationship of the caregiver to the patient (e.g. 'partner', 'parent'). Drives wording in agent system prompts; defaults to 'caregiver'. |
| `language` | `str \| None` | Output language for caregiver-facing artifacts such as appointment questions, e.g. 'German'. Defaults to 'English'. |
| `regions_of_interest` | `list[str]` | Countries to prioritise in clinical-trial searches, e.g. ['Germany', 'Switzerland']. Empty list = no region filter. |

## `biomarkers[]`

A single lab result row (CgA, NSE, 5-HIAA, creatinine, etc.).

| Field | Type | Description |
|-------|------|-------------|
| `source_document_id` | `str \| None` |  |
| `source_quote` | `str \| None` | Exact immutable source text span |
| `evidence_status` | `'verified' \| 'missing' \| 'invalid' \| null` |  |
| `evidence_start` | `int \| None` |  |
| `evidence_end` | `int \| None` |  |
| `id` | `str \| None` | Stable identity for imported rows |
| `date` | `str \| None` | Exact source-derived YYYY-MM-DD, YYYY-MM, or YYYY |
| `date_precision` | `'day' \| 'month' \| 'year' \| 'unknown'` |  |
| `date_kind` | `'collection' \| 'result' \| 'clinical_unspecified' \| 'source_document' \| 'unknown'` |  |
| `source_document_date` | `str \| None` | Source document date when explicitly stated |
| `source_document_date_precision` | `'day' \| 'month' \| 'year' \| 'unknown'` |  |
| `marker` | `str \| None` |  |
| `value` | `Any` | number or string |
| `unit` | `str \| None` |  |
| `reference_range` | `str \| None` |  |
| `flag` | `'high' \| 'low' \| 'normal' \| null` |  |
| `flag_authority` | `'source_reported' \| 'caregiver_corrected' \| 'legacy_unknown' \| 'unknown'` |  |
| `specimen` | `str \| None` |  |
| `assay` | `str \| None` |  |
| `method` | `str \| None` |  |
| `added_at` | `str \| None` | Timestamp when the item first entered the patient profile. |

## `imaging[]`

| Field | Type | Description |
|-------|------|-------------|
| `source_document_id` | `str \| None` |  |
| `source_quote` | `str \| None` | Exact immutable source text span |
| `evidence_status` | `'verified' \| 'missing' \| 'invalid' \| null` |  |
| `evidence_start` | `int \| None` |  |
| `evidence_end` | `int \| None` |  |
| `id` | `str \| None` | Stable identity for imported rows |
| `date` | `str \| None` | YYYY-MM-DD |
| `modality` | `'CT' \| 'MRI' \| 'PET-CT' \| 'ultrasound' \| 'other' \| null` |  |
| `findings` | `str \| None` |  |
| `impression` | `str \| None` |  |
| `new_lesions` | `bool \| None` |  |
| `added_at` | `str \| None` | Timestamp when the item first entered the patient profile. |

## `documents[]`

Every fed document, kept for audit and downstream re-analysis.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str \| None` | Stable identity for imported rows |
| `date` | `str \| None` |  |
| `type` | `'lab_result' \| 'imaging_report' \| 'doctor_note' \| 'research_paper' \| 'appointment_summary' \| 'pathology_report' \| 'other' \| null` |  |
| `summary` | `str \| None` | 1–2 sentence intake-agent summary |
| `key_findings` | `list[str]` |  |
| `raw_text` | `str \| None` | First ~3000 chars of input |
| `source_document_id` | `str \| None` |  |
| `excluded_from_clinical_context` | `bool` | True after a caregiver removes or undoes this import's clinical effects |
| `evidence` | `list[Any]]` | Anchored evidence for document-level findings not stored as structured rows |
| `added_at` | `str \| None` | Timestamp when the item first entered the patient profile. |

## `trials_tracked[]`

| Field | Type | Description |
|-------|------|-------------|
| `nct_id` | `str \| None` | ClinicalTrials.gov ID, primary key |
| `title` | `str \| None` |  |
| `status` | `str \| None` |  |
| `phase` | `str \| None` |  |
| `countries` | `list[str]` |  |
| `url` | `str \| None` |  |
| `brief_summary` | `str \| None` |  |
| `eligibility_excerpt` | `str \| None` |  |
| `date_added` | `str \| None` | Timestamp when the trial was first tracked |
| `eligibility_notes` | `str \| None` |  |

## `literature_watched[]`

| Field | Type | Description |
|-------|------|-------------|
| `pmid` | `str \| None` | PubMed ID, primary key |
| `title` | `str \| None` |  |
| `authors` | `str \| None` |  |
| `journal` | `str \| None` |  |
| `date` | `str \| None` |  |
| `url` | `str \| None` |  |
| `query` | `str \| None` |  |
| `date_added` | `str \| None` | Timestamp when the paper was first tracked |
| `relevance_notes` | `str \| None` |  |

## `alerts[]`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str \| None` | Stable identity for imported rows |
| `date` | `str \| None` |  |
| `priority` | `'urgent' \| 'high' \| 'medium' \| 'low' \| null` |  |
| `message` | `str \| None` |  |
| `action_required` | `str \| None` |  |
| `resolved` | `bool` |  |
| `source_document_id` | `str \| None` |  |
| `source_job_id` | `str \| None` |  |
| `generation_profile_revision` | `int \| None` |  |
| `dependency_kind` | `'durable' \| 'source' \| 'profile_snapshot'` |  |
| `source_dependency_active` | `bool` |  |
| `source_invalidated_at` | `str \| None` |  |
| `inactive_reason` | `str \| None` |  |
| `resolution` | `Any] \| None` |  |
| `history` | `ForwardRef('list[WorkflowAuditEvent]')` |  |
| `added_at` | `str \| None` | Timestamp when the item first entered the patient profile. |

## `treatments_classified[]`

Built by agent.classify.classify_treatments — deduped + categorised.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str \| None` |  |
| `text` | `str \| None` | Canonical merged description |
| `category` | `'active' \| 'planned' \| 'completed' \| null` |  |
| `label` | `str \| None` |  |
| `date` | `str \| None` | YYYY-MM, YYYY, or null |
| `source_treatment_ids` | `list[str]` |  |

## `clinical_judgments[]`

Hard constraints captured from oncologist consultations.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str \| None` |  |
| `date` | `str \| None` |  |
| `category` | `'constraint' \| 'preference' \| 'outcome' \| 'context' \| null` |  |
| `text` | `str \| None` |  |
| `source` | `'manual' \| 'ai' \| null` |  |
| `scope` | `str \| None` | Clinical topic or decision this judgment governs |
| `status` | `'active' \| 'superseded' \| 'needs_review'` |  |
| `review_after` | `str \| None` | YYYY-MM-DD; review due on/after this date |
| `valid_until` | `str \| None` | YYYY-MM-DD; ceases to constrain after this date |
| `supersedes` | `str \| None` | ID of the prior judgment this replaces |
| `updated_at` | `str \| None` |  |
| `added_at` | `str \| None` | Timestamp when the item first entered the patient profile. |

## `symptoms[]`

Patient-reported symptom or side effect.

    Bridges the gap between objective biomarkers and the oncologist's
    consultation notes — the day-to-day experiential data that informs
    appointment prep.

| Field | Type | Description |
|-------|------|-------------|
| `source_document_id` | `str \| None` |  |
| `source_quote` | `str \| None` | Exact immutable source text span |
| `evidence_status` | `'verified' \| 'missing' \| 'invalid' \| null` |  |
| `evidence_start` | `int \| None` |  |
| `evidence_end` | `int \| None` |  |
| `id` | `str \| None` |  |
| `date` | `str \| None` | YYYY-MM-DD |
| `symptom` | `str \| None` |  |
| `severity` | `int \| None` | 1=mild .. 5=severe |
| `note` | `str \| None` |  |
| `related_treatment` | `str \| None` | Optional link to a treatment name in current_treatments |
| `source` | `'manual' \| 'ai' \| null` |  |
| `added_at` | `str \| None` | Timestamp when the item first entered the patient profile. |

## `questions[]`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str \| None` |  |
| `text` | `str \| None` |  |
| `category` | `'Treatment' \| 'Diagnostics' \| 'Symptoms' \| 'Trials' \| 'Monitoring' \| 'Other' \| null` |  |
| `priority` | `'urgent' \| 'high' \| 'medium' \| null` |  |
| `rationale` | `str \| None` |  |
| `source` | `'manual' \| 'ai' \| null` |  |
| `asked` | `bool` |  |
| `created_at` | `str \| None` |  |
| `source_profile_revision` | `int \| None` |  |
| `stale` | `bool` |  |
| `stale_reason` | `str \| None` |  |
| `stale_at` | `str \| None` |  |
| `generation_job_id` | `str \| None` |  |

## `appointments[]`

| Field | Type | Description |
|-------|------|-------------|
| `source_document_id` | `str \| None` |  |
| `source_quote` | `str \| None` | Exact immutable source text span |
| `evidence_status` | `'verified' \| 'missing' \| 'invalid' \| null` |  |
| `evidence_start` | `int \| None` |  |
| `evidence_end` | `int \| None` |  |
| `id` | `str \| None` | Stable identity for imported rows |
| `date` | `str \| None` |  |
| `time` | `str \| None` |  |
| `with` | `str \| None` |  |
| `location` | `str \| None` |  |
| `notes` | `str \| None` |  |
| `description` | `str \| None` |  |
| `type` | `str \| None` |  |
| `added_at` | `str \| None` |  |

## `source_documents[]`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` |  |
| `ingested_at` | `str` |  |
| `filename` | `str \| None` |  |
| `media_type` | `str \| None` |  |
| `source` | `SourceArtifact` |  |
| `text` | `SourceArtifact` |  |

## `document_imports[]`

Profile-backed receipt tying one feed job to its immutable source and audit history.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` |  |
| `job_id` | `str` |  |
| `source_document_id` | `str` |  |
| `ingested_at` | `str` |  |
| `filename` | `str \| None` |  |
| `media_type` | `str \| None` |  |
| `document_type` | `str \| None` |  |
| `document_date` | `str \| None` |  |
| `document_summary` | `str \| None` |  |
| `applied_revision` | `int` |  |
| `receipt_revision` | `int` |  |
| `status` | `'active' \| 'corrected' \| 'partially_removed' \| 'undone'` |  |
| `changes` | `list[ImportChange]` |  |

## `document_imports[].changes[]`

One direct or derived outcome shown in a document reconciliation receipt.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` |  |
| `category` | `str` |  |
| `label` | `str` |  |
| `operation` | `'added' \| 'updated' \| 'unchanged' \| 'conflict' \| 'derived'` |  |
| `target` | `ImportTarget` |  |
| `before` | `Any` |  |
| `after` | `Any` |  |
| `effective_value` | `Any` |  |
| `evidence_status` | `'verified' \| 'missing' \| 'invalid' \| null` |  |
| `evidence_start` | `int \| None` |  |
| `evidence_end` | `int \| None` |  |
| `source_document_id` | `str \| None` |  |
| `editable_fields` | `list[str]` |  |
| `state` | `'active' \| 'corrected' \| 'removed' \| 'unchanged' \| 'derived' \| 'undone'` |  |
| `history` | `list[ImportHistoryEvent]` |  |

## `document_imports[].changes[].target`

Server-owned locator used for compare-and-swap receipt mutations.

| Field | Type | Description |
|-------|------|-------------|
| `kind` | `'collection' \| 'scalar' \| 'treatment' \| 'none'` |  |
| `collection` | `str \| None` |  |
| `record_id` | `str \| None` |  |
| `path` | `list[str]` |  |

## `document_imports[].changes[].history[]`

Immutable before/after record for a caregiver correction, removal, or undo.

| Field | Type | Description |
|-------|------|-------------|
| `event` | `'corrected' \| 'removed' \| 'undone'` |  |
| `at` | `str` |  |
| `before` | `Any` |  |
| `after` | `Any` |  |

## `feedback[]`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` |  |
| `target` | `str` |  |
| `item_id` | `str` |  |
| `assessment` | `'agreed' \| 'corrected' \| 'acted' \| 'helpful' \| 'incorrect' \| 'missed'` |  |
| `note` | `str \| None` |  |
| `outcome` | `str \| None` |  |
| `created_at` | `str` |  |
| `updated_at` | `str` |  |

## `caregiver_actions[]`

Durable caregiver-owned follow-up independent of generated artifacts.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` |  |
| `origin_snapshot` | `ActionOriginSnapshot` |  |
| `text` | `str` |  |
| `owner` | `str \| None` |  |
| `due_date` | `str \| None` |  |
| `status` | `'open' \| 'in_progress' \| 'completed' \| 'cancelled'` |  |
| `outcome` | `ActionOutcome \| None` |  |
| `visit_id` | `str \| None` |  |
| `decision_id` | `str \| None` |  |
| `alert_id` | `str \| None` |  |
| `created_at` | `str` |  |
| `updated_at` | `str` |  |
| `completed_at` | `str \| None` |  |
| `cancelled_at` | `str \| None` |  |
| `history` | `list[WorkflowAuditEvent]` |  |

## `caregiver_actions[].origin_snapshot`

Immutable source snapshot captured when a caregiver accepts an action.

| Field | Type | Description |
|-------|------|-------------|
| `kind` | `'manual' \| 'executive_summary_action' \| 'alert' \| 'visit_decision'` |  |
| `source_id` | `str \| None` |  |
| `source_job_id` | `str \| None` |  |
| `source_profile_revision` | `int \| None` |  |
| `generation_id` | `str \| None` |  |
| `text` | `str` |  |
| `snapshot` | `Any]` |  |

## `caregiver_actions[].outcome`

| Field | Type | Description |
|-------|------|-------------|
| `kind` | `'administrative' \| 'caregiver_reported' \| 'clinician_attributed'` |  |
| `text` | `str` |  |
| `recorded_at` | `str` |  |
| `provenance` | `dict[str, str]` |  |

## `visits[]`

Caregiver working record, optionally linked to an imported appointment.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` |  |
| `title` | `str` |  |
| `date` | `str \| None` |  |
| `time` | `str \| None` |  |
| `clinician` | `str \| None` |  |
| `location` | `str \| None` |  |
| `status` | `'planned' \| 'in_progress' \| 'completed' \| 'cancelled'` |  |
| `source_appointment_id` | `str \| None` |  |
| `question_snapshots` | `list[VisitQuestionSnapshot]` |  |
| `decisions` | `list[VisitDecision]` |  |
| `follow_up_ids` | `list[str]` |  |
| `created_at` | `str` |  |
| `updated_at` | `str` |  |
| `completed_at` | `str \| None` |  |
| `cancelled_at` | `str \| None` |  |
| `history` | `list[WorkflowAuditEvent]` |  |

## `visits[].question_snapshots[]`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` |  |
| `text` | `str` |  |
| `category` | `str \| None` |  |
| `priority` | `str \| None` |  |
| `rationale` | `str \| None` |  |
| `source_kind` | `'manual' \| 'generated'` |  |
| `source_question_id` | `str \| None` |  |
| `source_generation_id` | `str \| None` |  |
| `source_profile_revision` | `int \| None` |  |
| `pinned` | `bool` |  |
| `order` | `int` |  |
| `answer` | `VisitAnswer \| None` |  |
| `created_at` | `str` |  |

## `visits[].question_snapshots[].answer`

| Field | Type | Description |
|-------|------|-------------|
| `status` | `'answered' \| 'unknown'` |  |
| `text` | `str \| None` |  |
| `recorded_at` | `str` |  |
| `provenance` | `CaptureProvenance` |  |

## `visits[].decisions[]`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` |  |
| `text` | `str` |  |
| `status` | `'active' \| 'superseded' \| 'retracted' \| 'needs_confirmation'` |  |
| `provenance` | `CaptureProvenance` |  |
| `supersedes_id` | `str \| None` |  |
| `created_at` | `str` |  |
| `updated_at` | `str` |  |

## `workflow_history[]`

Append-only mutation event supporting idempotent target-level updates.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` |  |
| `mutation_id` | `str` |  |
| `endpoint` | `str \| None` |  |
| `operation` | `str` |  |
| `target` | `str \| None` |  |
| `at` | `str` |  |
| `request_hash` | `str` |  |
| `before_token` | `str \| None` |  |
| `after_token` | `str \| None` |  |
| `changes` | `Any]` |  |
| `result_hash` | `str \| None` |  |
| `result_snapshot` | `Any] \| None` |  |

## `executive_summary`

Most recent JSON output of agent.exec_summary.generate_executive_summary.

| Field | Type | Description |
|-------|------|-------------|
| `generated_at` | `str \| None` |  |
| `generated_at_timestamp` | `str \| None` |  |
| `generation_id` | `str \| None` |  |
| `summary_revision` | `int \| None` |  |
| `stale` | `bool` |  |
| `summary_error` | `str \| None` |  |
| `model` | `str \| None` |  |
| `summary` | `Any` |  |

## `latest_research_update`

Exact net-new research records added by the latest discovery batch.

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | `str \| None` | Run identifier that produced this batch |
| `trigger` | `str \| None` | Discovery source: digest or feed |
| `completed_at` | `str \| None` | ISO timestamp when the batch was recorded |
| `trial_ids` | `list[str]` | Canonical NCT IDs newly added by this batch |
| `paper_ids` | `list[str]` | Canonical numeric PubMed IDs newly added by this batch |

## Notes

- `extra="allow"` on every sub-model — unknown keys are preserved on round-trip through `normalize_profile()`.
- Enum-like fields (e.g. `sex`, `priority`, `modality`) document the expected values via `Literal[...]` but are not strictly enforced — drift is logged, not blocked.
- `Patient.sstr_score` is the only field with a numeric range constraint (0–4, the Krenning scale).
- `document_imports[]` is append-only audit provenance. Corrections and undo update active clinical state and append history events; they never delete immutable `source_documents[]` artifacts.
