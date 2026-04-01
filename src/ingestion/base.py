"""Abstract base class for ingestion adapters."""

from abc import ABC, abstractmethod

from src.models import SubmissionWorkItem


class IngestionAdapter(ABC):
    """Interface for reading submission directories."""

    @abstractmethod
    def list_submissions(self) -> list[SubmissionWorkItem]:
        """Return all available submissions."""

    @abstractmethod
    def download_submission(self, submission_id: str) -> SubmissionWorkItem:
        """Download / retrieve a single submission by ID."""
