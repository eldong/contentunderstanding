"""Data-driven form type configuration loaded from YAML files."""

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class FormTypeConfig(BaseModel):
    """Schema for a form type definition YAML file."""

    doc_type: str
    display_name: str
    description: str
    required_attachment_types: list[str] = Field(default_factory=list)
    form_validation_rules: list[str] = Field(default_factory=list)


def load_form_type_configs(config_dir: Path) -> list[FormTypeConfig]:
    """Load all form type configs from YAML files in the given directory."""
    configs: list[FormTypeConfig] = []
    if not config_dir.is_dir():
        logger.warning("Config directory %s does not exist", config_dir)
        return configs
    for yaml_file in sorted(config_dir.glob("*.yaml")):
        try:
            raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            configs.append(FormTypeConfig.model_validate(raw))
        except Exception:
            logger.warning("Skipping invalid config file %s", yaml_file.name, exc_info=True)
    return configs
