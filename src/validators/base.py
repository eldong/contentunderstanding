"""Abstract base class for document validators."""

from abc import ABC, abstractmethod

from src.models import ExtractedDoc, FormAnalysisResult, ValidationResult


class BaseValidator(ABC):
    """Base interface for all document validators."""

    @abstractmethod
    async def validate(
        self,
        form_analysis: FormAnalysisResult,
        attachment_extracted: ExtractedDoc,
    ) -> ValidationResult: ...
