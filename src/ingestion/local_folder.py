"""Local-folder ingestion adapter."""

import json
import logging
from pathlib import Path

from src.ingestion.base import IngestionAdapter
from src.models import SubmissionWorkItem

logger = logging.getLogger(__name__)

ATTACHMENT_EXTENSIONS = {".pdf", ".docx", ".jpg", ".png"}


class LocalFolderAdapter(IngestionAdapter):
    """Reads submission directories from a local folder."""

    def __init__(self, root_dir: Path | str) -> None:
        self.root_dir = Path(root_dir).resolve()

    def list_submissions(self) -> list[SubmissionWorkItem]:
        submissions: list[SubmissionWorkItem] = []
        for entry in sorted(self.root_dir.iterdir()):
            if not entry.is_dir():
                continue
            metadata_file = entry / "metadata.json"
            if not metadata_file.exists():
                logger.warning("Skipping %s — no metadata.json", entry.name)
                continue
            with metadata_file.open(encoding="utf-8") as f:
                meta = json.load(f)

            # Find the form file (filename contains "form")
            form_path: Path | None = None
            attachment_paths: list[Path] = []
            for file in sorted(entry.iterdir()):
                if not file.is_file():
                    continue
                if file.suffix.lower() not in ATTACHMENT_EXTENSIONS:
                    continue
                if "form" in file.stem.lower():
                    form_path = file.resolve()
                else:
                    attachment_paths.append(file.resolve())

            if form_path is None:
                logger.warning("Skipping %s — no form file found", entry.name)
                continue

            submissions.append(
                SubmissionWorkItem(
                    submission_id=meta["submission_id"],
                    submitted_by=meta["submitted_by"],
                    form_path=form_path,
                    attachment_paths=attachment_paths,
                    metadata=meta,
                )
            )
        return submissions

    def download_submission(self, submission_id: str) -> SubmissionWorkItem:
        for item in self.list_submissions():
            if item.submission_id == submission_id:
                return item
        raise KeyError(f"Submission {submission_id!r} not found")
