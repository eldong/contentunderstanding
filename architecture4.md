# Architecture: HR Benefits Submission Validation

## Overview

This system automates validation of HR benefits submissions. Each submission consists of a form (e.g., a health insurance dependent addition) and one or more supporting attachments (e.g., a marriage certificate or birth certificate). The system extracts text, classifies documents, validates them against configurable business rules, and writes results back to SharePoint.

The architecture is a submission-level pipeline orchestrated by Azure Durable Functions, with Azure Document Intelligence for OCR, Azure OpenAI for classification and soft judgment, and deterministic Python for exact rule enforcement.

### Volume Assumptions

| Metric | Estimate |
|--------|----------|
| Total submissions per year | ~50,000 |
| Average working days per year | ~250 |
| **Submissions per day (average)** | **~200** |
| Peak multiplier (open enrollment, life events) | 3–5× |
| **Submissions per day (peak)** | **~600–1,000** |
| Working hours per day | ~8 |
| **Submissions per hour (average)** | **~25** |
| **Submissions per hour (peak)** | **~75–125** |
| Average attachments per submission | 1–2 |
| **Total documents per submission (form + attachments)** | **2–3** |
| **Document Intelligence calls per hour (average)** | **~50–75** |
| **Document Intelligence calls per hour (peak)** | **~150–375** |
| **OpenAI calls per submission** | **3–5** (1 form analysis + 1 classification per attachment + 1 validation per attachment) |
| **OpenAI calls per hour (average)** | **~75–125** |
| **OpenAI calls per hour (peak)** | **~225–625** |

At average load this is a light workload — well within default service tier limits. The architecture is designed to handle peak periods and future growth without rearchitecting. The Service Bus buffer, Durable Functions concurrency, and per-service rate limiting mean that a burst of 1,000 submissions arriving in a single morning does not translate into 1,000 simultaneous calls to downstream services.

### Processing Bottlenecks

Three external services dominate processing time and impose rate/throughput constraints. The architecture is designed around them.

| Bottleneck | Why It's Slow | Constraint Type | Mitigation |
|------------|---------------|-----------------|------------|
| **Azure Document Intelligence** | OCR is computationally expensive. Each document requires image rendering, layout analysis, and text extraction. A single call typically takes 2–10 seconds depending on page count and complexity. Every document in a submission (form + all attachments) must pass through it. | Throughput — limited transactions per second on the resource. Latency — seconds per document. | Fan-out extraction of attachments in parallel within a submission. Service Bus buffering prevents overloading the endpoint during submission bursts. Concurrency limits cap simultaneous calls. |
| **Azure OpenAI (GPT-4o)** | LLM inference is the most expensive per-call operation. The system makes multiple calls per submission: one for form analysis, one per attachment for classification, and one per attachment for validation. Each call involves prompt construction, token processing, and structured JSON response parsing. Latency is typically 1–5 seconds per call, and token-per-minute quotas can throttle throughput. | Throughput — tokens-per-minute (TPM) and requests-per-minute (RPM) quotas on the deployment. Latency — seconds per call. Cost — token consumption scales with document length and rule count. | Prompts are built once at startup and reused. Classification and validation are constrained to known YAML-defined types (shorter, more focused prompts). The hybrid validation approach offloads date math to deterministic Python, avoiding unnecessary LLM retries on date comparisons. Service Bus absorbs bursts upstream so LLM calls arrive at a controlled rate. |
| **SharePoint / Microsoft Graph** | The system reads original files from SharePoint on demand. Graph API has per-tenant and per-app throttling (HTTP 429). File downloads are I/O-bound and subject to network latency. During high submission volumes, concurrent file fetches can trigger throttling. | Throughput — Graph API rate limits per app registration. Latency — network round-trip per file download. | Files are fetched on demand (not bulk-copied), reducing unnecessary reads. Service Bus decouples submission arrival from processing, spreading file fetches over time. The orchestrator fetches files only when the activity needs them, not all upfront. Retry with exponential backoff handles transient Graph throttling. |

The rest of the pipeline — YAML config loading, deterministic Python rule checks, and result writing — is fast and cheap. The architecture concentrates its buffering, concurrency control, and parallelism strategies around these three external service bottlenecks.

## Architecture Diagram

See [architecture4-mermaid.mmd](architecture4-mermaid.mmd) for the full Mermaid diagram and [architecture4-high.mmd](architecture4-high.mmd) for the simplified business view.

## Azure Services

| Service | Role |
|---------|------|
| **SharePoint Online** | System of record. HR staff upload forms and attachments here. Validation results are written back as CSV. |
| **Azure Functions** | Hosts the ingestion function (submission discovery) and the Durable Functions orchestrator. |
| **Azure Service Bus** | Buffers submission work items between ingestion and processing. Absorbs bursts, supports retries and dead-lettering. |
| **Azure Durable Functions** | Coordinates the per-submission workflow. Each submission gets its own orchestration instance that sequences extraction, classification, validation, and result writing. |
| **Azure Document Intelligence** | OCR and text extraction from PDFs, images, and scanned documents using the `prebuilt-read` model. |
| **Azure OpenAI / AI Foundry** | GPT-4o for form analysis, attachment classification, fact extraction, and soft validation judgments. All prompts are constrained to known types defined in YAML. |
| **Azure Storage** | Durable Functions runtime state and optional audit artifacts. Not used to store permanent copies of original documents. |

## Processing Flow

### 1. Submission Discovery

An Azure Function scans SharePoint for new or changed files and groups them by submission ID. It reads metadata only — no file content is downloaded at this stage. The function produces a lightweight submission manifest and sends it to Azure Service Bus.

### 2. Queuing

Azure Service Bus holds the submission manifest until the processing tier is ready. This decouples ingestion from processing, protects downstream services from load spikes, and provides dead-letter handling for failed submissions.

### 3. Orchestration

A Durable Functions orchestrator picks up the queued submission and coordinates all subsequent activities. Each submission is an independent workflow instance. The orchestrator does not hold large document payloads in its state.

### 4. Extract Form Text

The orchestrator fetches the form file from SharePoint and sends it to Azure Document Intelligence for OCR. The result is structured text with extracted key-value pairs and word-level confidence scores.

### 5. Extract Attachment Text

Each attachment is extracted in parallel (fan-out). The same Document Intelligence `prebuilt-read` model is used. Each attachment produces an independent text extraction result.

### 6. Analyze Form

The extracted form text is sent to Azure OpenAI (GPT-4o) along with a prompt built dynamically from all known form type definitions in YAML. The model determines:

- **Form type** — which HR action this form represents (e.g., `add_dependent_health`)
- **Reason / life event** — the specific reason for the submission (e.g., marriage, birth of child)
- **Key facts** — employee name, beneficiary name, relationship
- **Relevance** — whether this form type is one the system knows how to validate

The model chooses from a closed set of known form types. It does not invent categories.

### 7. Relevance Check

If the form type is not recognized or not relevant, the orchestrator writes an error result and stops processing. No further classification or validation is attempted.

### 8. Classify Attachments

Each attachment's extracted text is sent to Azure OpenAI with a prompt built from all known attachment type definitions in YAML. The model classifies each attachment as one of the known document types (e.g., `marriage_certificate`, `birth_certificate`) or `unknown`. Each classification includes a confidence score and reasoning.

Like form analysis, this is constrained classification — the model selects from pre-defined types, not open-ended categorization.

### 9. Validate Submission

Validation is driven by YAML configuration. Each document type defines validation rules in plain English:

```yaml
# Example: config/doc_types/marriage_certificate.yaml
validation_rules:
  - "The names on the certificate must match the employee and/or beneficiary names on the form"
  - "The marriage date must be within the last 12 months of the application date from the form"
  - "The document must appear to be an official government-issued certificate"
```

A generic validation engine (`LLMValidator`) sends the form text, attachment text, and rule list to Azure OpenAI. The model evaluates each rule and returns a pass/fail judgment with an explanation.

**Hybrid approach for date rules:** The LLM extracts dates and identifies the comparison window, but Python performs the actual date arithmetic deterministically. This avoids LLM unreliability with date math while keeping YAML rules in plain English.

**Deterministic Python** also handles:
- Required attachment checks (based on form type configuration)
- Name matching and normalization
- Any rule where exact enforcement is needed

Each rule produces a `RuleResult` with the rule text, pass/fail status, and a detail explanation. The overall submission status is `passed` if all rules pass, `failed` if any fail, or `error` if processing could not complete.

### 10. Write Results

Results are written back to SharePoint as CSV organized by form type. Each result includes the submission ID, form name, submitter, document type, overall status, and per-rule details.

## YAML-Driven Configuration

The system is designed so that adding support for a new form type or attachment type requires only adding a YAML file — no Python code changes.

**Form types** (`config/form_types/`) define HR actions and their requirements:

```yaml
doc_type: add_dependent_health
display_name: Health Insurance Dependent Addition Form
description: "Form for adding a dependent to employee health insurance coverage"
required_attachment_types:
  - marriage_certificate
  - birth_certificate
form_validation_rules:
  - "The employee name must be filled out on the form"
  - "A relationship must be selected (spouse or child)"
```

**Document types** (`config/doc_types/`) define attachment types the system can recognize and validate:

```yaml
doc_type: marriage_certificate
display_name: Marriage Certificate
description: "Official government-issued certificate or license of marriage"
indicators:
  - "certificate of marriage"
  - "marriage license"
validation_rules:
  - "The names on the certificate must match the employee and/or beneficiary names"
  - "The marriage date must be within the last 12 months of the application date"
  - "The document must appear to be an official government-issued certificate"
```

The `FormAnalyzer`, `AttachmentClassifier`, and `ValidatorRegistry` all build their prompts and lookup tables dynamically from these YAML files at startup.

## Authentication

All Azure service calls use `DefaultAzureCredential` from `azure-identity`. No API keys are stored or passed. Locally, developers run `az login`. In production, managed identity is used.

## Error Handling

The orchestrator catches exceptions at every stage and continues processing:

| Stage | On Error | Behavior |
|-------|----------|----------|
| Form extraction | `status: error` | Skip entire submission |
| Form analysis | `status: error` | Skip entire submission |
| Form not relevant | `status: error` | Skip (no matching form type) |
| Attachment extraction | `status: error` | Skip this attachment, continue others |
| Attachment classification | `status: error` | Skip this attachment, continue others |
| No validator registered | `status: failed` | Record failure, continue others |
| Validation exception | `status: error` | Record error, continue others |

## Scaling Considerations

The architecture supports scaling through several mechanisms:

- **Service Bus** absorbs bursts and lets the processing tier scale independently
- **Durable Functions** fan-out enables parallel attachment processing within a submission
- **Concurrency limits** protect downstream dependencies (SharePoint/Graph, Document Intelligence, OpenAI) from overload
- **Future option:** Split heavy stages (OCR, LLM calls, validation) into separate queues with independent worker pools for stage-level scaling
