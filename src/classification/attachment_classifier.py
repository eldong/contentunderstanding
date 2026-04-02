"""Attachment classifier that uses Azure OpenAI GPT-4o to classify documents."""

from openai import AsyncAzureOpenAI

from src.classification.doc_type_config import DocTypeConfig
from src.models import ClassifierResponse, ExtractedDoc

SYSTEM_PROMPT_TEMPLATE = """\
You are a document classifier for HR benefit submissions.
Given the extracted text of an attachment document, classify it into exactly \
one of these categories:

{categories}
- "unknown" — does not match any of the above categories

Return ONLY valid JSON matching this exact schema:
{{
  "doc_type": {doc_type_enum},
  "confidence": 0.0 to 1.0,
  "reasoning": "brief explanation of why this classification was chosen"
}}"""


def _build_classifier_prompt(doc_type_configs: list[DocTypeConfig]) -> str:
    """Build the system prompt with categories from all doc type configs."""
    lines = []
    for config in doc_type_configs:
        indicators = ", ".join(config.indicators)
        lines.append(
            f'- "{config.doc_type}" — {config.display_name}: '
            f"{config.description}. Look for: {indicators}"
        )
    categories = "\n".join(lines)
    doc_type_enum = (
        " | ".join(f'"{c.doc_type}"' for c in doc_type_configs) + ' | "unknown"'
    )
    return SYSTEM_PROMPT_TEMPLATE.format(
        categories=categories,
        doc_type_enum=doc_type_enum,
    )


class AttachmentClassifier:
    """Classifies extracted attachment text using GPT-4o."""

    def __init__(
        self,
        client: AsyncAzureOpenAI,
        deployment: str,
        doc_type_configs: list[DocTypeConfig],
    ) -> None:
        self._client = client
        self._deployment = deployment
        self._system_prompt = _build_classifier_prompt(doc_type_configs)

    async def classify(self, extracted: ExtractedDoc) -> ClassifierResponse:
        response = await self._client.chat.completions.create(
            model=self._deployment,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": f"Classify this document:\n\n{extracted.content}"},
            ],
            response_format={"type": "json_object"},
        )
        return ClassifierResponse.model_validate_json(
            response.choices[0].message.content
        )
