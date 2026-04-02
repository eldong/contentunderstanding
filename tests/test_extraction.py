"""Tests for the extraction layer."""

import json

import pytest

from src.extraction.mock_extractor import MockExtractor


class TestMockExtractor:
    @pytest.mark.asyncio
    async def test_extract_with_sidecar(self, tmp_path):
        doc = tmp_path / "form.pdf"
        doc.write_bytes(b"%PDF-1.4 placeholder")
        sidecar = tmp_path / "form.pdf.mock.extracted.json"
        sidecar.write_text(
            json.dumps(
                {
                    "source_path": "form.pdf",
                    "content": "Hello world",
                    "fields": {"name": "Alice"},
                    "confidence": 0.99,
                }
            ),
            encoding="utf-8",
        )

        extractor = MockExtractor()
        result = await extractor.extract(doc)

        assert result.content == "Hello world"
        assert result.fields == {"name": "Alice"}
        assert result.confidence == 0.99
        assert result.source_path == "form.pdf"

    @pytest.mark.asyncio
    async def test_extract_missing_sidecar(self, tmp_path):
        doc = tmp_path / "nodata.pdf"
        doc.write_bytes(b"%PDF-1.4 placeholder")

        extractor = MockExtractor()
        result = await extractor.extract(doc)

        assert result.content == ""
        assert result.fields == {}
        assert result.confidence == 0.0
        assert result.source_path == str(doc)

    @pytest.mark.asyncio
    async def test_extract_sample_form_sidecar(self):
        """Smoke test against the real sample sidecar files."""
        from pathlib import Path

        form_path = Path("samples/submission_001/form.pdf")
        if not form_path.exists():
            pytest.skip("Sample files not present")

        extractor = MockExtractor()
        result = await extractor.extract(form_path)

        assert "BENEFICIARY" in result.content
        assert result.confidence > 0.0
        assert result.fields.get("action") == "Add Beneficiary"


class TestDocIntelligenceExtractor:
    def test_instantiation(self):
        """Verify the extractor can be constructed with a fake endpoint."""
        from unittest.mock import patch

        with patch("src.extraction.doc_intelligence.DocumentIntelligenceClient"):
            with patch("src.extraction.doc_intelligence.DefaultAzureCredential"):
                from src.extraction.doc_intelligence import DocIntelligenceExtractor

                extractor = DocIntelligenceExtractor(
                    endpoint="https://fake.cognitiveservices.azure.com/"
                )
                assert extractor is not None
