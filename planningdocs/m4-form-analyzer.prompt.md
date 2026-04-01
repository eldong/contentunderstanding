You are implementing Milestone 4 of a Document Validation System POC.

## Context
This is a Python project at `c:\work\opm\contentunderstanding`. See `planningdocs/plan.md` for full architecture. Milestones 1-3 are complete — we have Pydantic contracts, local ingestion, and document extraction (mock + Azure Doc Intelligence).

## Goal
Build the `FormAnalyzer` class that uses Azure OpenAI GPT-4o to analyze extracted form text and determine: (1) form type, (2) life event / reason selected, (3) employee and beneficiary names. Returns a `FormAnalysisResult` from `src/models.py`.

## Files to Create

### `src/classification/form_analyzer.py`
- `FormAnalyzer` class — constructor takes an `openai.AsyncAzureOpenAI` client and `deployment: str` (model deployment name)
- Method: `async analyze(extracted: ExtractedDoc) -> FormAnalysisResult`
- Implementation:
  1. Build a system prompt:
     ```
     You are a document analyst specializing in HR benefits forms.
     Given the extracted text of a form, determine:
     1. Is this an "Add Beneficiary to employer-sponsored health plan" form? If yes, set form_type to "add_beneficiary". Otherwise set form_type to "unknown".
     2. What reason/life event is selected on the form? Look for checkboxes or indicators like Marriage, Birth, Adoption, Court Order, New Hire, etc. Set reason to the lowercase event name (e.g., "marriage", "birth", "adoption") or null if none found.
     3. Extract the employee's first and last name.
     4. Extract the beneficiary's first name.
     5. Set is_relevant to true ONLY if form_type is "add_beneficiary" AND a reason is selected.

     Return ONLY valid JSON matching this exact schema:
     {
       "form_type": "add_beneficiary" | "unknown",
       "reason": "marriage" | "birth" | "adoption" | "court_order" | "new_hire" | null,
       "employee_first_name": "string or null",
       "employee_last_name": "string or null",
       "beneficiary_first_name": "string or null",
       "is_relevant": true | false
     }
     ```
  2. Send the user message with the extracted text: `"Analyze this form:\n\n{extracted.content}"`
  3. Use `response_format={"type": "json_object"}` to enforce JSON output
  4. Parse the response JSON into `FormAnalysisResult` using `FormAnalysisResult.model_validate_json(response_content)`
  5. Return the validated result

### `tests/test_classification.py`
- Create test class `TestFormAnalyzer`
- Mock the `openai.AsyncAzureOpenAI` client — mock `client.chat.completions.create()` to return a fake completion with JSON content
- Test cases:
  1. **Relevant form** — mock LLM returns `{"form_type": "add_beneficiary", "reason": "marriage", "employee_first_name": "Jane", "employee_last_name": "Smith", "beneficiary_first_name": "Michael", "is_relevant": true}`. Assert `FormAnalysisResult` fields match.
  2. **Irrelevant form** — mock LLM returns `{"form_type": "unknown", "reason": null, ... "is_relevant": false}`. Assert `is_relevant` is False.
  3. **Form with no reason selected** — mock LLM returns `{"form_type": "add_beneficiary", "reason": null, ... "is_relevant": false}`. Assert `is_relevant` is False (form type matches but no reason).
- Verify the system prompt is passed correctly (assert on the messages list sent to the API)
- Verify `response_format` is set to `{"type": "json_object"}`
- Use `pytest.mark.asyncio` for all tests
- Use `unittest.mock.AsyncMock` for mocking the async OpenAI client

## Acceptance Criteria
- `FormAnalyzer.analyze()` sends a well-structured prompt to Azure OpenAI and parses the JSON response into `FormAnalysisResult`
- Mock tests cover: relevant form, irrelevant form, missing reason
- The system prompt clearly instructs the LLM to return the exact JSON schema
- `response_format={"type": "json_object"}` is always used
- `pytest tests/test_classification.py::TestFormAnalyzer` — all tests pass

## Constraints
- The `FormAnalyzer` constructor takes an already-configured `AsyncAzureOpenAI` client — it does NOT load env vars or create the client itself (that's the CLI's job in `main.py`)
- All methods are `async`
- Do not import or depend on ingestion, extraction, or validator modules
- Strict JSON output only — no free-text LLM responses
- Do not add new dependencies
