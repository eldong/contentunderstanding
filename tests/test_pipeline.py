"""End-to-end pipeline tests with all components mocked."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.classification.attachment_classifier import AttachmentClassifier
from src.classification.doc_type_config import DocTypeConfig
from src.classification.doc_type_rule_config import DocTypeRuleConfig
from src.classification.form_analyzer import FormAnalyzer
from src.extraction.mock_extractor import MockExtractor
from src.models import (
    ClassifierResponse,
    ExtractedDoc,
    FormAnalysisResult,
    SubmissionWorkItem,
    ValidationResult,
)
from src.orchestrator import Orchestrator
from src.result_writer import ResultWriter
from src.validators.base import BaseValidator
from src.validators.registry import ValidatorRegistry


# --- Fixtures ---

def _make_mock_ingestion(submissions: list[SubmissionWorkItem]):
    ingestion = MagicMock()
    ingestion.list_submissions.return_value = submissions
    return ingestion


def _make_submission(
    submission_id: str = "sub_001",
    form_path: str = "samples/sub_001/form.pdf",
    attachment_paths: list[str] | None = None,
    submitted_by: str = "John Doe",
) -> SubmissionWorkItem:
    return SubmissionWorkItem(
        submission_id=submission_id,
        form_path=Path(form_path),
        attachment_paths=[Path(p) for p in (attachment_paths or [])],
        submitted_by=submitted_by,
    )


FORM_EXTRACTED = ExtractedDoc(
    source_path="form.pdf",
    content="HEALTH BENEFITS FORM\nAction: Add Beneficiary\nReason: Marriage\nEmployee: Jane Smith\nBeneficiary: Michael Johnson",
    fields={},
    confidence=0.95,
)

ATTACHMENT_EXTRACTED = ExtractedDoc(
    source_path="marriage_cert.pdf",
    content="CERTIFICATE OF MARRIAGE\nJane Smith and Michael Johnson\nDate: 2026-03-01",
    fields={},
    confidence=0.93,
)

RELEVANT_FORM = FormAnalysisResult(
    form_type="add_beneficiary",
    reason="marriage",
    employee_first_name="Jane",
    employee_last_name="Smith",
    beneficiary_first_name="Michael",
    is_relevant=True,
)

IRRELEVANT_FORM = FormAnalysisResult(
    form_type="unknown",
    reason=None,
    is_relevant=False,
)


def _make_mock_extractor(
    form_extracted: ExtractedDoc = FORM_EXTRACTED,
    attachment_extracted: ExtractedDoc = ATTACHMENT_EXTRACTED,
) -> AsyncMock:
    extractor = AsyncMock()
    async def _extract(path: Path) -> ExtractedDoc:
        if "form" in str(path).lower():
            return form_extracted
        return attachment_extracted
    extractor.extract = _extract
    return extractor


def _make_mock_form_analyzer(result: FormAnalysisResult) -> MagicMock:
    analyzer = MagicMock()
    analyzer.analyze = AsyncMock(return_value=result)
    return analyzer


def _make_mock_classifier(doc_type: str, confidence: float = 0.95) -> MagicMock:
    classifier = MagicMock()
    classifier.classify = AsyncMock(
        return_value=ClassifierResponse(
            doc_type=doc_type, confidence=confidence, reasoning="test"
        )
    )
    return classifier


def _make_mock_validator(status: str = "pass", reasons: list[str] | None = None) -> MagicMock:
    validator = MagicMock()

    async def _validate(form_analysis, att_extracted):
        return ValidationResult(
            submission_id="",
            form_name="",
            submitted_by="",
            status=status,
            reasons=list(reasons) if reasons else [],
        )

    validator.validate = _validate
    return validator


def _make_mock_registry(validators: dict[str, MagicMock] | None = None) -> MagicMock:
    registry = MagicMock()
    validators = validators or {}
    registry.get_validator = MagicMock(side_effect=lambda dt: validators.get(dt))
    registry.list_doc_types = MagicMock(return_value=sorted(validators.keys()))
    return registry


class TestResultWriter:
    def test_write_and_read(self, tmp_path):
        writer = ResultWriter(tmp_path / "results.jsonl")
        result = ValidationResult(
            submission_id="sub_001",
            form_name="add_beneficiary",
            submitted_by="Jane",
            status="pass",
            reasons=[],
        )
        writer.write(result)
        writer.write(result)

        all_results = writer.read_all()
        assert len(all_results) == 2
        assert all_results[0].submission_id == "sub_001"

    def test_read_empty_file(self, tmp_path):
        writer = ResultWriter(tmp_path / "results.jsonl")
        assert writer.read_all() == []

    def test_jsonl_format(self, tmp_path):
        out = tmp_path / "results.jsonl"
        writer = ResultWriter(out)
        writer.write(ValidationResult(
            submission_id="s1", form_name="f", submitted_by="u",
            status="pass",
        ))
        writer.write(ValidationResult(
            submission_id="s2", form_name="f", submitted_by="u",
            status="fail", reasons=["bad"],
        ))

        lines = out.read_text().strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert "submission_id" in parsed


class TestPipeline:
    @pytest.mark.asyncio
    async def test_happy_path_pass(self, tmp_path):
        submission = _make_submission(
            attachment_paths=["samples/sub_001/cert.pdf"]
        )
        validator = _make_mock_validator(status="pass")
        registry = _make_mock_registry({"marriage_certificate": validator})

        orchestrator = Orchestrator(
            ingestion=_make_mock_ingestion([submission]),
            extractor=_make_mock_extractor(),
            form_analyzer=_make_mock_form_analyzer(RELEVANT_FORM),
            attachment_classifier=_make_mock_classifier("marriage_certificate"),
            validator_registry=registry,
            result_writer=ResultWriter(tmp_path / "results.jsonl"),
        )

        results = await orchestrator.run()

        assert len(results) == 1
        assert results[0].status == "pass"
        assert results[0].submission_id == "sub_001"
        assert results[0].submitted_by == "John Doe"

    @pytest.mark.asyncio
    async def test_skip_irrelevant_form(self, tmp_path):
        submission = _make_submission(
            attachment_paths=["samples/sub_001/cert.pdf"]
        )

        orchestrator = Orchestrator(
            ingestion=_make_mock_ingestion([submission]),
            extractor=_make_mock_extractor(),
            form_analyzer=_make_mock_form_analyzer(IRRELEVANT_FORM),
            attachment_classifier=_make_mock_classifier("marriage_certificate"),
            validator_registry=_make_mock_registry(),
            result_writer=ResultWriter(tmp_path / "results.jsonl"),
        )

        results = await orchestrator.run()

        assert len(results) == 1
        assert results[0].status == "skip"
        assert "not relevant" in results[0].reasons[0]

    @pytest.mark.asyncio
    async def test_fail_no_validator(self, tmp_path):
        submission = _make_submission(
            attachment_paths=["samples/sub_001/cert.pdf"]
        )

        orchestrator = Orchestrator(
            ingestion=_make_mock_ingestion([submission]),
            extractor=_make_mock_extractor(),
            form_analyzer=_make_mock_form_analyzer(RELEVANT_FORM),
            attachment_classifier=_make_mock_classifier("unknown"),
            validator_registry=_make_mock_registry(),  # empty registry
            result_writer=ResultWriter(tmp_path / "results.jsonl"),
        )

        results = await orchestrator.run()

        assert len(results) == 1
        assert results[0].status == "fail"
        assert "No validator registered" in results[0].reasons[0]

    @pytest.mark.asyncio
    async def test_fail_validation_failure(self, tmp_path):
        submission = _make_submission(
            attachment_paths=["samples/sub_001/cert.pdf"]
        )
        validator = _make_mock_validator(
            status="fail", reasons=["Names do not match", "Date too old"]
        )
        registry = _make_mock_registry({"marriage_certificate": validator})

        orchestrator = Orchestrator(
            ingestion=_make_mock_ingestion([submission]),
            extractor=_make_mock_extractor(),
            form_analyzer=_make_mock_form_analyzer(RELEVANT_FORM),
            attachment_classifier=_make_mock_classifier("marriage_certificate"),
            validator_registry=registry,
            result_writer=ResultWriter(tmp_path / "results.jsonl"),
        )

        results = await orchestrator.run()

        assert len(results) == 1
        assert results[0].status == "fail"
        assert "Names do not match" in results[0].reasons
        assert "Date too old" in results[0].reasons

    @pytest.mark.asyncio
    async def test_multiple_submissions(self, tmp_path):
        submissions = [
            _make_submission(
                submission_id="sub_001",
                form_path="samples/sub_001/form.pdf",
                attachment_paths=["samples/sub_001/cert.pdf"],
            ),
            _make_submission(
                submission_id="sub_002",
                form_path="samples/sub_002/form.pdf",
                attachment_paths=["samples/sub_002/cert.pdf"],
                submitted_by="Alice",
            ),
        ]
        validator = _make_mock_validator(status="pass")
        registry = _make_mock_registry({"marriage_certificate": validator})

        out = tmp_path / "results.jsonl"
        orchestrator = Orchestrator(
            ingestion=_make_mock_ingestion(submissions),
            extractor=_make_mock_extractor(),
            form_analyzer=_make_mock_form_analyzer(RELEVANT_FORM),
            attachment_classifier=_make_mock_classifier("marriage_certificate"),
            validator_registry=registry,
            result_writer=ResultWriter(out),
        )

        results = await orchestrator.run()

        assert len(results) == 2
        assert results[0].submission_id == "sub_001"
        assert results[1].submission_id == "sub_002"

        # Verify JSONL file
        writer = ResultWriter(out)
        saved = writer.read_all()
        assert len(saved) == 2

    @pytest.mark.asyncio
    async def test_submission_no_attachments(self, tmp_path):
        submission = _make_submission(attachment_paths=[])

        orchestrator = Orchestrator(
            ingestion=_make_mock_ingestion([submission]),
            extractor=_make_mock_extractor(),
            form_analyzer=_make_mock_form_analyzer(RELEVANT_FORM),
            attachment_classifier=_make_mock_classifier("marriage_certificate"),
            validator_registry=_make_mock_registry(),
            result_writer=ResultWriter(tmp_path / "results.jsonl"),
        )

        results = await orchestrator.run()

        # Relevant form but no attachments → no results
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_results_written_to_jsonl(self, tmp_path):
        submission = _make_submission(
            attachment_paths=["samples/sub_001/cert.pdf"]
        )
        validator = _make_mock_validator(status="pass")
        registry = _make_mock_registry({"marriage_certificate": validator})

        out = tmp_path / "results.jsonl"
        orchestrator = Orchestrator(
            ingestion=_make_mock_ingestion([submission]),
            extractor=_make_mock_extractor(),
            form_analyzer=_make_mock_form_analyzer(RELEVANT_FORM),
            attachment_classifier=_make_mock_classifier("marriage_certificate"),
            validator_registry=registry,
            result_writer=ResultWriter(out),
        )

        await orchestrator.run()

        lines = out.read_text().strip().split("\n")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["status"] == "pass"
        assert parsed["submission_id"] == "sub_001"
