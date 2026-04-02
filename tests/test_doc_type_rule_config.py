"""Tests for the doc type rule config loader."""

import pytest

from src.classification.doc_type_rule_config import DocTypeRuleConfig, load_doc_type_rule_configs


VALID_YAML = """\
reason: marriage
display_name: Marriage
description: "Adding beneficiary due to marriage"
required_doc_types:
  - marriage_certificate
form_validation_rules:
  - "Beneficiary first name must be filled out"
"""

NO_ATTACHMENTS_YAML = """\
reason: new_hire
display_name: New Hire
description: "New hire enrollment"
required_doc_types: []
form_validation_rules:
  - "Hire date must be filled out"
"""

INVALID_YAML = """\
reason: bad
# missing required fields
"""


class TestDocTypeRuleConfig:
    def test_valid_config(self):
        config = DocTypeRuleConfig(
            reason="marriage",
            display_name="Marriage",
            description="Adding beneficiary due to marriage",
            required_doc_types=["marriage_certificate"],
            form_validation_rules=["Beneficiary first name must be filled out"],
        )
        assert config.reason == "marriage"
        assert config.required_doc_types == ["marriage_certificate"]

    def test_no_attachments_required(self):
        config = DocTypeRuleConfig(
            reason="new_hire",
            display_name="New Hire",
            description="New hire enrollment",
            required_doc_types=[],
            form_validation_rules=["Hire date must be filled out"],
        )
        assert config.required_doc_types == []
        assert len(config.form_validation_rules) == 1

    def test_defaults_to_empty_lists(self):
        config = DocTypeRuleConfig(
            reason="test",
            display_name="Test",
            description="Test reason",
        )
        assert config.required_doc_types == []
        assert config.form_validation_rules == []

    def test_missing_field_raises(self):
        with pytest.raises(Exception):
            DocTypeRuleConfig(reason="bad")


class TestLoadDocTypeRuleConfigs:
    def test_loads_yaml_files(self, tmp_path):
        (tmp_path / "marriage.yaml").write_text(VALID_YAML, encoding="utf-8")
        configs = load_doc_type_rule_configs(tmp_path)
        assert len(configs) == 1
        assert configs[0].reason == "marriage"

    def test_loads_multiple_files(self, tmp_path):
        (tmp_path / "marriage.yaml").write_text(VALID_YAML, encoding="utf-8")
        (tmp_path / "new_hire.yaml").write_text(NO_ATTACHMENTS_YAML, encoding="utf-8")
        configs = load_doc_type_rule_configs(tmp_path)
        assert len(configs) == 2
        reasons = {c.reason for c in configs}
        assert reasons == {"marriage", "new_hire"}

    def test_skips_invalid_yaml(self, tmp_path):
        (tmp_path / "good.yaml").write_text(VALID_YAML, encoding="utf-8")
        (tmp_path / "bad.yaml").write_text(INVALID_YAML, encoding="utf-8")
        configs = load_doc_type_rule_configs(tmp_path)
        assert len(configs) == 1

    def test_empty_directory(self, tmp_path):
        configs = load_doc_type_rule_configs(tmp_path)
        assert configs == []

    def test_nonexistent_directory(self, tmp_path):
        configs = load_doc_type_rule_configs(tmp_path / "nonexistent")
        assert configs == []
