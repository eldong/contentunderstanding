"""Tests for the validator framework: BaseValidator, LLMValidator, ValidatorRegistry."""

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.classification.doc_type_config import DocTypeConfig
from src.models import ExtractedDoc, FormAnalysisResult, ValidationResult
from src.validators.base import BaseValidator
from src.validators.llm_validator import LLMValidator
from src.validators.registry import ValidatorRegistry


SAMPLE_DOC_TYPE_CONFIG = DocTypeConfig(
    doc_type="marriage_certificate",
    display_name="Marriage Certificate",
    description="Official government-issued certificate of marriage",
    indicators=["certificate of marriage", "united in marriage"],
    validation_rules=[
        "The names must match the employee and beneficiary on the form",
        "The marriage date must be within the last 12 months",
        "The document must be an official government-issued certificate",
    ],
)

SAMPLE_FORM_ANALYSIS = FormAnalysisResult(
    form_type="add_beneficiary",
    reason="marriage",
    employee_first_name="Jane",
    employee_last_name="Smith",
    beneficiary_first_name="Michael",
    application_date="2026-03-15",
    is_relevant=True,
)

SAMPLE_ATTACHMENT = ExtractedDoc(
    source_path="marriage_cert.pdf",
    content="CERTIFICATE OF MARRIAGE\nJane Smith and Michael Johnson\nDate: 2024-06-15",
    fields={},
    confidence=0.95,
)


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


class TestBaseValidator:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseValidator()


class TestLLMValidator:
    @pytest.mark.asyncio
    @patch("src.validators.llm_validator.date")
    async def test_all_rules_pass(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 2)
        mock_date.fromisoformat = date.fromisoformat
        response = {
            "results": [
                {"rule": "names match", "passed": True, "reason": "Names match form", "date_check": None},
                {"rule": "marriage date within 12 months", "passed": True, "reason": "extracted date", "date_check": {"extracted_date": "2026-02-14", "reference_date": "2026-03-15", "window": "12 months"}},
                {"rule": "official doc", "passed": True, "reason": "Appears official", "date_check": None},
            ]
        }
        client = _make_mock_client(response)
        validator = LLMValidator(client, "gpt-4o", SAMPLE_DOC_TYPE_CONFIG)

        result = await validator.validate(SAMPLE_FORM_ANALYSIS, SAMPLE_ATTACHMENT)

        assert result.status == "passed"
        assert result.reasons == []
        assert len(result.passed_reasons) == 3
        assert "Names match form" in result.passed_reasons
        assert any("within" in r for r in result.passed_reasons)
        assert "Appears official" in result.passed_reasons

    @pytest.mark.asyncio
    @patch("src.validators.llm_validator.date")
    async def test_some_rules_fail(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 2)
        mock_date.fromisoformat = date.fromisoformat
        response = {
            "results": [
                {"rule": "names match", "passed": True, "reason": "Names match", "date_check": None},
                {"rule": "date within 12 months", "passed": True, "reason": "extracted", "date_check": {"extracted_date": "2020-01-10", "reference_date": "2026-03-15", "window": "12 months"}},
                {"rule": "official doc", "passed": False, "reason": "No seal found", "date_check": None},
            ]
        }
        client = _make_mock_client(response)
        validator = LLMValidator(client, "gpt-4o", SAMPLE_DOC_TYPE_CONFIG)

        result = await validator.validate(SAMPLE_FORM_ANALYSIS, SAMPLE_ATTACHMENT)

        assert result.status == "failed"
        assert len(result.reasons) == 2
        assert "No seal found" in result.reasons
        assert any("not within" in r for r in result.reasons)
        assert len(result.passed_reasons) == 1
        assert "Names match" in result.passed_reasons[0]

    @pytest.mark.asyncio
    async def test_prompt_includes_validation_rules(self):
        client = _make_mock_client({"results": []})
        validator = LLMValidator(client, "gpt-4o", SAMPLE_DOC_TYPE_CONFIG)

        await validator.validate(SAMPLE_FORM_ANALYSIS, SAMPLE_ATTACHMENT)

        call_args = client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]
        for rule in SAMPLE_DOC_TYPE_CONFIG.validation_rules:
            assert rule in system_msg

    @pytest.mark.asyncio
    async def test_prompt_includes_form_data(self):
        client = _make_mock_client({"results": []})
        validator = LLMValidator(client, "gpt-4o", SAMPLE_DOC_TYPE_CONFIG)

        await validator.validate(SAMPLE_FORM_ANALYSIS, SAMPLE_ATTACHMENT)

        call_args = client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]
        assert "Jane" in system_msg
        assert "Smith" in system_msg
        assert "Michael" in system_msg

    @pytest.mark.asyncio
    async def test_prompt_includes_attachment_content(self):
        client = _make_mock_client({"results": []})
        validator = LLMValidator(client, "gpt-4o", SAMPLE_DOC_TYPE_CONFIG)

        await validator.validate(SAMPLE_FORM_ANALYSIS, SAMPLE_ATTACHMENT)

        call_args = client.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]
        assert "CERTIFICATE OF MARRIAGE" in user_msg

    @pytest.mark.asyncio
    async def test_uses_json_response_format(self):
        client = _make_mock_client({"results": []})
        validator = LLMValidator(client, "gpt-4o", SAMPLE_DOC_TYPE_CONFIG)

        await validator.validate(SAMPLE_FORM_ANALYSIS, SAMPLE_ATTACHMENT)

        call_args = client.chat.completions.create.call_args
        assert call_args.kwargs["response_format"] == {"type": "json_object"}


class TestValidatorRegistry:
    def test_load_from_config_dir(self, tmp_path):
        yaml_content = """
doc_type: marriage_certificate
display_name: Marriage Certificate
description: Official marriage certificate
indicators:
  - certificate of marriage
validation_rules:
  - Names must match
"""
        (tmp_path / "marriage_certificate.yaml").write_text(yaml_content)
        client = AsyncMock()

        registry = ValidatorRegistry.load(tmp_path, client, "gpt-4o")

        assert "marriage_certificate" in registry.list_doc_types()

    def test_get_known_validator(self, tmp_path):
        yaml_content = """
doc_type: marriage_certificate
display_name: Marriage Certificate
description: Official marriage certificate
indicators:
  - certificate of marriage
validation_rules:
  - Names must match
"""
        (tmp_path / "marriage_certificate.yaml").write_text(yaml_content)
        client = AsyncMock()
        registry = ValidatorRegistry.load(tmp_path, client, "gpt-4o")

        validator = registry.get_validator("marriage_certificate")

        assert validator is not None
        assert isinstance(validator, LLMValidator)

    def test_get_unknown_validator(self, tmp_path):
        yaml_content = """
doc_type: marriage_certificate
display_name: Marriage Certificate
description: Official marriage certificate
indicators:
  - certificate of marriage
validation_rules:
  - Names must match
"""
        (tmp_path / "marriage_certificate.yaml").write_text(yaml_content)
        client = AsyncMock()
        registry = ValidatorRegistry.load(tmp_path, client, "gpt-4o")

        assert registry.get_validator("unknown_type") is None

    def test_list_doc_types_sorted(self, tmp_path):
        for name, dtype in [("b.yaml", "birth_certificate"), ("a.yaml", "adoption_decree")]:
            (tmp_path / name).write_text(
                f"doc_type: {dtype}\ndisplay_name: X\ndescription: X\nindicators:\n  - x\nvalidation_rules:\n  - rule"
            )
        client = AsyncMock()
        registry = ValidatorRegistry.load(tmp_path, client, "gpt-4o")

        doc_types = registry.list_doc_types()
        assert doc_types == ["adoption_decree", "birth_certificate"]

    def test_empty_config_dir(self, tmp_path):
        client = AsyncMock()
        registry = ValidatorRegistry.load(tmp_path, client, "gpt-4o")

        assert registry.list_doc_types() == []
        assert registry.get_validator("anything") is None


# --- Marriage certificate validation scenarios (M7) ---

# Use the real rules from config/doc_types/marriage_certificate.yaml
MARRIAGE_CERT_CONFIG = DocTypeConfig(
    doc_type="marriage_certificate",
    display_name="Marriage Certificate",
    description="Official government-issued certificate or license of marriage",
    indicators=[
        "certificate of marriage",
        "united in marriage",
        "marriage license",
        "joined in marriage",
        "certificate of marriage registration",
    ],
    validation_rules=[
        "The names on the certificate must match the employee and/or beneficiary names on the form",
        "The marriage date must be within the last 12 months",
        "The document must appear to be an official government-issued certificate",
    ],
)

MARRIAGE_FORM = FormAnalysisResult(
    form_type="add_beneficiary",
    reason="marriage",
    employee_first_name="Jane",
    employee_last_name="Smith",
    beneficiary_first_name="Michael",
    application_date="2026-03-25",
    is_relevant=True,
)

MARRIAGE_ATTACHMENT = ExtractedDoc(
    source_path="marriage_cert.pdf",
    content=(
        "STATE OF VIRGINIA - CERTIFICATE OF MARRIAGE\n"
        "This certifies that Jane Smith and Michael Johnson\n"
        "were united in marriage on March 15, 2026.\n"
        "Officiant: Rev. Thomas Williams\n"
        "Filed: March 16, 2026\n"
        "Seal: Commonwealth of Virginia"
    ),
    fields={},
    confidence=0.95,
)


class TestMarriageCertificateValidation:
    """Tests the LLMValidator with the real marriage_certificate.yaml rules."""

    @pytest.mark.asyncio
    @patch("src.validators.llm_validator.date")
    async def test_all_rules_pass(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 2)
        mock_date.fromisoformat = date.fromisoformat
        response = {
            "results": [
                {"rule": "names match", "passed": True, "reason": "Jane Smith and Michael appear on certificate", "date_check": None},
                {"rule": "date recent", "passed": True, "reason": "extracted", "date_check": {"extracted_date": "2026-03-15", "reference_date": "2026-03-25", "window": "12 months"}},
                {"rule": "official doc", "passed": True, "reason": "Contains state seal and officiant", "date_check": None},
            ]
        }
        client = _make_mock_client(response)
        validator = LLMValidator(client, "gpt-4o", MARRIAGE_CERT_CONFIG)

        result = await validator.validate(MARRIAGE_FORM, MARRIAGE_ATTACHMENT)

        assert result.status == "passed"
        assert result.reasons == []
        assert len(result.passed_reasons) == 3
        assert any("Jane Smith" in r or "Michael" in r for r in result.passed_reasons)
        assert any("within" in r for r in result.passed_reasons)
        assert any("seal" in r.lower() or "officiant" in r.lower() for r in result.passed_reasons)

    @pytest.mark.asyncio
    @patch("src.validators.llm_validator.date")
    async def test_employee_name_mismatch(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 2)
        mock_date.fromisoformat = date.fromisoformat
        response = {
            "results": [
                {"rule": "names match", "passed": False, "reason": "Employee name Jane Smith not found on certificate", "date_check": None},
                {"rule": "date recent", "passed": True, "reason": "extracted", "date_check": {"extracted_date": "2026-03-15", "reference_date": "2026-03-25", "window": "12 months"}},
                {"rule": "official doc", "passed": True, "reason": "Appears official", "date_check": None},
            ]
        }
        client = _make_mock_client(response)
        validator = LLMValidator(client, "gpt-4o", MARRIAGE_CERT_CONFIG)

        result = await validator.validate(MARRIAGE_FORM, MARRIAGE_ATTACHMENT)

        assert result.status == "failed"
        assert len(result.reasons) == 1
        assert "Jane Smith" in result.reasons[0]
        assert len(result.passed_reasons) == 2

    @pytest.mark.asyncio
    @patch("src.validators.llm_validator.date")
    async def test_beneficiary_name_mismatch(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 2)
        mock_date.fromisoformat = date.fromisoformat
        response = {
            "results": [
                {"rule": "names match", "passed": False, "reason": "Beneficiary name Michael does not appear on certificate", "date_check": None},
                {"rule": "date recent", "passed": True, "reason": "extracted", "date_check": {"extracted_date": "2026-03-15", "reference_date": "2026-03-25", "window": "12 months"}},
                {"rule": "official doc", "passed": True, "reason": "Appears official", "date_check": None},
            ]
        }
        client = _make_mock_client(response)
        validator = LLMValidator(client, "gpt-4o", MARRIAGE_CERT_CONFIG)

        result = await validator.validate(MARRIAGE_FORM, MARRIAGE_ATTACHMENT)

        assert result.status == "failed"
        assert len(result.reasons) == 1
        assert "Michael" in result.reasons[0]
        assert len(result.passed_reasons) == 2

    @pytest.mark.asyncio
    @patch("src.validators.llm_validator.date")
    async def test_date_too_old(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 2)
        mock_date.fromisoformat = date.fromisoformat
        response = {
            "results": [
                {"rule": "names match", "passed": True, "reason": "Names match", "date_check": None},
                {"rule": "date recent", "passed": True, "reason": "extracted", "date_check": {"extracted_date": "2020-01-10", "reference_date": "2026-03-25", "window": "12 months"}},
                {"rule": "official doc", "passed": True, "reason": "Appears official", "date_check": None},
            ]
        }
        client = _make_mock_client(response)
        validator = LLMValidator(client, "gpt-4o", MARRIAGE_CERT_CONFIG)

        result = await validator.validate(MARRIAGE_FORM, MARRIAGE_ATTACHMENT)

        assert result.status == "failed"
        assert len(result.reasons) == 1
        assert "not within" in result.reasons[0]
        assert "2020-01-10" in result.reasons[0]
        assert len(result.passed_reasons) == 2
        assert "Names match" in result.passed_reasons[0]

    @pytest.mark.asyncio
    @patch("src.validators.llm_validator.date")
    async def test_not_official_document(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 2)
        mock_date.fromisoformat = date.fromisoformat
        response = {
            "results": [
                {"rule": "names match", "passed": True, "reason": "Names match", "date_check": None},
                {"rule": "date recent", "passed": True, "reason": "extracted", "date_check": {"extracted_date": "2026-03-15", "reference_date": "2026-03-25", "window": "12 months"}},
                {"rule": "official doc", "passed": False, "reason": "No government seal or letterhead found", "date_check": None},
            ]
        }
        client = _make_mock_client(response)
        validator = LLMValidator(client, "gpt-4o", MARRIAGE_CERT_CONFIG)

        result = await validator.validate(MARRIAGE_FORM, MARRIAGE_ATTACHMENT)

        assert result.status == "failed"
        assert len(result.reasons) == 1
        assert "seal" in result.reasons[0].lower() or "government" in result.reasons[0].lower()
        assert len(result.passed_reasons) == 2

    @pytest.mark.asyncio
    @patch("src.validators.llm_validator.date")
    async def test_multiple_failures(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 2)
        mock_date.fromisoformat = date.fromisoformat
        response = {
            "results": [
                {"rule": "names match", "passed": False, "reason": "No matching names found", "date_check": None},
                {"rule": "date recent", "passed": True, "reason": "extracted", "date_check": {"extracted_date": "2020-01-10", "reference_date": "2026-03-25", "window": "12 months"}},
                {"rule": "official doc", "passed": False, "reason": "Document appears to be a photocopy", "date_check": None},
            ]
        }
        client = _make_mock_client(response)
        validator = LLMValidator(client, "gpt-4o", MARRIAGE_CERT_CONFIG)

        result = await validator.validate(MARRIAGE_FORM, MARRIAGE_ATTACHMENT)

        assert result.status == "failed"
        assert len(result.reasons) == 3
        assert result.passed_reasons == []

    @pytest.mark.asyncio
    async def test_prompt_uses_real_yaml_rules(self):
        client = _make_mock_client({"results": []})
        validator = LLMValidator(client, "gpt-4o", MARRIAGE_CERT_CONFIG)

        await validator.validate(MARRIAGE_FORM, MARRIAGE_ATTACHMENT)

        call_args = client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]
        assert "employee and/or beneficiary names" in system_msg
        assert "within the last 12 months" in system_msg
        assert "official government-issued certificate" in system_msg

    @pytest.mark.asyncio
    async def test_prompt_includes_employee_and_beneficiary(self):
        client = _make_mock_client({"results": []})
        validator = LLMValidator(client, "gpt-4o", MARRIAGE_CERT_CONFIG)

        await validator.validate(MARRIAGE_FORM, MARRIAGE_ATTACHMENT)

        call_args = client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]
        assert "Jane" in system_msg
        assert "Smith" in system_msg
        assert "Michael" in system_msg
        assert "Marriage Certificate" in system_msg
