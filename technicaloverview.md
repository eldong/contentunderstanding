# Technical Overview

Developer reference for the Document Validation System. For setup and usage, see [README.md](README.md).

## Architecture

The system is a four-stage async pipeline: **Ingestion → Extraction → Classification → Validation**. Each stage is defined by an abstract base class with swappable implementations. All document types and validation rules are configured via YAML files — no per-type Python code is needed.

```
src/
  models.py                          # Pydantic v2 data contracts
  orchestrator.py                    # Pipeline wiring
  result_writer.py                   # JSONL output
  ingestion/
    base.py                          # IngestionAdapter ABC
    local_folder.py                  # LocalFolderAdapter
  extraction/
    base.py                          # Extractor ABC
    mock_extractor.py                # MockExtractor (sidecar JSON)
    doc_intelligence.py              # DocIntelligenceExtractor (Azure)
  classification/
    doc_type_config.py               # DocTypeConfig model + YAML loader
    form_type_config.py              # FormTypeConfig model + YAML loader
    form_analyzer.py                 # FormAnalyzer (GPT-4o)
    attachment_classifier.py         # AttachmentClassifier (GPT-4o)
  validators/
    base.py                          # BaseValidator ABC
    llm_validator.py                 # LLMValidator (GPT-4o, rules-driven)
    registry.py                      # ValidatorRegistry (auto-discovers from YAML)
config/
  doc_types/                         # Attachment document type definitions
  form_types/                        # Form type / life event definitions
tests/                               # 90 tests, all mock Azure services
```

## Data Contracts

Five Pydantic v2 models in [src/models.py](src/models.py) define the data flowing through the pipeline:

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `SubmissionWorkItem` | One submission to process | `submission_id`, `form_path`, `attachment_paths`, `submitted_by`, `metadata` |
| `ExtractedDoc` | OCR/extraction output | `source_path`, `content`, `fields`, `confidence` |
| `FormAnalysisResult` | LLM form analysis | `form_type`, `reason`, `employee_first_name`, `employee_last_name`, `beneficiary_first_name`, `is_relevant` |
| `ClassifierResponse` | LLM attachment classification | `doc_type`, `confidence`, `reasoning` |
| `ValidationResult` | Final output per attachment | `submission_id`, `form_name`, `submitted_by`, `doc_type`, `status` (`"passed"` / `"failed"` / `"error"`), `reasons`, `timestamp` |

## Pipeline Stages

### 1. Ingestion

**Interface:** `IngestionAdapter` (ABC) — [src/ingestion/base.py](src/ingestion/base.py)

| Method | Returns |
|--------|---------|
| `list_submissions()` | `list[SubmissionWorkItem]` |
| `download_submission(submission_id)` | `SubmissionWorkItem` |

**Implementation:** `LocalFolderAdapter` — [src/ingestion/local_folder.py](src/ingestion/local_folder.py)

Scans a root directory for submission subfolders. For each subfolder:
- Reads optional `metadata.json` for `submitted_by` (defaults to `""`)
- Identifies the form file (filename stem contains "form", extension in `.pdf`, `.docx`, `.jpg`, `.png`)
- Collects all other supported files as attachments
- Skips directories without a form file
- Uses the folder name as `submission_id`

### 2. Extraction

**Interface:** `Extractor` (ABC) — [src/extraction/base.py](src/extraction/base.py)

| Method | Returns |
|--------|---------|
| `async extract(file_path)` | `ExtractedDoc` |

**Implementations:**

| Class | Source | Behavior |
|-------|--------|----------|
| `MockExtractor` | [mock_extractor.py](src/extraction/mock_extractor.py) | Reads `{file}.mock.extracted.json` sidecar files. Returns empty `ExtractedDoc` if sidecar is missing. |
| `DocIntelligenceExtractor` | [doc_intelligence.py](src/extraction/doc_intelligence.py) | Calls Azure Document Intelligence `prebuilt-read` model. Runs the synchronous SDK call in `asyncio.to_thread`. Extracts page text, key-value pairs, and average word confidence. Uses `body=io.BytesIO(file_bytes)` (v1.0.2 GA SDK). Writes `{file}.docintell.extracted.json` sidecar for debugging. |

Both extractors authenticate via `DefaultAzureCredential`.

### 3. Classification

Two classifiers, both GPT-4o-based. Each builds its system prompt once at construction from loaded YAML configs and reuses it across calls.

#### FormAnalyzer — [src/classification/form_analyzer.py](src/classification/form_analyzer.py)

```python
FormAnalyzer(client: AsyncAzureOpenAI, deployment: str, form_type_configs: list[FormTypeConfig])
```

- Receives extracted form text
- Determines `form_type`, `reason` (life event), employee/beneficiary names, and `is_relevant`
- Prompt built dynamically from all `FormTypeConfig` `doc_type` values (inserted as valid reason enum)
- Returns `FormAnalysisResult`
- Uses `response_format={"type": "json_object"}`

#### AttachmentClassifier — [src/classification/attachment_classifier.py](src/classification/attachment_classifier.py)

```python
AttachmentClassifier(client: AsyncAzureOpenAI, deployment: str, doc_type_configs: list[DocTypeConfig])
```

- Receives extracted attachment text
- Classifies into one of the registered doc types or `"unknown"`
- Prompt includes each doc type's `display_name`, `description`, and `indicators`
- Returns `ClassifierResponse` with `doc_type`, `confidence`, and `reasoning`
- Uses `response_format={"type": "json_object"}`

### 4. Validation

**Interface:** `BaseValidator` (ABC) — [src/validators/base.py](src/validators/base.py)

```python
async def validate(self, form_analysis: FormAnalysisResult, attachment_extracted: ExtractedDoc) -> ValidationResult
```

**Implementation:** `LLMValidator` — [src/validators/llm_validator.py](src/validators/llm_validator.py)

A single generic validator class. Uses `validation_rules` from a `DocTypeConfig` to build a GPT-4o prompt that checks each rule against the attachment text. The prompt includes employee/beneficiary names from the form analysis and today's date for time-sensitive rules.

Returns `ValidationResult` with:
- `status = "passed"` if all rules pass, `"failed"` if any fail
- `reasons` = list of explanations for failed rules

**Registry:** `ValidatorRegistry` — [src/validators/registry.py](src/validators/registry.py)

```python
ValidatorRegistry.load(config_dir: Path, client: AsyncAzureOpenAI, deployment: str) -> ValidatorRegistry
```

- Auto-discovers all `config/doc_types/*.yaml` files at load time
- Creates one `LLMValidator` per config
- Lookup via `get_validator(doc_type) -> BaseValidator | None`
- `list_doc_types() -> list[str]` returns sorted registered types

## YAML Configuration

### Document Types (`config/doc_types/`)

Each file defines an attachment type the system can recognize and validate:

```yaml
doc_type: marriage_certificate          # Unique key, used for classifier and validator lookup
display_name: Marriage Certificate
description: "Official government-issued certificate or license of marriage"
indicators:                             # Keywords used by AttachmentClassifier
  - "certificate of marriage"
  - "marriage license"
validation_rules:                       # Rules used by LLMValidator
  - "The names on the certificate must match the employee and/or beneficiary names"
  - "The marriage date must be within the last 12 months"
  - "The document must appear to be an official government-issued certificate"
```

### Form Types (`config/form_types/`)

Each file defines an HR action and the attachments it requires:

```yaml
doc_type: add_dependent_health          # Unique key, matched by FormAnalyzer
display_name: Health Insurance Dependent Addition Form
description: "Form for adding a dependent to employee health insurance"
required_attachment_types:              # Which doc_types are valid for this form
  - marriage_certificate
  - birth_certificate
form_validation_rules:                  # Form-level rules (used by FormAnalyzer prompt)
  - "The employee name must be filled out on the form"
  - "A relationship must be selected (spouse or child)"
```

Forms that require no attachments (e.g. `new_hire`) set `required_attachment_types: []`.

## Orchestrator

[src/orchestrator.py](src/orchestrator.py) wires all stages together. For each submission:

1. **Extract form** — OCR the form file
2. **Analyze form** — classify form type and extract names
3. **Check relevance** — skip if `is_relevant` is false (writes `"error"` result)
4. **For each attachment:**
   - Extract attachment text
   - Classify attachment doc type
   - Look up validator from registry
   - If no validator registered → write `"failed"` result
   - Run validation → write result

Every stage is wrapped in `try/except`. Errors produce a `ValidationResult` with `status="error"` and processing continues to the next submission/attachment.

## Result Writer

[src/result_writer.py](src/result_writer.py) — appends `ValidationResult` objects as JSON lines (one per line) to the output file. The `read_all()` method parses the file back into a list.

## Error Handling

The orchestrator catches exceptions at each pipeline stage and continues processing:

| Stage | Error Status | Behavior |
|-------|-------------|----------|
| Form extraction | `"error"` | Skip entire submission |
| Form analysis | `"error"` | Skip entire submission |
| Form not relevant | `"error"` | Skip (no matching form type) |
| Attachment extraction | `"error"` | Skip attachment, continue others |
| Attachment classification | `"error"` | Skip attachment, continue others |
| No validator registered | `"failed"` | Record failure, continue |
| Validation exception | `"error"` | Record error, continue |

## Authentication

All Azure calls use `DefaultAzureCredential` from `azure-identity`. No API keys are stored or passed. Locally, run `az login` before use. In production, managed identity or other credential types are picked up automatically.

The OpenAI client obtains a token for the `https://cognitiveservices.azure.com/.default` scope and passes it as `api_key` to `AsyncAzureOpenAI`.

## Testing

90 tests across 8 test files. All tests mock Azure services — no live calls.

| Test File | What It Covers |
|-----------|---------------|
| [test_models.py](tests/test_models.py) | Pydantic model validation, serialization, defaults |
| [test_ingestion.py](tests/test_ingestion.py) | `LocalFolderAdapter` — folder scanning, metadata, form detection |
| [test_extraction.py](tests/test_extraction.py) | `MockExtractor` sidecar loading, `DocIntelligenceExtractor` instantiation |
| [test_doc_type_config.py](tests/test_doc_type_config.py) | `DocTypeConfig` model + YAML loader |
| [test_form_type_config.py](tests/test_form_type_config.py) | `FormTypeConfig` model + YAML loader |
| [test_classification.py](tests/test_classification.py) | `FormAnalyzer` and `AttachmentClassifier` — prompt building, LLM mocking |
| [test_validators.py](tests/test_validators.py) | `LLMValidator`, `ValidatorRegistry`, marriage certificate scenarios |
| [test_pipeline.py](tests/test_pipeline.py) | `Orchestrator` end-to-end, `ResultWriter`, error handling |

Tests use `tmp_path` for filesystem fixtures and `unittest.mock.AsyncMock` for Azure/OpenAI clients.

```bash
# Run all tests
pytest -v

# Run a specific test file
pytest tests/test_pipeline.py -v

# Run a specific test class
pytest tests/test_validators.py::TestMarriageCertificateValidation -v
```

## Dependencies

Declared in [pyproject.toml](pyproject.toml). No `requirements.txt`.

| Package | Purpose |
|---------|---------|
| `pydantic>=2.0` | Data contracts |
| `python-dotenv>=1.0` | `.env` file loading |
| `openai>=1.0` | Azure OpenAI client |
| `azure-ai-documentintelligence>=1.0.0b4` | Document Intelligence SDK |
| `azure-identity>=1.15` | `DefaultAzureCredential` |
| `pyyaml>=6.0` | YAML config parsing |
| `pytest>=8.0` | Testing (dev) |
| `pytest-asyncio>=0.23` | Async test support (dev) |

## Extending the System

### Add a new document type

Create a YAML file in `config/doc_types/`:

```yaml
doc_type: drivers_license
display_name: Driver's License
description: "Government-issued photo ID"
indicators:
  - "driver license"
  - "operator license"
validation_rules:
  - "The name must match the employee name on the form"
  - "The license must not be expired"
```

The `AttachmentClassifier` and `ValidatorRegistry` will pick it up automatically on next run.

### Add a new form type

Create a YAML file in `config/form_types/`:

```yaml
doc_type: name_change
display_name: Legal Name Change
description: "Employee requesting a legal name change"
required_attachment_types:
  - court_order
form_validation_rules:
  - "Both old and new names must be filled out"
```

The `FormAnalyzer` will include it as a valid reason on next run.

### Add a new ingestion source

Implement `IngestionAdapter` and return `SubmissionWorkItem` objects:

```python
class BlobStorageAdapter(IngestionAdapter):
    def list_submissions(self) -> list[SubmissionWorkItem]: ...
    def download_submission(self, submission_id: str) -> SubmissionWorkItem: ...
```

### Add a new extraction backend

Implement the `Extractor` ABC:

```python
class CustomExtractor(Extractor):
    async def extract(self, file_path: Path) -> ExtractedDoc: ...
```
