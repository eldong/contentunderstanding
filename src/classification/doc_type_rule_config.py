"""Data-driven document type rule configuration loaded from YAML files."""

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DocTypeRuleConfig(BaseModel):
    """Schema for a document type rule definition YAML file."""

    reason: str
    display_name: str
    description: str
    required_doc_types: list[str] = Field(default_factory=list)
    form_validation_rules: list[str] = Field(default_factory=list)


def load_doc_type_rule_configs(config_dir: Path) -> list[DocTypeRuleConfig]:
    """Load all doc type rule configs from YAML files in the given directory."""
    configs: list[DocTypeRuleConfig] = []
    if not config_dir.is_dir():
        logger.warning("Config directory %s does not exist", config_dir)
        return configs
    for yaml_file in sorted(config_dir.glob("*.yaml")):
        try:
            raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            configs.append(DocTypeRuleConfig.model_validate(raw))
        except Exception:
            logger.warning("Skipping invalid config file %s", yaml_file.name, exc_info=True)
    return configs
