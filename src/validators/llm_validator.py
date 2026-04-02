"""Generic LLM-based document validator driven by YAML config rules."""

import json
from datetime import date

from openai import AsyncAzureOpenAI

from src.classification.doc_type_config import DocTypeConfig
from src.models import ExtractedDoc, FormAnalysisResult, ValidationResult
from src.validators.base import BaseValidator

SYSTEM_PROMPT_TEMPLATE = """\
You are a document validator for HR benefit submissions.
You are verifying a "{display_name}" attachment against the submitted form.

Employee name from form: {employee_first_name} {employee_last_name}
Beneficiary name from form: {beneficiary_first_name}
Today's date: {today_date}

Validate the following rules against the attachment text:
{rules}

For each rule, determine if it passes or fails. Return ONLY valid JSON:
{{
  "results": [
    {{"rule": "rule text", "passed": true, "reason": "explanation"}}
  ]
}}"""


class LLMValidator(BaseValidator):
    """Validates attachments using GPT-4o with rules from a DocTypeConfig."""

    def __init__(
        self,
        client: AsyncAzureOpenAI,
        deployment: str,
        doc_type_config: DocTypeConfig,
    ) -> None:
        self._client = client
        self._deployment = deployment
        self._config = doc_type_config

    async def validate(
        self,
        form_analysis: FormAnalysisResult,
        attachment_extracted: ExtractedDoc,
    ) -> ValidationResult:
        rules_text = "\n".join(f"- {r}" for r in self._config.validation_rules)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            display_name=self._config.display_name,
            employee_first_name=form_analysis.employee_first_name or "",
            employee_last_name=form_analysis.employee_last_name or "",
            beneficiary_first_name=form_analysis.beneficiary_first_name or "",
            today_date=date.today().isoformat(),
            rules=rules_text,
        )

        response = await self._client.chat.completions.create(
            model=self._deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Validate this document:\n\n{attachment_extracted.content}"},
            ],
            response_format={"type": "json_object"},
        )

        raw = json.loads(response.choices[0].message.content)
        failed_reasons = [
            r["reason"] for r in raw["results"] if not r["passed"]
        ]

        return ValidationResult(
            submission_id="",
            form_name=str(attachment_extracted.source_path),
            submitted_by="",
            status="passed" if not failed_reasons else "failed",
            reasons=failed_reasons,
        )
