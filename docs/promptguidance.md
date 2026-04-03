# Prompt Guidance for Writing Validation Rules

This guide explains how to write YAML configuration files that define document types and form types. These files control how the system classifies and validates HR submissions — no code changes required.

## How It Works

The system uses AI to evaluate each validation rule you write against the submitted documents. Your rules are written in **plain English** and are sent directly to the AI model as instructions. The clearer and more specific your rules are, the more consistent the results will be.

There are two kinds of config files:

| File type | Location | Purpose |
|-----------|----------|---------|
| **Doc type** | `config/doc_types/` | Defines an attachment type (e.g., marriage certificate, birth certificate) |
| **Form type** | `config/form_types/` | Defines a form / life-event and which attachments are required |

## Doc Type Config (`config/doc_types/`)

Each file defines one attachment document type.

```yaml
doc_type: marriage_certificate          # unique identifier (snake_case)
display_name: Marriage Certificate      # human-readable name
description: "Official government-issued certificate or license of marriage"

indicators:                             # phrases the AI looks for when classifying
  - "certificate of marriage"
  - "united in marriage"
  - "marriage license"

validation_rules:                       # plain-English rules the AI checks
  - "The names on the certificate must match the employee and/or beneficiary names on the form."
  - "The marriage date must be within the last 12 months of the application date from the form they filled out"
  - "The document must appear to be an official government-issued certificate"
```

## Form Type Config (`config/form_types/`)

Each file defines a form (life event) and which attachments it requires.

```yaml
doc_type: add_dependent_health
display_name: Health Insurance Dependent Addition Form
description: "Form for adding a dependent (spouse or child) to employee health insurance coverage"

required_attachment_types:              # which doc types must be attached
  - marriage_certificate
  - birth_certificate

form_validation_rules:                  # rules checked against the form itself
  - "The employee name must be filled out on the form"
  - "The dependent name must be filled out on the form"
```

## Writing Good Validation Rules

### Be specific, not vague

The AI interprets your rules literally. Vague rules produce inconsistent results.

| Avoid | Prefer |
|-------|--------|
| "Names must match" | "The child's name on the certificate must match the dependent name on the form" |
| "The date must be recent" | "The birth date must be within the last 12 months" |
| "It must be official" | "The document must appear to be an official government-issued certificate" |

### Call out acceptable exceptions

If there is a known scenario where a rule might look like a failure but is actually acceptable, **say so explicitly in the rule**. Otherwise the AI may inconsistently pass or fail the same scenario.

**Example — maiden names on marriage certificates:**

Without guidance, the AI sometimes fails a marriage certificate because the spouse's last name on the certificate (maiden name) differs from the married name on the form — and other times it correctly recognizes the maiden name difference and passes it. To get consistent results, state the exception directly:

```yaml
# Too vague — AI may pass or fail maiden-name differences inconsistently
- "The names on the certificate must match the employee and/or beneficiary names on the form"

# Better — tells the AI exactly how to handle the maiden-name case
- "The names on the certificate must match the employee and/or beneficiary names on the form. A maiden name vs. married name difference is acceptable for marriage certificates — if the first names match and the last name difference can be explained by the marriage, treat it as a match."
```

### Date rules — how they work

Date rules get special treatment. The AI extracts the dates, and the system uses **exact math** to verify them (no AI guessing). This means date checks are always consistent.

When writing a date rule:
- State the **time window** clearly (e.g., "within the last 12 months", "within 60 days")
- State the **reference date** — what the window is relative to. If it should be relative to a date on the form, say so explicitly.

```yaml
# Relative to the form's application/signature date
- "The marriage date must be within the last 12 months of the application date from the form they filled out"

# Relative to today (implicit — the AI uses current date if no reference date is specified)
- "The birth date must be within the last 12 months"

# Custom window
- "The court order date must be within 60 days of the effective date on the form"
```

Supported time units: **days**, **weeks**, **months**, **years**.

### One rule per bullet

Each `- "..."` entry is evaluated independently. Don't combine multiple checks into a single rule.

```yaml
# Avoid — two different checks in one rule
- "The names must match and the date must be recent"

# Prefer — separate rules
- "The names on the certificate must match the employee and/or beneficiary names on the form"
- "The marriage date must be within the last 12 months of the application date from the form they filled out"
```

### Indicators — help with classification

The `indicators` list helps the AI identify what type of document an attachment is. Use phrases that commonly appear **in the document text itself**.

```yaml
indicators:
  - "certificate of birth"
  - "certificate of live birth"
  - "born on"
  - "department of vital statistics"
```

## Adding a New Document Type

1. Create a new YAML file in `config/doc_types/` (e.g., `court_order.yaml`)
2. Fill in `doc_type`, `display_name`, `description`, `indicators`, and `validation_rules`
3. Add the `doc_type` value to the `required_attachment_types` list in the relevant form type config
4. No code changes needed — the system auto-discovers new configs

## Adding a New Form Type

1. Create a new YAML file in `config/form_types/` (e.g., `name_change.yaml`)
2. Fill in `doc_type`, `display_name`, `description`, `required_attachment_types`, and `form_validation_rules`
3. No code changes needed

## Tips

- **Test after changes.** Run the pipeline on a sample submission to verify your rules produce the expected results.
- **When in doubt, be explicit.** If you can think of an edge case, address it in the rule text. The AI follows what you write.
- **Check results for inconsistency.** If the same scenario sometimes passes and sometimes fails, the rule probably needs to be more specific about that scenario.
