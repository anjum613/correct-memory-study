#!/usr/bin/env python3
"""Capture stable environment-content digest artifacts for the vLLM runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.environment_content_digest import (  # noqa: E402
    classify_content_comparison,
    fingerprint_installed_distributions,
    fingerprint_recorded_distribution_snapshot,
    write_content_digest_artifacts,
)


DEFAULT_DISTRIBUTIONS = ("vllm", "outlines", "pyairports", "lm-format-enforcer")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--recorded-files", type=Path)
    parser.add_argument("--recorded-summary", type=Path)
    parser.add_argument("--read-current-bytes", action="store_true")
    parser.add_argument("--compare-with-record", type=Path)
    parser.add_argument("--classification", type=Path)
    parser.add_argument("--metadata-differed", action="store_true")
    arguments = parser.parse_args()
    if bool(arguments.recorded_files) != bool(arguments.recorded_summary):
        parser.error("--recorded-files and --recorded-summary must be used together")
    if arguments.recorded_files:
        result = fingerprint_recorded_distribution_snapshot(
            arguments.recorded_files,
            arguments.recorded_summary,
            read_current_bytes=arguments.read_current_bytes,
        )
    else:
        result = fingerprint_installed_distributions(DEFAULT_DISTRIBUTIONS)
    write_content_digest_artifacts(arguments.inventory, arguments.record, result)
    status = 0
    if arguments.compare_with_record:
        if not arguments.classification:
            parser.error("--classification is required with --compare-with-record")
        expected = json.loads(arguments.compare_with_record.read_text(encoding="utf-8"))
        comparison = classify_content_comparison(
            expected, result.as_record(), metadata_differed=arguments.metadata_differed
        )
        arguments.classification.write_text(
            json.dumps(comparison, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        status = 0 if comparison["authoritative_content_matches"] else 75
    print(json.dumps(result.as_record(), sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
