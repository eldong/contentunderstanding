# Copilot Instructions

## Project Overview
Document Validation System POC — validates HR submissions (form PDF + supporting attachments) using Azure Document Intelligence for extraction and Azure OpenAI GPT-4o for classification/validation.

## Key Decisions
- **Authentication**: Use `DefaultAzureCredential` from `azure-identity` everywhere. No API keys.
- **Endpoints**: Two Azure AI Foundry endpoints:
  - `AZURE_AI_FOUNDRY_OPENAI_ENDPOINT` — for OpenAI/GPT-4o calls
  - `AZURE_AI_FOUNDRY_SERVICES_ENDPOINT` — for Document Intelligence and other AI services
- **Submission ID**: Folder name is the submission ID. No `submission_id` in `metadata.json`.
- **metadata.json**: Optional per submission. Provides `submitted_by` if present; defaults to `""` if absent.
- **Form detection**: File with "form" in the name. Directories without a form file are skipped.
- **Attachments**: All other PDF/DOCX/JPG/PNG files in the submission directory.

## Architecture
- `src/models.py` — 5 Pydantic v2 contracts (SubmissionWorkItem, ExtractedDoc, FormAnalysisResult, ClassifierResponse, ValidationResult)
- `src/ingestion/` — `IngestionAdapter` ABC + `LocalFolderAdapter`
- `src/extraction/` — `Extractor` ABC + `DocIntelligenceExtractor` + `MockExtractor` (sidecar JSON)
- `src/classification/` — form analyzer + attachment classifier (GPT-4o)
- `src/validators/` — registry + doc-type-specific validators

## Conventions
- Python 3.11+, Pydantic v2
- `pathlib.Path` throughout, no string paths
- Async for extraction and LLM calls
- Tests use `tmp_path` fixture, mock Azure services — never call Azure in automated tests
- Dependencies declared in `pyproject.toml`, no `requirements.txt`
- Install with `pip install -e ".[dev]"`
