"""Generic LLM-based document validator driven by YAML config rules."""

import json
import re
from datetime import date, timedelta

from openai import AsyncAzureOpenAI

from src.classification.doc_type_config import DocTypeConfig
from src.models import ExtractedDoc, FormAnalysisResult, RuleResult, ValidationResult
from src.validators.base import BaseValidator

SYSTEM_PROMPT_TEMPLATE = """\
You are a document validator for HR benefit submissions.
You are verifying a "{display_name}" attachment against the submitted form.

Employee name from form: {employee_first_name} {employee_last_name}
Beneficiary name from form: {beneficiary_first_name}
Today's date: {today_date}

Validate the following rules against the attachment text.
The full text of the submitted form is provided below the attachment text
so you can extract any dates or details the rules reference from the form.

Rules:
{rules}

For each rule, determine if it passes or fails.

If a rule involves checking whether a date falls within a time window
(e.g. "must be within the last 12 months"), you MUST include a "date_check"
object with the extracted date, the required window, and the reference date
that the window is measured from. The system will verify the date comparison
programmatically — do NOT decide pass/fail for date-window rules yourself.
Set "passed" to true as a placeholder for those rules.

Return ONLY valid JSON:
{{
  "results": [
    {{
      "rule": "rule text",
      "passed": true,
      "reason": "explanation",
      "date_check": null
    }},
    {{
      "rule": "date rule text",
      "passed": true,
      "reason": "extracted date for programmatic check",
      "date_check": {{
        "extracted_date": "YYYY-MM-DD",
        "reference_date": "YYYY-MM-DD",
        "window": "N units"
      }}
    }}
  ]
}}

The "date_check.extracted_date" is the date found on the attachment document.
The "date_check.reference_date" is the date the window is measured from.
Extract it from the form text or attachment text based on what the rule
describes. If the rule does not specify a reference, use today's date.
The "date_check.window" field must use the format "<number> <unit>" where
unit is one of: days, weeks, months, years. Example: "12 months".
Set "date_check" to null for rules that do not involve date-window checks."""


def _parse_duration(duration_str: str) -> timedelta:
    """Parse a human-readable duration like '12 months' or '60 days' into a timedelta."""
    m = re.match(r"(\d+)\s+(day|week|month|year)s?", duration_str.strip(), re.IGNORECASE)
    if not m:
        raise ValueError(f"Cannot parse duration: {duration_str!r}")
    amount = int(m.group(1))
    unit = m.group(2).lower()
    if unit == "day":
        return timedelta(days=amount)
    if unit == "week":
        return timedelta(weeks=amount)
    if unit == "month":
        return timedelta(days=amount * 30)
    # year
    return timedelta(days=amount * 365)


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
        form_extracted: ExtractedDoc,
        attachment_extracted: ExtractedDoc,
    ) -> ValidationResult:
        rules_text = "\n".join(f"- {r}" for r in self._config.validation_rules)
        today = date.today()
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            display_name=self._config.display_name,
            employee_first_name=form_analysis.employee_first_name or "",
            employee_last_name=form_analysis.employee_last_name or "",
            beneficiary_first_name=form_analysis.beneficiary_first_name or "",
            today_date=today.isoformat(),
            rules=rules_text,
        )

        user_content = (
            f"=== ATTACHMENT TEXT ===\n{attachment_extracted.content}\n\n"
            f"=== SUBMITTED FORM TEXT ===\n{form_extracted.content}"
        )

        response = await self._client.chat.completions.create(
            model=self._deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )

        raw = json.loads(response.choices[0].message.content)
        rule_results: list[RuleResult] = []

        for r in raw["results"]:
            date_check = r.get("date_check")
            if date_check:
                # Override LLM pass/fail with deterministic Python date math
                date_str = date_check.get("extracted_date")
                window_str = date_check.get("window")
                ref_str = date_check.get("reference_date")
                if not date_str:
                    rule_results.append(RuleResult(
                        rule=r["rule"],
                        result="fail",
                        detail=f"Could not extract a date for rule: {r['rule']}",
                    ))
                    continue
                try:
                    event_date = date.fromisoformat(date_str)
                except ValueError:
                    rule_results.append(RuleResult(
                        rule=r["rule"],
                        result="fail",
                        detail=f"Could not parse date '{date_str}' for rule: {r['rule']}",
                    ))
                    continue
                try:
                    ref_date = date.fromisoformat(ref_str) if ref_str else today
                except ValueError:
                    ref_date = today
                try:
                    window = _parse_duration(window_str)
                except (ValueError, TypeError):
                    rule_results.append(RuleResult(
                        rule=r["rule"],
                        result="fail",
                        detail=f"Could not parse time window '{window_str}' for rule: {r['rule']}",
                    ))
                    continue
                cutoff = ref_date - window
                if event_date > ref_date:
                    rule_results.append(RuleResult(
                        rule=r["rule"],
                        result="fail",
                        detail=(
                            f"The date {event_date.isoformat()} is after the "
                            f"application date {ref_date.isoformat()}"
                        ),
                    ))
                elif event_date < cutoff:
                    rule_results.append(RuleResult(
                        rule=r["rule"],
                        result="fail",
                        detail=(
                            f"The date {event_date.isoformat()} is not within the last "
                            f"{window_str} of {ref_date.isoformat()} "
                            f"(cutoff: {cutoff.isoformat()})"
                        ),
                    ))
                else:
                    rule_results.append(RuleResult(
                        rule=r["rule"],
                        result="pass",
                        detail=(
                            f"The date {event_date.isoformat()} is within the last "
                            f"{window_str} of {ref_date.isoformat()} "
                            f"(cutoff: {cutoff.isoformat()})"
                        ),
                    ))
            else:
                rule_results.append(RuleResult(
                    rule=r["rule"],
                    result="pass" if r["passed"] else "fail",
                    detail=r["reason"],
                ))

        has_failures = any(rr.result == "fail" for rr in rule_results)
        return ValidationResult(
            submission_id="",
            form_name=str(attachment_extracted.source_path),
            submitted_by="",
            status="failed" if has_failures else "passed",
            rule_results=rule_results,
        )
