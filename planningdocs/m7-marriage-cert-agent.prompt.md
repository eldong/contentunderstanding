You are implementing Milestone 7 of a Document Validation System POC.

## Context
This is a Python project at `c:\work\opm\contentunderstanding`. See `planningdocs/plan.md` for full architecture. Milestones 1-6 are complete — we have contracts, ingestion, extraction, form analyzer, attachment classifier, and a data-driven validator framework. The `LLMValidator` class (built in M6) reads validation rules from `config/doc_types/*.yaml` and builds GPT-4o prompts dynamically. The `config/doc_type_rules/*.yaml` files define required attachment types (`required_attachment_types`) and form-field validation rules (`form_validation_rules`) per life event.

## Goal
This milestone is now about **end-to-end validation testing** with the marriage certificate doc type. The `LLMValidator` and `config/doc_types/marriage_certificate.yaml` already exist. We need to:
1. Verify the marriage certificate validation rules produce correct results
2. Create thorough tests for the specific marriage certificate scenarios
3. Optionally refine the `marriage_certificate.yaml` rules if the LLM responses aren't accurate enough

## What Already Exists
- `config/doc_types/marriage_certificate.yaml` — defines rules like name matching, date recency, and official document check
- `src/validators/llm_validator.py` — generic validator that builds prompts from YAML rules
- `src/validators/registry.py` — auto-discovers configs and creates `LLMValidator` instances

## Files to Create / Edit

### `tests/test_validators.py` (append test class)
- Add `TestMarriageCertificateValidation` class — tests the `LLMValidator` specifically with marriage certificate config
- Mock the `openai.AsyncAzureOpenAI` client
- Test cases:
  1. **All rules pass** — mock LLM returns all rules passed. Assert `status="pass"`, `reasons=[]`.
  2. **Employee name missing** — mock returns name rule failed. Assert `status="fail"`, reason includes name mismatch.
  3. **Beneficiary name missing** — mock returns beneficiary rule failed. Assert `status="fail"` + reason.
  4. **Date too old** — mock returns date rule failed. Assert `status="fail"` + `"older than 12 months"` or similar in reasons.
  5. **Not an official document** — mock returns official doc rule failed. Assert `status="fail"` + reason.
  6. **Multiple failures** — multiple rules fail. Assert `status="fail"` with multiple reasons.
- Verify the system prompt includes the employee/beneficiary names from `form_analysis`
- Verify the system prompt includes all `validation_rules` from the marriage certificate config
- Use `pytest.mark.asyncio` and `unittest.mock.AsyncMock`

### `config/doc_types/marriage_certificate.yaml` (refine if needed)
- Review and refine the validation rules to ensure they produce clear, testable LLM outputs
- Ensure rules cover: name matching (employee + beneficiary), date recency, official document verification

## Acceptance Criteria
- Marriage certificate with matching names + recent date → `status="pass"`, `reasons=[]`
- Missing name → `status="fail"` with specific reason
- Old date → `status="fail"` with date-related reason
- Multiple failures → `status="fail"` with all applicable reasons
- The `LLMValidator` handles marriage certificate validation entirely via config — no marriage-specific Python code
- `pytest tests/test_validators.py` — all tests pass (registry tests + marriage cert tests)

## Constraints
- No `MarriageCertificateAgent` class — the generic `LLMValidator` handles everything
- All validation logic comes from `config/doc_types/marriage_certificate.yaml` rules
- Do not modify `LLMValidator` or `ValidatorRegistry` — only test and refine the YAML config
- Use `DefaultAzureCredential` from `azure-identity` — no API keys
- Do not call Azure in automated tests — mock only

## Constraints
- Constructor pattern: keep it compatible with the registry's dynamic instantiation
- Use `datetime.date.today()` for the current date (makes it testable — can be mocked)
- Strict JSON output — `response_format={"type": "json_object"}`
- Do not modify `base.py` or `registry.py` unless strictly necessary
- Do not add new dependencies
