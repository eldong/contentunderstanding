# Plan: Document Validation System (Local-First POC)

## Architecture Summary

A Python CLI pipeline reads submissions from a local `samples/` folder (swappable to SharePoint later via adapter interface). Each submission contains a form PDF and one or more attachments. The **Orchestrator** drives a linear pipeline: **Ingestion → Extraction → Form Analysis → Attachment Classification → Validation → Result Writing**. The orchestrator is doc-type-agnostic — it delegates to a **Form Analyzer** (LLM) to understand the form, an **Attachment Classifier** (LLM) to determine attachment doc-type, and a **Validator Registry** (YAML config) to route to the correct **Validator Agent**. For this POC the only validator is `MarriageCertificateAgent`. Adding a new document type means: (1) add a validator class inheriting `BaseValidator`, (2) add a registry entry. No orchestrator changes required.

**Tech stack**: Python 3.11+, Pydantic v2 (strict JSON contracts), Azure Document Intelligence (extraction), Azure OpenAI GPT-4o (classification/validation prompts), pytest.

---

## Repo Structure

```
contentunderstanding/
├── pyproject.toml
├── .env.example                    # AZURE_OPENAI_*, AZURE_DOC_INTEL_*
├── config/
│   └── registry.yaml              # doc_type → validator class mapping
├── samples/
│   └── submission_001/
│       ├── form.pdf
│       ├── attachment.pdf
│       └── metadata.json          # { submitted_by, submission_id }
├── src/
│   ├── __init__.py
│   ├── models.py                  # All Pydantic contracts
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── base.py                # IngestionAdapter ABC
│   │   └── local_folder.py        # LocalFolderAdapter
│   ├── extraction/
│   │   ├── __init__.py
│   │   ├── base.py                # Extractor ABC
│   │   ├── doc_intelligence.py    # Azure Doc Intelligence impl
│   │   └── mock_extractor.py      # Returns canned text (offline dev)
│   ├── classification/
│   │   ├── __init__.py
│   │   ├── form_analyzer.py       # LLM: form_type + reason + names
│   │   └── attachment_classifier.py  # LLM: doc_type
│   ├── validators/
│   │   ├── __init__.py
│   │   ├── base.py                # BaseValidator ABC
│   │   ├── registry.py            # ValidatorRegistry (loads YAML)
│   │   └── marriage_certificate.py  # MarriageCertificateAgent
│   ├── orchestrator.py            # Pipeline: doc-type-agnostic
│   └── result_writer.py           # JSONL writer
├── tests/
│   ├── conftest.py                # Shared fixtures, mock factories
│   ├── test_models.py
│   ├── test_ingestion.py
│   ├── test_classification.py
│   ├── test_validators.py
│   └── test_pipeline.py
└── main.py                        # CLI entry point
```

---

## Contracts (Pydantic v2 models in `src/models.py`)

### SubmissionWorkItem
- `submission_id: str`
- `form_path: Path`
- `attachment_paths: list[Path]`
- `submitted_by: str`
- `metadata: dict[str, Any] = {}`

### ExtractedDoc
- `source_path: str`
- `content: str` — full extracted text
- `fields: dict[str, Any] = {}` — structured key-value pairs (from form fields)
- `confidence: float = 0.0`

### FormAnalysisResult
- `form_type: str` — e.g. `"add_beneficiary"`, `"unknown"`
- `reason: str | None` — e.g. `"marriage"`, `"birth"`, `"adoption"`
- `employee_first_name: str | None`
- `employee_last_name: str | None`
- `beneficiary_first_name: str | None`
- `is_relevant: bool` — True if form_type is recognized AND a reason is selected

### ClassifierResponse
- `doc_type: str` — e.g. `"marriage_certificate"`, `"unknown"`
- `confidence: float`
- `reasoning: str`

### ValidationResult
- `submission_id: str`
- `form_name: str`
- `submitted_by: str`
- `status: Literal["pass", "fail", "skip"]`
- `reasons: list[str]`
- `timestamp: str` — ISO 8601

---

## Milestones

### M1: Project Scaffold + Contracts
**Goal**: Runnable Python project with all Pydantic data models.

**Files to create**:
- `pyproject.toml` — project metadata, dependencies: `pydantic>=2.0`, `python-dotenv`, `pytest`
- `.env.example` — placeholder keys for Azure OpenAI and Doc Intelligence
- `src/__init__.py`
- `src/models.py` — all 5 Pydantic models above

**Acceptance criteria**: `python -c "from src.models import SubmissionWorkItem, ExtractedDoc, FormAnalysisResult, ClassifierResponse, ValidationResult"` succeeds. Models serialize to/from JSON correctly.

**Test**: `pytest tests/test_models.py` — tests round-trip JSON serialization, validation of required fields, rejection of bad data.

---

### M2: Local Ingestion + Sample Data
**Goal**: Read submissions from a local folder into `SubmissionWorkItem` objects.

**Files to create**:
- `src/ingestion/base.py` — `IngestionAdapter` ABC with method `list_submissions() -> list[SubmissionWorkItem]`
- `src/ingestion/local_folder.py` — `LocalFolderAdapter(root_dir: Path)` scans subdirectories, reads `metadata.json`, builds `SubmissionWorkItem`
- `samples/submission_001/metadata.json` — `{"submission_id": "SUB-001", "submitted_by": "Jane Employee"}`
- `samples/submission_001/form.pdf` — placeholder (any small PDF)
- `samples/submission_001/attachment.pdf` — placeholder

**Acceptance criteria**: `LocalFolderAdapter("samples").list_submissions()` returns a list of `SubmissionWorkItem` with correct paths and metadata.

**Test**: `pytest tests/test_ingestion.py` — creates temp dir with sample structure, asserts correct parsing. Also a manual smoke test: `python -c "from src.ingestion.local_folder import LocalFolderAdapter; print(LocalFolderAdapter('samples').list_submissions())"`.

**Stub note**: `IngestionAdapter` ABC is the future SharePoint adapter interface. Its contract: `list_submissions() -> list[SubmissionWorkItem]`, `download_submission(id) -> SubmissionWorkItem`. A `SharePointAdapter` stub file can be added later with `raise NotImplementedError`.

---

### M3: Document Extraction Layer
**Goal**: Extract text/fields from PDFs and images via Azure Document Intelligence, with a mock fallback for offline development.

**Files to create**:
- `src/extraction/base.py` — `Extractor` ABC with `async extract(file_path: Path) -> ExtractedDoc`
- `src/extraction/doc_intelligence.py` — `DocIntelligenceExtractor` using `azure-ai-documentintelligence` SDK, `prebuilt-read` model; returns `ExtractedDoc` with full text content
- `src/extraction/mock_extractor.py` — `MockExtractor` returns canned `ExtractedDoc` from a JSON sidecar file (e.g., `form.pdf.extracted.json` next to the PDF)

**Dependencies to add**: `azure-ai-documentintelligence`, `azure-identity`

**Acceptance criteria**: `MockExtractor` returns valid `ExtractedDoc`. `DocIntelligenceExtractor` (when Azure creds are set) extracts text from a real PDF.

**Test**: `pytest tests/test_extraction.py` — tests `MockExtractor` with fixture data. Manual integration test: `python -c "..."` with real Azure creds + a sample PDF.

---

### M4: Form Analyzer
**Goal**: LLM-based analysis of the extracted form to determine form type, reason/event, and employee/beneficiary names.

**Files to create**:
- `src/classification/form_analyzer.py` — `FormAnalyzer` class with `async analyze(extracted: ExtractedDoc) -> FormAnalysisResult`
  - Uses Azure OpenAI chat completion with a system prompt
  - Prompt instructs the LLM to output strict JSON matching `FormAnalysisResult` schema
  - System prompt: "You are a document analyst. Given the extracted text of an HR form, determine: (1) Is this an 'Add Beneficiary to employer-sponsored health plan' form? (2) What reason/life event is selected (marriage, birth, adoption, etc.)? (3) Extract employee and beneficiary names. Return JSON."
  - Uses `response_format={"type": "json_object"}` for strict JSON output

**Dependencies to add**: `openai`

**Acceptance criteria**: Given extracted text containing "Add Beneficiary" and "Marriage" checkbox marked, returns `FormAnalysisResult(form_type="add_beneficiary", reason="marriage", is_relevant=True, ...)`. Given unrelated form text, returns `is_relevant=False`.

**Test**: `pytest tests/test_classification.py::test_form_analyzer` — mock the OpenAI client, assert correct prompt structure and response parsing. Manual test with real Azure OpenAI + sample form.

---

### M5: Attachment Classifier
**Goal**: LLM-based classification of the attachment document type.

**Files to create**:
- `src/classification/attachment_classifier.py` — `AttachmentClassifier` class with `async classify(extracted: ExtractedDoc) -> ClassifierResponse`
  - System prompt: "You are a document classifier. Given extracted text from an HR submission attachment, classify it as one of: marriage_certificate, birth_certificate, court_order, unknown. Return JSON with doc_type, confidence, reasoning."

**Acceptance criteria**: Marriage certificate text → `ClassifierResponse(doc_type="marriage_certificate", ...)`. Random text → `doc_type="unknown"`.

**Test**: `pytest tests/test_classification.py::test_attachment_classifier` — mock OpenAI, verify prompt and parsing.

---

### M6: Validator Framework + Registry
**Goal**: Pluggable validator architecture with YAML-driven routing.

**Files to create**:
- `src/validators/base.py` — `BaseValidator` ABC with `async validate(form_analysis: FormAnalysisResult, attachment: ExtractedDoc) -> ValidationResult`
- `src/validators/registry.py` — `ValidatorRegistry` class:
  - `load(config_path: Path)` — reads `registry.yaml`, dynamically imports validator classes
  - `get_validator(doc_type: str) -> BaseValidator | None`
- `config/registry.yaml`:
  ```yaml
  validators:
    marriage_certificate:
      class: src.validators.marriage_certificate.MarriageCertificateAgent
  ```

**Acceptance criteria**: `ValidatorRegistry` loads config, `get_validator("marriage_certificate")` returns an instance. `get_validator("unknown")` returns `None`.

**Test**: `pytest tests/test_validators.py::test_registry` — temp YAML config, verify dynamic loading.

---

### M7: MarriageCertificateAgent
**Goal**: Validate a marriage certificate attachment against form data.

**Files to create**:
- `src/validators/marriage_certificate.py` — `MarriageCertificateAgent(BaseValidator)`:
  - `async validate(form_analysis, attachment_extracted) -> ValidationResult`
  - Uses LLM prompt: "Given this marriage certificate text, verify: (1) Does it contain employee name '{first} {last}'? (2) Does it contain beneficiary name '{first}'? (3) Is the certificate date within the last 12 months from today? Return JSON with found_employee_name: bool, found_beneficiary_name: bool, certificate_date: str|null, is_date_valid: bool."
  - Maps LLM response to pass/fail with specific reasons list

**Acceptance criteria**: Certificate with matching names + recent date → `status="pass"`. Missing name → `status="fail", reasons=["Employee name not found on certificate"]`. Old date → `status="fail", reasons=["Certificate date is older than 12 months"]`.

**Test**: `pytest tests/test_validators.py::test_marriage_cert_agent` — mock LLM responses for pass/fail scenarios.

---

### M8: Orchestrator + Result Writer + CLI
**Goal**: Wire everything into an end-to-end pipeline with CLI entry point and JSONL output.

**Files to create**:
- `src/orchestrator.py` — `Orchestrator` class:
  - Constructor takes: `ingestion_adapter`, `extractor`, `form_analyzer`, `attachment_classifier`, `validator_registry`, `result_writer`
  - `async run() -> list[ValidationResult]`:
    1. `submissions = ingestion.list_submissions()`
    2. For each submission:
       a. `form_extracted = extractor.extract(submission.form_path)`
       b. `form_analysis = form_analyzer.analyze(form_extracted)`
       c. If `not form_analysis.is_relevant` → write skip result, continue
       d. For each attachment:
          - `att_extracted = extractor.extract(att_path)`
          - `classification = attachment_classifier.classify(att_extracted)`
          - `validator = registry.get_validator(classification.doc_type)`
          - If no validator → fail("No validator for doc_type {x}")
          - `result = validator.validate(form_analysis, att_extracted)`
       e. Write result
  - **Note**: orchestrator has ZERO doc-type-specific logic
- `src/result_writer.py` — `ResultWriter` with `write(result: ValidationResult, output_path: Path)` appending JSONL
- `main.py` — CLI entry point:
  - Args: `--input` (samples dir), `--output` (results file), `--mock` (use mock extractor)
  - Wires all components, calls `orchestrator.run()`
  - Example: `python main.py --input samples/ --output results.jsonl`

**Acceptance criteria**:
- Full pipeline runs end-to-end with mock extractor + mock LLM → produces `results.jsonl`
- Full pipeline runs with real Azure services → produces correct results
- JSONL output contains one line per submission with all `ValidationResult` fields

**Test**:
- `pytest tests/test_pipeline.py` — full pipeline with all mocks, assert JSONL output
- Manual: `python main.py --input samples/ --output results.jsonl --mock`
- Integration: `python main.py --input samples/ --output results.jsonl` (with `.env` configured)

---

## AI Integration Points

| Component | Service | Why |
|---|---|---|
| `DocIntelligenceExtractor` | Azure Document Intelligence (`prebuilt-read`) | Extract text from PDFs, images, DOCX — handles both fillable and scanned forms |
| `FormAnalyzer` | Azure OpenAI GPT-4o | Classify form type, extract reason + names — needs reasoning over unstructured text |
| `AttachmentClassifier` | Azure OpenAI GPT-4o | Classify attachment doc type — lightweight prompt |
| `MarriageCertificateAgent` | Azure OpenAI GPT-4o | Validate names + date presence — needs reasoning over certificate text |

All LLM calls use `response_format={"type": "json_object"}` and validate against Pydantic schemas.

---

## Decisions

- **Pydantic v2** for all contracts — provides JSON schema generation, validation, and strict LLM output parsing
- **JSONL** over CSV for results — better for structured data with variable-length `reasons` lists
- **Async** throughout — `DocIntelligenceExtractor` and OpenAI calls are I/O-bound; async allows future parallelism
- **Mock extractor uses JSON sidecar files** — place `form.pdf.extracted.json` next to sample PDFs for offline testing
- **Single `models.py`** — POC has 5 models, no need to split into separate files yet
- **`registry.yaml`** uses fully qualified class paths — `ValidatorRegistry` does dynamic import via `importlib`
- **SharePoint adapter**: `IngestionAdapter` ABC defines the interface; a `SharePointAdapter` can be added later without changing any other component
- **Scope boundary**: This POC covers only the "Add Beneficiary / Marriage" path. Other form types and life events are out of scope but the architecture supports them via registry entries.
