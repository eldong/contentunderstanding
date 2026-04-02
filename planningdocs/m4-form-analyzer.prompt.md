You are implementing Milestone 4 of a Document Validation System POC.

## Context
This is a Python project at `c:\work\opm\contentunderstanding`. See `planningdocs/plan.md` for full architecture. Milestones 1-3 are complete — we have Pydantic contracts, local ingestion, and document extraction (mock + Azure Doc Intelligence).

## Goal
Build the `FormAnalyzer` class that uses Azure OpenAI GPT-4o to analyze extracted form text. The analyzer dynamically loads document type definitions from `config/doc_types/*.yaml` files to build its prompt. Returns a `FormAnalysisResult` from `src/models.py`.

## Data-Driven Design
Document types and rules are defined in YAML files under two directories:
- `config/doc_types/` — attachment document types (indicators, validation rules)
- `config/form_types/` — life events / form types (required attachment types, form-field validation rules)

The form analyzer reads `FormTypeConfig` objects from `config/form_types/` to learn what form types exist. Adding a new type means adding a YAML file — no code changes.

## Files to Create

### `config/doc_types/marriage_certificate.yaml`
```yaml
doc_type: marriage_certificate
display_name: Marriage Certificate
description: "Official government-issued certificate or license of marriage"
indicators:
  - "certificate of marriage"
  - "united in marriage"
  - "marriage license"
validation_rules:
  - "The names on the certificate must match the employee and/or beneficiary names on the form"
  - "The marriage date must be recent (within the last 12 months)"
  - "The document must appear to be an official government-issued certificate"
```

### `config/form_types/marriage.yaml`
```yaml
doc_type: marriage
display_name: Marriage
description: "Employee is adding a beneficiary due to a recent marriage"
required_attachment_types:
  - marriage_certificate
form_validation_rules:
  - "Beneficiary first name must be filled out"
  - "The marriage checkbox or reason must be selected on the form"
```

### `config/form_types/new_hire.yaml`
```yaml
doc_type: new_hire
display_name: New Hire
description: "Employee is enrolling beneficiaries as part of new hire onboarding"
required_attachment_types: []
form_validation_rules:
  - "Employee hire date or effective date must be filled out"
  - "The new hire checkbox or reason must be selected on the form"
  - "At least one beneficiary must be listed on the form"
```

### `src/classification/doc_type_config.py`
- `DocTypeConfig` — a Pydantic model that represents one doc type definition:
  - `doc_type: str`
  - `display_name: str`
  - `description: str`
  - `indicators: list[str]`
  - `validation_rules: list[str]`
- Function: `load_doc_type_configs(config_dir: Path) -> list[DocTypeConfig]`
  - Reads all `*.yaml` files in `config_dir`
  - Validates each against the Pydantic model
  - Returns list of all loaded configs
  - Logs a warning and skips any file that fails validation

### `src/classification/form_type_config.py`
- `FormTypeConfig` — a Pydantic model that represents one form type definition:
  - `doc_type: str`
  - `display_name: str`
  - `description: str`
  - `required_attachment_types: list[str]` (defaults to empty)
  - `form_validation_rules: list[str]` (defaults to empty)
- Function: `load_form_type_configs(config_dir: Path) -> list[FormTypeConfig]`
  - Reads all `*.yaml` files in `config_dir`
  - Validates each against the Pydantic model
  - Returns list of all loaded configs
  - Logs a warning and skips any file that fails validation

### `src/classification/form_analyzer.py`
- `FormAnalyzer` class — constructor takes:
  - `client: openai.AsyncAzureOpenAI`
  - `deployment: str`
  - `form_type_configs: list[FormTypeConfig]`
- Method: `async analyze(extracted: ExtractedDoc) -> FormAnalysisResult`
- Implementation:
  1. Build the system prompt dynamically from `form_type_configs`:
     - Collect all `doc_type` values from the configs → these are the valid reasons/types
     - The core prompt instructs the LLM to determine form type, reason, names, and relevance
     - The valid reasons list is injected into the prompt
     ```
     You are a document analyst specializing in HR benefits forms.
     Given the extracted text of a form, determine:
     1. Is this an "Add Beneficiary to employer-sponsored health plan" form? If yes, set form_type to "add_beneficiary". Otherwise set form_type to "unknown".
     2. What reason/life event is selected on the form? Valid reasons: {reasons_list}. Set reason to the lowercase event name or null if none found.
     3. Extract the employee's first and last name.
     4. Extract the beneficiary's first name.
     5. Set is_relevant to true ONLY if form_type is "add_beneficiary" AND a reason is selected.

     Return ONLY valid JSON matching this exact schema:
     {
       "form_type": "add_beneficiary" | "unknown",
       "reason": {reasons_json_enum},
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
  3. **Form with no reason selected** — mock LLM returns `{"form_type": "add_beneficiary", "reason": null, ... "is_relevant": false}`. Assert `is_relevant` is False.
  4. **Prompt includes loaded reasons** — assert that the system prompt sent to GPT-4o contains the reasons from the doc type configs (e.g., "marriage")
- Verify `response_format` is set to `{"type": "json_object"}`
- Use `pytest.mark.asyncio` for all tests
- Use `unittest.mock.AsyncMock` for mocking the async OpenAI client
- Create `FormTypeConfig` test fixtures directly (don't load from actual YAML in unit tests)

### `tests/test_doc_type_config.py`
- Test `load_doc_type_configs`:
  - Create temp YAML files in `tmp_path`, call `load_doc_type_configs()`, assert correct parsing
  - Test invalid YAML is skipped with a warning
  - Test empty directory returns empty list

### `tests/test_form_type_config.py`
- Test `load_form_type_configs`:
  - Create temp YAML files in `tmp_path`, call `load_form_type_configs()`, assert correct parsing
  - Test invalid YAML is skipped with a warning
  - Test empty directory returns empty list
  - Test configs with `required_attachment_types: []`

## Acceptance Criteria
- `FormAnalyzer.analyze()` builds its prompt dynamically from doc type configs
- The prompt contains the valid reasons extracted from all doc type config files
- Mock tests cover: relevant form, irrelevant form, missing reason, dynamic prompt content
- `config/doc_types/marriage_certificate.yaml` exists and loads correctly
- `pytest tests/test_classification.py::TestFormAnalyzer` — all tests pass
- `pytest tests/test_doc_type_config.py` — all tests pass

## Constraints
- The `FormAnalyzer` constructor takes an already-configured `AsyncAzureOpenAI` client — it does NOT load env vars or create the client itself (that's the CLI's job in `main.py`)
- All methods are `async`
- Do not import or depend on ingestion, extraction, or validator modules
- Strict JSON output only — no free-text LLM responses
- Do not add new dependencies
- Use `DefaultAzureCredential` from `azure-identity` — no API keys
