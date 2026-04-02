"""Tests for Pydantic data contracts."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.models import (
    ClassifierResponse,
    ExtractedDoc,
    FormAnalysisResult,
    SubmissionWorkItem,
    ValidationResult,
)


class TestSubmissionWorkItem:
    def test_roundtrip(self):
        item = SubmissionWorkItem(
            submission_id="SUB-001",
            form_path=Path("samples/submission_001/form.pdf"),
            attachment_paths=[Path("samples/submission_001/attachment.pdf")],
            submitted_by="Jane Employee",
        )
        data = item.model_dump_json()
        restored = SubmissionWorkItem.model_validate_json(data)
        assert restored.submission_id == "SUB-001"
        assert restored.submitted_by == "Jane Employee"
        assert len(restored.attachment_paths) == 1

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            SubmissionWorkItem(form_path=Path("x.pdf"), submitted_by="A")  # type: ignore[call-arg]

    def test_defaults(self):
        item = SubmissionWorkItem(
            submission_id="SUB-002",
            form_path=Path("form.pdf"),
            submitted_by="Bob",
        )
        assert item.attachment_paths == []
        assert item.metadata == {}


class TestExtractedDoc:
    def test_roundtrip(self):
        doc = ExtractedDoc(
            source_path="form.pdf",
            content="Some extracted text",
            fields={"name": "John"},
            confidence=0.95,
        )
        data = doc.model_dump_json()
        restored = ExtractedDoc.model_validate_json(data)
        assert restored.content == "Some extracted text"
        assert restored.fields["name"] == "John"
        assert restored.confidence == 0.95

    def test_defaults(self):
        doc = ExtractedDoc(source_path="x.pdf", content="text")
        assert doc.fields == {}
        assert doc.confidence == 0.0


class TestFormAnalysisResult:
    def test_relevant_form(self):
        result = FormAnalysisResult(
            form_type="add_beneficiary",
            reason="marriage",
            employee_first_name="Jane",
            employee_last_name="Doe",
            beneficiary_first_name="John",
            is_relevant=True,
        )
        data = result.model_dump_json()
        restored = FormAnalysisResult.model_validate_json(data)
        assert restored.is_relevant is True
        assert restored.reason == "marriage"

    def test_irrelevant_form(self):
        result = FormAnalysisResult(form_type="unknown", is_relevant=False)
        assert result.reason is None
        assert result.employee_first_name is None

    def test_json_schema_generation(self):
        schema = FormAnalysisResult.model_json_schema()
        assert "form_type" in schema["properties"]
        assert "is_relevant" in schema["properties"]


class TestClassifierResponse:
    def test_roundtrip(self):
        resp = ClassifierResponse(
            doc_type="marriage_certificate",
            confidence=0.92,
            reasoning="Document contains marriage-related language",
        )
        data = resp.model_dump_json()
        restored = ClassifierResponse.model_validate_json(data)
        assert restored.doc_type == "marriage_certificate"
        assert restored.confidence == 0.92


class TestValidationResult:
    def test_pass_result(self):
        result = ValidationResult(
            submission_id="SUB-001",
            form_name="Add Beneficiary",
            submitted_by="Jane",
            status="passed",
        )
        assert result.status == "passed"
        assert result.reasons == []
        assert result.timestamp  # auto-generated

    def test_fail_result(self):
        result = ValidationResult(
            submission_id="SUB-001",
            form_name="Add Beneficiary",
            submitted_by="Jane",
            status="failed",
            reasons=["Employee name not found", "Date too old"],
        )
        assert len(result.reasons) == 2

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            ValidationResult(
                submission_id="SUB-001",
                form_name="X",
                submitted_by="Y",
                status="invalid",  # type: ignore[arg-type]
            )

    def test_roundtrip(self):
        result = ValidationResult(
            submission_id="SUB-001",
            form_name="Add Beneficiary",
            submitted_by="Jane",
            status="error",
            reasons=["Form not relevant"],
        )
        data = result.model_dump_json()
        restored = ValidationResult.model_validate_json(data)
        assert restored.status == "error"
        assert restored.reasons == ["Form not relevant"]
