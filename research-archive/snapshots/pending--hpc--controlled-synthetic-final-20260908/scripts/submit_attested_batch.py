#!/usr/bin/env python3
"""Submit one deferred Slurm job and attest its controller-stored script."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.batch_script_attestation import (  # noqa: E402
    submit_with_controller_attestation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument("--evidence-directory", type=Path, required=True)
    parser.add_argument("--begin", default="now+2minutes")
    arguments = parser.parse_args()
    result = submit_with_controller_attestation(
        arguments.script,
        evidence_dir=arguments.evidence_directory,
        begin=arguments.begin,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
