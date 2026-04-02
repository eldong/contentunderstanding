# Document Validation System POC

Validates HR submissions (form PDF + supporting attachments) using Azure Document Intelligence for extraction and Azure OpenAI GPT-4o for classification/validation.

## Prerequisites

- Python 3.11+
- Azure CLI (`az login` for authentication)
- Azure AI Foundry project with:
  - GPT-4o deployment
  - Document Intelligence service

## Setup

```bash
# Clone and install
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with your Azure AI Foundry endpoints
```

Authentication uses `DefaultAzureCredential` — no API keys needed. Run `az login` locally.

## Project Structure

```
src/
  models.py              # Pydantic v2 data contracts
  ingestion/             # Read submission directories
  extraction/            # Extract text from documents (Azure Doc Intelligence or mock)
  classification/        # Classify forms and attachments (GPT-4o)
  validators/            # Validate attachments against form requirements
config/
  doc_types/             # YAML definitions for attachment document types
  doc_type_rules/        # YAML definitions for life events / validation rules per reason
samples/                 # Sample submission folders for development
tests/                   # Automated tests (no Azure calls)
```

## How It Works

Each submission is a folder containing:
- A **form** (filename contains "form") — the HR enrollment/change form
- **Attachments** — supporting documents (marriage certificates, birth certificates, etc.)
- Optional **metadata.json** — provides `submitted_by` if present

The folder name is the submission ID.

The pipeline:
1. **Ingestion** — scans submission folders, builds work items
2. **Extraction** — OCRs documents into text + structured fields
3. **Classification** — identifies form type and attachment document types
4. **Validation** — checks attachments against form requirements

## Milestones

### M1: Scaffold & Contracts (complete)
Pydantic v2 data models in `src/models.py`:
- `SubmissionWorkItem`, `ExtractedDoc`, `FormAnalysisResult`, `ClassifierResponse`, `ValidationResult`

```bash
python -c "from src.models import SubmissionWorkItem, ExtractedDoc, FormAnalysisResult, ClassifierResponse, ValidationResult; print('OK')"
```

### M2: Ingestion (complete)
Local folder adapter reads submission directories from `samples/`.

```bash
# List all submissions
python -c "from src.ingestion.local_folder import LocalFolderAdapter; print(LocalFolderAdapter('samples').list_submissions())"
```

### M3: Extraction (complete)
Two extractors:
- `MockExtractor` — reads `.extracted.json` sidecar files (offline development)
- `DocIntelligenceExtractor` — calls Azure Document Intelligence (used in production)

```bash
# Test mock extraction
python -c "
import asyncio
from pathlib import Path
from src.extraction.mock_extractor import MockExtractor
result = asyncio.run(MockExtractor().extract(Path('samples/submission_001/form.pdf')))
print(result.content[:100])
"
```

### M4: Form Analyzer (complete)
GPT-4o analyzes extracted form text to determine form type, life event reason, employee/beneficiary names, and relevance. Returns `FormAnalysisResult`.

Configuration is **data-driven** with two YAML folders:
- `config/doc_types/` — defines attachment document types (indicators, validation rules)
- `config/doc_type_rules/` — defines life events (required doc types, form-field validation rules)

Reasons that need no attachments (e.g. `new_hire`) set `required_doc_types: []` and only have `form_validation_rules`. Adding a new reason or document type means adding a YAML file; no Python code changes needed.

```bash
pytest tests/test_classification.py tests/test_doc_type_config.py tests/test_doc_type_rule_config.py -v
```

### M5: Attachment Classifier
_Coming soon_ — GPT-4o classifies attachment documents.

### M6: Validator Registry
_Coming soon_ — YAML-driven registry maps document types to validators.

### M7: Marriage Certificate Validator
_Coming soon_ — First concrete validator using GPT-4o.

### M8: Orchestrator & CLI
_Coming soon_ — End-to-end pipeline with CLI interface.

## Running Tests

```bash
# All tests
pytest -v

# Specific milestone
pytest tests/test_models.py -v           # M1
pytest tests/test_ingestion.py -v        # M2
pytest tests/test_extraction.py -v       # M3
pytest tests/test_classification.py -v   # M4
pytest tests/test_doc_type_config.py -v  # M4 doc type configs
pytest tests/test_doc_type_rule_config.py -v  # M4 doc type rules
```
