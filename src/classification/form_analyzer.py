"""Form analyzer that uses Azure OpenAI GPT-4o to classify HR forms."""

from openai import AsyncAzureOpenAI

from src.classification.form_type_config import FormTypeConfig
from src.models import ExtractedDoc, FormAnalysisResult

SYSTEM_PROMPT_TEMPLATE = """\
You are a document analyst specializing in HR benefits forms.
Given the extracted text of a form, determine:
1. Is this an "Add Beneficiary to employer-sponsored health plan" form? \
If yes, set form_type to "add_beneficiary". Otherwise set form_type to "unknown".
2. What reason/life event is selected on the form? Look for checkboxes or \
indicators. Valid reasons: {reasons_list}. \
Set reason to the lowercase event name or null if none found.
3. Extract the employee's first and last name.
4. Extract the beneficiary's first name.
5. Extract the application/signature/submission date from the form in YYYY-MM-DD format. \
Look for the date the employee signed or submitted the form (not the effective date). \
Set to null if not found.
6. Set is_relevant to true ONLY if form_type is "add_beneficiary" AND a reason \
is selected.

Return ONLY valid JSON matching this exact schema:
{{
  "form_type": "add_beneficiary" | "unknown",
  "reason": {reasons_enum},
  "employee_first_name": "string or null",
  "employee_last_name": "string or null",
  "beneficiary_first_name": "string or null",
  "application_date": "YYYY-MM-DD or null",
  "is_relevant": true | false
}}"""


def _build_system_prompt(form_type_configs: list[FormTypeConfig]) -> str:
    """Build the system prompt with valid doc types from all form type configs."""
    types_sorted = sorted(c.doc_type for c in form_type_configs)
    reasons_list = ", ".join(types_sorted)
    reasons_enum = " | ".join(f'"{ r}"' for r in types_sorted) + " | null"
    return SYSTEM_PROMPT_TEMPLATE.format(
        reasons_list=reasons_list,
        reasons_enum=reasons_enum,
    )


class FormAnalyzer:
    """Analyzes extracted form text using GPT-4o to produce a FormAnalysisResult."""

    def __init__(
        self,
        client: AsyncAzureOpenAI,
        deployment: str,
        form_type_configs: list[FormTypeConfig],
    ) -> None:
        self._client = client
        self._deployment = deployment
        self._system_prompt = _build_system_prompt(form_type_configs)

    async def analyze(self, extracted: ExtractedDoc) -> FormAnalysisResult:
        response = await self._client.chat.completions.create(
            model=self._deployment,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": f"Analyze this form:\n\n{extracted.content}"},
            ],
            response_format={"type": "json_object"},
        )
        return FormAnalysisResult.model_validate_json(
            response.choices[0].message.content
        )
