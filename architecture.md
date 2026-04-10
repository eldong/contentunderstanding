# Revised Azure Architecture for HR Benefits Submission Validation

## Brief summary of key points

- **SharePoint remains the system of record** for submitted files.
- **No permanent duplicate copy of originals** is required in Blob Storage.
- **Azure Service Bus provides buffering** to absorb bursts and reduce pressure on SharePoint / Graph.
- **Azure Durable Functions orchestrates processing** at the submission level.
- **Azure Blob Storage is still part of the solution** for Durable Functions runtime state and optional temporary/audit artifacts.
- **Azure Document Intelligence** performs OCR/text extraction.
- **Azure OpenAI** classifies and extracts validation facts.
- **Deterministic Python code** performs exact rule validation.
- **Results are written back to SharePoint** as CSV by form type.

---

## Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────────┐
│                         SharePoint Online                           │
│  - Source of truth for forms and supporting documents              │
│  - Files uploaded individually                                     │
│  - Results CSVs written back to same site                          │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                │ Metadata scan / file discovery
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Azure Function (Ingestion)                      │
│  - Timer-triggered poller or event-driven detector                 │
│  - Reads SharePoint metadata only                                  │
│  - Groups files by submission ID prefix                            │
│  - Creates submission manifest                                     │
│  - Sends message to Service Bus                                    │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Azure Service Bus Queue                       │
│  - Buffers work                                                    │
│  - Smooths bursts                                                  │
│  - Reduces pressure on SharePoint / Graph                          │
│  - Supports retries / dead-lettering                               │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│             Azure Functions + Durable Functions                    │
│                    (Submission Orchestrator)                       │
│                                                                     │
│  Steps:                                                             │
│  1. Load submission manifest                                         │
│  2. Fetch files from SharePoint on demand                           │
│  3. Extract text from each file                                     │
│  4. Classify form and attachments                                   │
│  5. Load YAML validation rules                                      │
│  6. Validate attachments against requested benefit change           │
│  7. Write structured results                                        │
└─────────────────────────────────────────────────────────────────────┘
                │                          │
                │                          │
                ▼                          ▼
┌──────────────────────────────┐   ┌─────────────────────────────────┐
│ Azure Document Intelligence  │   │ Azure OpenAI                   │
│ - OCR / text extraction      │   │ - Form classification          │
│ - PDFs and images            │   │ - Attachment classification    │
│                              │   │ - Fact extraction for rules    │
└──────────────────────────────┘   └─────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                Deterministic Validation Code (Python)              │
│  - Date recency windows                                            │
│  - Name matching / normalization                                   │
│  - Required document checks                                        │
│  - Exact rule enforcement                                          │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ├─────────────────────────────────────┐
                                │                                     │
                                ▼                                     ▼
┌──────────────────────────────────────────────────────┐   ┌─────────────────────────────────────┐
│                  Azure Blob Storage                  │   │         SharePoint Online            │
│  - Durable Functions runtime storage                 │   │  - CSV results by form type         │
│  - Optional temporary working artifacts              │   │  - Final business-facing output     │
│  - Optional JSON audit results                       │   │                                     │
│  - Optional YAML rule storage                        │   │                                     │
└──────────────────────────────────────────────────────┘   └─────────────────────────────────────┘
```

---

## Azure Resources

### Core
- **Azure Function App**
- **Azure Service Bus**  
  - Queue: `submission-intake`
- **Azure Storage Account / Blob Storage**
  - Durable Functions runtime storage
  - Optional temporary processing artifacts
  - Optional JSON audit output
  - Optional YAML rules
- **Azure Document Intelligence**
- **Azure OpenAI**
- **Azure Key Vault**
- **Application Insights**

### Optional
- **Cosmos DB / Table Storage / SQL** for status tracking
- **Log Analytics**
- **Azure Monitor alerts**

---

## What Blob Storage is doing in this design

Blob Storage is **not** the primary repository for original submitted documents.

It is included for:
- **Durable Functions runtime state**
- **Optional temporary working files**
- **Optional JSON audit artifacts**
- **Optional rule files**

It is **not intended to be a permanent duplicate store of SharePoint originals**.

---

## Processing Flow

1. Files are uploaded to SharePoint.
2. Azure Function scans metadata and groups files by submission ID.
3. A submission manifest is sent to Service Bus.
4. Durable Functions processes the submission.
5. Files are fetched on demand from SharePoint.
6. OCR → Classification → Validation.
7. Results are written back to SharePoint as CSV.
8. Optional audit/working artifacts can be stored in Blob Storage.

---

## Key Design Choices

- **Buffer work, not files**
- **Read from SharePoint on demand**
- **Use Blob for runtime state and optional artifacts**
- **One orchestrator per submission**
- **Separate classification and validation**
- **Keep rules in YAML**

---

## Sample Submission Manifest

```json
{
  "submission_id": "12345",
  "files": [
    {"file_name": "12345_form.pdf"},
    {"file_name": "12345_marriage_cert.pdf"}
  ]
}
```

---

## Final Recommendation

**SharePoint → Azure Function → Service Bus → Durable Functions → Document Intelligence / Azure OpenAI / Python validation → SharePoint CSV results**, with **Blob Storage supporting Durable runtime state and optional temporary/audit artifacts**.
