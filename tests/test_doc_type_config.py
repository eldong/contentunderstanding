"""Tests for the doc type config loader."""

import pytest

from src.classification.doc_type_config import DocTypeConfig, load_doc_type_configs


VALID_YAML = """\
doc_type: marriage_certificate
display_name: Marriage Certificate
description: "Official government-issued certificate of marriage"
indicators:
  - "certificate of marriage"
validation_rules:
  - "Names must match"
"""

INVALID_YAML = """\
doc_type: bad
# missing required fields
"""


class TestDocTypeConfig:
    def test_valid_config(self):
        config = DocTypeConfig(
            doc_type="marriage_certificate",
            display_name="Marriage Certificate",
            description="Official marriage certificate",
            indicators=["certificate of marriage"],
            validation_rules=["Names must match"],
        )
        assert config.doc_type == "marriage_certificate"

    def test_missing_field_raises(self):
        with pytest.raises(Exception):
            DocTypeConfig(doc_type="bad", display_name="Bad")


class TestLoadDocTypeConfigs:
    def test_loads_yaml_files(self, tmp_path):
        (tmp_path / "marriage.yaml").write_text(VALID_YAML, encoding="utf-8")
        configs = load_doc_type_configs(tmp_path)
        assert len(configs) == 1
        assert configs[0].doc_type == "marriage_certificate"

    def test_skips_invalid_yaml(self, tmp_path):
        (tmp_path / "good.yaml").write_text(VALID_YAML, encoding="utf-8")
        (tmp_path / "bad.yaml").write_text(INVALID_YAML, encoding="utf-8")
        configs = load_doc_type_configs(tmp_path)
        assert len(configs) == 1

    def test_empty_directory(self, tmp_path):
        configs = load_doc_type_configs(tmp_path)
        assert configs == []

    def test_nonexistent_directory(self, tmp_path):
        configs = load_doc_type_configs(tmp_path / "nonexistent")
        assert configs == []

    def test_ignores_non_yaml_files(self, tmp_path):
        (tmp_path / "notes.txt").write_text("not yaml", encoding="utf-8")
        (tmp_path / "marriage.yaml").write_text(VALID_YAML, encoding="utf-8")
        configs = load_doc_type_configs(tmp_path)
        assert len(configs) == 1
