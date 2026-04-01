You are implementing Milestone 3 of a Document Validation System POC.

## Context
This is a Python project at `c:\work\opm\contentunderstanding`. See `planningdocs/plan.md` for full architecture. Milestones 1-2 are complete — we have Pydantic contracts in `src/models.py` and local folder ingestion in `src/ingestion/`.

## Goal
Build the document extraction layer with two implementations:
1. `DocIntelligenceExtractor` — uses Azure Document Intelligence (`prebuilt-read` model) for real extraction
2. `MockExtractor` — reads canned JSON sidecar files for offline development

Both return `ExtractedDoc` from `src/models.py`.

## Files to Create

### `src/extraction/base.py`
- Define `Extractor` as an ABC
- Single method: `async extract(file_path: Path) -> ExtractedDoc`
- Import `ExtractedDoc` from `src.models`

### `src/extraction/doc_intelligence.py`
- `DocIntelligenceExtractor(Extractor)` — constructor takes `endpoint: str` (the Azure AI Foundry endpoint from env var `AZURE_AI_FOUNDRY_ENDPOINT`)
- Uses `DefaultAzureCredential` from `azure-identity` for authentication — no API keys
- `async extract(file_path: Path) -> ExtractedDoc`:
  - Use `azure.ai.documentintelligence.DocumentIntelligenceClient` with `DefaultAzureCredential` (sync client wrapped in async, or use the async client if available)
  - Use the `prebuilt-read` model
  - Read the file bytes, call `begin_analyze_document` with the file content
  - Extract all text content from the result pages
  - Extract key-value pairs if available (from `result.key_value_pairs`)
  - Return `ExtractedDoc(source_path=str(file_path), content=full_text, fields=kv_pairs, confidence=avg_confidence)`
- Load endpoint from environment using `python-dotenv`; authenticate via `DefaultAzureCredential` (no API keys)

### `src/extraction/mock_extractor.py`
- `MockExtractor(Extractor)` — no constructor args needed
- `async extract(file_path: Path) -> ExtractedDoc`:
  - Look for a JSON sidecar file next to the input file: `{file_path}.extracted.json`
    - e.g., for `samples/submission_001/form.pdf`, look for `samples/submission_001/form.pdf.extracted.json`
  - If the sidecar exists, read it and return `ExtractedDoc.model_validate_json(contents)`
  - If no sidecar, return `ExtractedDoc(source_path=str(file_path), content="", fields={}, confidence=0.0)` with a warning log

### `samples/submission_001/form.pdf.extracted.json`
Create a realistic mock extraction result for an "Add Beneficiary" form:
```json
{
  "source_path": "samples/submission_001/form.pdf",
  "content": "EMPLOYER-SPONSORED HEALTH PLAN\nBENEFICIARY ENROLLMENT / CHANGE FORM\n\nAction: [X] Add Beneficiary  [ ] Remove Beneficiary  [ ] Change Beneficiary\n\nReason for Change:\n[ ] New Hire  [X] Marriage  [ ] Birth/Adoption  [ ] Court Order  [ ] Other\n\nEmployee Information:\nFirst Name: Jane\nLast Name: Smith\nEmployee ID: EMP-4521\n\nBeneficiary Information:\nFirst Name: Michael\nLast Name: Johnson\nRelationship: Spouse\nDate of Birth: 1990-05-15\n\nEffective Date: 2026-03-15\nSignature: Jane Smith\nDate: 2026-03-10",
  "fields": {
    "action": "Add Beneficiary",
    "reason": "Marriage",
    "employee_first_name": "Jane",
    "employee_last_name": "Smith",
    "beneficiary_first_name": "Michael",
    "beneficiary_last_name": "Johnson"
  },
  "confidence": 0.95
}
```

### `samples/submission_001/attachment.pdf.extracted.json`
Create a realistic mock extraction result for a marriage certificate:
```json
{
  "source_path": "samples/submission_001/attachment.pdf",
  "content": "STATE OF MARYLAND\nCERTIFICATE OF MARRIAGE\n\nThis is to certify that\nJane Smith\nand\nMichael Johnson\nwere united in marriage on\nFebruary 14, 2026\n\nOfficiating: Rev. Thomas Brown\nCounty: Montgomery County\nState: Maryland\n\nCertificate Number: MC-2026-08841\nDate of Issue: February 15, 2026\n\nRegistrar: Sarah Williams\nOffice of Vital Records",
  "fields": {},
  "confidence": 0.92
}
```

### `tests/test_extraction.py`
- Test `MockExtractor`:
  - Create a temp directory with a sidecar `.extracted.json` file
  - Call `extract()`, assert the returned `ExtractedDoc` matches the sidecar content
  - Test missing sidecar — should return empty content with confidence 0.0
- Test `DocIntelligenceExtractor` construction (don't call Azure — just assert it can be instantiated with a fake endpoint)
- Use `pytest.mark.asyncio` for async tests

## Acceptance Criteria
- `MockExtractor` returns valid `ExtractedDoc` from sidecar JSON files
- `MockExtractor` handles missing sidecar gracefully (returns empty doc, no crash)
- Sample sidecar files in `samples/submission_001/` contain realistic form + marriage certificate text
- `pytest tests/test_extraction.py` — all tests pass
- `DocIntelligenceExtractor` can be instantiated with `DefaultAzureCredential` (integration test with real Azure is manual)

## Constraints
- All extract methods are `async` (the ABC enforces this)
- Do not call Azure in automated tests — mock/sidecar only
- Do not add dependencies beyond what's already in `pyproject.toml`
- Keep `DocIntelligenceExtractor` simple — `prebuilt-read` model, no custom models
