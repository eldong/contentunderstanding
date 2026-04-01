You are implementing Milestone 8 (final) of a Document Validation System POC.

## Context
This is a Python project at `c:\work\opm\contentunderstanding`. See `planningdocs/plan.md` for full architecture. Milestones 1-7 are complete — we have:
- `src/models.py` — 5 Pydantic contracts
- `src/ingestion/` — `IngestionAdapter` ABC + `LocalFolderAdapter`
- `src/extraction/` — `Extractor` ABC + `DocIntelligenceExtractor` + `MockExtractor`
- `src/classification/form_analyzer.py` — `FormAnalyzer` (LLM)
- `src/classification/attachment_classifier.py` — `AttachmentClassifier` (LLM)
- `src/validators/base.py` — `BaseValidator` ABC
- `src/validators/registry.py` — `ValidatorRegistry` (YAML config, dynamic import)
- `src/validators/marriage_certificate.py` — `MarriageCertificateAgent` (LLM)
- `config/registry.yaml` — maps `marriage_certificate` → `MarriageCertificateAgent`
- `samples/submission_001/` — sample submission with mock sidecar JSON files

Now wire everything together: Orchestrator, Result Writer, and CLI entry point.

## Files to Create

### `src/result_writer.py`
- `ResultWriter` class — constructor takes `output_path: Path`
- Method: `write(result: ValidationResult)` — appends one JSON line to the output file (JSONL format)
  - Each line is `result.model_dump_json() + "\n"`
  - Create the file if it doesn't exist; append if it does
- Method: `read_all() -> list[ValidationResult]` — reads the JSONL file and returns all results (useful for testing)

### `src/orchestrator.py`
- `Orchestrator` class — constructor takes all components:
  - `ingestion: IngestionAdapter`
  - `extractor: Extractor`
  - `form_analyzer: FormAnalyzer`
  - `attachment_classifier: AttachmentClassifier`
  - `validator_registry: ValidatorRegistry`
  - `result_writer: ResultWriter`
- Method: `async run() -> list[ValidationResult]`
  - Implementation (doc-type-agnostic — ZERO doc-specific logic):
    ```
    results = []
    submissions = ingestion.list_submissions()

    for submission in submissions:
        # 1. Extract form
        form_extracted = await extractor.extract(submission.form_path)

        # 2. Analyze form
        form_analysis = await form_analyzer.analyze(form_extracted)

        # 3. If not relevant, skip
        if not form_analysis.is_relevant:
            skip_result = ValidationResult(
                submission_id=submission.submission_id,
                form_name=form_analysis.form_type,
                submitted_by=submission.submitted_by,
                status="skip",
                reasons=[f"Form type '{form_analysis.form_type}' is not relevant or no reason selected"],
            )
            result_writer.write(skip_result)
            results.append(skip_result)
            continue

        # 4. Process each attachment
        for att_path in submission.attachment_paths:
            # Extract attachment
            att_extracted = await extractor.extract(att_path)

            # Classify attachment
            classification = await attachment_classifier.classify(att_extracted)

            # Look up validator
            validator = validator_registry.get_validator(classification.doc_type)

            if validator is None:
                fail_result = ValidationResult(
                    submission_id=submission.submission_id,
                    form_name=form_analysis.form_type,
                    submitted_by=submission.submitted_by,
                    status="fail",
                    reasons=[f"No validator registered for document type '{classification.doc_type}'"],
                )
                result_writer.write(fail_result)
                results.append(fail_result)
                continue

            # Validate
            result = await validator.validate(form_analysis, att_extracted)
            # Fill in submission-level fields
            result.submission_id = submission.submission_id
            result.submitted_by = submission.submitted_by
            result.form_name = form_analysis.form_type

            result_writer.write(result)
            results.append(result)

    return results
    ```
- **CRITICAL**: The orchestrator has NO knowledge of marriage certificates, form types, or any specific doc type. It routes purely via the classifier + registry.

### `main.py`
- CLI entry point using `argparse`
- Arguments:
  - `--input` / `-i` — path to submissions folder (default: `samples/`)
  - `--output` / `-o` — path to results file (default: `results.jsonl`)
  - `--mock` — flag: use `MockExtractor` instead of `DocIntelligenceExtractor`
- Implementation:
  1. Load `.env` file using `dotenv.load_dotenv()`
  2. Set up components:
     - If `--mock`: use `MockExtractor()`
     - Else: use `DocIntelligenceExtractor(endpoint=os.getenv("AZURE_AI_FOUNDRY_ENDPOINT"))`
     - Create `AsyncAzureOpenAI` client using `DefaultAzureCredential` from `azure-identity` and `AZURE_AI_FOUNDRY_ENDPOINT` (unless `--mock` — then create mock-compatible stubs)
     - Create `FormAnalyzer(client, deployment)`
     - Create `AttachmentClassifier(client, deployment)`
     - Load `ValidatorRegistry.load("config/registry.yaml")`
     - Configure validators that need the OpenAI client (call `validator.configure(client, deployment)` for each)
     - Create `LocalFolderAdapter(args.input)`
     - Create `ResultWriter(args.output)`
  3. Create `Orchestrator` with all components
  4. Run `asyncio.run(orchestrator.run())`
  5. Print summary: number of submissions processed, pass/fail/skip counts
- For `--mock` mode: also need to handle the LLM calls. Two approaches:
  - **Option A (recommended)**: When `--mock` is set, also mock the LLM responses using a `MockFormAnalyzer` / `MockAttachmentClassifier` that return hardcoded results based on heuristics (e.g., if "add beneficiary" in text → relevant)
  - **Option B**: Still call Azure OpenAI even in mock mode (only extraction is mocked)
  - **Go with Option B** — mock only extraction, still use real LLM. Add a `--mock-llm` flag for fully offline mode later if needed.

### `tests/test_pipeline.py`
- Full end-to-end pipeline test with all components mocked
- Test class `TestPipeline`:
  1. **Happy path — pass**: Mock extractor returns form + marriage cert text. Mock form analyzer returns relevant result. Mock classifier returns `marriage_certificate`. Mock validator returns `status="pass"`. Assert JSONL output has one pass result.
  2. **Skip — irrelevant form**: Mock form analyzer returns `is_relevant=False`. Assert result is `status="skip"`.
  3. **Fail — no validator**: Mock classifier returns `doc_type="unknown"`. Assert `status="fail"` with "No validator registered" reason.
  4. **Fail — validation failure**: Mock validator returns `status="fail"` with reasons. Assert reasons propagate.
  5. **Multiple submissions**: Two submissions in ingestion. Assert two result rows in JSONL.
- For each test:
  - Use `tmp_path` for JSONL output
  - Mock all components (don't call Azure)
  - Verify JSONL file contains correct number of lines with valid JSON

### `tests/conftest.py`
- Shared pytest fixtures:
  - `mock_openai_client` — returns an `AsyncMock` of `AsyncAzureOpenAI`
  - `sample_form_extracted` — returns an `ExtractedDoc` with the sample add-beneficiary form text
  - `sample_attachment_extracted` — returns an `ExtractedDoc` with the sample marriage certificate text
  - `sample_form_analysis_relevant` — returns a `FormAnalysisResult` with `is_relevant=True, reason="marriage"`
  - `sample_form_analysis_irrelevant` — returns a `FormAnalysisResult` with `is_relevant=False`
  - `sample_classifier_response_marriage` — returns `ClassifierResponse(doc_type="marriage_certificate")`

## Acceptance Criteria
- `python main.py --input samples/ --output results.jsonl --mock` runs end-to-end (extraction mocked, LLM calls real if Azure creds are set)
- `results.jsonl` contains one JSON line per submission/attachment with all `ValidationResult` fields
- Orchestrator contains ZERO doc-type-specific logic
- `pytest tests/test_pipeline.py` — all tests pass with fully mocked components
- `pytest` (all tests) — everything passes

## Constraints
- Orchestrator must be doc-type-agnostic — no `if doc_type == "marriage_certificate"` anywhere
- JSONL format — one JSON object per line, no pretty-printing
- Do not modify files from previous milestones unless strictly necessary for integration
- Keep `main.py` simple — it's a wiring layer, not business logic
- Use `asyncio.run()` to bridge sync CLI → async pipeline
