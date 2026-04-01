You are implementing Milestone 7 of a Document Validation System POC.

## Context
This is a Python project at `c:\work\opm\contentunderstanding`. See `planningdocs/plan.md` for full architecture. Milestones 1-6 are complete — we have contracts, ingestion, extraction, form analyzer, attachment classifier, and a validator registry with a stub `MarriageCertificateAgent`. Now implement the real agent.

## Goal
Implement `MarriageCertificateAgent` — a validator that uses Azure OpenAI GPT-4o to verify a marriage certificate attachment against the form data (employee name, beneficiary name, certificate date).

## Files to Edit

### `src/validators/marriage_certificate.py` (replace the stub)
- `MarriageCertificateAgent(BaseValidator)` — constructor takes an `openai.AsyncAzureOpenAI` client and `deployment: str`
- Method: `async validate(form_analysis: FormAnalysisResult, attachment_extracted: ExtractedDoc) -> ValidationResult`
- Implementation:
  1. Build a system prompt:
     ```
     You are a document validator for HR benefit submissions.
     You are given the extracted text of a marriage certificate. Your job is to verify the following:

     1. Does the certificate contain the employee's name: "{employee_first_name} {employee_last_name}"?
        Look for exact or close matches (e.g., middle names, maiden names are acceptable).
     2. Does the certificate contain the beneficiary's name: "{beneficiary_first_name}"?
        Look for the first name appearing anywhere on the certificate.
     3. What is the date on the certificate (the date of the marriage ceremony)?
        Extract it as an ISO date string (YYYY-MM-DD) if found.
     4. Is the certificate date within the last 12 months from today ({today_date})?

     Return ONLY valid JSON matching this exact schema:
     {
       "found_employee_name": true | false,
       "found_beneficiary_name": true | false,
       "certificate_date": "YYYY-MM-DD" | null,
       "is_date_valid": true | false
     }
     ```
  2. Insert the actual employee name, beneficiary name, and today's date into the prompt
  3. Send user message: `"Verify this marriage certificate:\n\n{attachment_extracted.content}"`
  4. Use `response_format={"type": "json_object"}`
  5. Parse the JSON response
  6. Build the `ValidationResult`:
     - `submission_id` — pass through (this will come from the orchestrator; for now accept it as a parameter or use a default)
     - `form_name` — `"Add Beneficiary"`
     - `submitted_by` — pass through
     - Collect `reasons` list:
       - If `found_employee_name` is False → add `"Employee name not found on certificate"`
       - If `found_beneficiary_name` is False → add `"Beneficiary name not found on certificate"`
       - If `certificate_date` is None → add `"Certificate date not found"`
       - If `is_date_valid` is False and `certificate_date` is not None → add `"Certificate date is older than 12 months"`
     - `status` = `"pass"` if `reasons` is empty, else `"fail"`
     - `timestamp` = auto-generated (the Pydantic default handles this)

- **Note on constructor args**: The registry currently calls no-arg constructors. You have two options:
  - Option A: Add `client` and `deployment` as optional fields with `None` defaults, and add a `configure(client, deployment)` method the orchestrator calls after getting the validator from the registry
  - Option B: Have the registry pass kwargs from YAML config — but keep it simple for POC
  - **Recommended**: Option A — add a `configure()` method. The validate() method should raise if not configured.

### `src/validators/registry.py` (minor update if needed)
- If using the `configure()` pattern, no changes needed to the registry — the orchestrator will call `configure()` after `get_validator()`.

### `tests/test_validators.py` (append test class)
- Add `TestMarriageCertificateAgent` class
- Mock the `openai.AsyncAzureOpenAI` client
- Test cases:
  1. **All checks pass** — mock LLM returns `{"found_employee_name": true, "found_beneficiary_name": true, "certificate_date": "2026-02-14", "is_date_valid": true}`. Assert `status="pass"`, `reasons=[]`.
  2. **Employee name missing** — mock returns `found_employee_name: false`. Assert `status="fail"`, `"Employee name not found on certificate"` in reasons.
  3. **Beneficiary name missing** — `found_beneficiary_name: false`. Assert fail + reason.
  4. **Date too old** — `certificate_date: "2024-06-01"`, `is_date_valid: false`. Assert fail + `"Certificate date is older than 12 months"`.
  5. **Date not found** — `certificate_date: null`, `is_date_valid: false`. Assert fail + `"Certificate date not found"`.
  6. **Multiple failures** — both names missing + date too old. Assert `status="fail"` with 3 reasons.
- Verify the system prompt includes the employee/beneficiary names from `form_analysis`
- Use `pytest.mark.asyncio` and `unittest.mock.AsyncMock`

## Acceptance Criteria
- `MarriageCertificateAgent.validate()` sends a well-structured prompt with employee/beneficiary names + today's date
- Certificate with matching names + recent date → `status="pass"`, `reasons=[]`
- Missing name → `status="fail"` with specific reason
- Old date → `status="fail"` with `"Certificate date is older than 12 months"`
- Multiple failures → `status="fail"` with all applicable reasons
- `pytest tests/test_validators.py` — all tests pass (registry tests + agent tests)

## Constraints
- Constructor pattern: keep it compatible with the registry's dynamic instantiation
- Use `datetime.date.today()` for the current date (makes it testable — can be mocked)
- Strict JSON output — `response_format={"type": "json_object"}`
- Do not modify `base.py` or `registry.py` unless strictly necessary
- Do not add new dependencies
