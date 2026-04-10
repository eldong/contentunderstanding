# Scaling the Document Validation System — Phase 1

Production architecture for Phase 1: 10,000 submissions per month from a single SharePoint site, 25 form types, validation results written back to SharePoint as CSV.

---

## Phase 1 Assumptions

| Parameter | Value |
|-----------|-------|
| **Source** | Single SharePoint site; files uploaded individually (not zipped) |
| **Volume** | ~10,000 submissions per month (~500/business day) |
| **Form types** | 25 |
| **File naming** | Forms: `{ID}_form.pdf`. Attachments: `{ID}_xx.pdf` or `{ID}_xx.jpg/png` |
| **Grouping** | Submissions are grouped by the shared ID prefix in the filename |
| **Rule ownership** | HR subject matter experts maintain validation rules (YAML configs) |
| **Results destination** | One CSV per form type, stored on the same SharePoint site |

---

## Architecture Overview

```
SharePoint Site (single source of truth for documents)
    │
    ├─ Source document library (forms + attachments)
    │
    ▼
Azure Function (Timer / Graph webhook)
    │  List new/changed files via Microsoft Graph API
    │  Group files by ID prefix → one submission per group
    │  Queue each new submission for processing
    ▼
Azure Queue Storage
    │
    ▼
Azure Function (Queue-triggered processing pipeline)
    │  1. Stream file bytes from SharePoint via Graph API
    │  2. Extract  → Document Intelligence (from byte stream)
    │  3. Classify → GPT-4o (form analyzer + attachment classifier)
    │  4. Validate → GPT-4o (LLM validator per form type)
    │  5. Append result row to CSV on SharePoint
    ▼
SharePoint Site
    └─ Results document library (one CSV per form type)
```

Documents are **never copied** out of SharePoint. The processing function reads file content on demand via the Graph API, streams it to Document Intelligence for extraction, and discards the bytes after processing. Only the extracted text (for caching/retry) and validation results are stored outside SharePoint.

---

## 1. Ingestion — Discovering New Submissions

A timer-triggered Azure Function polls the SharePoint site on a schedule (e.g., every 15 minutes) using the Microsoft Graph API. For each polling cycle it:

1. Lists files in the source document library that have been added or modified since the last poll (using the `delta` endpoint for efficiency).
2. Groups files by the ID prefix in the filename — all files sharing the same ID belong to one submission.
3. Checks each submission ID against a lightweight tracking store (Azure Table Storage) to skip already-processed submissions.
4. Drops a queue message for each new submission containing the ID and the Graph API file references (drive item IDs).

No files are downloaded or copied during ingestion. The function only discovers what's new and queues it for processing.

**Alternative:** Instead of timer polling, register a Graph webhook (change notification) on the document library for near-real-time triggering. Timer polling is simpler to implement and debug; webhooks reduce latency to minutes.

---

## 2. File Identification & Grouping

No LLM classification is needed to determine which file is the form vs. attachments — the naming convention handles it:

- **Form:** filename contains `_form` → e.g., `12345_form.pdf`
- **Attachments:** same ID prefix, any other suffix → e.g., `12345_01.pdf`, `12345_02.jpg`

The ingestion function groups files by ID prefix and identifies the form file by the `_form` suffix. This is the same pattern the POC uses (file with "form" in the name), now applied to a naming convention rather than a substring match.

**Form type classification** still requires an LLM call. With 25 form types, a single GPT-4o call with all 25 type definitions in the prompt is practical — the prompt stays well within token limits and classification accuracy is high. This is the same approach the POC uses today, scaled from 1 to 25 types with no architectural change.

**Attachment classification** also uses a single GPT-4o call per attachment, matching against the document type configs. Same as the POC.

---

## 3. Processing Pipeline

A queue-triggered Azure Function picks up each submission message and runs the full pipeline:

### Step 1: Fetch & Extract
For each file in the submission, stream the file bytes from SharePoint via the Graph API download endpoint. Pass the byte stream directly to Azure Document Intelligence (prebuilt read model) — no intermediate storage. Cache the extracted text in Azure Table Storage (keyed by file ID + last-modified timestamp) so retries and reprocessing don't re-extract.

### Step 2: Form Analysis
Send the extracted form text to GPT-4o with the 25 form type definitions. Returns the identified form type, life event, and key field values. Same as the POC's `FormAnalyzer`.

### Step 3: Attachment Classification
For each attachment, send the extracted text to GPT-4o with the document type definitions. Returns the document type for each attachment. Same as the POC's `AttachmentClassifier`.

### Step 4: Validation
Look up the validation rules for the identified form type (from YAML config). Run `LLMValidator` for each applicable rule — same as the POC. Collect all rule results into a `ValidationResult`.

### Step 5: Write Results
Append the validation result as a row to the CSV for that form type directly on SharePoint (see section 5). Update the tracking record in Table Storage to mark the submission as processed.

### Concurrency & Throughput

At 500 submissions/day, the processing load is modest:

| Metric | Estimate |
|--------|----------|
| Submissions per day | ~500 |
| Document Intelligence calls per day | ~1,500 (avg 3 files per submission) |
| GPT-4o calls per day | ~2,500 (1 form analysis + 1 per attachment + validation calls) |
| Processing time per submission | ~30–60 seconds |
| Concurrent functions needed | 5–10 (assuming steady flow, not all at once) |

Azure Functions on the **Consumption plan** handles this comfortably. No need for Premium or dedicated plans at this volume. If processing clusters around certain times of day, Functions auto-scales to handle the burst.

---

## 4. Configuration Management

### YAML Configs in Git

The 25 form type configs (`config/form_types/*.yaml`) and their associated document type configs (`config/doc_types/*.yaml`) live in the Git repository, same as the POC. Deploying the Azure Function app deploys the configs with it.

### HR SME Workflow for Rule Changes

HR subject matter experts own the validation rules. For Phase 1, the workflow for rule changes is:

1. HR SME describes the rule change (e.g., "marriage certificates must now be dated within 24 months instead of 12").
2. A developer updates the YAML config and submits a pull request.
3. The PR is reviewed and merged.
4. CI/CD redeploys the Function app with the updated config.

This is simple and auditable. Every rule change is tracked in Git with full history. Phase 2 could introduce a self-service UI for HR SMEs to edit rules directly, with automated testing and approval workflows.

### Adding a New Form Type

Adding a new form type means adding a YAML file — no Python code changes. The process:

1. Create `config/form_types/{new_type}.yaml` with the form definition, required attachment types, and validation rules.
2. Create any new `config/doc_types/*.yaml` files for attachment types not already defined.
3. Test against sample documents.
4. Deploy.

---

## 5. Results — CSV to SharePoint

Validation results are stored as one CSV per form type. Each row represents one submission's validation outcome.

### CSV Structure (per form type)

| Column | Description |
|--------|-------------|
| `submission_id` | The ID prefix from the filename |
| `submitted_by` | From metadata if available |
| `processed_date` | Timestamp of validation |
| `form_status` | `pass` / `fail` / `error` |
| `attachment_count` | Number of attachments in the submission |
| `missing_attachments` | Comma-separated list of required but missing doc types |
| `rule_results` | Summary of each rule: rule name + pass/fail |
| `failure_reasons` | Human-readable explanation of any failures |
| `confidence` | Overall confidence score |

### Writing Results to SharePoint

The processing function appends each result row to the appropriate CSV on SharePoint via the Graph API. To handle concurrent writes safely:

1. Each processing function instance acquires a short lease (Azure Blob lease on a lock blob per form type) before writing.
2. Downloads the current CSV from SharePoint, appends the new row, and uploads the updated file.
3. Releases the lease.

At ~500 submissions/day spread across 25 form types, write contention is minimal (~20 writes per type per day). The lease pattern is a simple safeguard, not a bottleneck.

**Alternative:** If write contention becomes an issue, batch results in Table Storage and use a timer-triggered function to flush them to the SharePoint CSVs periodically.

---

## 6. Azure Services Summary

| Layer | Service | Purpose |
|-------|---------|---------|
| **Document storage** | SharePoint (existing) | Single source of truth — documents stay here, never copied |
| **Ingestion** | Azure Functions (timer trigger) + Microsoft Graph API | Discover new files, group by ID, queue for processing |
| **Queue** | Azure Queue Storage | Decouple ingestion from processing, handle retries |
| **Tracking & cache** | Azure Table Storage | Track processed submissions, cache extracted text |
| **Extraction** | Azure Document Intelligence (prebuilt read) | OCR / text extraction for PDFs and images |
| **Classification** | Azure OpenAI GPT-4o | Form type identification, attachment classification |
| **Validation** | Azure OpenAI GPT-4o | Rule evaluation via LLM |
| **Results** | SharePoint (same site) + Microsoft Graph API | CSV per form type written directly to SharePoint |
| **Config** | Git repository (YAML files) | Form type and doc type definitions |
| **Auth** | DefaultAzureCredential / Managed Identity | No API keys; Function app uses system-assigned identity |
| **Monitoring** | Application Insights | Processing times, failure rates, LLM latency |

---

## 7. Cost Estimate (Phase 1)

Rough monthly estimates at 10,000 submissions/month, assuming ~3 files per submission (1 form + 2 attachments) and ~3 pages per file:

| Service | Usage | Estimated Monthly Cost |
|---------|-------|----------------------|
| **Azure Functions** (Consumption) | ~10K executions, ~150K seconds | < $5 (likely free tier) |
| **Azure Table + Queue Storage** | Tracking records + queue messages | < $2 |
| **Document Intelligence** (prebuilt read) | ~30K files × 3 pages = 90K pages | ~$900 (at $0.01/page) |
| **Azure OpenAI GPT-4o** | ~75K calls (classification + validation) | ~$500–$1,500 (depends on token volume) |
| **Application Insights** | Logging and metrics | < $10 |
| **Total** | | **~$1,400–$2,400/month** |

Document Intelligence is the largest cost driver. Optimizations:
- Cache extracted text — never re-extract the same file.
- For image attachments (JPG/PNG), consider whether GPT-4o vision can extract the needed information directly, skipping Document Intelligence for simple documents.
- Use the `prebuilt-read` model (cheapest) unless specific form fields need the `prebuilt-layout` or custom models.

---

## 8. Monitoring & Operations

### Key Metrics to Track

- **Submissions processed per day** — expected ~500, alert if significantly lower (ingestion issue) or higher (unexpected spike)
- **Processing failures by form type** — sudden spike means a rule config issue or document format change
- **LLM call latency (P50/P95)** — baseline and alert on degradation
- **Document Intelligence errors** — rate limit hits, unsupported formats
- **SharePoint write status** — confirm CSVs are being updated successfully

### Application Insights Dashboard

A single Azure Monitor dashboard showing:
- Daily submission count (trend)
- Pass/fail ratio by form type
- Average processing time per submission
- Error count by stage (extraction, classification, validation)
- Queue depth / backlog (Azure Queue Storage)

---

## 9. What This Doesn't Cover (Future Phases)

| Concern | Phase 1 Approach | Future Phase |
|---------|-----------------|--------------|
| **Multiple SharePoint sites** | Single site | Expand ingestion to poll multiple sites or use a central upload portal |
| **Self-service rule editing** | Developer edits YAML via PR | Web UI for HR SMEs to edit rules directly with validation and preview |
| **Real-time processing** | Timer polling (15-min intervals) | Graph webhooks or event-driven for near-real-time |
| **Results in HR systems** | CSV on SharePoint | API integration with HRIS, case management, or a dedicated review UI |
| **Human review workflow** | Not included | Exception queue with UI for HR to review flagged submissions |
| **Volume beyond 10K/month** | Single Function app | Service Bus routing, parallel processing, queue-per-type architecture |
| **Audit / compliance** | Git history for rules, SharePoint for documents | Dedicated audit log, retention policies, data classification |

---

## Summary

Phase 1 takes the proven POC pipeline — extract, classify, validate with YAML-driven rules — and deploys it as a set of Azure Functions connected to a single SharePoint site. The architecture is deliberately simple:

- **SharePoint** is both the document store and the results destination — no duplication.
- **Azure Functions** orchestrates everything on a serverless, pay-per-use model.
- **Azure Table Storage** provides lightweight tracking and extracted-text caching.
- **GPT-4o** handles classification and validation, same as the POC.
- **CSV per form type** gives HR immediate, familiar access to results.

At 10K submissions/month with 25 form types, this architecture stays well within the capacity of Azure Functions Consumption plan and standard Azure OpenAI quotas. The same data-driven YAML config pattern from the POC scales directly — adding a new form type is still just adding a YAML file.
