"""Mock extractor that reads canned JSON sidecar files."""

import logging
from pathlib import Path

from src.extraction.base import Extractor
from src.models import ExtractedDoc

logger = logging.getLogger(__name__)


class MockExtractor(Extractor):
    """Returns pre-built ExtractedDoc from .extracted.json sidecar files."""

    async def extract(self, file_path: Path) -> ExtractedDoc:
        sidecar = Path(f"{file_path}.extracted.json")
        if sidecar.exists():
            return ExtractedDoc.model_validate_json(sidecar.read_text(encoding="utf-8"))
        logger.warning("No sidecar found for %s — returning empty extraction", file_path)
        return ExtractedDoc(
            source_path=str(file_path), content="", fields={}, confidence=0.0
        )
