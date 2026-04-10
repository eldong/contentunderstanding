---
name: form-type-scaffold
description: 'Scaffold a new form type (life event) with YAML config and tests. Use when: add form type, new life event, new enrollment reason, add form config, support new HR form.'
---

# Scaffold a New Form Type

Creates a new form type (life event / enrollment reason) by generating a YAML config in `config/form_types/` and corresponding tests.

## When to Use

- Adding a new life event or enrollment reason (e.g., divorce, adoption, new hire, retirement)
- User says "add form type", "new life event", "support new enrollment reason"

## Procedure

### 1. Gather Requirements

Ask the user for:
- **doc_type**: snake_case identifier for the form type (e.g., `remove_dependent_health`, `adoption_enrollment`)
- **display_name**: Human-readable name (e.g., "Adoption Enrollment Form")
- **description**: One-line description of what this form is for
- **required_attachment_types**: Which doc types must be attached. Use existing doc_type identifiers from `config/doc_types/`. Set to `[]` if no attachments are needed (e.g., new_hire).
- **form_validation_rules**: Plain-English rules checked against the form itself (not the attachments)

### 2. Cross-Check Required Attachment Types

Before generating, verify that every entry in `required_attachment_types` matches an existing `doc_type` value in `config/doc_types/*.yaml`.

List the existing doc types by scanning `config/doc_types/`. If a required type doesn't exist yet, tell the user they need to create it first (use the `doc-type-scaffold` skill).

### 3. Rule-Writing Guidance

Apply the same principles from [docs/promptguidance.md](../../../docs/promptguidance.md):

- **Be specific.** "The employee name must be filled out on the form" is better than "Name is required."
- **State conditional logic clearly.** Example: "If spouse is selected, a marriage certificate attachment is required."
- Form validation rules check the **form itself** — not the attachments. Attachment validation is handled by each doc type's own `validation_rules`.

### 4. Generate the YAML Config

Create the file at `config/form_types/{doc_type}.yaml` using this structure:

```yaml
doc_type: {doc_type}
display_name: {display_name}
description: "{description}"
required_attachment_types:
  - {attachment_type_1}
  - {attachment_type_2}
form_validation_rules:
  - "{rule_1}"
  - "{rule_2}"
```

For form types that require no attachments:

```yaml
doc_type: {doc_type}
display_name: {display_name}
description: "{description}"
required_attachment_types: []
form_validation_rules:
  - "{rule_1}"
```

**Validation**: The YAML must parse successfully with `FormTypeConfig.model_validate()` from `src/classification/form_type_config.py`. Required fields: `doc_type`, `display_name`, `description`. Lists `required_attachment_types` and `form_validation_rules` default to `[]` if omitted.

### 5. Generate Tests

Add tests to `tests/test_form_type_config.py` following the existing pattern.

Add a YAML constant and config-loading test:

```python
{DOC_TYPE_UPPER}_YAML = """\
doc_type: {doc_type}
display_name: {display_name}
description: "{description}"
required_attachment_types:
  - {attachment_type_1}
form_validation_rules:
  - "{first_rule}"
"""

# In TestLoadFormTypeConfigs:
def test_loads_{doc_type}_config(self, tmp_path):
    (tmp_path / "{doc_type}.yaml").write_text({DOC_TYPE_UPPER}_YAML, encoding="utf-8")
    configs = load_form_type_configs(tmp_path)
    assert len(configs) == 1
    assert configs[0].doc_type == "{doc_type}"
    assert configs[0].required_attachment_types == ["{attachment_type_1}"]
```

For form types with no attachments, test that `required_attachment_types` is `[]`.

### 6. Cross-Check

- Verify the `doc_type` value doesn't duplicate an existing config in `config/form_types/`
- Confirm all `required_attachment_types` entries exist in `config/doc_types/`
- If new attachment types are needed, prompt the user to create them with the `doc-type-scaffold` skill first

### 7. Run Tests

Run `pytest tests/test_form_type_config.py -v` to verify everything passes.

## Reference: Existing Examples

- [config/form_types/add_dependent_health.yaml](../../../config/form_types/add_dependent_health.yaml) — form requiring multiple attachment types
- [tests/test_form_type_config.py](../../../tests/test_form_type_config.py) — includes patterns for forms with and without attachments
- [src/classification/form_type_config.py](../../../src/classification/form_type_config.py) — Pydantic model + loader
- [docs/promptguidance.md](../../../docs/promptguidance.md) — rule-writing best practices
