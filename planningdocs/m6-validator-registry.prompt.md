You are implementing Milestone 6 of a Document Validation System POC.

## Context
This is a Python project at `c:\work\opm\contentunderstanding`. See `planningdocs/plan.md` for full architecture. Milestones 1-5 are complete — we have contracts, ingestion, extraction, form analyzer, and attachment classifier. Classification is data-driven via:
- `config/doc_types/*.yaml` — attachment document types (indicators, validation rules)
- `config/form_types/*.yaml` — life events (required attachment types, form-field validation rules)
Now build the validator framework that uses the same config files.

## Goal
Build the pluggable validator architecture: a `BaseValidator` ABC and a `ValidatorRegistry` that auto-discovers doc types from `config/doc_types/` and creates a generic `LLMValidator` for each. No per-type Python classes needed — validation rules come from the YAML config files.

## Data-Driven Design
Instead of a separate `registry.yaml` and per-type validator classes, the registry auto-discovers `config/doc_types/*.yaml` files (already created in M4). Each file's `validation_rules` list drives a generic `LLMValidator` that builds a GPT-4o prompt from those rules. The `config/form_types/*.yaml` files define which attachment types are required per life event (`required_attachment_types`) and form-field validation rules (`form_validation_rules`). Adding a new validated type = adding a YAML file.

## Files to Create

### `src/validators/base.py`
- Define `BaseValidator` as an ABC
- Single abstract method: `async validate(form_analysis: FormAnalysisResult, attachment_extracted: ExtractedDoc) -> ValidationResult`
- Import `FormAnalysisResult`, `ExtractedDoc`, `ValidationResult` from `src.models`

### `src/validators/llm_validator.py`
- `LLMValidator(BaseValidator)` — a generic validator driven by config
- Constructor takes:
  - `client: openai.AsyncAzureOpenAI`
  - `deployment: str`
  - `doc_type_config: DocTypeConfig`
- Method: `async validate(form_analysis: FormAnalysisResult, attachment_extracted: ExtractedDoc) -> ValidationResult`
- Implementation:
  1. Build a system prompt from `doc_type_config.validation_rules`:
     ```
     You are a document validator for HR benefit submissions.
     You are verifying a "{display_name}" attachment against the submitted form.

     Employee name from form: {employee_first_name} {employee_last_name}
     Beneficiary name from form: {beneficiary_first_name}
     Today's date: {today_date}

     Validate the following rules against the attachment text:
     {for each rule in validation_rules:}
     - {rule}

     For each rule, determine if it passes or fails. Return ONLY valid JSON:
     {
       "results": [
         {"rule": "rule text", "passed": true|false, "reason": "explanation"}
       ]
     }
     ```
  2. Send user message with attachment text
  3. Use `response_format={"type": "json_object"}`
  4. Parse response and build `ValidationResult`:
     - Collect all failed rules as `reasons`
     - `status` = `"pass"` if no failures, else `"fail"`

### `src/validators/registry.py`
- `ValidatorRegistry` class
- Constructor: `__init__(self, validators: dict[str, BaseValidator])`
- Class method: `load(config_dir: Path, client: AsyncAzureOpenAI, deployment: str) -> ValidatorRegistry`
  - Calls `load_doc_type_configs(config_dir)` (from M4's `doc_type_config.py`)
  - For each config, creates an `LLMValidator(client, deployment, config)`
  - Stores in `_validators[config.doc_type]`
  - Returns populated registry
- Method: `get_validator(doc_type: str) -> BaseValidator | None`
  - Returns the validator for the given doc type, or `None` if not registered
- Method: `list_doc_types() -> list[str]`
  - Returns all registered doc type names

### `tests/test_validators.py`
- Test class `TestValidatorRegistry`:
  1. **Load from config dir** — create temp YAML files, call `ValidatorRegistry.load()` with a mock OpenAI client, assert it loads
  2. **Get known validator** — `get_validator("marriage_certificate")` returns an `LLMValidator` instance
  3. **Get unknown validator** — `get_validator("unknown")` returns `None`
  4. **List doc types** — returns all registered types
  5. **Empty config dir** — loads fine, all lookups return `None`
- Test class `TestLLMValidator`:
  1. **All rules pass** — mock LLM returns all rules passed. Assert `status="pass"`, `reasons=[]`
  2. **Some rules fail** — mock LLM returns mixed results. Assert `status="fail"` with failed rule reasons
  3. **Prompt includes validation rules** — assert system prompt contains rules from the config
  4. **Prompt includes form data** — assert employee/beneficiary names appear in the prompt
- Test `BaseValidator` is abstract — cannot be instantiated directly
- Use `pytest.mark.asyncio` and `unittest.mock.AsyncMock`

## Acceptance Criteria
- `ValidatorRegistry.load("config/doc_types/", client, deployment)` auto-discovers YAML files and creates `LLMValidator` instances
- `registry.get_validator("marriage_certificate")` returns an `LLMValidator` configured with the marriage certificate rules
- `registry.get_validator("unknown")` returns `None`
- `LLMValidator` builds prompts dynamically from `validation_rules` in the YAML
- `pytest tests/test_validators.py` — all tests pass
- Adding a new validated doc type requires ONLY adding a new YAML file in `config/doc_types/`

## Constraints
- No per-type Python validator classes — `LLMValidator` is the single generic implementation
- The `config/registry.yaml` file is NOT used — auto-discovery from `config/doc_types/` replaces it
- All methods are `async`
- Use `DefaultAzureCredential` from `azure-identity` — no API keys
- Do not add new dependencies

## Constraints
- Use `importlib` for dynamic imports — no hardcoded class references in the registry
- Validators take constructor args later (e.g., OpenAI client) — for now, the registry calls the no-arg constructor. A future enhancement can pass constructor kwargs from YAML config.
- `BaseValidator.validate()` is `async`
- Do not modify any files from previous milestones except adding to `tests/test_validators.py`
- Use `pyyaml` (already in `pyproject.toml`)
