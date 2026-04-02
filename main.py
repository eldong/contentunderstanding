"""CLI entry point for the Document Validation System."""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.classification.attachment_classifier import AttachmentClassifier
from src.classification.doc_type_config import load_doc_type_configs
from src.classification.doc_type_rule_config import load_doc_type_rule_configs
from src.classification.form_analyzer import FormAnalyzer
from src.extraction.mock_extractor import MockExtractor
from src.ingestion.local_folder import LocalFolderAdapter
from src.models import ValidationResult
from src.orchestrator import Orchestrator
from src.result_writer import ResultWriter
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
        "--rules", "-r", default="config/doc_type_rules/",
        help="Path to doc type rules config directory (default: config/doc_type_rules/)",
    )
    parser.add_argument(
        "--mock", action="store_true",
        help="Use MockExtractor instead of Azure Document Intelligence",
    )
    return parser.parse_args(argv)


def _print_summary(results: list[ValidationResult]) -> None:
    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")
    skipped = sum(1 for r in results if r.status == "skip")
    total = len(results)
    print(f"\n{'='*50}")
    print(f"Results: {total} total — {passed} pass, {failed} fail, {skipped} skip")
    print(f"{'='*50}")


async def run(args: argparse.Namespace) -> list[ValidationResult]:
    load_dotenv()

    doc_type_configs = load_doc_type_configs(Path(args.config))
    doc_type_rule_configs = load_doc_type_rule_configs(Path(args.rules))

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
    client = AsyncAzureOpenAI(
        azure_endpoint=openai_endpoint,
        api_key=token.token,
        api_version="2024-12-01-preview",
    )
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")

    ingestion = LocalFolderAdapter(args.input)
    form_analyzer = FormAnalyzer(client, deployment, doc_type_rule_configs)
    attachment_classifier = AttachmentClassifier(client, deployment, doc_type_configs)
    validator_registry = ValidatorRegistry.load(
        Path(args.config), client, deployment
    )
    result_writer = ResultWriter(Path(args.output))

    orchestrator = Orchestrator(
        ingestion=ingestion,
        extractor=extractor,
        form_analyzer=form_analyzer,
        attachment_classifier=attachment_classifier,
        validator_registry=validator_registry,
        result_writer=result_writer,
    )

    return await orchestrator.run()


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    args = parse_args(argv)
    results = asyncio.run(run(args))
    _print_summary(results)


if __name__ == "__main__":
    main()
