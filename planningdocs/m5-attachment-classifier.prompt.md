You are implementing Milestone 5 of a Document Validation System POC.

## Context
This is a Python project at `c:\work\opm\contentunderstanding`. See `planningdocs/plan.md` for full architecture. Milestones 1-4 are complete — we have Pydantic contracts, local ingestion, document extraction, and the `FormAnalyzer`. Now build the `AttachmentClassifier`.

## Goal
Build the `AttachmentClassifier` class that uses Azure OpenAI GPT-4o to classify an extracted attachment document into a known doc type (e.g., `marriage_certificate`, `birth_certificate`, `court_order`, `unknown`). Returns a `ClassifierResponse` from `src/models.py`.

## Files to Create

### `src/classification/attachment_classifier.py`
- `AttachmentClassifier` class — constructor takes an `openai.AsyncAzureOpenAI` client and `deployment: str`
- Method: `async classify(extracted: ExtractedDoc) -> ClassifierResponse`
- Implementation:
  1. Build a system prompt:
     ```
     You are a document classifier for HR benefit submissions.
     Given the extracted text of an attachment document, classify it into exactly one of these categories:
     - "marriage_certificate" — a marriage certificate, marriage license, or certificate of marriage
     - "birth_certificate" — a birth certificate or certificate of live birth
     - "court_order" — a court order, legal decree, or qualified domestic relations order
     - "unknown" — does not match any of the above categories

     Return ONLY valid JSON matching this exact schema:
     {
       "doc_type": "marriage_certificate" | "birth_certificate" | "court_order" | "unknown",
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
  3. **Birth certificate** — mock LLM returns birth_certificate classification. Assert correct doc_type.
- Verify system prompt contains all valid doc type categories
- Verify `response_format` is set
- Use `pytest.mark.asyncio` and `unittest.mock.AsyncMock`

## Acceptance Criteria
- `AttachmentClassifier.classify()` sends a prompt to Azure OpenAI and returns a typed `ClassifierResponse`
- Marriage cert text → `doc_type="marriage_certificate"`
- Random/unrecognizable text → `doc_type="unknown"`
- All tests in `tests/test_classification.py` pass (both `TestFormAnalyzer` and `TestAttachmentClassifier`)
- `pytest tests/test_classification.py` — all pass

## Constraints
- Constructor takes an already-configured `AsyncAzureOpenAI` client (same pattern as `FormAnalyzer`)
- All methods are `async`
- Strict JSON output — `response_format={"type": "json_object"}`
- The doc type categories must be extensible — when a new doc type is added in the future, only this prompt needs updating (plus a new validator + registry entry)
- Do not modify `FormAnalyzer` or any other existing files except `tests/test_classification.py` (append tests)
