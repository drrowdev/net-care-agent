"""Chat handler — pure function for the /api/chat endpoint."""

from __future__ import annotations

from . import config
from .llm import client
from .profile import build_patient_context


def build_chat_system(profile: dict) -> str:
    """Compose the system prompt: patient profile + executive summary + history slices."""
    p = profile.get("patient", {})
    patient_context = build_patient_context(profile)
    lines = [
        "You are a medical research assistant with full access to a specific patient's clinical record.",
        f"The patient is {patient_context}.",
        "Answer questions about the case using the data below. Be precise, cite specific values and dates.",
        "When uncertain, say so. Never give generic advice — always tie answers to the actual patient data.",
        "If asked about something not in the record, say the data isn't available.",
        "When asked about a specific past document, biomarker reading, or imaging study, "
        "consult the DOCUMENTS / BIOMARKERS / IMAGING sections below — they list every "
        "clinical artefact the system has seen, not just the most recent.",
        "",
        "═══ PATIENT RECORD ═══",
        "",
        f"Diagnosis: {p.get('diagnosis') or 'unknown'}",
        f"Ki-67: {p.get('ki67_percent', 'unknown')}%",
        f"SSTR status: {p.get('sstr_status', 'unknown')} (score: {p.get('sstr_score', 'unknown')})",
        f"Treating center: {p.get('treating_center', 'unknown')}",
        f"Oncologist: {p.get('oncologist', 'unknown')}",
        "",
    ]

    summary = profile.get("executive_summary", {})
    if summary and summary.get("overall_status"):
        lines += [
            "── CURRENT ASSESSMENT ──",
            f"Overall status: {summary.get('overall_status')}",
            f"Key concern: {summary.get('key_concern', '')}",
            f"Summary: {summary.get('summary', '')}",
            f"PRRT status: {summary.get('prrt_status', '')}",
            f"CgA trend: {summary.get('cga_trend', '')}",
            "",
        ]
        actions = summary.get("next_actions", [])
        if actions:
            lines.append("── RECOMMENDED ACTIONS ──")
            for a in actions:
                lines.append(
                    f"[{a.get('priority','?').upper()}] {a.get('action','')} — {a.get('timeframe','')}"
                )
                if a.get("rationale"):
                    lines.append(f"  Rationale: {a.get('rationale','')}")
            lines.append("")

    treatments = profile.get("treatments_classified") or []
    if treatments:
        lines.append("── TREATMENTS ──")
        for t in treatments:
            lines.append(
                f"[{t.get('category','?').upper()}] {t.get('text','')} ({t.get('date','')})"
            )
        lines.append("")

    biomarkers = profile.get("biomarkers", [])
    if biomarkers:
        lines.append(f"── BIOMARKERS ({len(biomarkers)} entries, most recent first) ──")
        for b in sorted(biomarkers, key=lambda x: x.get("date", ""), reverse=True):
            flag = f" [{b.get('flag', '')}]" if b.get("flag") else ""
            ref = f" ref: {b.get('reference_range', '')}" if b.get("reference_range") else ""
            lines.append(
                f"{b.get('date', '')} {b.get('marker', '')}: {b.get('value', '')} {b.get('unit', '')}{flag}{ref}"
            )
        lines.append("")

    imaging = profile.get("imaging", [])
    if imaging:
        lines.append(f"── IMAGING ({len(imaging)} studies, most recent first) ──")
        for img in sorted(imaging, key=lambda x: x.get("date", ""), reverse=True):
            lines.append(
                f"{img.get('date', '')} {img.get('modality', '')}: "
                f"{img.get('impression', '') or img.get('findings', '')}"
            )
        lines.append("")

    documents = profile.get("documents", [])
    if documents:
        lines.append(f"── DOCUMENTS ({len(documents)} entries, most recent first) ──")
        for d in sorted(documents, key=lambda x: x.get("date", ""), reverse=True):
            findings = d.get("key_findings") or []
            findings_str = " | ".join(findings[:3]) if findings else ""
            summary = (d.get("summary") or "").strip()
            line = f"[{d.get('date', '')}] {d.get('type', '?')}: {summary}"
            if findings_str:
                line += f"  · key: {findings_str}"
            lines.append(line)
        lines.append("")

    trials = profile.get("trials_tracked", [])
    if trials:
        lines.append(f"── TRACKED TRIALS ({len(trials)}) ──")
        for t in trials[:10]:
            lines.append(
                f"{t.get('nct_id','')} — {t.get('title','')} "
                f"[{t.get('status','')}] Phase {t.get('phase','?')}"
            )
            if t.get("brief_summary"):
                lines.append(f"  {t.get('brief_summary','')[:150]}")
        lines.append("")

    papers = profile.get("literature_watched", [])
    if papers:
        lines.append(f"── TRACKED PAPERS ({len(papers)}) ──")
        for p2 in papers[:10]:
            lines.append(f"{p2.get('date','')} {p2.get('title','')} — {p2.get('journal','')}")
        lines.append("")

    judgments = profile.get("clinical_judgments", [])
    if judgments:
        lines.append("── CLINICAL JUDGMENTS FROM CONSULTATIONS ──")
        for j in judgments:
            lines.append(f"[{j.get('category','').upper()}] {j.get('date','')} {j.get('text','')}")
        lines.append("")

    alerts = [a for a in profile.get("alerts", []) if not a.get("resolved")]
    if alerts:
        lines.append("── ACTIVE ALERTS ──")
        for a in alerts:
            lines.append(
                f"[{a.get('priority','?').upper()}] {a.get('message','')} → {a.get('action_required','')}"
            )
        lines.append("")

    return "\n".join(lines)


def handle_chat(profile: dict, user_message: str, history: list[dict]) -> str:
    """Run a chat turn. Returns the assistant reply text. Raises on API error."""
    system_prompt = build_chat_system(profile)

    messages = []
    for h in history[-20:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_message})

    resp = client.messages.create(
        model=config.MODEL_CHAT,
        max_tokens=1500,
        system=system_prompt,
        messages=messages,
    )
    return resp.content[0].text
