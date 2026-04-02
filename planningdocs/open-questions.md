# Open Questions & Things to Think Through

## Data-Driven Document Types

We decided that adding a new document type should be "add a file, not modify code." This shapes M4-M8 significantly.

### Design: Type Definition Files
Each doc type is defined by a YAML file in `config/doc_types/`. Example:
```yaml
doc_type: marriage_certificate
display_name: Marriage Certificate
description: "Official government-issued certificate of marriage"
required_for_reasons:
  - marriage
indicators:
  - "certificate of marriage"
  - "united in marriage"
  - "marriage license"
validation_rules:
  - "The names on the certificate must match the employee and/or beneficiary names on the form"
  - "The marriage date must be recent (within the last 12 months)"
  - "The document must appear to be an official government-issued certificate"
```

### How the Pipeline Uses Type Definitions
- **Form Analyzer** — core prompt is static; valid `form_type` values and their associated reasons are assembled from all type definition files at startup
- **Attachment Classifier** — valid `doc_type` values, descriptions, and indicators are injected into the classification prompt dynamically
- **Validator Registry** — auto-discovers from `config/doc_types/` instead of a separate `registry.yaml`
- **Validation** — a generic `LLMValidator` builds a GPT-4o prompt from the `validation_rules` list in the YAML; no per-type Python class needed

### Open Questions

1. **Validation rule expressiveness** — Free-text rules work well for GPT-4o, but will we need structured rule types (e.g., `name_match`, `date_within_months: 12`) for reliability? Or is natural language sufficient for a POC?

2. **Testing new types** — When an admin adds a YAML file, how do they know it works? Options:
   - Dry-run mode against sample documents
   - Schema validation on the YAML at load time
   - A "preview prompt" command that shows what GPT-4o would see

3. **YAML schema validation** — Should we validate the YAML against a JSON Schema or Pydantic model at load time so a malformed file doesn't crash the system?

4. **Prompt assembly complexity** — As the number of types grows, the assembled prompts get longer. At what point does this degrade GPT-4o quality? Mitigation: only inject types relevant to the form's reason?

5. **Form types vs. doc types vs. reasons** — These are related but different dimensions:
   - Form type: "add_beneficiary" (what the form is)
   - Reason: "marriage" (why the change is happening)
   - Doc type: "marriage_certificate" (what the attachment is)
   - The mapping is: reason → required doc types. Where does this mapping live? In the type definition file (`required_for_reasons`) makes sense.

6. **Multiple validators per type** — Could a single doc type need multiple validation passes? For now, one set of rules per YAML file seems sufficient.

7. **Admin UI vs. file-based** — For the POC, files are fine. For production, would an admin API/UI write these YAML files? Or store in a database?

8. **Versioning** — When a type definition changes, should old submissions be re-validated? Out of scope for POC but worth noting.
