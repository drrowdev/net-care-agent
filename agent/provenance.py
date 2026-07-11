"""Immutable source artifacts and deterministic evidence anchoring."""

from __future__ import annotations

import datetime
import hashlib
import re
import shutil
import unicodedata
import uuid
from pathlib import Path

from . import config
from .io import atomic_write_bytes, atomic_write_text

SOURCE_ROOT_NAME = "source_documents"
_SOURCE_ID_RE = re.compile(r"^doc_[0-9a-f]{32}$")
_ARTIFACT_NAMES = {"source": "source.bin", "text": "extracted.txt"}


def new_source_document_id() -> str:
    return f"doc_{uuid.uuid4().hex}"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def preserve_source_document(
    text: str,
    *,
    raw_bytes: bytes | None = None,
    filename: str | None = None,
    media_type: str = "text/plain",
    source_document_id: str | None = None,
    ingested_at: str | None = None,
) -> dict:
    """Atomically persist an immutable source and return compact profile metadata."""
    source_id = source_document_id or new_source_document_id()
    if not _SOURCE_ID_RE.fullmatch(source_id):
        raise ValueError("Invalid source document ID")
    timestamp = ingested_at or datetime.datetime.now().isoformat(timespec="seconds")
    source_bytes = raw_bytes if raw_bytes is not None else text.encode("utf-8")
    source_dir = config.DATA_DIR / SOURCE_ROOT_NAME / source_id
    source_path = source_dir / _ARTIFACT_NAMES["source"]
    text_path = source_dir / _ARTIFACT_NAMES["text"]
    if source_path.exists() or text_path.exists():
        raise FileExistsError(f"Source document already exists: {source_id}")
    atomic_write_bytes(source_path, source_bytes)
    try:
        atomic_write_text(text_path, text)
    except BaseException:
        source_path.unlink(missing_ok=True)
        raise
    relative_root = f"{SOURCE_ROOT_NAME}/{source_id}"
    return {
        "id": source_id,
        "ingested_at": timestamp,
        "filename": Path(filename).name[:255] if filename else None,
        "media_type": media_type,
        "source": {
            "path": f"{relative_root}/{_ARTIFACT_NAMES['source']}",
            "sha256": _sha256(source_bytes),
            "length": len(source_bytes),
        },
        "text": {
            "path": f"{relative_root}/{_ARTIFACT_NAMES['text']}",
            "sha256": _sha256(text.encode("utf-8")),
            "length": len(text.encode("utf-8")),
        },
    }


def remove_source_document(source: dict) -> None:
    """Remove a newly-created source directory after a failed transaction."""
    source_id = source.get("id", "")
    if not _SOURCE_ID_RE.fullmatch(source_id):
        raise ValueError("Invalid source document ID")
    root = (config.DATA_DIR / SOURCE_ROOT_NAME).resolve()
    candidate = (root / source_id).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Source directory escapes source root") from exc
    if candidate.exists():
        shutil.rmtree(candidate)


def resolve_source_artifact(source: dict, artifact: str) -> Path:
    """Resolve indexed artifact metadata inside DATA_DIR without traversal."""
    if artifact not in _ARTIFACT_NAMES:
        raise ValueError("Unknown source artifact")
    entry = source.get(artifact)
    if not isinstance(entry, dict) or not entry.get("path"):
        raise FileNotFoundError("Source artifact is not indexed")
    root = config.DATA_DIR.resolve()
    candidate = (config.DATA_DIR / entry["path"]).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Source artifact path escapes DATA_DIR") from exc
    expected = config.DATA_DIR / SOURCE_ROOT_NAME / source.get("id", "") / _ARTIFACT_NAMES[artifact]
    if candidate != expected.resolve():
        raise ValueError("Source artifact path does not match its document ID")
    return candidate


def validate_source_artifact(source: dict, artifact: str, content: bytes) -> bool:
    """Verify served bytes still match the immutable profile index."""
    entry = source.get(artifact)
    if not isinstance(entry, dict):
        return False
    return entry.get("length") == len(content) and entry.get("sha256") == _sha256(content)


def _canonical_with_map(value: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    positions: list[int] = []
    in_space = False
    for index, raw_char in enumerate(value):
        normalized = unicodedata.normalize("NFKC", raw_char).casefold()
        for char in normalized:
            if char.isspace():
                if chars and not in_space:
                    chars.append(" ")
                    positions.append(index)
                in_space = True
            else:
                chars.append(char)
                positions.append(index)
                in_space = False
    if chars and chars[-1] == " ":
        chars.pop()
        positions.pop()
    return "".join(chars), positions


def anchor_source_quote(text: str, quote: object) -> dict:
    """Validate a model quote and return the exact source slice and offsets."""
    if not isinstance(quote, str) or not quote.strip():
        return {
            "source_quote": None,
            "evidence_status": "missing",
            "evidence_start": None,
            "evidence_end": None,
        }
    exact_start = text.find(quote)
    if exact_start >= 0:
        exact_end = exact_start + len(quote)
        return {
            "source_quote": text[exact_start:exact_end],
            "evidence_status": "verified",
            "evidence_start": exact_start,
            "evidence_end": exact_end,
        }
    canonical_text, positions = _canonical_with_map(text)
    canonical_quote, _ = _canonical_with_map(quote)
    search_from = 0
    while canonical_quote:
        canonical_start = canonical_text.find(canonical_quote, search_from)
        if canonical_start < 0:
            break
        canonical_end = canonical_start + len(canonical_quote)
        # NFKC can expand one source character into several canonical
        # characters (e.g. ½ -> 1⁄2). A match may not begin/end inside that
        # expansion or "1" and "2" would both falsely verify against "½".
        starts_on_source_boundary = (
            canonical_start == 0 or positions[canonical_start - 1] != positions[canonical_start]
        )
        ends_on_source_boundary = (
            canonical_end == len(positions)
            or positions[canonical_end - 1] != positions[canonical_end]
        )
        if starts_on_source_boundary and ends_on_source_boundary:
            start = positions[canonical_start]
            end = positions[canonical_end - 1] + 1
            source_slice = text[start:end]
            canonical_slice, _ = _canonical_with_map(source_slice)
            if canonical_slice == canonical_quote:
                return {
                    "source_quote": source_slice,
                    "evidence_status": "verified",
                    "evidence_start": start,
                    "evidence_end": end,
                }
        search_from = canonical_start + 1
    return {
        "source_quote": None,
        "evidence_status": "invalid",
        "evidence_start": None,
        "evidence_end": None,
    }


def attach_evidence(item: dict, text: str, source_document_id: str) -> dict:
    evidence = anchor_source_quote(text, item.pop("source_quote", None))
    item.update(evidence)
    item["source_document_id"] = source_document_id
    return item
