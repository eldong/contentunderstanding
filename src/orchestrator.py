"""Orchestrator that wires all pipeline components together."""

import logging

from src.classification.attachment_classifier import AttachmentClassifier
from src.classification.form_analyzer import FormAnalyzer
from src.extraction.base import Extractor
from src.ingestion.base import IngestionAdapter
from src.models import ValidationResult
from src.result_writer import ResultWriter
from src.validators.registry import ValidatorRegistry

logger = logging.getLogger(__name__)


class Orchestrator:
    """Runs the full validation pipeline across all submissions."""

    def __init__(
        self,
        ingestion: IngestionAdapter,
        extractor: Extractor,
        form_analyzer: FormAnalyzer,
        attachment_classifier: AttachmentClassifier,
        validator_registry: ValidatorRegistry,
        result_writer: ResultWriter,
    ) -> None:
        self._ingestion = ingestion
        self._extractor = extractor
        self._form_analyzer = form_analyzer
        self._attachment_classifier = attachment_classifier
        self._validator_registry = validator_registry
        self._result_writer = result_writer

    async def run(self) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        submissions = self._ingestion.list_submissions()

        for submission in submissions:
            # 1. Extract form
            try:
                form_extracted = await self._extractor.extract(
                    submission.form_path
                )
            except Exception as exc:
                logger.error(
                    "Failed to extract form %s: %s",
                    submission.form_path, exc,
                )
                error_result = ValidationResult(
                    submission_id=submission.submission_id,
                    form_name=str(submission.form_path),
                    submitted_by=submission.submitted_by,
                    status="error",
                    reasons=[f"Form extraction failed: {exc}"],
                )
                self._result_writer.write(error_result)
                results.append(error_result)
                continue

            # 2. Analyze form
            try:
                form_analysis = await self._form_analyzer.analyze(form_extracted)
            except Exception as exc:
                logger.error(
                    "Failed to analyze form %s: %s",
                    submission.form_path, exc,
                )
                error_result = ValidationResult(
                    submission_id=submission.submission_id,
                    form_name=str(submission.form_path),
                    submitted_by=submission.submitted_by,
                    status="error",
                    reasons=[f"Form analysis failed: {exc}"],
                )
                self._result_writer.write(error_result)
                results.append(error_result)
                continue

            # 3. If not relevant, skip
            if not form_analysis.is_relevant:
                error_result = ValidationResult(
                    submission_id=submission.submission_id,
                    form_name=form_analysis.form_type,
                    submitted_by=submission.submitted_by,
                    status="error",
                    reasons=[
                        f"No matching form type for '{form_analysis.form_type}'"
                    ],
                )
                self._result_writer.write(error_result)
                results.append(error_result)
                continue

            # 4. Process each attachment
            for att_path in submission.attachment_paths:
                try:
                    att_extracted = await self._extractor.extract(att_path)
                except Exception as exc:
                    logger.error(
                        "Failed to extract attachment %s: %s", att_path, exc,
                    )
                    error_result = ValidationResult(
                        submission_id=submission.submission_id,
                        form_name=form_analysis.form_type,
                        submitted_by=submission.submitted_by,
                        status="error",
                        reasons=[f"Attachment extraction failed for {att_path}: {exc}"],
                    )
                    self._result_writer.write(error_result)
                    results.append(error_result)
                    continue

                try:
                    classification = await self._attachment_classifier.classify(
                        att_extracted
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to classify attachment %s: %s", att_path, exc,
                    )
                    error_result = ValidationResult(
                        submission_id=submission.submission_id,
                        form_name=form_analysis.form_type,
                        submitted_by=submission.submitted_by,
                        status="error",
                        reasons=[f"Attachment classification failed for {att_path}: {exc}"],
                    )
                    self._result_writer.write(error_result)
                    results.append(error_result)
                    continue

                validator = self._validator_registry.get_validator(
                    classification.doc_type
                )

                if validator is None:
                    fail_result = ValidationResult(
                        submission_id=submission.submission_id,
                        form_name=form_analysis.form_type,
                        submitted_by=submission.submitted_by,
                        status="failed",
                        reasons=[
                            f"No validator registered for document type "
                            f"'{classification.doc_type}'"
                        ],
                    )
                    self._result_writer.write(fail_result)
                    results.append(fail_result)
                    continue

                try:
                    result = await validator.validate(form_analysis, att_extracted)
                except Exception as exc:
                    logger.error(
                        "Failed to validate attachment %s: %s", att_path, exc,
                    )
                    error_result = ValidationResult(
                        submission_id=submission.submission_id,
                        form_name=form_analysis.form_type,
                        submitted_by=submission.submitted_by,
                        status="error",
                        reasons=[f"Validation failed for {att_path}: {exc}"],
                    )
                    self._result_writer.write(error_result)
                    results.append(error_result)
                    continue

                result.submission_id = submission.submission_id
                result.submitted_by = submission.submitted_by
                result.form_name = form_analysis.form_type

                self._result_writer.write(result)
                results.append(result)

        return results
