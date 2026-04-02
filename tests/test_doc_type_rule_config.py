"""Tests for the doc type rule config loader."""

import pytest

from src.classification.doc_type_rule_config import DocTypeRuleConfig, load_doc_type_rule_configs


VALID_YAML = """\
doc_type: marriage
display_name: Marriage
description: "Adding beneficiary due to marriage"
required_attachment_types:
  - marriage_certificate
form_validation_rules:
  - "Beneficiary first name must be filled out"
"""

NO_ATTACHMENTS_YAML = """\
doc_type: new_hire
display_name: New Hire
description: "New hire enrollment"
required_attachment_types: []
form_validation_rules:
  - "Hire date must be filled out"
"""

INVALID_YAML = """\
doc_type: bad
# missing required fields
"""


class TestDocTypeRuleConfig:
    def test_valid_config(self):
        config = DocTypeRuleConfig(
            doc_type="marriage",
            display_name="Marriage",
            description="Adding beneficiary due to marriage",
            required_attachment_types=["marriage_certificate"],
            form_validation_rules=["Beneficiary first name must be filled out"],
        )
        assert config.doc_type == "marriage"
        assert config.required_attachment_types == ["marriage_certificate"]

    def test_no_attachments_required(self):
        config = DocTypeRuleConfig(
            doc_type="new_hire",
            display_name="New Hire",
            description="New hire enrollment",
            required_attachment_types=[],
            form_validation_rules=["Hire date must be filled out"],
        )
        assert config.required_attachment_types == []
        assert len(config.form_validation_rules) == 1

    def test_defaults_to_empty_lists(self):
        config = DocTypeRuleConfig(
            doc_type="test",
            display_name="Test",
            description="Test doc type",
        )
        assert config.required_attachment_types == []
        assert config.form_validation_rules == []

    def test_missing_field_raises(self):
        with pytest.raises(Exception):
            DocTypeRuleConfig(doc_type="bad")


class TestLoadDocTypeRuleConfigs:
    def test_loads_yaml_files(self, tmp_path):
        (tmp_path / "marriage.yaml").write_text(VALID_YAML, encoding="utf-8")
        configs = load_doc_type_rule_configs(tmp_path)
        assert len(configs) == 1
        assert configs[0].doc_type == "marriage"

    def test_loads_multiple_files(self, tmp_path):
        (tmp_path / "marriage.yaml").write_text(VALID_YAML, encoding="utf-8")
        (tmp_path / "new_hire.yaml").write_text(NO_ATTACHMENTS_YAML, encoding="utf-8")
        configs = load_doc_type_rule_configs(tmp_path)
        assert len(configs) == 2
        doc_types = {c.doc_type for c in configs}
        assert doc_types == {"marriage", "new_hire"}

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
