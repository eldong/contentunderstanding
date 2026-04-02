# Document Validation System

Automates the validation of HR benefit submissions. Each submission contains an enrollment form and supporting documents (marriage certificates, birth certificates, etc.). The system extracts text from all documents, classifies them, and validates that the supporting documents satisfy the requirements for the requested benefit change.

Built on Azure Document Intelligence (OCR/extraction) and Azure OpenAI GPT-4o (classification/validation).

## How It Works

```
Submission Folder          Pipeline                        Output
┌──────────────────┐                                  ┌───────────────┐
│ form.pdf         │──▶ Extract ──▶ Classify Form     │ results.jsonl │
│ marriage_cert.pdf│──▶ Extract ──▶ Classify ──▶ Validate ──▶│               │
│ metadata.json    │                                  └───────────────┘
└──────────────────┘
```

1. **Ingestion** — scans a folder of submissions; each subfolder is one submission
2. **Extraction** — converts PDFs and images to text using Azure Document Intelligence
3. **Classification** — GPT-4o identifies the form type (e.g. "add dependent") and each attachment's document type (e.g. "marriage certificate")
4. **Validation** — GPT-4o checks each attachment against the validation rules for its document type (name matching, date recency, official document, etc.)

Results are written to a JSONL file with one line per validated attachment, including status (`passed`, `failed`, or `error`) and reasons. If `AZURE_STORAGE_ACCOUNT_URL` and `AZURE_RESULTS_CONTAINER_NAME` are set, results are also uploaded to the specified Azure Blob Storage container.

## Key Concepts

### Submissions

A submission is a folder containing:

| Item | Description |
|------|-------------|
| **Form** | The HR enrollment/change form. Identified by having "form" in the filename. |
| **Attachments** | Supporting documents — any other PDF, DOCX, JPG, or PNG file in the folder. |
| **metadata.json** | Optional. Provides `submitted_by` if present. |

The folder name is used as the submission ID. Folders without a form file are skipped.

### Data-Driven Configuration

All document types and form rules are defined in YAML — no code changes needed to support new types.

**Document types** (`config/doc_types/`) define what kinds of attachments the system recognizes and how to validate them:

```yaml
# config/doc_types/marriage_certificate.yaml
doc_type: marriage_certificate
display_name: Marriage Certificate
description: "Official government-issued certificate or license of marriage"
indicators:
  - "certificate of marriage"
  - "marriage license"
validation_rules:
  - "The names on the certificate must match the employee and/or beneficiary names"
  - "The marriage date must be within the last 12 months"
  - "The document must appear to be an official government-issued certificate"
```

**Form types** (`config/form_types/`) define which attachments are required for each type of HR action:

```yaml
# config/form_types/add_dependent_health.yaml
doc_type: add_dependent_health
display_name: Health Insurance Dependent Addition Form
description: "Form for adding a dependent to employee health insurance"
required_attachment_types:
  - marriage_certificate
  - birth_certificate
form_validation_rules:
  - "The employee name must be filled out on the form"
  - "A relationship must be selected (spouse or child)"
```

To add support for a new document type or form type, add a YAML file to the appropriate folder.

## Setup

### Prerequisites

- Python 3.11+
- Azure CLI (run `az login` for authentication)
- An Azure AI Foundry project with a GPT-4o deployment and Document Intelligence service

### Install

```bash
pip install -e ".[dev]"
```

### Environment

Copy the example and fill in your Azure endpoints:

```bash
cp .env.example .env
```

| Variable | Description |
|----------|-------------|
| `AZURE_AI_FOUNDRY_OPENAI_ENDPOINT` | Your Azure OpenAI endpoint (e.g. `https://your-project.openai.azure.com/`) |
| `AZURE_AI_FOUNDRY_SERVICES_ENDPOINT` | Your Azure AI Services endpoint (for Document Intelligence) |
| `AZURE_OPENAI_DEPLOYMENT` | Model deployment name (default: `gpt-4o`) |
| `AZURE_OPENAI_API_VERSION` | API version (default: `2024-12-01-preview`) |
| `AZURE_STORAGE_ACCOUNT_URL` | *(Optional)* Azure Storage account URL for uploading results (e.g. `https://myaccount.blob.core.windows.net`) |
| `AZURE_RESULTS_CONTAINER_NAME` | *(Optional)* Blob container name for results. Set both blob vars to enable upload. |

Authentication uses `DefaultAzureCredential` — no API keys needed. Run `az login` before use.

## Usage

### Validate submissions

```bash
# Using Azure Document Intelligence for extraction
python main.py --input samples/ --output results.jsonl

# Using mock extraction (offline development, reads .mock.extracted.json sidecar files)
python main.py --mock --input samples/ --output results.jsonl
```

### CLI options

| Flag | Default | Description |
|------|---------|-------------|
| `--input`, `-i` | `samples/` | Path to the submissions folder |
| `--output`, `-o` | `results.jsonl` | Path to the output JSONL file |
| `--config`, `-c` | `config/doc_types/` | Path to document type configs |
| `--rules`, `-r` | `config/form_types/` | Path to form type configs |
| `--mock` | off | Use mock extraction instead of Azure Document Intelligence |

### Output format

Each line in `results.jsonl` is a JSON object:

```json
{
  "submission_id": "submission_001",
  "form_name": "add_dependent_health",
  "submitted_by": "john.doe",
  "doc_type": "marriage_certificate",
  "status": "passed",
  "reasons": [],
  "passed_reasons": [
    "Names Jane Smith and Michael match the employee and beneficiary on the form",
    "The date 2026-02-14 is within the last 12 months (cutoff: 2025-04-02)",
    "Document contains official state seal and officiant signature"
  ],
  "timestamp": "2026-04-02T12:00:00+00:00"
}
```

| Field | Description |
|-------|-------------|
| `status` | `"passed"` — all validation rules satisfied. `"failed"` — one or more rules not met. `"error"` — a processing failure occurred (extraction, classification, or no matching form type). |
| `reasons` | Empty when passed. When failed, lists the specific rules that were not satisfied (e.g. `"The marriage date must be within the last 12 months"`). When error, describes what went wrong (e.g. `"Form extraction failed: ..."`). |
| `passed_reasons` | Lists the specific rules that were satisfied, with explanations. Provides an audit trail showing why each rule passed. |

### Run tests

```bash
pytest -v
```
