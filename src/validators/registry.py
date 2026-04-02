"""Auto-discovers doc-type configs and creates LLMValidator instances."""

from pathlib import Path

from openai import AsyncAzureOpenAI

from src.classification.doc_type_config import DocTypeConfig, load_doc_type_configs
from src.validators.base import BaseValidator
from src.validators.llm_validator import LLMValidator


class ValidatorRegistry:
    """Registry of validators keyed by doc_type, built from YAML configs."""

    def __init__(self, validators: dict[str, BaseValidator]) -> None:
        self._validators = validators

    @classmethod
    def load(
        cls,
        config_dir: Path,
        client: AsyncAzureOpenAI,
        deployment: str,
    ) -> "ValidatorRegistry":
        """Load all doc-type configs and create an LLMValidator for each."""
        configs = load_doc_type_configs(config_dir)
        validators: dict[str, BaseValidator] = {}
        for cfg in configs:
            validators[cfg.doc_type] = LLMValidator(client, deployment, cfg)
        return cls(validators)

    def get_validator(self, doc_type: str) -> BaseValidator | None:
        """Return the validator for a doc type, or None if not registered."""
        return self._validators.get(doc_type)

    def list_doc_types(self) -> list[str]:
        """Return sorted list of registered doc types."""
        return sorted(self._validators.keys())
