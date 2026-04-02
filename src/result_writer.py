"""Writes ValidationResult objects to a JSONL file or Azure Blob Storage."""

import io
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

from src.models import ValidationResult


class ResultWriter:
    """Appends validation results as JSON lines to an output file."""

    def __init__(self, output_path: Path) -> None:
        self._output_path = output_path

    def write(self, result: ValidationResult) -> None:
        """Append a single result as a JSON line."""
        with open(self._output_path, "a", encoding="utf-8") as f:
            f.write(result.model_dump_json() + "\n")

    def read_all(self) -> list[ValidationResult]:
        """Read all results from the JSONL file."""
        if not self._output_path.exists():
            return []
        results: list[ValidationResult] = []
        with open(self._output_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    results.append(ValidationResult.model_validate_json(line))
        return results


class BlobResultWriter(ResultWriter):
    """Writes results to a local JSONL file and uploads it to Azure Blob Storage."""

    def __init__(
        self,
        output_path: Path,
        storage_account_url: str,
        container_name: str,
    ) -> None:
        super().__init__(output_path)
        credential = DefaultAzureCredential()
        self._blob_service = BlobServiceClient(
            account_url=storage_account_url, credential=credential
        )
        self._container_name = container_name
        self._blob_name = output_path.name

    def upload(self) -> None:
        """Upload the local JSONL file to the configured blob container."""
        container_client = self._blob_service.get_container_client(
            self._container_name
        )
        with open(self._output_path, "rb") as f:
            container_client.upload_blob(
                name=self._blob_name, data=f, overwrite=True
            )
