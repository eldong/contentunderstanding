You are implementing Milestone 5 of a Document Validation System POC.

## Context
This is a Python project at `c:\work\opm\contentunderstanding`. See `planningdocs/plan.md` for full architecture. Milestones 1-4 are complete \u2014 we have Pydantic contracts, local ingestion, document extraction, and the `FormAnalyzer` with data-driven configs:
- `config/doc_types/*.yaml` \u2014 attachment document types (indicators, validation rules)
- `config/form_types/*.yaml` — life events (required attachment types, form-field validation rules)
Now build the `AttachmentClassifier`.

## Goal
Build the `AttachmentClassifier` class that uses Azure OpenAI GPT-4o to classify an extracted attachment document. Like the form analyzer, it dynamically loads its valid categories and indicators from the same `config/doc_types/*.yaml` files. Returns a `ClassifierResponse` from `src/models.py`.

## Data-Driven Design
The classifier reads `DocTypeConfig` objects (loaded in M4 from `config/doc_types/`) to learn what document types exist, their descriptions, and their textual indicators. Adding a new classifiable type means adding a YAML file — no code changes.

## Files to Create

### `src/classification/attachment_classifier.py`
- `AttachmentClassifier` class — constructor takes:
  - `client: openai.AsyncAzureOpenAI`
  - `deployment: str`
  - `doc_type_configs: list[DocTypeConfig]`
- Method: `async classify(extracted: ExtractedDoc) -> ClassifierResponse`
- Implementation:
  1. Build the system prompt dynamically from `doc_type_configs`:
     - For each config, include its `doc_type`, `display_name`, `description`, and `indicators`
     - Always include `"unknown"` as a fallback category
     ```
     You are a document classifier for HR benefit submissions.
     Given the extracted text of an attachment document, classify it into exactly one of these categories:

     {for each config:}
     - "{doc_type}" — {display_name}: {description}. Look for: {indicators joined by ", "}

     - "unknown" — does not match any of the above categories

     Return ONLY valid JSON matching this exact schema:
     {
       "doc_type": {doc_type_enum},
       "confidence": 0.0 to 1.0,
       "reasoning": "brief explanation of why this classification was chosen"
     }
     ```
  2. Send user message: `"Classify this document:\n\n{extracted.content}"`
  3. Use `response_format={"type": "json_object"}`
  4. Parse response into `ClassifierResponse.model_validate_json(response_content)`
  5. Return the validated result

### `tests/test_classification.py` (append to existing file)
- Add test class `TestAttachmentClassifier` (keep existing `TestFormAnalyzer` tests intact)
- Mock the `openai.AsyncAzureOpenAI` client
- Test cases:
  1. **Marriage certificate** — mock LLM returns `{"doc_type": "marriage_certificate", "confidence": 0.95, "reasoning": "Contains marriage certificate language"}`. Assert fields match.
  2. **Unknown document** — mock LLM returns `{"doc_type": "unknown", "confidence": 0.3, "reasoning": "Document does not match known categories"}`. Assert `doc_type` is `"unknown"`.
  3. **Prompt includes loaded doc types** — assert that the system prompt contains the doc type names and indicators from the configs
- Verify `response_format` is set
- Use `pytest.mark.asyncio` and `unittest.mock.AsyncMock`
- Create `DocTypeConfig` test fixtures directly (don't load from actual YAML in unit tests)

## Acceptance Criteria
- `AttachmentClassifier.classify()` builds its prompt dynamically from doc type configs
- The prompt contains all registered doc types with their descriptions and indicators
- Marriage cert text → `doc_type="marriage_certificate"`
- Random/unrecognizable text → `doc_type="unknown"`
- All tests in `tests/test_classification.py` pass (both `TestFormAnalyzer` and `TestAttachmentClassifier`)
- `pytest tests/test_classification.py` — all pass

## Constraints
- Constructor takes an already-configured `AsyncAzureOpenAI` client (same pattern as `FormAnalyzer`)
- All methods are `async`
- Strict JSON output — `response_format={"type": "json_object"}`
- Doc type categories are fully driven by `config/doc_types/*.yaml` — no hardcoded categories
- Do not modify `FormAnalyzer` or any other existing files except `tests/test_classification.py` (append tests)
- Use `DefaultAzureCredential` from `azure-identity` — no API keys
