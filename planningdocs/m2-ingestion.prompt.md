You are implementing Milestone 2 of a Document Validation System POC.

## Context
This is a Python project at `c:\work\opm\contentunderstanding`. See `planningdocs/plan.md` for full architecture. Milestone 1 (scaffold + Pydantic contracts) is complete — `src/models.py` has all 5 data models.

## Goal
Build the local folder ingestion layer that reads submission directories from a `samples/` folder and produces `SubmissionWorkItem` objects. Also define the abstract `IngestionAdapter` interface so a SharePoint adapter can be swapped in later.

## Files to Create

### `src/ingestion/base.py`
- Define `IngestionAdapter` as an ABC (abstract base class)
- Methods:
  - `list_submissions() -> list[SubmissionWorkItem]` — abstract, returns all available submissions
  - `download_submission(submission_id: str) -> SubmissionWorkItem` — abstract, for future SharePoint use
- Import `SubmissionWorkItem` from `src.models`

### `src/ingestion/local_folder.py`
- `LocalFolderAdapter(IngestionAdapter)` — constructor takes `root_dir: Path`
- `list_submissions()` implementation:
  - Scans `root_dir` for subdirectories (each subdirectory = one submission)
  - Each subdirectory must contain a `metadata.json` with `{"submission_id": "...", "submitted_by": "..."}`
  - Finds the form file: look for a file with "form" in the name (e.g., `form.pdf`)
  - Finds attachment files: all other PDF/DOCX/JPG/PNG files in the directory
  - Returns a list of `SubmissionWorkItem` with absolute paths
- `download_submission()` — just return the matching `SubmissionWorkItem` from `list_submissions()` (local files are already "downloaded")
- Skip subdirectories that don't have a `metadata.json` (log a warning)

### `samples/submission_001/metadata.json`
```json
{
  "submission_id": "SUB-001",
  "submitted_by": "Jane Employee"
}
```

### `samples/submission_001/` — placeholder files
- Create a minimal `form.pdf` placeholder (can be an empty file or minimal valid PDF for now)
- Create a minimal `attachment.pdf` placeholder

### `tests/test_ingestion.py`
- Test `LocalFolderAdapter` using a temp directory (`tmp_path` fixture):
  - Create a sample submission directory structure with `metadata.json`, `form.pdf`, `attachment.pdf`
  - Assert `list_submissions()` returns correct number of submissions
  - Assert `submission_id`, `submitted_by`, `form_path`, `attachment_paths` are correct
  - Assert directories without `metadata.json` are skipped
  - Test with multiple submissions
- Test `download_submission()` returns the correct item

## Acceptance Criteria
- `LocalFolderAdapter("samples").list_submissions()` returns a list with `SubmissionWorkItem(submission_id="SUB-001", submitted_by="Jane Employee", ...)`
- `form_path` points to the actual form file; `attachment_paths` contains the attachment file(s)
- `pytest tests/test_ingestion.py` — all tests pass
- Manual smoke test: `python -c "from src.ingestion.local_folder import LocalFolderAdapter; print(LocalFolderAdapter('samples').list_submissions())"`

## Constraints
- Do not import or depend on extraction, classification, or validator modules
- `IngestionAdapter` ABC is the future SharePoint interface — keep it clean and minimal
- Do not over-engineer; no async needed for local file scanning
- Use `pathlib.Path` throughout, not string paths
