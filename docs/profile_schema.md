# Patient profile schema

_Auto-generated from `agent/schema.py` — run `python -m agent.schema dump-md` after changing the model._

The patient profile lives at `${DATA_DIR}/patient_profile.json` (defaults to `/home/data/patient_profile.json` on Azure). It is the single source of truth for the entire app — every other artefact (reports, backups, dashboards) is derivable from this file.

All sub-models accept **extra** fields (forward-compat) and treat every documented field as optional — `load_profile()` never rejects real-world data, only logs a warning on type mismatch.

## Top-level shape

```jsonc
{
  'patient': Patient,
  'biomarkers': list[Biomarker],
  'imaging': list[Imaging],
  'appointments': list[Appointment],
  'documents': list[Document],
  'trials_tracked': list[TrialTracked],
  'literature_watched': list[LiteratureWatched],
  'alerts': list[Alert],
  'treatments_classified': list[TreatmentClassified],
  'clinical_judgments': list[ClinicalJudgment],
  'questions': list[Question],
  'executive_summary': ExecutiveSummary | None,
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
| `date` | `str \| None` | YYYY-MM-DD |
| `marker` | `str \| None` |  |
| `value` | `Any` | number or string |
| `unit` | `str \| None` |  |
| `reference_range` | `str \| None` |  |
| `flag` | `'high' \| 'low' \| 'normal' \| null` |  |

## `imaging[]`

| Field | Type | Description |
|-------|------|-------------|
| `date` | `str \| None` | YYYY-MM-DD |
| `modality` | `'CT' \| 'MRI' \| 'PET-CT' \| 'ultrasound' \| 'other' \| null` |  |
| `findings` | `str \| None` |  |
| `impression` | `str \| None` |  |
| `new_lesions` | `bool \| None` |  |

## `documents[]`

Every fed document, kept for audit and downstream re-analysis.

| Field | Type | Description |
|-------|------|-------------|
| `date` | `str \| None` |  |
| `type` | `'lab_result' \| 'imaging_report' \| 'doctor_note' \| 'research_paper' \| 'appointment_summary' \| 'pathology_report' \| 'other' \| null` |  |
| `summary` | `str \| None` | 1–2 sentence intake-agent summary |
| `key_findings` | `list[str]` |  |
| `raw_text` | `str \| None` | First ~3000 chars of input |

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
| `date_added` | `str \| None` |  |
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
| `date_added` | `str \| None` |  |
| `relevance_notes` | `str \| None` |  |

## `alerts[]`

| Field | Type | Description |
|-------|------|-------------|
| `date` | `str \| None` |  |
| `priority` | `'urgent' \| 'high' \| 'medium' \| 'low' \| null` |  |
| `message` | `str \| None` |  |
| `action_required` | `str \| None` |  |
| `resolved` | `bool` |  |

## `treatments_classified[]`

Built by agent.classify.classify_treatments — deduped + categorised.

| Field | Type | Description |
|-------|------|-------------|
| `text` | `str \| None` | Canonical merged description |
| `category` | `'active' \| 'planned' \| 'completed' \| null` |  |
| `label` | `str \| None` |  |
| `date` | `str \| None` | YYYY-MM, YYYY, or null |

## `clinical_judgments[]`

Hard constraints captured from oncologist consultations.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str \| None` |  |
| `date` | `str \| None` |  |
| `category` | `'constraint' \| 'preference' \| 'outcome' \| 'context' \| null` |  |
| `text` | `str \| None` |  |
| `source` | `'manual' \| 'ai' \| null` |  |

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

## `appointments[]`

| Field | Type | Description |
|-------|------|-------------|
| `date` | `str \| None` |  |
| `time` | `str \| None` |  |
| `with` | `str \| None` |  |
| `location` | `str \| None` |  |
| `notes` | `str \| None` |  |

## `executive_summary`

Most recent JSON output of agent.exec_summary.generate_executive_summary.

| Field | Type | Description |
|-------|------|-------------|
| `generated_at` | `str \| None` |  |
| `model` | `str \| None` |  |
| `summary` | `Any` |  |

## Notes

- `extra="allow"` on every sub-model — unknown keys are preserved on round-trip through `normalize_profile()`.
- Enum-like fields (e.g. `sex`, `priority`, `modality`) document the expected values via `Literal[...]` but are not strictly enforced — drift is logged, not blocked.
- `Patient.sstr_score` is the only field with a numeric range constraint (0–4, the Krenning scale).
