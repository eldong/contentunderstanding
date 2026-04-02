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

Reasons that need no attachments (e.g. `new_hire`) set `required_attachment_types: []` and only have `form_validation_rules`. Adding a new reason or document type means adding a YAML file; no Python code changes needed.

```bash
pytest tests/test_classification.py tests/test_doc_type_config.py tests/test_doc_type_rule_config.py -v
```

### M5: Attachment Classifier (complete)
GPT-4o classifies attachment documents into registered doc types (or `"unknown"`). The `AttachmentClassifier` builds its prompt dynamically from `config/doc_types/` configs — doc types, descriptions, and indicators. Returns `ClassifierResponse` with `doc_type`, `confidence`, and `reasoning`.

```bash
pytest tests/test_classification.py::TestAttachmentClassifier -v
```

### M6: Validator Registry (complete)
YAML-driven validator framework with three components:
- `BaseValidator` — abstract interface for all validators
- `LLMValidator` — generic GPT-4o validator driven by `validation_rules` from `config/doc_types/` configs. Builds a prompt with employee/beneficiary names and validation rules, sends attachment text, parses pass/fail results.
- `ValidatorRegistry` — auto-discovers doc-type configs and creates an `LLMValidator` per type. Lookup by `doc_type`, no per-type Python classes needed.

```bash
pytest tests/test_validators.py -v
```

### M7: Marriage Certificate Validation (complete)
End-to-end validation testing for the marriage certificate doc type. Verifies the `LLMValidator` with the real `config/doc_types/marriage_certificate.yaml` rules across 8 scenarios: all-pass, employee name mismatch, beneficiary name mismatch, date too old, unofficial document, multiple failures, prompt rule inclusion, and prompt form-data inclusion. No marriage-specific Python code — the generic `LLMValidator` handles everything via YAML config.

```bash
pytest tests/test_validators.py::TestMarriageCertificateValidation -v
```

### M8: Orchestrator & CLI (complete)
End-to-end pipeline wiring all components together:
- `ResultWriter` — appends `ValidationResult` objects as JSON lines (JSONL format)
- `Orchestrator` — runs the full pipeline: ingestion → extraction → form analysis → attachment classification → validation. Contains zero doc-type-specific logic; routes entirely via classifier + registry.
- `main.py` — CLI entry point with `argparse`

```bash
# Run with mock extraction (no Azure Doc Intelligence needed)
python main.py --mock --input samples/ --output results.jsonl

# Run with real Azure services
python main.py --input samples/ --output results.jsonl
```

CLI flags:
- `--input` / `-i` — submissions folder (default: `samples/`)
- `--output` / `-o` — results JSONL file (default: `results.jsonl`)
- `--config` / `-c` — doc types config dir (default: `config/doc_types/`)
- `--rules` / `-r` — doc type rules config dir (default: `config/doc_type_rules/`)
- `--mock` — use `MockExtractor` instead of Azure Document Intelligence

```bash
pytest tests/test_pipeline.py -v
```

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
pytest tests/test_validators.py -v        # M6
pytest tests/test_validators.py::TestMarriageCertificateValidation -v  # M7
pytest tests/test_pipeline.py -v          # M8
```
