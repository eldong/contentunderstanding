---
name: doc-type-scaffold
description: 'Scaffold a new attachment document type with YAML config and tests. Use when: add document type, new doc type, create attachment type, support new certificate, add new attachment config.'
---

# Scaffold a New Document Type

Creates a new attachment document type by generating a YAML config in `config/doc_types/` and corresponding tests.

## When to Use

- Adding a new type of attachment the system should recognize (e.g., court order, adoption decree, death certificate)
- User says "add document type", "new doc type", "support [X] certificate"

## Procedure

### 1. Gather Requirements

Ask the user for:
- **doc_type**: snake_case identifier (e.g., `court_order`, `adoption_decree`)
- **display_name**: Human-readable name (e.g., "Court Order")
- **description**: One-line description of what the document is
- **indicators**: 3-5 phrases the AI classifier looks for in the document text to identify it
- **validation_rules**: Plain-English rules the AI checks when validating this attachment

### 2. Rule-Writing Guidance

Apply these principles from [docs/promptguidance.md](../../../docs/promptguidance.md):

- **Be specific, not vague.** "Names must match" is bad. "The child's name on the certificate must match the dependent name on the form" is good.
- **Call out exceptions explicitly.** If a known scenario might look like a failure but is acceptable, state it in the rule. Example: maiden-name differences on marriage certificates.
- **Date rules get special treatment.** The AI extracts dates and Python does exact math. Always state the time window ("within 12 months") and the reference date ("of the application date from the form"). See the date-rule section of the prompt guidance doc for details.

### 3. Generate the YAML Config

Create the file at `config/doc_types/{doc_type}.yaml` using this structure:

```yaml
doc_type: {doc_type}
display_name: {display_name}
description: "{description}"
indicators:
  - "{indicator_1}"
  - "{indicator_2}"
  - "{indicator_3}"
validation_rules:
  - "{rule_1}"
  - "{rule_2}"
  - "{rule_3}"
```

**Validation**: The YAML must parse successfully with `DocTypeConfig.model_validate()` from `src/classification/doc_type_config.py`. All five fields (`doc_type`, `display_name`, `description`, `indicators`, `validation_rules`) are required.

### 4. Generate Tests

Add tests to `tests/test_doc_type_config.py` following the existing pattern. Use the existing `VALID_YAML` constant as a reference for format.

Add a config-loading test:

```python
def test_loads_{doc_type}_config(self, tmp_path):
    yaml_content = """\
doc_type: {doc_type}
display_name: {display_name}
description: "{description}"
indicators:
  - "{first_indicator}"
validation_rules:
  - "{first_rule}"
"""
    (tmp_path / "{doc_type}.yaml").write_text(yaml_content, encoding="utf-8")
    configs = load_doc_type_configs(tmp_path)
    assert len(configs) == 1
    assert configs[0].doc_type == "{doc_type}"
```

### 5. Generate Validator Tests (if rules warrant it)

If the doc type has date-window rules or name-matching rules, add tests to `tests/test_validators.py` following the existing `TestLLMValidator` pattern:

- Create a `SAMPLE_{DOC_TYPE}_CONFIG` constant with the new `DocTypeConfig`
- Create sample `ExtractedDoc` fixtures with realistic content for the new doc type
- Test the pass case with a mock LLM response where all rules pass
- Test the fail case (especially for date rules, where Python overrides LLM with exact math)
- For date rules, mock `date_check` responses: `{"extracted_date": "...", "reference_date": "...", "window": "12 months"}`

Use the existing `_make_mock_client` helper and `@pytest.mark.asyncio` decorator.

### 6. Cross-Check

- Verify the `doc_type` value doesn't duplicate an existing config in `config/doc_types/`
- If this doc type should be required by a form type, remind the user to add it to the relevant `config/form_types/*.yaml` under `required_attachment_types`

### 7. Run Tests

Run `pytest tests/test_doc_type_config.py tests/test_validators.py -v` to verify everything passes.

## Reference: Existing Examples

- [config/doc_types/marriage_certificate.yaml](../../../config/doc_types/marriage_certificate.yaml)
- [config/doc_types/birth_certificate.yaml](../../../config/doc_types/birth_certificate.yaml)
- [src/classification/doc_type_config.py](../../../src/classification/doc_type_config.py) — Pydantic model + loader
- [tests/test_doc_type_config.py](../../../tests/test_doc_type_config.py) — config test patterns
- [tests/test_validators.py](../../../tests/test_validators.py) — validator test patterns
- [docs/promptguidance.md](../../../docs/promptguidance.md) — rule-writing best practices
