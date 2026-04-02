"""Generic LLM-based document validator driven by YAML config rules."""

import json
import re
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from openai import AsyncAzureOpenAI

from src.classification.doc_type_config import DocTypeConfig
from src.models import ExtractedDoc, FormAnalysisResult, ValidationResult
from src.validators.base import BaseValidator

# Regex to detect date-based rules so they can be handled in Python
_DATE_RULE_PATTERN = re.compile(r"\bdate\b.*\bwithin\b.*\b(\d+)\s+(month|year|day)s?\b", re.IGNORECASE)

SYSTEM_PROMPT_TEMPLATE = """\
You are a document validator for HR benefit submissions.
You are verifying a "{display_name}" attachment against the submitted form.

Employee name from form: {employee_first_name} {employee_last_name}
Beneficiary name from form: {beneficiary_first_name}

Validate the following rules against the attachment text:
{rules}

Additionally, extract all dates mentioned in the document.

For each rule, determine if it passes or fails. Return ONLY valid JSON:
{{
  "results": [
    {{"rule": "rule text", "passed": true, "reason": "explanation"}}
  ],
  "extracted_dates": [
    {{"label": "what this date represents", "value": "YYYY-MM-DD"}}
  ]
}}"""


def _parse_date_rule(rule: str) -> tuple[str, int, str] | None:
    """If the rule is a date-within-window rule, return (date_label_hint, amount, unit)."""
    m = _DATE_RULE_PATTERN.search(rule)
    if m:
        amount = int(m.group(1))
        unit = m.group(2).lower()
        # Extract a label hint: e.g. "marriage date" from "The marriage date must be within..."
        label_match = re.match(r"(?:The\s+)?(.+?date)", rule, re.IGNORECASE)
        label_hint = label_match.group(1).lower() if label_match else "date"
        return label_hint, amount, unit
    return None


def _check_date_within(event_date: date, today: date, amount: int, unit: str) -> bool:
    """Check if event_date is within the last `amount` `unit`s from today."""
    if event_date > today:
        return False
    if unit == "month":
        cutoff = today - relativedelta(months=amount)
    elif unit == "year":
        cutoff = today - relativedelta(years=amount)
    else:
        cutoff = today - timedelta(days=amount)
    return event_date >= cutoff


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
        # Separate date-window rules (handled in Python) from other rules (handled by LLM)
        date_rules: list[tuple[str, str, int, str]] = []  # (original_rule, label_hint, amount, unit)
        llm_rules: list[str] = []
        for rule in self._config.validation_rules:
            parsed = _parse_date_rule(rule)
            if parsed:
                date_rules.append((rule, *parsed))
            else:
                llm_rules.append(rule)

        rules_text = "\n".join(f"- {r}" for r in llm_rules)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            display_name=self._config.display_name,
            employee_first_name=form_analysis.employee_first_name or "",
            employee_last_name=form_analysis.employee_last_name or "",
            beneficiary_first_name=form_analysis.beneficiary_first_name or "",
            rules=rules_text,
        )

        response = await self._client.chat.completions.create(
            model=self._deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Validate this document:\n\n{attachment_extracted.content}"},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )

        raw = json.loads(response.choices[0].message.content)
        failed_reasons = [
            r["reason"] for r in raw["results"] if not r["passed"]
        ]

        # Evaluate date-window rules in Python using LLM-extracted dates
        today = date.today()
        extracted_dates = raw.get("extracted_dates", [])
        for original_rule, label_hint, amount, unit in date_rules:
            # Find the best matching extracted date by label
            matched_date = None
            for d in extracted_dates:
                if label_hint in d.get("label", "").lower():
                    try:
                        matched_date = date.fromisoformat(d["value"])
                    except (ValueError, KeyError):
                        continue
                    break
            # Fall back to first extracted date if no label match
            if matched_date is None and extracted_dates:
                try:
                    matched_date = date.fromisoformat(extracted_dates[0]["value"])
                except (ValueError, KeyError):
                    pass

            if matched_date is None:
                failed_reasons.append(f"Could not find a date in the document to evaluate: {original_rule}")
            elif not _check_date_within(matched_date, today, amount, unit):
                failed_reasons.append(
                    f"The date {matched_date.isoformat()} is not within the last {amount} {unit}(s) "
                    f"from today ({today.isoformat()})"
                )

        return ValidationResult(
            submission_id="",
            form_name=str(attachment_extracted.source_path),
            submitted_by="",
            status="passed" if not failed_reasons else "failed",
            reasons=failed_reasons,
        )
