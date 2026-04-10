# HR Benefits Submission Validation - Updated Azure Architecture

## Summary

This architecture is designed for **SharePoint-based HR benefits submissions** where each submission includes a form and one or more supporting documents such as marriage certificates or birth certificates.

The design goals are:

- **SharePoint remains the system of record**
- **No permanent duplicate copy of original files**
- **Service Bus buffers the workload** to absorb bursts and reduce pressure on SharePoint / Microsoft Graph
- **Durable Functions coordinates submission-level processing**
- **YAML drives form and attachment definitions**
- **Azure AI is used for constrained classification, extraction, and soft judgment**
- **Deterministic Python performs exact rule enforcement**
- **The architecture can evolve for much larger scale by splitting heavy stages into separate queues/workers**

---

## High-level architecture

```text
SharePoint Online
  → Azure Function (submission discovery / metadata scan)
  → Azure Service Bus (submission queue)
  → Durable Functions Orchestrator
      → Load YAML definitions
      → Extract text from documents
      → Route form to known form type
      → Route attachments to known attachment types
      → Validate using YAML-driven validation engine
      → Use deterministic Python for exact rules
      → Aggregate results
  → SharePoint CSV output
  → Optional Blob audit artifacts
```

---

## Core design principles

### 1. SharePoint is the source of truth
Original form and attachment files remain in SharePoint. The solution reads them on demand and does not require a permanent duplicate repository in Azure Blob Storage.

### 2. Buffer work, not files
The system uses **Azure Service Bus** as the primary buffering layer. This protects SharePoint / Graph from spikes and lets the processing tier scale independently.

### 3. Submission-level orchestration
Each submission is processed as a single business transaction. The orchestrator coordinates all work for the submission and aggregates the final outcome.

### 4. YAML-driven configuration
Form types and attachment types are pre-defined in YAML. This means the AI layer is not inventing categories. It is choosing from known types and extracting facts against known rules.

### 5. AI for extraction and judgment, code for exact decisions
Azure AI helps with:
- OCR and text extraction
- classifying a form into one of the known form types
- classifying attachments into one of the known attachment types
- extracting names, dates, relationship, and other facts
- soft judgments such as whether a document appears official

Deterministic Python handles:
- required attachment logic
- exact date-window calculations
- name comparison rules
- final pass/fail enforcement

---

## Processing flow

### Step 1. Submission discovery
An Azure Function scans SharePoint metadata, identifies new or changed files, and groups files by the shared submission ID in the filename.

Example:
- `12345_form.pdf`
- `12345_marriage_cert.pdf`
- `12345_birth_cert.jpg`

These are grouped into one submission.

### Step 2. Submission manifest creation
The ingestion function creates a lightweight manifest that includes:
- submission ID
- SharePoint site/library references
- file references
- filenames
- etags or timestamps

This manifest is sent to **Azure Service Bus**.

### Step 3. Durable orchestration
A Durable Functions orchestrator starts for the submission. It controls the workflow but does not hold large document payloads in orchestration state.

### Step 4. Load YAML definitions
The workflow loads:
- known form definitions
- known attachment definitions
- validation rules

These can live in Blob Storage, source control, or another managed configuration store.

### Step 5. Text extraction
Files are fetched from SharePoint on demand and sent to **Azure Document Intelligence** for OCR/text extraction.

### Step 6. YAML-aware routing
The orchestrator routes the form and attachments using known YAML-defined types:

- Form is classified as one of the known form `doc_type` values
- Attachments are classified as one of the known attachment `doc_type` values

This can be done using:
- indicator/rule matching first
- model classification if needed
- manual review for ambiguous cases

### Step 7. YAML-driven validation engine
A generic validation engine evaluates the submission using the matched YAML config.

For example, for this form definition:

```yaml
doc_type: add_dependent_health
display_name: Health Insurance Dependent Addition Form
description: "Form for adding a dependent (spouse or child) to employee health insurance coverage"
required_attachment_types:
  - marriage_certificate
  - birth_certificate
form_validation_rules:
  - "The employee name must be filled out on the form"
  - "The dependent name must be filled out on the form"
  - "A relationship must be selected (spouse or child)"
  - "If spouse is selected, a marriage certificate attachment is required"
  - "If child is selected, a birth certificate attachment is required"
```

And this attachment definition:

```yaml
doc_type: marriage_certificate
display_name: Marriage Certificate
description: "Official government-issued certificate or license of marriage"
indicators:
  - "certificate of marriage"
  - "united in marriage"
  - "marriage license"
  - "joined in marriage"
  - "certificate of marriage registration"
validation_rules:
  - "The names on the certificate must match the employee and/or beneficiary names on the form. A maiden name vs. married name difference is acceptable for marriage certificates — if the first names match and the last name difference can be explained by the marriage, treat it as a match."
  - "The marriage date must be within the last 12 months of the application date from the form they filled out"
  - "The document must appear to be an official government-issued certificate"
```

The engine can evaluate:
- which attachments are required
- whether the required attachment exists
- which facts must be extracted
- which exact rules must be enforced

### Step 8. Deterministic validation
The model extracts facts such as:
- employee name
- dependent name
- relationship
- application date
- marriage date

Python then enforces exact rules such as:
- spouse selected → marriage certificate required
- child selected → birth certificate required
- marriage date must be within 12 months of the application date
- acceptable name variation logic

### Step 9. Aggregation and results
The orchestrator aggregates:
- form-level validation results
- attachment-level validation results
- reasons for pass/fail/review
- final submission status

Results are written back to SharePoint as CSV by form type, and optional audit artifacts can be written to Blob Storage.

---

## Why Service Bus instead of Event Grid as the main buffer

Event Grid is useful for event notification, but **Service Bus is the better primary work buffer** for this solution because it provides:
- durable queueing
- better control of worker pull patterns
- safer burst absorption
- dead-letter handling
- more explicit operational control over backlog

A hybrid pattern is still possible:

```text
SharePoint / Graph event
  → Event Grid
  → Azure Function
  → Service Bus
  → Durable Functions
```

But for the core processing buffer, **Service Bus remains the preferred choice**.

---

## Scaling strategy for larger loads

If load increases significantly, scaling should be managed through **controlled elasticity**, not just raw autoscale.

### Stage 1. Initial scale pattern
Start with:
- one submission queue
- one Durable orchestrator per submission
- bounded concurrency for Graph, OCR, and model calls

### Stage 2. Protect downstream dependencies
Treat these as protected dependencies:
- SharePoint / Graph
- Azure Document Intelligence
- Azure OpenAI / Foundry model endpoints

Do not allow unlimited fan-out. Use concurrency limits and retry with backoff.

### Stage 3. Split heavy stages into separate workers
As load grows, move to a tiered queue model:

```text
submission-intake
  → submission-router
  → ocr-jobs
  → llm-jobs
  → validation-jobs
  → result-writer
```

This allows:
- OCR workers to scale independently
- model workers to scale independently
- validation workers to remain lightweight
- backlog to be visible by stage

### Stage 4. Premium messaging and monitoring
For large-scale production, use **Service Bus Premium** and monitor:
- queue depth
- dead-letter count
- 429 / throttling rates
- OCR latency
- model latency
- SharePoint retry volume

### Stage 5. Future compute options
If the system becomes much larger or needs reserved heavy-batch compute, consider:
- Azure Container Apps jobs/workers
- AKS workers
- Azure Batch

For Phase 1 and likely beyond, **Functions + Durable Functions + Service Bus** is still a strong foundation.

---

## Recommended Azure resources

### Core resources
- **SharePoint Online**
- **Azure Function App**
- **Azure Service Bus Namespace**
  - queue: `submission-intake`
- **Azure Storage Account**
  - Durable Functions runtime state
  - optional audit artifacts
  - optional YAML storage
- **Azure Document Intelligence**
- **Azure OpenAI / Azure AI Foundry model deployments**
- **Azure Key Vault**
- **Application Insights**
- **Log Analytics Workspace**

### Optional resources
- **Azure Event Grid** for event notification in front of Service Bus
- **Azure Table Storage / Cosmos DB / Azure SQL** for searchable status and audit tracking
- **Azure Monitor Alerts**

---

## Exact role of Blob Storage

Blob Storage is included, but it is **not the permanent repository for original SharePoint documents**.

Blob Storage is used for:
- Durable Functions runtime storage
- optional short-lived working artifacts
- optional JSON audit outputs
- optional YAML rule/config storage

It is **not intended to store permanent duplicate copies of originals**.

---

## Router / handler / validator explanation

The logical pattern is:

```text
Durable Orchestrator
  → Router step
      → determine form type from known YAML form definitions
      → determine attachment types from known YAML attachment definitions
  → Validation engine
      → apply form rules
      → apply attachment rules
      → call AI where needed for extraction or soft judgment
      → call deterministic Python for exact checks
  → Aggregate results
```

Because your categories are already defined in YAML, the system should be thought of as a **configuration-driven validation platform**, not a free-form agent system.

### Where Foundry can help
Azure AI Foundry can still be used for:
- constrained classification
- structured extraction
- soft judgments
- future ambiguous-case review experiences

For Phase 1, a **model-endpoint approach** is likely more practical than building a large multi-agent system from the start.

---

## Example output shape

```json
{
  "submission_id": "12345",
  "form_type": "add_dependent_health",
  "form_status": "passed",
  "attachments": [
    {
      "doc_type": "marriage_certificate",
      "status": "passed",
      "reasons": [
        "Marriage certificate is present",
        "Names are consistent with the form",
        "Marriage date is within 12 months of application date",
        "Document appears to be official"
      ]
    }
  ],
  "final_status": "passed"
}
```

---

## Final recommendation

Build Phase 1 as a **YAML-driven, submission-oriented validation platform** on Azure:

- SharePoint as the source of truth
- Azure Function for submission discovery
- Service Bus for buffering
- Durable Functions for orchestration
- Document Intelligence for OCR
- Azure OpenAI / Foundry for constrained classification and extraction
- deterministic Python for exact validation
- SharePoint CSV output for business consumption
- optional Blob audit artifacts for engineering/compliance needs
