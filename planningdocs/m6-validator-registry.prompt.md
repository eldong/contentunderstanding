You are implementing Milestone 6 of a Document Validation System POC.

## Context
This is a Python project at `c:\work\opm\contentunderstanding`. See `planningdocs/plan.md` for full architecture. Milestones 1-5 are complete — we have contracts, ingestion, extraction, form analyzer, and attachment classifier. Now build the validator framework.

## Goal
Build the pluggable validator architecture: a `BaseValidator` ABC, a `ValidatorRegistry` that loads validator mappings from YAML config and dynamically imports validator classes, and the `config/registry.yaml` file.

## Files to Create

### `src/validators/base.py`
- Define `BaseValidator` as an ABC
- Single abstract method: `async validate(form_analysis: FormAnalysisResult, attachment_extracted: ExtractedDoc) -> ValidationResult`
- Import `FormAnalysisResult`, `ExtractedDoc`, `ValidationResult` from `src.models`

### `src/validators/registry.py`
- `ValidatorRegistry` class
- Constructor: `__init__(self)` — initializes an empty `_validators: dict[str, BaseValidator]` mapping
- Class method or static method: `load(config_path: Path) -> ValidatorRegistry`
  - Reads `config_path` (a YAML file) using `yaml.safe_load()`
  - Expected YAML structure:
    ```yaml
    validators:
      marriage_certificate:
        class: src.validators.marriage_certificate.MarriageCertificateAgent
      # future:
      # birth_certificate:
      #   class: src.validators.birth_certificate.BirthCertificateAgent
    ```
  - For each entry: dynamically import the class using `importlib.import_module()` and `getattr()`
    - Split the class path: module = everything before the last dot, class_name = last dot segment
    - e.g., `"src.validators.marriage_certificate.MarriageCertificateAgent"` → module `"src.validators.marriage_certificate"`, class `"MarriageCertificateAgent"`
  - Instantiate the class (no-arg constructor for now) and store in `_validators[doc_type]`
  - Return the populated `ValidatorRegistry`
- Method: `get_validator(doc_type: str) -> BaseValidator | None`
  - Returns the validator instance for the given doc_type, or `None` if not registered

### `config/registry.yaml`
```yaml
validators:
  marriage_certificate:
    class: src.validators.marriage_certificate.MarriageCertificateAgent
```

### `src/validators/marriage_certificate.py` (STUB ONLY for this milestone)
- Create a minimal stub so the registry can import it:
  ```python
  from src.validators.base import BaseValidator
  from src.models import FormAnalysisResult, ExtractedDoc, ValidationResult

  class MarriageCertificateAgent(BaseValidator):
      async def validate(self, form_analysis: FormAnalysisResult, attachment_extracted: ExtractedDoc) -> ValidationResult:
          raise NotImplementedError("Will be implemented in Milestone 7")
  ```

### `tests/test_validators.py`
- Test class `TestValidatorRegistry`:
  1. **Load from YAML** — create a temp YAML file with a validator entry pointing to `MarriageCertificateAgent`, call `ValidatorRegistry.load()`, assert it loads without error
  2. **Get known validator** — `get_validator("marriage_certificate")` returns an instance of `MarriageCertificateAgent`
  3. **Get unknown validator** — `get_validator("unknown")` returns `None`
  4. **Get unregistered doc type** — `get_validator("birth_certificate")` returns `None`
  5. **Empty config** — YAML with no validators, registry loads fine, all lookups return `None`
- Test `BaseValidator` is abstract — cannot be instantiated directly

## Acceptance Criteria
- `ValidatorRegistry.load("config/registry.yaml")` succeeds and loads the `MarriageCertificateAgent` stub
- `registry.get_validator("marriage_certificate")` returns a `MarriageCertificateAgent` instance
- `registry.get_validator("unknown")` returns `None`
- `pytest tests/test_validators.py` — all tests pass
- Adding a new doc type requires only: (1) a new validator class file, (2) a new entry in `registry.yaml`. No code changes to registry or orchestrator.

## Constraints
- Use `importlib` for dynamic imports — no hardcoded class references in the registry
- Validators take constructor args later (e.g., OpenAI client) — for now, the registry calls the no-arg constructor. A future enhancement can pass constructor kwargs from YAML config.
- `BaseValidator.validate()` is `async`
- Do not modify any files from previous milestones except adding to `tests/test_validators.py`
- Use `pyyaml` (already in `pyproject.toml`)
