"""CLI entry point for the Document Validation System."""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

from src.classification.attachment_classifier import AttachmentClassifier
from src.classification.doc_type_config import load_doc_type_configs
from src.classification.form_type_config import load_form_type_configs
from src.classification.form_analyzer import FormAnalyzer
from src.extraction.mock_extractor import MockExtractor
from src.ingestion.local_folder import LocalFolderAdapter
from src.models import ValidationResult
from src.orchestrator import Orchestrator
from src.result_writer import BlobResultWriter, ResultWriter
from src.validators.registry import ValidatorRegistry


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Document Validation System — validates HR submissions"
    )
    parser.add_argument(
        "--input", "-i", default="samples/",
        help="Path to submissions folder (default: samples/)",
    )
    parser.add_argument(
        "--output", "-o", default="results.jsonl",
        help="Path to results JSONL file (default: results.jsonl)",
    )
    parser.add_argument(
        "--config", "-c", default="config/doc_types/",
        help="Path to doc types config directory (default: config/doc_types/)",
    )
    parser.add_argument(
        "--rules", "-r", default="config/form_types/",
        help="Path to form types config directory (default: config/form_types/)",
    )
    parser.add_argument(
        "--mock", action="store_true",
        help="Use MockExtractor instead of Azure Document Intelligence",
    )
    return parser.parse_args(argv)


def _print_summary(results: list[ValidationResult]) -> None:
    passed = sum(1 for r in results if r.status == "passed")
    failed = sum(1 for r in results if r.status == "failed")
    errors = sum(1 for r in results if r.status == "error")
    total = len(results)
    print(f"\n{'='*50}")
    print(f"Results: {total} total — {passed} passed, {failed} failed, {errors} error")
    print(f"{'='*50}")


async def run(args: argparse.Namespace) -> list[ValidationResult]:
    load_dotenv(override=True)

    doc_type_configs = load_doc_type_configs(Path(args.config))
    form_type_configs = load_form_type_configs(Path(args.rules))

    if args.mock:
        extractor = MockExtractor()
    else:
        from src.extraction.doc_intelligence import DocIntelligenceExtractor

        endpoint = os.getenv("AZURE_AI_FOUNDRY_SERVICES_ENDPOINT")
        if not endpoint:
            print("Error: AZURE_AI_FOUNDRY_SERVICES_ENDPOINT not set", file=sys.stderr)
            sys.exit(1)
        extractor = DocIntelligenceExtractor(endpoint=endpoint)

    # OpenAI client for classification and validation
    from azure.identity import DefaultAzureCredential
    from openai import AsyncAzureOpenAI

    openai_endpoint = os.getenv("AZURE_AI_FOUNDRY_OPENAI_ENDPOINT")
    if not openai_endpoint:
        print("Error: AZURE_AI_FOUNDRY_OPENAI_ENDPOINT not set", file=sys.stderr)
        sys.exit(1)

    credential = DefaultAzureCredential()
    token = credential.get_token("https://cognitiveservices.azure.com/.default")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    client = AsyncAzureOpenAI(
        azure_endpoint=openai_endpoint,
        api_key=token.token,
        api_version=api_version,
    )
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")

    ingestion = LocalFolderAdapter(args.input)
    form_analyzer = FormAnalyzer(client, deployment, form_type_configs)
    attachment_classifier = AttachmentClassifier(client, deployment, doc_type_configs)
    validator_registry = ValidatorRegistry.load(
        Path(args.config), client, deployment
    )

    storage_account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
    container_name = os.getenv("AZURE_RESULTS_CONTAINER_NAME")
    if storage_account_url and container_name:
        result_writer = BlobResultWriter(
            Path(args.output), storage_account_url, container_name
        )
    else:
        result_writer = ResultWriter(Path(args.output))

    orchestrator = Orchestrator(
        ingestion=ingestion,
        extractor=extractor,
        form_analyzer=form_analyzer,
        attachment_classifier=attachment_classifier,
        validator_registry=validator_registry,
        result_writer=result_writer,
    )

    results = await orchestrator.run()

    if isinstance(result_writer, BlobResultWriter):
        result_writer.upload()
        logger.info("Results uploaded to blob container '%s'", container_name)

    return results


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    args = parse_args(argv)
    results = asyncio.run(run(args))
    _print_summary(results)


if __name__ == "__main__":
    main()
