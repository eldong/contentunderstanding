"""Pydantic v2 contracts for the Document Validation System."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class SubmissionWorkItem(BaseModel):
    """A single submission to be validated (form + attachments)."""

    submission_id: str
    form_path: Path
    attachment_paths: list[Path] = Field(default_factory=list)
    submitted_by: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExtractedDoc(BaseModel):
    """Normalized output from document extraction (OCR / Doc Intelligence)."""

    source_path: str
    content: str
    fields: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0


class FormAnalysisResult(BaseModel):
    """LLM-produced analysis of the HR form."""

    form_type: str  # e.g. "add_beneficiary", "unknown"
    reason: str | None = None  # e.g. "marriage", "birth", "adoption"
    employee_first_name: str | None = None
    employee_last_name: str | None = None
    beneficiary_first_name: str | None = None
    application_date: str | None = None  # e.g. "2026-01-25" (YYYY-MM-DD)
    is_relevant: bool = False


class ClassifierResponse(BaseModel):
    """LLM-produced classification of an attachment document."""

    doc_type: str  # e.g. "marriage_certificate", "unknown"
    confidence: float = 0.0
    reasoning: str = ""


class ValidationResult(BaseModel):
    """Final validation outcome for a submission."""

    submission_id: str
    form_name: str
    submitted_by: str
    doc_type: str = ""
    status: Literal["passed", "failed", "error"]
    reasons: list[str] = Field(default_factory=list)
    passed_reasons: list[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
