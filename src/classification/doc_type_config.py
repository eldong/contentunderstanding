"""Data-driven document type configuration loaded from YAML files."""

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class DocTypeConfig(BaseModel):
    """Schema for a document type definition YAML file."""

    doc_type: str
    display_name: str
    description: str
    indicators: list[str]
    validation_rules: list[str]


def load_doc_type_configs(config_dir: Path) -> list[DocTypeConfig]:
    """Load all doc type configs from YAML files in the given directory."""
    configs: list[DocTypeConfig] = []
    if not config_dir.is_dir():
        logger.warning("Config directory %s does not exist", config_dir)
        return configs
    for yaml_file in sorted(config_dir.glob("*.yaml")):
        try:
            raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            configs.append(DocTypeConfig.model_validate(raw))
        except Exception:
            logger.warning("Skipping invalid config file %s", yaml_file.name, exc_info=True)
    return configs
