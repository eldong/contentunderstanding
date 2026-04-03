"""End-to-end pipeline tests with all components mocked."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.classification.attachment_classifier import AttachmentClassifier
from src.classification.doc_type_config import DocTypeConfig
from src.classification.form_type_config import FormTypeConfig
from src.classification.form_analyzer import FormAnalyzer
from src.extraction.mock_extractor import MockExtractor
from src.models import (
    ClassifierResponse,
    ExtractedDoc,
    FormAnalysisResult,
    RuleResult,
    SubmissionWorkItem,
    ValidationResult,
)
from src.orchestrator import Orchestrator
from src.result_writer import BlobResultWriter, ResultWriter
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


def _make_mock_validator(
    status: str = "passed",
    reasons: list[str] | None = None,
    rule_results: list[RuleResult] | None = None,
) -> MagicMock:
    validator = MagicMock()

    async def _validate(form_analysis, form_extracted, att_extracted):
        return ValidationResult(
            submission_id="",
            form_name="",
            submitted_by="",
            status=status,
            reasons=list(reasons) if reasons else [],
            rule_results=list(rule_results) if rule_results else [],
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
            status="passed",
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
            status="passed",
        ))
        writer.write(ValidationResult(
            submission_id="s2", form_name="f", submitted_by="u",
            status="failed", reasons=["bad"],
        ))

        lines = out.read_text().strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert "submission_id" in parsed


class TestBlobResultWriter:
    def test_upload_calls_blob_client(self, tmp_path):
        out = tmp_path / "results.jsonl"
        out.write_text('{"submission_id":"s1"}\n')

        mock_container = MagicMock()
        mock_blob_service = MagicMock()
        mock_blob_service.get_container_client.return_value = mock_container

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "src.result_writer.BlobServiceClient",
                lambda account_url, credential: mock_blob_service,
            )
            mp.setattr(
                "src.result_writer.DefaultAzureCredential",
                MagicMock,
            )
            writer = BlobResultWriter(out, "https://fake.blob.core.windows.net", "my-container")
            writer.upload()

        mock_blob_service.get_container_client.assert_called_once_with("my-container")
        mock_container.upload_blob.assert_called_once()
        call_kwargs = mock_container.upload_blob.call_args
        assert call_kwargs.kwargs["name"] == "results.jsonl"
        assert call_kwargs.kwargs["overwrite"] is True

    def test_write_then_upload(self, tmp_path):
        out = tmp_path / "results.jsonl"

        mock_container = MagicMock()
        mock_blob_service = MagicMock()
        mock_blob_service.get_container_client.return_value = mock_container

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "src.result_writer.BlobServiceClient",
                lambda account_url, credential: mock_blob_service,
            )
            mp.setattr(
                "src.result_writer.DefaultAzureCredential",
                MagicMock,
            )
            writer = BlobResultWriter(out, "https://fake.blob.core.windows.net", "results")
            writer.write(ValidationResult(
                submission_id="s1", form_name="f", submitted_by="u", status="passed",
            ))
            writer.upload()

        assert out.exists()
        mock_container.upload_blob.assert_called_once()


class TestPipeline:
    @pytest.mark.asyncio
    async def test_happy_path_pass(self, tmp_path):
        submission = _make_submission(
            attachment_paths=["samples/sub_001/cert.pdf"]
        )
        validator = _make_mock_validator(status="passed")
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
        assert results[0].status == "passed"
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
        assert results[0].status == "error"
        assert "No matching form type" in results[0].reasons[0]

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
        assert results[0].status == "failed"
        assert "No validator registered" in results[0].reasons[0]

    @pytest.mark.asyncio
    async def test_fail_validation_failure(self, tmp_path):
        submission = _make_submission(
            attachment_paths=["samples/sub_001/cert.pdf"]
        )
        validator = _make_mock_validator(
            status="failed",
            rule_results=[
                RuleResult(rule="Names must match", result="fail", detail="Names do not match"),
                RuleResult(rule="Date is recent", result="fail", detail="Date too old"),
            ],
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
        assert results[0].status == "failed"
        fails = [rr for rr in results[0].rule_results if rr.result == "fail"]
        assert len(fails) == 2
        assert "Names do not match" in fails[0].detail
        assert "Date too old" in fails[1].detail

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
        validator = _make_mock_validator(status="passed")
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
        validator = _make_mock_validator(status="passed")
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
        assert parsed["status"] == "passed"
        assert parsed["submission_id"] == "sub_001"

    @pytest.mark.asyncio
    async def test_form_extraction_error(self, tmp_path):
        submission = _make_submission(
            attachment_paths=["samples/sub_001/cert.pdf"]
        )
        extractor = AsyncMock()
        extractor.extract = AsyncMock(side_effect=Exception("corrupt file"))

        orchestrator = Orchestrator(
            ingestion=_make_mock_ingestion([submission]),
            extractor=extractor,
            form_analyzer=_make_mock_form_analyzer(RELEVANT_FORM),
            attachment_classifier=_make_mock_classifier("marriage_certificate"),
            validator_registry=_make_mock_registry(),
            result_writer=ResultWriter(tmp_path / "results.jsonl"),
        )

        results = await orchestrator.run()

        assert len(results) == 1
        assert results[0].status == "error"
        assert "Form extraction failed" in results[0].reasons[0]
        assert results[0].submission_id == "sub_001"

    @pytest.mark.asyncio
    async def test_attachment_extraction_error(self, tmp_path):
        submission = _make_submission(
            attachment_paths=["samples/sub_001/cert.pdf"]
        )
        call_count = 0

        async def _extract_side_effect(path):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return FORM_EXTRACTED  # form succeeds
            raise Exception("unsupported format")

        extractor = AsyncMock()
        extractor.extract = _extract_side_effect

        orchestrator = Orchestrator(
            ingestion=_make_mock_ingestion([submission]),
            extractor=extractor,
            form_analyzer=_make_mock_form_analyzer(RELEVANT_FORM),
            attachment_classifier=_make_mock_classifier("marriage_certificate"),
            validator_registry=_make_mock_registry({"marriage_certificate": _make_mock_validator()}),
            result_writer=ResultWriter(tmp_path / "results.jsonl"),
        )

        results = await orchestrator.run()

        assert len(results) == 1
        assert results[0].status == "error"
        assert "Attachment extraction failed" in results[0].reasons[0]

    @pytest.mark.asyncio
    async def test_error_does_not_stop_other_submissions(self, tmp_path):
        submissions = [
            _make_submission(submission_id="bad", form_path="samples/bad/form.pdf"),
            _make_submission(
                submission_id="good",
                form_path="samples/good/form.pdf",
                attachment_paths=["samples/good/cert.pdf"],
            ),
        ]
        call_count = 0

        async def _extract_side_effect(path):
            nonlocal call_count
            call_count += 1
            if "bad" in str(path):
                raise Exception("corrupt")
            return FORM_EXTRACTED if "form" in str(path).lower() else ATTACHMENT_EXTRACTED

        extractor = AsyncMock()
        extractor.extract = _extract_side_effect

        validator = _make_mock_validator(status="passed")
        registry = _make_mock_registry({"marriage_certificate": validator})

        orchestrator = Orchestrator(
            ingestion=_make_mock_ingestion(submissions),
            extractor=extractor,
            form_analyzer=_make_mock_form_analyzer(RELEVANT_FORM),
            attachment_classifier=_make_mock_classifier("marriage_certificate"),
            validator_registry=registry,
            result_writer=ResultWriter(tmp_path / "results.jsonl"),
        )

        results = await orchestrator.run()

        assert len(results) == 2
        assert results[0].status == "error"
        assert results[0].submission_id == "bad"
        assert results[1].status == "passed"
        assert results[1].submission_id == "good"
