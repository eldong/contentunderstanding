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
            form_extracted = await self._extractor.extract(submission.form_path)

            # 2. Analyze form
            form_analysis = await self._form_analyzer.analyze(form_extracted)

            # 3. If not relevant, skip
            if not form_analysis.is_relevant:
                skip_result = ValidationResult(
                    submission_id=submission.submission_id,
                    form_name=form_analysis.form_type,
                    submitted_by=submission.submitted_by,
                    status="skip",
                    reasons=[
                        f"Form type '{form_analysis.form_type}' is not relevant "
                        f"or no reason selected"
                    ],
                )
                self._result_writer.write(skip_result)
                results.append(skip_result)
                continue

            # 4. Process each attachment
            for att_path in submission.attachment_paths:
                att_extracted = await self._extractor.extract(att_path)

                classification = await self._attachment_classifier.classify(
                    att_extracted
                )

                validator = self._validator_registry.get_validator(
                    classification.doc_type
                )

                if validator is None:
                    fail_result = ValidationResult(
                        submission_id=submission.submission_id,
                        form_name=form_analysis.form_type,
                        submitted_by=submission.submitted_by,
                        status="fail",
                        reasons=[
                            f"No validator registered for document type "
                            f"'{classification.doc_type}'"
                        ],
                    )
                    self._result_writer.write(fail_result)
                    results.append(fail_result)
                    continue

                result = await validator.validate(form_analysis, att_extracted)
                result.submission_id = submission.submission_id
                result.submitted_by = submission.submitted_by
                result.form_name = form_analysis.form_type

                self._result_writer.write(result)
                results.append(result)

        return results
