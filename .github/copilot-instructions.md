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
- `src/classification/` — `DocTypeConfig` + `FormTypeConfig` + `FormAnalyzer` + `AttachmentClassifier` (GPT-4o, data-driven)
- `src/validators/` — `BaseValidator` ABC + `LLMValidator` (generic) + `ValidatorRegistry` (auto-discovers from config)
- `config/doc_types/` — YAML files defining attachment document types, indicators, and validation rules
- `config/form_types/` — YAML files defining life events, required doc types, and form-field validation rules

## Data-Driven Configuration
- **Doc types** (`config/doc_types/`): Each YAML defines an attachment document type (e.g., `marriage_certificate.yaml`)
  - Fields: `doc_type`, `display_name`, `description`, `indicators`, `validation_rules`
- **Doc type rules** (`config/form_types/`): Each YAML defines a life event / reason (e.g., `marriage.yaml`)
  - Fields: `doc_type`, `display_name`, `description`, `required_attachment_types`, `form_validation_rules`
  - Reasons with no attachments (e.g. `new_hire`) set `required_attachment_types: []`
- Adding a new type or reason = adding a YAML file. No Python code changes needed.
- `FormAnalyzer` builds its prompt dynamically from all loaded `FormTypeConfig`s
- `AttachmentClassifier` builds its prompt from all loaded `DocTypeConfig`s
- `ValidatorRegistry` auto-discovers configs and creates `LLMValidator` instances
- No per-type Python validator classes — `LLMValidator` is the single generic implementation

## Conventions
- Python 3.11+, Pydantic v2
- `pathlib.Path` throughout, no string paths
- Async for extraction and LLM calls
- Tests use `tmp_path` fixture, mock Azure services — never call Azure in automated tests
- Dependencies declared in `pyproject.toml`, no `requirements.txt`
- Install with `pip install -e ".[dev]"`

## Document Updates
- Update readme.md when adding new features or making significant changes that would a business user should know about
- Update technicaloverview.md and the docs in `docs/` for any architectural changes, new modules, or significant implementation details that developers should be aware of
- Update `copilot-instructions.md` for any changes that would impact how Copilot should generate code (e.g., new architectural patterns, coding conventions, or dependencies)