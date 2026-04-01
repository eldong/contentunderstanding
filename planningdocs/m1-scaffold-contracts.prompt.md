You are implementing Milestone 1 of a Document Validation System POC.

## Context
This is a Python project at `c:\work\opm\contentunderstanding`. It validates HR submissions (a form PDF + supporting attachment) using Azure Document Intelligence for extraction and Azure OpenAI GPT-4o for classification/validation. See `planningdocs/plan.md` for full architecture.

## What Already Exists
- `pyproject.toml` — project config (may need updates)
- `.env.example` — Azure AI Foundry endpoint placeholder (uses `DefaultAzureCredential`, no API keys)
- `src/__init__.py` — empty init
- `src/models.py` — all 5 Pydantic v2 contracts (SubmissionWorkItem, ExtractedDoc, FormAnalysisResult, ClassifierResponse, ValidationResult)
- `tests/test_models.py` — model tests
- Package init files for `src/ingestion/`, `src/extraction/`, `src/classification/`, `src/validators/`, `tests/`

## Goal
Ensure the project scaffold is complete and all Pydantic contracts compile, serialize, and validate correctly.

## Tasks
1. Review `pyproject.toml` — ensure dependencies are correct: `pydantic>=2.0`, `python-dotenv>=1.0`, `openai>=1.0`, `azure-ai-documentintelligence>=1.0.0b4`, `azure-identity>=1.15`, `pyyaml>=6.0`, and dev deps `pytest>=8.0`, `pytest-asyncio>=0.23`. The build-backend must be `setuptools.build_meta`.
2. Review `src/models.py` — confirm all 5 models match the contracts in `planningdocs/plan.md`. Fix any issues.
3. Review `tests/test_models.py` — ensure round-trip JSON serialization, required-field validation, and bad-data rejection are all covered.
4. Install the project with `pip install -e ".[dev]"` and run `pytest tests/test_models.py`.
5. Fix any failures until all tests pass.

## Acceptance Criteria
- `python -c "from src.models import SubmissionWorkItem, ExtractedDoc, FormAnalysisResult, ClassifierResponse, ValidationResult"` succeeds
- `pytest tests/test_models.py` — all tests pass
- All 5 models serialize to JSON and deserialize back correctly

## Constraints
- Python 3.11+
- Pydantic v2 (not v1)
- Do not add files beyond what's listed above
- Do not over-engineer — POC-minimal