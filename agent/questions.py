"""Appointment-question generation (output language configurable via profile)."""

from __future__ import annotations

import datetime
import json

from . import config
from .judgments import CLINICAL_JUDGMENTS_OVERRIDE, get_clinical_judgments_context
from .llm import client, first_text, strip_code_fences
from .profile import (
    build_patient_context,
    get_output_language,
    get_patient_summary,
)


def generate_appointment_questions(appointment_type: str, focus_areas: list, profile: dict) -> dict:
    """Use Claude to generate targeted pre-appointment questions (English, simple list).

    Used by the orchestrator's tool dispatcher; the rich language-aware version
    below is used by the dedicated `/api/questions/generate` endpoint.
    """
    resp = client.messages.create(
        model=config.MODEL_QUESTIONS,
        max_tokens=12000,
        thinking=config.THINKING,
        system=(
            "You are a specialist medical research assistant helping a caregiver "
            "prepare for a cancer consultation. Generate specific, informed questions "
            "based on the patient's current profile. Be concise but thorough."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Generate 10-12 specific questions for an upcoming {appointment_type} appointment.\n\n"
                    f"Patient context:\n{get_patient_summary(profile)}\n\n"
                    f"Focus areas: {', '.join(focus_areas) if focus_areas else 'general follow-up'}\n\n"
                    "Return ONLY a JSON object:\n"
                    '{"questions": ["...", ...], "documents_to_bring": ["...", ...], '
                    '"tests_to_request_if_not_done": ["...", ...]}'
                ),
            }
        ],
    )
    text = first_text(resp)
    raw = strip_code_fences(text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "questions": [text],
            "documents_to_bring": [],
            "tests_to_request_if_not_done": [],
        }


def _build_questions_system_prompt(profile: dict) -> str:
    """Compose the system prompt from the live profile.

    Output language and the example referral question are parameterised from
    `patient.language` / `patient.regions_of_interest` so source code ships
    no patient-identifying details.
    """
    patient_context = build_patient_context(profile)
    language = get_output_language(profile)
    is_english = language.strip().lower() == "english"

    if is_english:
        language_block = ""
    else:
        language_block = (
            f"IMPORTANT: Generate all question text and rationale IN {language.upper()}. "
            f"The caregiver will ask these questions to a {language}-speaking oncologist.\n\n"
        )

    regions = [r for r in (profile.get("patient", {}).get("regions_of_interest") or []) if r]
    region_phrase = " or ".join(regions) if regions else "your country or region"
    referral_example = f"'Which centers in {region_phrase} should we contact about PRRT trials?'"

    return (
        "You are a specialist medical research assistant helping a caregiver "
        f"prepare for a cancer consultation for {patient_context}.\n\n"
        f"{language_block}"
        "Generate specific, clinically informed questions based on the patient's "
        "current profile. Each question must be concrete, answerable by the treating "
        "oncologist, and anchored to a specific datum in the profile (a value with its "
        "date, an imaging finding, a treatment, an alert, or a gap such as a missing "
        "test) — the rationale should name that anchor. No generic questionnaire items.\n\n"
        "IMPORTANT RULES:\n"
        "- Do NOT generate questions about specific clinical trial eligibility "
        "(e.g. 'Does the patient qualify for NCT...'). Trial enrollment is handled by "
        "trial coordinators, not the primary oncologist.\n"
        "- Instead, for the Trials category, only ask general referral questions "
        "like 'Are there any trials you would recommend we explore?' or "
        f"{referral_example}\n"
        "- Focus on questions the primary oncologist can actually answer or act on.\n\n"
        "Return ONLY valid JSON array, no markdown:\n"
        "[\n"
        "  {\n"
        f'    "text": "Question text in {language}",\n'
        '    "category": "Treatment|Diagnostics|Symptoms|Trials|Monitoring|Other",\n'
        '    "priority": "urgent|high|medium",\n'
        f'    "rationale": "Why this question matters now (1 sentence in {language})"\n'
        "  }\n"
        "]\n\n"
        'The "category" and "priority" values must stay EXACTLY these English enum '
        "strings — the UI matches on them. The text and rationale go in the caregiver's "
        "language above.\n"
        "Categories (keep in English for code, display translated in UI):\n"
        "- Treatment: current/upcoming treatment decisions\n"
        "- Diagnostics: scans, tests, biopsies needed\n"
        "- Symptoms: symptom management, side effects\n"
        "- Trials: clinical trial eligibility and access\n"
        "- Monitoring: follow-up schedule, biomarker tracking\n"
        "- Other: prognosis, referrals, logistics\n\n"
        "Priority: urgent = affects a decision or safety issue that cannot wait past "
        "this appointment; high = materially affects the treatment plan or next steps; "
        "medium = useful context, not time-critical.\n\n"
        "Generate 10-15 questions when the profile supports them; if the profile is "
        "sparse, return fewer well-grounded questions rather than padding with generic "
        "ones. Order matters less than correct priority values — the UI groups and "
        "sorts.\n\n"
        + CLINICAL_JUDGMENTS_OVERRIDE
        + "- You MAY ask a clarifying question where a judgment is ambiguous, "
        "conditional, or time-limited (e.g. what result would change the plan).\n"
    )


def generate_questions_for_profile(
    profile: dict, appointment_type: str = "oncology follow-up"
) -> list:
    """Structured appointment question list for the UI.

    Output language is configurable via `patient.language` in the profile
    (defaults to English).
    """
    try:
        resp = client.messages.create(
            model=config.MODEL_QUESTIONS,
            max_tokens=16000,
            thinking=config.THINKING,
            system=_build_questions_system_prompt(profile),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Generate appointment questions for a {appointment_type} visit.\n\n"
                        f"Patient profile:\n{get_patient_summary(profile)}\n\n"
                        f"Active alerts: {json.dumps([a for a in profile.get('alerts', []) if not a.get('resolved')], default=str)}\n\n"
                        f"Most recent imaging: {json.dumps(profile.get('imaging', [])[-2:], default=str)}\n\n"
                        f"Recent biomarkers: {json.dumps(profile.get('biomarkers', [])[-6:], default=str)}\n\n"
                        f"IMPORTANT — Clinical judgments from previous consultations (do not generate questions about things already addressed):\n"
                        f"{get_clinical_judgments_context(profile)}\n\n"
                        f"Today: {datetime.date.today().isoformat()}"
                    ),
                }
            ],
        )
        raw = strip_code_fences(first_text(resp))
        questions = json.loads(raw)
        if not isinstance(questions, list):
            return []
        today = datetime.date.today().isoformat()
        return [
            {
                "id": f"q_{i}_{today.replace('-','')}",
                "text": q.get("text", ""),
                "category": q.get("category", "Other"),
                "priority": q.get("priority", "medium"),
                "rationale": q.get("rationale", ""),
                "source": "ai",
                "asked": False,
                "created_at": today,
            }
            for i, q in enumerate(questions)
            if q.get("text")
        ]
    except Exception as e:
        print(f"  ⚠  Question generation failed: {e}")
        return []
