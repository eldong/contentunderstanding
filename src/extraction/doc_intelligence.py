"""Azure Document Intelligence extractor using DefaultAzureCredential."""

import asyncio
import io
import logging
from pathlib import Path

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.identity import DefaultAzureCredential

from src.extraction.base import Extractor
from src.models import ExtractedDoc

logger = logging.getLogger(__name__)


class DocIntelligenceExtractor(Extractor):
    """Extracts text and fields from documents using Azure Document Intelligence."""

    def __init__(self, endpoint: str) -> None:
        self._credential = DefaultAzureCredential()
        self._client = DocumentIntelligenceClient(
            endpoint=endpoint, credential=self._credential
        )

    async def extract(self, file_path: Path) -> ExtractedDoc:
        file_bytes = file_path.read_bytes()
        result = await asyncio.to_thread(
            self._analyze, file_bytes, str(file_path)
        )
        return result

    def _analyze(self, file_bytes: bytes, source_path: str) -> ExtractedDoc:
        poller = self._client.begin_analyze_document(
            "prebuilt-read",
            body=io.BytesIO(file_bytes),
        )
        result = poller.result()

        # Extract text from pages
        pages_text: list[str] = []
        confidences: list[float] = []
        for page in result.pages or []:
            for line in page.lines or []:
                pages_text.append(line.content)
            if page.words:
                confidences.extend(w.confidence for w in page.words if w.confidence)

        full_text = "\n".join(pages_text)

        # Extract key-value pairs if available
        kv_pairs: dict[str, str] = {}
        for kv in result.key_value_pairs or []:
            if kv.key and kv.key.content and kv.value and kv.value.content:
                kv_pairs[kv.key.content] = kv.value.content

        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        return ExtractedDoc(
            source_path=source_path,
            content=full_text,
            fields=kv_pairs,
            confidence=avg_confidence,
        )
