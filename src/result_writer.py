"""Writes ValidationResult objects to a JSONL file."""

from pathlib import Path

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
