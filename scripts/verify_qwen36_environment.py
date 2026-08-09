#!/usr/bin/env python3
"""Compare the live Qwen3.6 environment with its captured immutable records."""

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
    write_content_digest_artifacts,
)
from cmpilot.environment_fingerprint import (  # noqa: E402
    compare_fingerprint_records,
    write_fingerprint_artifacts,
)
from cmpilot.qwen36_candidate import ENVIRONMENT_PATH, load_json, write_canonical_json  # noqa: E402
from scripts.capture_qwen36_environment import CONTENT_DISTRIBUTIONS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--expected-fingerprint", required=True, type=Path)
    parser.add_argument("--expected-content", required=True, type=Path)
    arguments = parser.parse_args()
    if Path(sys.prefix).resolve(strict=True) != ENVIRONMENT_PATH.resolve(strict=True):
        raise RuntimeError("environment verification used the wrong interpreter")
    output = arguments.output_directory
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"environment verification output exists: {output}")
    output.mkdir(parents=True, mode=0o700)
    fingerprint = write_fingerprint_artifacts(
        output / "environment-inventory.json",
        output / "environment-fingerprint.json",
        interpreter=sys.executable,
    )
    content = fingerprint_installed_distributions(CONTENT_DISTRIBUTIONS)
    write_content_digest_artifacts(
        output / "environment-content-inventory.json",
        output / "environment-content-digest.json",
        content,
    )
    expected_fingerprint = load_json(arguments.expected_fingerprint)
    actual_fingerprint = fingerprint.as_record(interpreter=sys.executable)
    fingerprint_match = compare_fingerprint_records(
        expected_fingerprint, actual_fingerprint
    )
    content_comparison = classify_content_comparison(
        load_json(arguments.expected_content),
        content.as_record(),
        metadata_differed=not fingerprint_match,
    )
    result = {
        "content": content_comparison,
        "environment_path": str(ENVIRONMENT_PATH),
        "fingerprint_match": fingerprint_match,
        "pass": fingerprint_match
        and bool(content_comparison["authoritative_content_matches"]),
        "schema": "qwen36-serving-environment-verification-v1",
    }
    write_canonical_json(output / "result.json", result, exclusive=True)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
