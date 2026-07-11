# Intake extraction evaluation gate

`Scripts/eval_harness.py` evaluates intake extraction with static golden JSON and
deterministic scoring. It never uses an LLM judge. The checked-in default is
`eval_cases/synthetic`; private patient cases must remain outside the repository.

## Safety and golden contract

Every real-model case runs with a fresh temporary `DATA_DIR`, profile path,
reports path, and source-artifact area. The directory is deleted after the case,
including on failure. Evaluation does not write to configured patient storage,
and artifacts contain no document text, quotes, model output, or private paths.

Schema `2.0.0` validates the intake contract's document types
(`lab_result`, `imaging_report`, `doctor_note`, `research_paper`,
`appointment_summary`, `pathology_report`, `other`) and appointment types
(`call`, `appointment`, `scan`, `review`, `infusion`, `other`). Ki-67 is
annotated through `ki67_update`; SSTR uses `sstr_status_update` and
`sstr_score_update`. Mitotic rate is not a biomarker. Scalar ranges and enums
are validated.

Goldens retain scoring annotations for treatment state, dates, and criticality.
Treatment changes include only starts/restarts, stops/holds, and dose or schedule
changes—not routine administration, unchanged continuation, or consideration.
`imaging_facts` contains at most one compound annotation because intake returns
one `imaging_findings` object. Mixed-response and lesion-specific SSTR facts are
therefore scored as one contract-shaped record.

All 40 synthetic cases are static and substantive. Validation fails on missing
or unknown fields, unknown enums, duplicate IDs, non-finite/out-of-range
scalars, or reviewed quotes absent from source text.

## Scoring and evidence

Repeated labels use deterministic maximum-quality one-to-one assignment.
Assignment quality considers label, date, value, unit, treatment state, and
source agreement, so reordered repeated lab rows pair correctly. Matching is
Unicode-normalized, case-folded, punctuation-insensitive, and
whitespace-collapsed.

Source support requires evidence emitted by the evaluated model:

- structured biomarkers, imaging, symptoms, and appointments use their own
  `source_quote`;
- treatment changes, key findings, and special scalars use mapped `evidence[]`
  rows (`field` plus `item_index` where applicable).

The quote must occur in the input and support the matched label and applicable
value, unit, appointment date, treatment state, or scalar. A reviewed golden
quote or unrelated true sentence does not establish model support.
List evidence requires the exact `item_index`; a null index is scalar-only.

The artifact reports per-field recall/precision and aggregates:

- overall recall and precision;
- all unsupported additions and must-not-infer violations;
- exact date, value, and unit accuracy;
- treatment-state and special-scalar accuracy;
- source support;
- critical recall, omissions, regressions, and unsupported additions.

Both aggregate and worst-of-run metrics are gated. The default three runs retain
the worst observed result rather than averaging away a failure.

## Accuracy-first defaults

Defaults are:

- overall recall `>= 0.98` and precision `>= 0.98`;
- source support `>= 0.99`;
- date/value/unit, treatment-state, and special-scalar accuracy `>= 0.99`;
- critical-event recall `= 1.0`;
- zero unsupported additions, critical omissions, critical regressions,
  critical unsupported additions, and must-not-infer violations.

Each threshold has a corresponding CLI option, such as
`--min-overall-precision`, `--min-date-accuracy`, or
`--max-unsupported-additions`. Minimum thresholds must be finite values in
`[0,1]`; maximum thresholds must be non-negative integers.

## Running

Real-model evaluation is external and requires normal model credentials:

```powershell
python Scripts\eval_harness.py --runs 1
python Scripts\eval_harness.py --golden-dir D:\private\net-evals --runs 3 `
  --artifact D:\private\results\eval.json
```

The artifact records the exact Git `HEAD` and dirty state; SHA-256 hashes of all
evaluated golden, harness, intake, prompt, configuration, profile, provenance,
and schema source files; the exact effective rendered prompt-input hash; model
IDs; adaptive-thinking configuration; `INTAKE_VERIFY`; token limits; run count;
per-run scores; aggregate/worst metrics; thresholds; and pass state. A dirty
tree is explicitly marked, and evaluated source changes alter its hashes.
Private-corpus filenames and case IDs are replaced with ordinal/hash identifiers.

For private corpora, transcribe only the minimum necessary excerpt. A clinician
must review clinical meaning, dates, units, negations, critical labels, and
must-not-infer statements. Never copy patient text into issues, logs, or
artifacts.

Exit codes are `0` pass, `2` metric failure, `3` schema/configuration/harness
error, and `4` model/runtime error.
