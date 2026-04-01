"""Abstract base class for document extractors."""

from abc import ABC, abstractmethod
from pathlib import Path

from src.models import ExtractedDoc


class Extractor(ABC):
    """Interface for extracting text and fields from documents."""

    @abstractmethod
    async def extract(self, file_path: Path) -> ExtractedDoc:
        """Extract text content and fields from a document file."""
