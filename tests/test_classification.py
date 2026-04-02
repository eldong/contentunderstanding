"""Tests for the form analyzer and attachment classifier."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.classification.attachment_classifier import (
    AttachmentClassifier,
    _build_classifier_prompt,
)
from src.classification.doc_type_config import DocTypeConfig
from src.classification.doc_type_rule_config import DocTypeRuleConfig
from src.classification.form_analyzer import FormAnalyzer, _build_system_prompt
from src.models import ExtractedDoc


SAMPLE_RULE_CONFIGS = [
    DocTypeRuleConfig(
        doc_type="marriage",
        display_name="Marriage",
        description="Adding beneficiary due to marriage",
        required_attachment_types=["marriage_certificate"],
        form_validation_rules=["Beneficiary first name must be filled out"],
    ),
    DocTypeRuleConfig(
        doc_type="birth",
        display_name="Birth",
        description="Adding beneficiary due to birth",
        required_attachment_types=["birth_certificate"],
        form_validation_rules=[],
    ),
    DocTypeRuleConfig(
        doc_type="new_hire",
        display_name="New Hire",
        description="New hire enrollment",
        required_attachment_types=[],
        form_validation_rules=["Hire date must be filled out"],
    ),
]


def _make_mock_client(response_json: dict) -> AsyncMock:
    """Create a mock AsyncAzureOpenAI client that returns the given JSON."""
    client = AsyncMock()
    message = MagicMock()
    message.content = json.dumps(response_json)
    choice = MagicMock()
    choice.message = message
    completion = MagicMock()
    completion.choices = [choice]
    client.chat.completions.create.return_value = completion
    return client


SAMPLE_FORM = ExtractedDoc(
    source_path="form.pdf",
    content="BENEFICIARY ENROLLMENT FORM\nAction: Add Beneficiary\nReason: Marriage\nEmployee: Jane Smith\nBeneficiary: Michael Johnson",
    fields={},
    confidence=0.95,
)


class TestFormAnalyzer:
    @pytest.mark.asyncio
    async def test_relevant_form(self):
        response = {
            "form_type": "add_beneficiary",
            "reason": "marriage",
            "employee_first_name": "Jane",
            "employee_last_name": "Smith",
            "beneficiary_first_name": "Michael",
            "is_relevant": True,
        }
        client = _make_mock_client(response)
        analyzer = FormAnalyzer(client, "gpt-4o", SAMPLE_RULE_CONFIGS)

        result = await analyzer.analyze(SAMPLE_FORM)

        assert result.form_type == "add_beneficiary"
        assert result.reason == "marriage"
        assert result.employee_first_name == "Jane"
        assert result.employee_last_name == "Smith"
        assert result.beneficiary_first_name == "Michael"
        assert result.is_relevant is True

    @pytest.mark.asyncio
    async def test_irrelevant_form(self):
        response = {
            "form_type": "unknown",
            "reason": None,
            "employee_first_name": None,
            "employee_last_name": None,
            "beneficiary_first_name": None,
            "is_relevant": False,
        }
        client = _make_mock_client(response)
        analyzer = FormAnalyzer(client, "gpt-4o", SAMPLE_RULE_CONFIGS)

        result = await analyzer.analyze(SAMPLE_FORM)

        assert result.form_type == "unknown"
        assert result.reason is None
        assert result.is_relevant is False

    @pytest.mark.asyncio
    async def test_no_reason_selected(self):
        response = {
            "form_type": "add_beneficiary",
            "reason": None,
            "employee_first_name": "Jane",
            "employee_last_name": "Smith",
            "beneficiary_first_name": None,
            "is_relevant": False,
        }
        client = _make_mock_client(response)
        analyzer = FormAnalyzer(client, "gpt-4o", SAMPLE_RULE_CONFIGS)

        result = await analyzer.analyze(SAMPLE_FORM)

        assert result.form_type == "add_beneficiary"
        assert result.reason is None
        assert result.is_relevant is False

    @pytest.mark.asyncio
    async def test_system_prompt_sent(self):
        client = _make_mock_client(
            {"form_type": "unknown", "reason": None, "is_relevant": False}
        )
        analyzer = FormAnalyzer(client, "gpt-4o", SAMPLE_RULE_CONFIGS)

        await analyzer.analyze(SAMPLE_FORM)

        call_kwargs = client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert "marriage" in messages[0]["content"]
        assert messages[1]["role"] == "user"
        assert SAMPLE_FORM.content in messages[1]["content"]

    @pytest.mark.asyncio
    async def test_json_response_format(self):
        client = _make_mock_client(
            {"form_type": "unknown", "reason": None, "is_relevant": False}
        )
        analyzer = FormAnalyzer(client, "gpt-4o", SAMPLE_RULE_CONFIGS)

        await analyzer.analyze(SAMPLE_FORM)

        call_kwargs = client.chat.completions.create.call_args.kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}


class TestBuildSystemPrompt:
    def test_prompt_includes_all_reasons(self):
        prompt = _build_system_prompt(SAMPLE_RULE_CONFIGS)
        assert "birth" in prompt
        assert "marriage" in prompt
        assert "new_hire" in prompt

    def test_prompt_with_empty_configs(self):
        prompt = _build_system_prompt([])
        assert "Valid reasons:" in prompt

    @pytest.mark.asyncio
    async def test_deployment_used_as_model(self):
        client = _make_mock_client(
            {"form_type": "unknown", "reason": None, "is_relevant": False}
        )
        analyzer = FormAnalyzer(client, "my-gpt4o-deployment", SAMPLE_RULE_CONFIGS)

        await analyzer.analyze(SAMPLE_FORM)

        call_kwargs = client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "my-gpt4o-deployment"


# --- Attachment Classifier Tests ---

SAMPLE_DOC_TYPE_CONFIGS = [
    DocTypeConfig(
        doc_type="marriage_certificate",
        display_name="Marriage Certificate",
        description="Official government-issued certificate of marriage",
        indicators=["certificate of marriage", "united in marriage", "marriage license"],
        validation_rules=["Names must match"],
    ),
    DocTypeConfig(
        doc_type="birth_certificate",
        display_name="Birth Certificate",
        description="Official government-issued certificate of live birth",
        indicators=["certificate of live birth", "date of birth", "born on"],
        validation_rules=["Date must be recent"],
    ),
]

SAMPLE_ATTACHMENT = ExtractedDoc(
    source_path="marriage_cert.pdf",
    content="STATE OF CALIFORNIA\nCERTIFICATE OF MARRIAGE\nThis certifies that Jane Smith and Michael Johnson were united in marriage on January 15, 2026.",
    fields={},
    confidence=0.90,
)


class TestAttachmentClassifier:
    @pytest.mark.asyncio
    async def test_marriage_certificate(self):
        response = {
            "doc_type": "marriage_certificate",
            "confidence": 0.95,
            "reasoning": "Contains marriage certificate language",
        }
        client = _make_mock_client(response)
        classifier = AttachmentClassifier(client, "gpt-4o", SAMPLE_DOC_TYPE_CONFIGS)

        result = await classifier.classify(SAMPLE_ATTACHMENT)

        assert result.doc_type == "marriage_certificate"
        assert result.confidence == 0.95
        assert result.reasoning == "Contains marriage certificate language"

    @pytest.mark.asyncio
    async def test_unknown_document(self):
        response = {
            "doc_type": "unknown",
            "confidence": 0.3,
            "reasoning": "Document does not match known categories",
        }
        client = _make_mock_client(response)
        classifier = AttachmentClassifier(client, "gpt-4o", SAMPLE_DOC_TYPE_CONFIGS)

        unknown_doc = ExtractedDoc(
            source_path="random.pdf",
            content="This is a random document with no recognizable pattern.",
            fields={},
            confidence=0.80,
        )
        result = await classifier.classify(unknown_doc)

        assert result.doc_type == "unknown"
        assert result.confidence == 0.3

    @pytest.mark.asyncio
    async def test_prompt_includes_doc_types_and_indicators(self):
        client = _make_mock_client(
            {"doc_type": "unknown", "confidence": 0.0, "reasoning": ""}
        )
        classifier = AttachmentClassifier(client, "gpt-4o", SAMPLE_DOC_TYPE_CONFIGS)

        await classifier.classify(SAMPLE_ATTACHMENT)

        call_kwargs = client.chat.completions.create.call_args.kwargs
        prompt = call_kwargs["messages"][0]["content"]
        assert "marriage_certificate" in prompt
        assert "birth_certificate" in prompt
        assert "certificate of marriage" in prompt
        assert "certificate of live birth" in prompt
        assert '"unknown"' in prompt

    @pytest.mark.asyncio
    async def test_json_response_format(self):
        client = _make_mock_client(
            {"doc_type": "unknown", "confidence": 0.0, "reasoning": ""}
        )
        classifier = AttachmentClassifier(client, "gpt-4o", SAMPLE_DOC_TYPE_CONFIGS)

        await classifier.classify(SAMPLE_ATTACHMENT)

        call_kwargs = client.chat.completions.create.call_args.kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_user_message_contains_content(self):
        client = _make_mock_client(
            {"doc_type": "unknown", "confidence": 0.0, "reasoning": ""}
        )
        classifier = AttachmentClassifier(client, "gpt-4o", SAMPLE_DOC_TYPE_CONFIGS)

        await classifier.classify(SAMPLE_ATTACHMENT)

        call_kwargs = client.chat.completions.create.call_args.kwargs
        user_msg = call_kwargs["messages"][1]["content"]
        assert SAMPLE_ATTACHMENT.content in user_msg


class TestBuildClassifierPrompt:
    def test_includes_all_doc_types(self):
        prompt = _build_classifier_prompt(SAMPLE_DOC_TYPE_CONFIGS)
        assert "marriage_certificate" in prompt
        assert "birth_certificate" in prompt
        assert '"unknown"' in prompt

    def test_empty_configs(self):
        prompt = _build_classifier_prompt([])
        assert '"unknown"' in prompt
